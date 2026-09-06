"""
STS2 Companion - Merchant & Shop Advisor.
Calculates optimal gold spending at Shops/Merchants in Slay the Spire 2.
Evaluates card removal vs. relics vs. cards vs. potions, generates optimal
purchase baskets within budget constraints, and provides strategic shopping guidance.
"""

import itertools
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import requests

from sts2_companion.core.config import get_gemini_api_key, get_gemini_model
from sts2_companion.advisor.archetypes import infer_card_roles, find_card_combos, find_relic_combos, ROLE_LABELS

logger = logging.getLogger("sts2_companion.shop_advisor")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class STS2ShopAdvisor:
    def __init__(
        self,
        cards_db: Dict[str, Dict[str, Any]],
        relics_db: Optional[Dict[str, Dict[str, Any]]] = None,
        potions_db: Optional[Dict[str, Dict[str, Any]]] = None,
        player_stats: Optional[Dict[str, Any]] = None,
    ):
        self.cards_db = cards_db
        self.relics_db = relics_db or {}
        self.potions_db = potions_db or {}
        self.player_stats = player_stats or {}

    def update_player_stats(self, player_stats: Dict[str, Any]) -> None:
        self.player_stats = player_stats

    def evaluate_shop(
        self,
        shop_data: Dict[str, Any],
        active_run: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluates the shop items against the player's active deck, relics, and gold budget.
        Returns:
          - optimal_baskets: Top 2 recommended purchase combinations fitting within gold budget.
          - ranked_items: Every offered item ranked by value-to-cost ratio.
          - purge_evaluation: Analysis of Card Removal value vs. buying items.
          - gemini_advice: Strategic shopping verdict.
        """
        gold = shop_data.get("gold", active_run.get("gold", 0))
        removal_cost = shop_data.get("removal_cost", 75)
        removal_available = shop_data.get("removal_available", True)

        cards_offered = shop_data.get("cards", [])
        relics_offered = shop_data.get("relics", [])
        potions_offered = shop_data.get("potions", [])

        deck = active_run.get("deck", [])
        deck_size = len(deck)
        act = active_run.get("current_act", 1)
        floor = active_run.get("current_floor", 1)
        relics = active_run.get("relics", [])

        # Evaluate Card Removal Service
        purge_eval = self._evaluate_card_removal(deck, removal_cost, gold, act)

        # Evaluate individual items
        evaluated_items: List[Dict[str, Any]] = []

        # 1. Cards
        for c_entry in cards_offered:
            c_name = c_entry.get("name") if isinstance(c_entry, dict) else str(c_entry)
            c_cost = c_entry.get("price", 65) if isinstance(c_entry, dict) else 65
            c_info = self._resolve_card(c_name)
            if c_info:
                val_score, reasoning, priority = self._score_shop_card(c_info, deck, relics, act, floor)
                evaluated_items.append({
                    "item_type": "card",
                    "id": c_info.get("id", ""),
                    "name": c_info.get("name", c_name),
                    "price": c_cost,
                    "score": val_score,
                    "priority": priority,
                    "reasoning": reasoning,
                    "details": c_info,
                })

        # 2. Relics
        for r_entry in relics_offered:
            r_name = r_entry.get("name") if isinstance(r_entry, dict) else str(r_entry)
            r_cost = r_entry.get("price", 160) if isinstance(r_entry, dict) else 160
            r_info = self._resolve_relic(r_name)
            val_score, reasoning, priority = self._score_shop_relic(r_info or {"name": r_name}, deck, relics, act)
            evaluated_items.append({
                "item_type": "relic",
                "id": r_info.get("id", "") if r_info else "",
                "name": r_info.get("name", r_name) if r_info else r_name,
                "price": r_cost,
                "score": val_score,
                "priority": priority,
                "reasoning": reasoning,
                "details": r_info or {},
            })

        # 3. Potions
        for p_entry in potions_offered:
            p_name = p_entry.get("name") if isinstance(p_entry, dict) else str(p_entry)
            p_cost = p_entry.get("price", 50) if isinstance(p_entry, dict) else 50
            val_score, reasoning, priority = self._score_shop_potion(p_name, act)
            evaluated_items.append({
                "item_type": "potion",
                "name": p_name,
                "price": p_cost,
                "score": val_score,
                "priority": priority,
                "reasoning": reasoning,
            })

        # 4. Include Card Removal as a purchasable candidate
        if removal_available:
            evaluated_items.append({
                "item_type": "removal",
                "name": f"Purge ({purge_eval['target']})",
                "price": removal_cost,
                "score": purge_eval["score"],
                "priority": purge_eval["priority"],
                "reasoning": purge_eval["reasoning"],
                "target_card": purge_eval["target"],
            })

        # Sort evaluated items by score/price ratio and absolute score
        evaluated_items.sort(key=lambda x: (x["score"] / max(x["price"], 1)), reverse=True)

        # Generate Optimal Purchase Baskets
        baskets = self._generate_purchase_baskets(evaluated_items, gold)

        # Gemini / Heuristic Advice
        shopping_verdict = self._generate_shopping_verdict(baskets, purge_eval, gold, active_run)

        return {
            "gold": gold,
            "removal_cost": removal_cost,
            "baskets": baskets,
            "ranked_items": evaluated_items,
            "purge_evaluation": purge_eval,
            "shopping_verdict": shopping_verdict,
            "gemini_advice": shopping_verdict,
        }

    def _evaluate_card_removal(
        self,
        deck: List[Dict[str, Any]],
        cost: int,
        gold: int,
        act: int,
    ) -> Dict[str, Any]:
        """
        Evaluates the strategic value of paying for a card purge at the merchant.
        """
        deck_size = len(deck)
        starter_strikes = [c for c in deck if "strike" in c.get("name", "").lower() and "twin" not in c.get("name", "").lower() and "pommel" not in c.get("name", "").lower()]
        starter_defends = [c for c in deck if "defend" in c.get("name", "").lower()]
        curses = [c for c in deck if c.get("card_type") in ["Curse", "Status"]]

        score = 6.0
        target = "Strike"
        reasoning = "Removes low-value starter card to draw key synergies faster."
        priority = "STRONG VALUE"

        if curses:
            score = 9.8
            target = curses[0].get("name", "Curse")
            reasoning = f"Urgent: Remove {target} to prevent dead draws and combat damage."
            priority = "MUST BUY"
        elif deck_size <= 12 and act == 1:
            # Early Act 1: Removing strike improves draw consistency immensely
            score = 8.2
            target = starter_strikes[0].get("name", "Strike") if starter_strikes else "Defend"
            reasoning = f"Purging starter {target} significantly increases your turn-1 damage and power draw odds."
            priority = "MUST BUY" if gold >= cost else "CONSIDER"
        elif len(starter_strikes) >= 3:
            score = 7.5
            target = starter_strikes[0].get("name", "Strike")
            reasoning = f"Deck carries {len(starter_strikes)} starter strikes. Purging cleanses draw bloat."
            priority = "STRONG VALUE"
        else:
            score = 6.5
            target = starter_strikes[0].get("name", "Strike") if starter_strikes else (starter_defends[0].get("name", "Defend") if starter_defends else "Card")
            reasoning = f"Purging {target} preserves deck velocity."
            priority = "CONSIDER"

        return {
            "score": score,
            "target": target,
            "cost": cost,
            "priority": priority,
            "reasoning": reasoning,
            "affordable": gold >= cost,
        }

    def _score_shop_card(
        self,
        card: Dict[str, Any],
        deck: List[Dict[str, Any]],
        relics: List[Dict[str, Any]],
        act: int,
        floor: int,
    ) -> Tuple[float, str, str]:
        roles = infer_card_roles(card)
        cname = card.get("name", "")
        deck_size = len(deck)

        # Audit current deck roles
        aoe_count = sum(1 for c in deck if "aoe_damage" in infer_card_roles(self._resolve_card(c.get("name", "")) or c))
        attacks = sum(1 for c in deck if c.get("card_type") == "Attack")

        card_combos = find_card_combos(card, deck)
        relic_combos = find_relic_combos(card, relics)

        score = 5.0
        reasoning = "Solid addition to active deck."
        priority = "CONSIDER"

        # 1. Missing AOE gap
        if "aoe_damage" in roles and aoe_count == 0:
            score = 9.5
            reasoning = f"Critical Gap: Deck has 0 AOE cards. {cname} solves upcoming Act multi-enemy threats."
            priority = "MUST BUY"

        # 2. Strong synergy combo
        elif len(card_combos) >= 1 or len(relic_combos) >= 1:
            score = 8.5
            combo_partner = card_combos[0]["partner"] if card_combos else relic_combos[0]["relic"]
            combo_note = card_combos[0]["explanation"] if card_combos else relic_combos[0]["explanation"]
            reasoning = f"Combos with {combo_partner}: {combo_note}."
            priority = "STRONG VALUE"

        # 3. Redundant attacks
        elif card.get("card_type") == "Attack" and attacks >= 9:
            score = 3.5
            reasoning = f"Redundant: Deck already saturated with {attacks} attacks. Don't waste gold on more attacks."
            priority = "SKIP"

        # 4. Scaling power
        elif "scaling_damage" in roles or "strength" in roles:
            score = 8.0
            reasoning = "Provides boss-scaling damage needed for long combats."
            priority = "STRONG VALUE"

        return score, reasoning, priority

    def _score_shop_relic(
        self,
        relic: Dict[str, Any],
        deck: List[Dict[str, Any]],
        relics: List[Dict[str, Any]],
        act: int,
    ) -> Tuple[float, str, str]:
        rname = relic.get("name", "")
        rid = relic.get("id", "")
        desc = relic.get("description", "").lower()

        score = 7.0
        reasoning = "Passive relic value that benefits the entire run."
        priority = "CONSIDER"

        # Check high impact relics
        if any(w in rname.lower() for w in ["akabeko", "vajra", "anchor", "horn cleat", "captain"]):
            score = 9.2
            reasoning = "Top-tier shop relic: provides immediate, combat-winning opening tempo."
            priority = "MUST BUY"
        elif any(w in rname.lower() for w in ["shuriken", "kunai", "fan"]):
            # Ninja relics: check attack count
            attacks = sum(1 for c in deck if c.get("card_type") == "Attack")
            if attacks >= 7:
                score = 9.4
                reasoning = "High attack density easily triggers 3-attacks/turn bonus."
                priority = "MUST BUY"
            else:
                score = 6.0
                reasoning = "Requires drafting more low-cost attacks to trigger consistently."
                priority = "CONSIDER"
        elif any(w in rname.lower() for w in ["dead branch", "charon"]):
            exhausts = sum(1 for c in deck if "exhaust" in c.get("description", "").lower())
            if exhausts >= 2:
                score = 9.6
                reasoning = f"Massive synergy with your {exhausts} exhaust cards."
                priority = "MUST BUY"
        elif any(w in rname.lower() for w in ["membership card", "courier"]):
            score = 8.8
            reasoning = "Economic relic that pays for itself across future shops."
            priority = "STRONG VALUE"

        return score, reasoning, priority

    def _score_shop_potion(self, p_name: str, act: int) -> Tuple[float, str, str]:
        name_lower = p_name.lower()
        if any(w in name_lower for w in ["fairy", "ghost", "cultist"]):
            return 9.0, "Game-saving emergency potion for tough Elite/Boss fights.", "STRONG VALUE"
        elif any(w in name_lower for w in ["strength", "fire", "explosive", "block"]):
            return 7.5, "Immediate combat buffer to prevent taking heavy Elite damage.", "CONSIDER"
        return 5.5, "Standard utility potion.", "LOW PRIORITY"

    def _generate_purchase_baskets(
        self,
        evaluated_items: List[Dict[str, Any]],
        gold: int,
    ) -> List[Dict[str, Any]]:
        """
        Generates the Top 2 highest-value purchase combinations that fit within the player's gold.
        """
        # Filter items with positive score
        candidates = [item for item in evaluated_items if item.get("score", 0) >= 5.0 and item.get("price", 0) <= gold]
        if not candidates:
            return [{
                "basket_id": 1,
                "name": "Save Gold",
                "title": "Save Gold",
                "items": [],
                "total_cost": 0,
                "total_spent": 0,
                "remaining_gold": gold,
                "gold_remaining": gold,
                "headline": "Save Gold for Future Shops",
                "rationale": f"None of the offered items justify spending your {gold} gold right now. Conserve gold for Act 2/3 shops.",
            }]

        all_combos = []
        # Test combos of 1 to 4 items
        for r in range(1, min(5, len(candidates) + 1)):
            for combo in itertools.combinations(candidates, r):
                tot_cost = sum(it["price"] for it in combo)
                if tot_cost <= gold:
                    tot_score = sum(it["score"] for it in combo)
                    all_combos.append({
                        "items": list(combo),
                        "total_cost": tot_cost,
                        "total_spent": tot_cost,
                        "remaining_gold": gold - tot_cost,
                        "gold_remaining": gold - tot_cost,
                        "total_score": round(tot_score, 2),
                    })

        if not all_combos:
            return [{
                "basket_id": 1,
                "name": "Save Gold",
                "title": "Save Gold",
                "items": [],
                "total_cost": 0,
                "total_spent": 0,
                "remaining_gold": gold,
                "gold_remaining": gold,
                "headline": "Insufficient Gold / Save",
                "rationale": "Items exceed your current budget. Conserve your gold.",
            }]

        # Sort combos by total score descending, then by remaining gold descending
        all_combos.sort(key=lambda c: (c["total_score"], -c["total_cost"]), reverse=True)

        baskets = []

        # Basket 1: Best Value Basket
        top_combo = all_combos[0]
        item_names = [it["name"] for it in top_combo["items"]]
        baskets.append({
            "basket_id": 1,
            "name": "Best Value Plan (Recommended)",
            "title": "Best Value Plan (Recommended)",
            "items": top_combo["items"],
            "total_cost": top_combo["total_cost"],
            "total_spent": top_combo["total_cost"],
            "remaining_gold": top_combo["remaining_gold"],
            "gold_remaining": top_combo["remaining_gold"],
            "total_score": top_combo["total_score"],
            "headline": f"Buy: {' + '.join(item_names)}",
            "rationale": f"Maximizes immediate combat power and deck consistency for {top_combo['total_cost']} gold.",
        })

        # Basket 2: Find distinct alternative (e.g. if Basket 1 bought relic+purge, Basket 2 shows key card+potion or saving)
        alt_combo = None
        for combo in all_combos[1:]:
            # Must differ by at least 1 item
            c_names = set(it["name"] for it in combo["items"])
            if c_names != set(item_names):
                alt_combo = combo
                break

        if alt_combo:
            alt_names = [it["name"] for it in alt_combo["items"]]
            baskets.append({
                "basket_id": 2,
                "name": "Alternative Plan",
                "title": "Alternative Plan",
                "items": alt_combo["items"],
                "total_cost": alt_combo["total_cost"],
                "total_spent": alt_combo["total_cost"],
                "remaining_gold": alt_combo["remaining_gold"],
                "gold_remaining": alt_combo["remaining_gold"],
                "total_score": alt_combo["total_score"],
                "headline": f"Buy: {' + '.join(alt_names)}",
                "rationale": f"Alternative setup leaving {alt_combo['remaining_gold']} gold in reserve.",
            })

        return baskets

    def _generate_shopping_verdict(
        self,
        baskets: List[Dict[str, Any]],
        purge_eval: Dict[str, Any],
        gold: int,
        active_run: Dict[str, Any],
    ) -> str:
        """Generates concise strategic shopping verdict."""
        if not baskets or not baskets[0]["items"]:
            return f"You have {gold} gold. The current shop offerings do not provide strong enough synergies to justify spending. Keep your gold for the next shop."

        best = baskets[0]
        item_str = " + ".join([it["name"] for it in best["items"]])
        return f"Optimal Shopping Plan: Purchase {item_str} ({best['total_cost']}g total). This leaves you with {best['remaining_gold']}g while solving your immediate combat needs."

    def _resolve_card(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        name_str = str(name_or_id).strip()
        if name_str.startswith("CARD.") and name_str in self.cards_db:
            return self.cards_db[name_str]
        for cid, cinfo in self.cards_db.items():
            if cinfo.get("name", "").lower() == name_str.lower():
                return cinfo
        return None

    def _resolve_relic(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        name_str = str(name_or_id).strip()
        if name_str.startswith("RELIC.") and name_str in self.relics_db:
            return self.relics_db[name_str]
        for rid, rinfo in self.relics_db.items():
            if rinfo.get("name", "").lower() == name_str.lower():
                return rinfo
        return None


# Singleton instance
_shop_advisor_instance: Optional[STS2ShopAdvisor] = None

def get_shop_advisor(cards_db: Optional[Dict[str, Any]] = None, relics_db: Optional[Dict[str, Any]] = None) -> STS2ShopAdvisor:
    global _shop_advisor_instance
    if _shop_advisor_instance is None:
        if cards_db is None:
            c_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sts2_cards.json")
            if os.path.exists(c_path):
                with open(c_path, "r", encoding="utf-8") as f:
                    cards_db = json.load(f)
            else:
                cards_db = {}
        if relics_db is None:
            r_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sts2_relics.json")
            if os.path.exists(r_path):
                with open(r_path, "r", encoding="utf-8") as f:
                    relics_db = json.load(f)
            else:
                relics_db = {}
        _shop_advisor_instance = STS2ShopAdvisor(cards_db, relics_db)
    return _shop_advisor_instance
