"""
STS2 Companion - Boss Reward & Boss Relic Advisor.
Evaluates Act clear Boss Relics against the player's active deck archetype,
energy economy, card cost curve, sustain status, and relic drawback severity.
Provides ranked choices, explicit drawback mitigation guides, and grounded advice.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import requests

from sts2_companion.core.config import get_gemini_api_key, get_gemini_model
from sts2_companion.advisor.archetypes import infer_card_roles, ROLE_LABELS

logger = logging.getLogger("sts2_companion.boss_advisor")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class STS2BossRewardAdvisor:
    def __init__(
        self,
        cards_db: Dict[str, Dict[str, Any]],
        relics_db: Optional[Dict[str, Dict[str, Any]]] = None,
        player_stats: Optional[Dict[str, Any]] = None,
    ):
        self.cards_db = cards_db
        self.relics_db = relics_db or {}
        self.player_stats = player_stats or {}

    def update_player_stats(self, player_stats: Dict[str, Any]) -> None:
        self.player_stats = player_stats

    def _resolve_relic(self, relic_identifier: str) -> Optional[Dict[str, Any]]:
        """Resolves relic name or ID to database entry."""
        clean = relic_identifier.strip()
        if clean in self.relics_db:
            return self.relics_db[clean]
        for rid, rinfo in self.relics_db.items():
            if rinfo.get("name", "").lower() == clean.lower():
                return rinfo
            if rinfo.get("key", "").lower() == clean.lower().replace(" ", "_"):
                return rinfo
        return None

    def analyze_deck_energy_profile(self, deck: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculates energy demand profile and starter bloat from deck."""
        total_cards = len(deck)
        if total_cards == 0:
            return {
                "avg_cost": 1.0,
                "high_cost_count": 0,
                "zero_cost_count": 0,
                "starter_count": 0,
                "energy_hungry": False,
            }

        costs = []
        high_cost_cards = []
        zero_cost_cards = []
        starters = []

        for c in deck:
            cname = c.get("name", "")
            cost = c.get("cost", 1)
            # Handle variable or unplayable costs
            if isinstance(cost, (int, float)) and cost >= 0:
                costs.append(cost)
                if cost >= 2:
                    high_cost_cards.append(cname)
                elif cost == 0:
                    zero_cost_cards.append(cname)

            if "strike" in cname.lower() or "defend" in cname.lower():
                if not any(k in cname.lower() for k in ["pommel", "twin", "perfected"]):
                    starters.append(cname)

        avg_cost = sum(costs) / len(costs) if costs else 1.0
        energy_hungry = len(high_cost_cards) >= 3 or avg_cost >= 1.35

        return {
            "avg_cost": round(avg_cost, 2),
            "high_cost_count": len(high_cost_cards),
            "high_cost_cards": high_cost_cards,
            "zero_cost_count": len(zero_cost_cards),
            "zero_cost_cards": zero_cost_cards,
            "starter_count": len(starters),
            "energy_hungry": energy_hungry,
        }

    def evaluate_boss_relic(
        self,
        relic_name_or_id: str,
        deck: List[Dict[str, Any]],
        active_relics: List[Dict[str, Any]],
        current_hp: int,
        max_hp: int,
        current_act: int,
    ) -> Dict[str, Any]:
        """Evaluates a single boss relic choice against the active run."""
        r_info = self._resolve_relic(relic_name_or_id)
        name = r_info.get("name", relic_name_or_id) if r_info else relic_name_or_id
        r_desc = r_info.get("description", "") if r_info else ""
        norm_name = name.lower()

        energy_profile = self.analyze_deck_energy_profile(deck)
        relic_names = [r.get("name", "").lower() for r in active_relics]

        # Base scoring
        score = 6.5
        priority = "VIABLE"
        is_energy_relic = False
        drawback_risk = "LOW"
        drawback_warning = ""
        mitigation_guide = "Standard play."
        synergy_reason = "Solid boss relic upgrade."

        # 1. VELVET CHOKER
        if "velvet choker" in norm_name or "choker" in norm_name:
            is_energy_relic = True
            # Trap test: high draw / zero cost spam
            spam_count = energy_profile["zero_cost_count"]
            has_spam_combos = any("anger" in c.get("name", "").lower() or "pommel" in c.get("name", "").lower() or "shiv" in c.get("name", "").lower() for c in deck)

            if spam_count >= 3 or has_spam_combos:
                score = 2.5
                priority = "TRAP / DO NOT PICK"
                drawback_risk = "LETHAL"
                drawback_warning = "Hard caps you at 6 cards per turn. Your deck contains rapid-cycle/0-cost cards that will be crippled."
                mitigation_guide = "Do not pick unless absolutely desperate for energy."
                synergy_reason = "Anti-synergistic with your card velocity."
            elif energy_profile["high_cost_count"] >= 3:
                score = 8.8
                priority = "EXCELLENT"
                drawback_risk = "LOW"
                drawback_warning = "Cannot play more than 6 cards per turn."
                mitigation_guide = "Your deck plays 2-3 heavy high-impact cards per turn, so the 6-card limit will rarely hinder you."
                synergy_reason = f"Enables consistent casting of high-cost powerhouses ({', '.join(energy_profile['high_cost_cards'][:3])})."
            else:
                score = 6.2
                priority = "VIABLE"
                drawback_risk = "MEDIUM"
                drawback_warning = "Limits future card choices away from low-cost cycling."
                mitigation_guide = "Pivot draft towards high-cost, high-value impacts."
                synergy_reason = "+1 Energy each turn."

        # 2. COFFEE DRIPPER
        elif "coffee dripper" in norm_name or "dripper" in norm_name:
            is_energy_relic = True
            has_sustain = any(s in relic_names for s in ["burning blood", "black blood", "meat on the bone", "blood vial"]) or \
                          any("reaper" in c.get("name", "").lower() or "feed" in c.get("name", "").lower() for c in deck)
            hp_ratio = current_hp / max(max_hp, 1)

            if has_sustain:
                score = 9.4
                priority = "EXCELLENT"
                drawback_risk = "LOW"
                drawback_warning = "Cannot rest at Rest Sites."
                mitigation_guide = "You have reliable combat sustain/healing, allowing you to smith at every camp."
                synergy_reason = "Top-tier energy relic with zero penalty due to existing sustain."
            elif hp_ratio < 0.5:
                score = 4.8
                priority = "RISKY"
                drawback_risk = "HIGH"
                drawback_warning = "Cannot rest at Rest Sites. You are currently below 50% HP with low sustain."
                mitigation_guide = "Prioritize drafting premium block cards and avoiding unnecessary elites."
                synergy_reason = "+1 Energy, but dangerous without sustain."
            else:
                score = 7.5
                priority = "VIABLE"
                drawback_risk = "MEDIUM"
                drawback_warning = "Cannot rest at Rest Sites."
                mitigation_guide = "Draft sustain cards or prioritize camp smithing while maintaining high block."
                synergy_reason = "+1 Energy per turn."

        # 3. CURSED KEY
        elif "cursed key" in norm_name:
            is_energy_relic = True
            has_omamori = "omamori" in relic_names
            score = 9.2 if has_omamori else 8.5
            priority = "EXCELLENT"
            drawback_risk = "LOW" if has_omamori else "MEDIUM"
            drawback_warning = "Opening chests adds a random Curse to your deck."
            mitigation_guide = "Omamori negates the curses! Or skip optional non-relic chests / plan gold for merchant card purges." if has_omamori else "Skip chests containing low-value rewards, or purge curses at subsequent shops."
            synergy_reason = "Unconditional +1 Energy with highly manageable drawback."

        # 4. FUSION HAMMER
        elif "fusion hammer" in norm_name:
            is_energy_relic = True
            upgraded_count = sum(1 for c in deck if c.get("is_upgraded") or "+" in c.get("name", ""))
            total_cards = max(len(deck), 1)
            upgraded_ratio = upgraded_count / total_cards
            has_apotheosis = any("apotheosis" in c.get("name", "").lower() or "lesson learned" in c.get("name", "").lower() for c in deck)

            if has_apotheosis or upgraded_ratio >= 0.55:
                score = 9.1
                priority = "EXCELLENT"
                drawback_risk = "LOW"
                drawback_warning = "Cannot smith (upgrade cards) at Rest Sites."
                mitigation_guide = "Your deck is either largely upgraded or has combat upgrade mechanics."
                synergy_reason = "Top-tier energy relic with negligible drawback."
            else:
                score = 7.2
                priority = "VIABLE"
                drawback_risk = "MEDIUM"
                drawback_warning = "Cannot smith at Rest Sites. Essential un-upgraded cards remain raw."
                mitigation_guide = "Take rest heals or seek upgrade events."
                synergy_reason = "+1 Energy per turn."

        # 5. RUNIC DOME
        elif "runic dome" in norm_name:
            is_energy_relic = True
            score = 6.8
            priority = "VIABLE"
            drawback_risk = "HIGH"
            drawback_warning = "Cannot see enemy intents."
            mitigation_guide = "Requires memorization of enemy attack patterns or building impassable baseline armor every turn."
            synergy_reason = "Free +1 Energy with no deck building restrictions."

        # 6. SLAVER'S COLLAR
        elif "slaver's collar" in norm_name or "collar" in norm_name:
            is_energy_relic = True
            score = 8.4
            priority = "STRONG VALUE"
            drawback_risk = "LOW"
            drawback_warning = "Only grants +1 Energy during Elite and Boss combats."
            mitigation_guide = "Normal hallway combats are usually manageable on 3 energy; saves full power for deadly lethal encounters."
            synergy_reason = "Delivers energy exactly when damage output and survivability are most critical."

        # 7. SNECKO EYE
        elif "snecko eye" in norm_name or "snecko" in norm_name:
            score = 9.3 if energy_profile["high_cost_count"] >= 3 else 7.0
            priority = "EXCELLENT" if energy_profile["high_cost_count"] >= 3 else "VIABLE"
            drawback_risk = "MEDIUM"
            drawback_warning = "Randomizes card costs between 0 and 3."
            mitigation_guide = "Draws 2 extra cards per turn! Pivot draft heavily towards 2-cost and 3-cost high-impact cards."
            synergy_reason = f"Massive draw acceleration (+2 cards/turn) that trivializes expensive cards ({', '.join(energy_profile['high_cost_cards'][:3])})."

        # 8. ASTROLABE / EMPTY CAGE / PANDORA'S BOX (Deck Thinning)
        elif "astrolabe" in norm_name:
            score = 9.0 if energy_profile["starter_count"] >= 5 else 7.8
            priority = "EXCELLENT"
            drawback_risk = "NONE"
            drawback_warning = "None."
            mitigation_guide = "Select 3 starter Strikes or Defends to transform and instantly upgrade."
            synergy_reason = f"Massively accelerates deck quality: converts 3 low-impact starter cards into upgraded archetype pieces."

        elif "empty cage" in norm_name:
            score = 8.7 if energy_profile["starter_count"] >= 4 else 7.2
            priority = "STRONG VALUE"
            drawback_risk = "NONE"
            drawback_warning = "None."
            mitigation_guide = "Remove 2 starter Strikes or Defends."
            synergy_reason = "Pure deck consistency: cuts 2 weak cards, equivalent to saving 175+ gold in shop purges."

        elif "pandora's box" in norm_name or "pandora" in norm_name:
            score = 8.5
            priority = "STRONG VALUE"
            drawback_risk = "MEDIUM"
            drawback_warning = "Transforms ALL Strikes and Defends. May temporarily leave block volatile."
            mitigation_guide = "Replaces 8-10 starter cards with random class cards, drastically raising deck ceiling."
            synergy_reason = "Extreme deck upgrade value; immediately removes starter bloat."

        # 9. RUNIC PYRAMID
        elif "runic pyramid" in norm_name or "pyramid" in norm_name:
            score = 9.6
            priority = "EXCELLENT"
            drawback_risk = "LOW"
            drawback_warning = "Cards are not discarded at end of turn. Wounds and Curses can clog hand without exhaust."
            mitigation_guide = "Enables flawless setup sequencing: hold your best combo pieces until optimal turns."
            synergy_reason = "Highest win-rate boss relic in the game; completely eliminates turn-by-turn draw variance."

        # 10. BLACK STAR
        elif "black star" in norm_name:
            score = 8.2 if current_act == 1 else 6.0
            priority = "STRONG VALUE" if current_act == 1 else "VIABLE"
            drawback_risk = "HIGH"
            drawback_warning = "Gives zero immediate combat stats. You must hunt and survive Elites in Act 2 to reap rewards."
            mitigation_guide = "Only pick if your Act 1 deck already dominates Elites comfortably."
            synergy_reason = "Exponential snowball potential: doubles relic rewards from all upcoming Elites."

        # 11. SACRED BARK
        elif "sacred bark" in norm_name:
            score = 8.0
            priority = "STRONG VALUE"
            drawback_risk = "LOW"
            drawback_warning = "Requires maintaining potion slots."
            mitigation_guide = "Doubles potion potency: a single potion can solve an entire Boss phase."
            synergy_reason = "Huge burst survivability and tempo spike during difficult combats."

        # General Fallback
        else:
            if "energy" in r_desc.lower():
                is_energy_relic = True
                score = 7.8
                priority = "STRONG VALUE"
                synergy_reason = "Grants additional energy economy."
            else:
                score = 6.5
                priority = "VIABLE"
                synergy_reason = "Passive boss relic utility."

        return {
            "name": name,
            "id": r_info.get("id", "") if r_info else "",
            "description": r_desc,
            "score": score,
            "priority": priority,
            "is_energy_relic": is_energy_relic,
            "drawback_risk": drawback_risk,
            "drawback_warning": drawback_warning,
            "mitigation_guide": mitigation_guide,
            "synergy_reason": synergy_reason,
            "details": r_info or {},
        }

    def evaluate_boss_rewards(
        self,
        offered_relics: List[str],
        active_run: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluates the 3 offered Boss Relics, ranks them, identifies the recommended pick,
        and provides grounded strategic coaching.
        """
        deck = active_run.get("deck", [])
        active_relics = active_run.get("relics", [])
        current_hp = active_run.get("current_hp", 60)
        max_hp = active_run.get("max_hp", 80)
        current_act = active_run.get("current_act", 1)

        energy_profile = self.analyze_deck_energy_profile(deck)

        evaluated: List[Dict[str, Any]] = []
        for r_name in offered_relics:
            if not r_name:
                continue
            ev = self.evaluate_boss_relic(r_name, deck, active_relics, current_hp, max_hp, current_act)
            evaluated.append(ev)

        # Sort by score descending
        evaluated.sort(key=lambda x: x["score"], reverse=True)

        # Assign rank
        for idx, item in enumerate(evaluated):
            item["rank"] = idx + 1

        rec = evaluated[0] if evaluated else None

        # Build coaching advice
        verdict = self._build_verdict(rec, evaluated, energy_profile, current_act, active_run)

        return {
            "recommended": rec,
            "ranked_choices": evaluated,
            "energy_profile": energy_profile,
            "verdict": verdict,
            "gemini_advice": verdict,
        }

    def _build_verdict(
        self,
        recommended: Optional[Dict[str, Any]],
        ranked: List[Dict[str, Any]],
        energy_profile: Dict[str, Any],
        act: int,
        active_run: Dict[str, Any],
    ) -> str:
        """Generates grounded strategic advice for the boss relic choice."""
        if not recommended:
            return "Enter the 3 offered Boss Relics above to evaluate their deck synergy and drawbacks."

        rec_name = recommended["name"]
        reason = recommended["synergy_reason"]
        mitigation = recommended["mitigation_guide"]

        verdict = f"Recommended Pick: {rec_name}. {reason} Playbook: {mitigation}"

        # If there is a trap relic in the choices, warn the player
        for r in ranked:
            if r.get("priority") == "TRAP / DO NOT PICK":
                verdict += f" WARNING: Avoid {r['name']} — {r.get('drawback_warning')}"
                break

        return verdict
