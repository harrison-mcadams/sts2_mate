"""
Card Reward Decision Evaluator for Slay the Spire 2.
Qualitative, synergy-first decision engine that audits deck gaps,
identifies explicit card/relic combos, and evaluates deck dilution impact.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
from .archetypes import (
    ROLE_FRONTLOAD_DAMAGE,
    ROLE_AOE_DAMAGE,
    ROLE_SCALING_DAMAGE,
    ROLE_BLOCK,
    ROLE_SCALING_DEFENSE,
    ROLE_DRAW,
    ROLE_ENERGY,
    ROLE_EXHAUST,
    ROLE_POISON,
    ROLE_SHIV,
    ROLE_STRENGTH,
    ROLE_VULNERABLE,
    ROLE_WEAK,
    ROLE_LABELS,
    infer_card_roles,
    find_card_combos,
    find_relic_combos,
)


class STS2CardRewardAdvisor:
    def __init__(self, cards_db: Dict[str, Dict[str, Any]], player_stats: Optional[Dict[str, Any]] = None):
        self.cards_db = cards_db
        self.player_stats = player_stats or {}

    def update_player_stats(self, player_stats: Dict[str, Any]) -> None:
        self.player_stats = player_stats

    def evaluate_reward(
        self,
        offered_card_ids: List[str],
        active_run: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Qualitatively evaluates offered cards in the context of the active deck,
        relics, floor/act challenges, and explicit combo interactions.
        """
        floor = active_run.get("current_floor", 1)
        act = active_run.get("current_act", 1)
        character = active_run.get("character", "Ironclad")
        deck = active_run.get("deck", [])
        relics = active_run.get("relics", [])
        current_hp = active_run.get("current_hp", 80)
        max_hp = active_run.get("max_hp", 80)
        hp_percent = active_run.get("hp_percent", 100.0)

        deck_size = len(deck)

        # Audit current deck roles
        deck_role_counts: Dict[str, int] = {}
        for c in deck:
            c_info = self.cards_db.get(c.get("id"), c)
            for role in infer_card_roles(c_info):
                deck_role_counts[role] = deck_role_counts.get(role, 0) + 1

        attack_count = sum(1 for c in deck if c.get("card_type") == "Attack")
        skill_count = sum(1 for c in deck if c.get("card_type") == "Skill")
        power_count = sum(1 for c in deck if c.get("card_type") == "Power")

        evaluated_options = []

        for cid in offered_card_ids:
            cinfo = self.cards_db.get(cid)
            if not cinfo:
                cinfo = {
                    "id": cid,
                    "name": cid.replace("CARD.", "").replace("_", " ").title(),
                    "card_type": "Skill",
                    "description": "",
                    "character": character.lower(),
                }

            analysis = self._analyze_card(
                card=cinfo,
                act=act,
                floor=floor,
                deck=deck,
                relics=relics,
                deck_size=deck_size,
                deck_role_counts=deck_role_counts,
                attack_count=attack_count,
                skill_count=skill_count,
                power_count=power_count,
                hp_percent=hp_percent,
            )

            # Check personal historical stats
            p_stats = self.player_stats.get("card_stats", {}).get(cid)
            personal_note = None
            if p_stats:
                p_win_rate = p_stats.get("win_rate", 0.0)
                p_pick_rate = p_stats.get("pick_rate", 0.0)
                drafted = p_stats.get("drafted_runs", 0)
                if drafted >= 5:
                    personal_note = {
                        "pick_rate": p_pick_rate,
                        "win_rate": p_win_rate,
                        "drafted_runs": drafted,
                        "highlight": f"{p_win_rate}% win rate across {drafted} runs"
                    }

            analysis["personal_stats"] = personal_note
            evaluated_options.append(analysis)

        # Rank options qualitatively
        priority_order = {
            "Fills Critical Gap": 1,
            "Strong Synergy": 2,
            "Solid Addition": 3,
            "Redundant Role": 4,
            "Dilution Risk": 5,
        }
        evaluated_options.sort(key=lambda x: (
            priority_order.get(x["tactical_fit"], 99),
            -len(x["card_combos"]) - len(x["relic_combos"])
        ))

        # Determine Skip Advice
        top_option = evaluated_options[0] if evaluated_options else None
        should_skip = False
        skip_reasons = []

        # When does high-level STS strategy recommend Skip?
        # 1. Deck is already functional (18+ cards) and top option is Redundant or Dilution
        if top_option and top_option["tactical_fit"] in ["Redundant Role", "Dilution Risk"]:
            should_skip = True
            skip_reasons.append(f"Offered cards are redundant with your current {deck_size}-card deck")
            if deck_size >= 15:
                skip_reasons.append("Skipping preserves your draw density for key cards")

        if should_skip:
            verdict = f"SKIP RECOMMENDED: None of the offered choices address an active deck gap or enable key combos. Skipping protects your {deck_size}-card deck consistency."
            top_choice = "SKIP"
        elif top_option:
            verdict = f"RECOMMENDATION: Pick **{top_option['card']['name']}**: {top_option['tactical_fit']} ({top_option['primary_role_label']})."
            top_choice = top_option["card"]["name"]
        else:
            verdict = "No card options offered."
            top_choice = "None"

        return {
            "verdict": verdict,
            "should_skip": should_skip,
            "skip_reasons": skip_reasons,
            "top_choice": top_choice,
            "ranked_options": evaluated_options,
            "deck_audit": {
                "deck_size": deck_size,
                "attacks": attack_count,
                "skills": skill_count,
                "powers": power_count,
                "aoe_count": deck_role_counts.get(ROLE_AOE_DAMAGE, 0),
                "block_count": deck_role_counts.get(ROLE_BLOCK, 0),
                "draw_count": deck_role_counts.get(ROLE_DRAW, 0),
                "scaling_count": deck_role_counts.get(ROLE_SCALING_DAMAGE, 0),
            },
            "context_summary": {
                "act": act,
                "floor": floor,
                "character": character,
                "hp_percent": hp_percent,
            }
        }

    def _analyze_card(
        self,
        card: Dict[str, Any],
        act: int,
        floor: int,
        deck: List[Dict[str, Any]],
        relics: List[Dict[str, Any]],
        deck_size: int,
        deck_role_counts: Dict[str, int],
        attack_count: int,
        skill_count: int,
        power_count: int,
        hp_percent: float,
    ) -> Dict[str, Any]:
        cname = card.get("name", "")
        ctype = card.get("card_type", "Skill")
        roles = infer_card_roles(card)

        # 1. Determine Primary Role
        if ROLE_AOE_DAMAGE in roles:
            primary_role = ROLE_AOE_DAMAGE
        elif ROLE_SCALING_DAMAGE in roles or ROLE_STRENGTH in roles:
            primary_role = ROLE_SCALING_DAMAGE
        elif ROLE_DRAW in roles:
            primary_role = ROLE_DRAW
        elif ROLE_BLOCK in roles:
            primary_role = ROLE_BLOCK
        elif ROLE_EXHAUST in roles:
            primary_role = ROLE_EXHAUST
        elif ROLE_FRONTLOAD_DAMAGE in roles:
            primary_role = ROLE_FRONTLOAD_DAMAGE
        else:
            primary_role = "utility"

        primary_role_label = ROLE_LABELS.get(primary_role, primary_role.title())

        # 2. Deck Gap Audit for this Role
        current_role_count = deck_role_counts.get(primary_role, 0)
        role_pct = round((current_role_count / deck_size * 100), 1) if deck_size > 0 else 0

        # Assess role urgency based on act & current inventory
        is_critical_gap = False
        gap_description = ""

        if primary_role == ROLE_AOE_DAMAGE:
            if current_role_count == 0:
                is_critical_gap = True
                gap_description = f"Critical Gap: Deck has 0 AOE cards (0%). Multi-enemy encounters in Act 2 will punish single-target decks."
            elif current_role_count == 1:
                gap_description = f"Moderate Need: You have 1 AOE card ({role_pct}% of deck)."
            else:
                gap_description = f"Well Stocked: You have {current_role_count} AOE cards ({role_pct}% of deck)."

        elif primary_role == ROLE_FRONTLOAD_DAMAGE:
            if act == 1 and floor <= 6 and attack_count <= 5:
                is_critical_gap = True
                gap_description = f"Critical Need: Early Act 1 requires heavy burst attacks to take down Gremlin Nob and Elites."
            elif attack_count >= 10:
                gap_description = f"Role Saturated: Deck already carries {attack_count} attacks ({round(attack_count/deck_size*100)}% of deck)."
            else:
                gap_description = f"Balanced: Currently {attack_count} attacks in deck."

        elif primary_role == ROLE_BLOCK:
            block_count = deck_role_counts.get(ROLE_BLOCK, 0)
            if block_count <= 4:
                is_critical_gap = True
                gap_description = f"Defensive Gap: Only {block_count} block sources in deck. High risk against hard-hitting turns."
            elif block_count >= 9:
                gap_description = f"Well Defended: {block_count} block sources already in deck."
            else:
                gap_description = f"Stable Block: {block_count} block sources ({round(block_count/deck_size*100)}% of deck)."

        elif primary_role == ROLE_SCALING_DAMAGE:
            if act >= 2 and current_role_count == 0:
                is_critical_gap = True
                gap_description = f"Boss Gap: 0 scaling cards in deck. Bosses and high-HP Elites require scaling damage."
            elif current_role_count >= 3:
                gap_description = f"Sufficient Scaling: {current_role_count} scaling cards active."
            else:
                gap_description = f"Developing Scaling: {current_role_count} scaling sources in deck."

        elif primary_role == ROLE_DRAW:
            draw_count = deck_role_counts.get(ROLE_DRAW, 0)
            if draw_count == 0:
                gap_description = f"Zero Draw: Adding card velocity prevents dead turns and finds key combos faster."
            else:
                gap_description = f"Active Velocity: {draw_count} draw cards currently in deck."
        else:
            gap_description = f"Current inventory: {current_role_count} in deck ({role_pct}%)."

        # 3. Explicit Card & Relic Combos
        card_combos = find_card_combos(card, deck)
        relic_combos = find_relic_combos(card, relics)

        # 4. Determine Qualitative Tactical Fit
        if is_critical_gap:
            tactical_fit = "Fills Critical Gap"
            summary_headline = f"Fills your missing {primary_role_label}"
        elif len(card_combos) >= 2 or (len(card_combos) >= 1 and len(relic_combos) >= 1):
            tactical_fit = "Strong Synergy"
            summary_headline = f"Direct combo synergy with your deck"
        elif len(card_combos) == 1 or len(relic_combos) == 1:
            tactical_fit = "Solid Addition"
            summary_headline = f"Combos with existing pieces"
        elif primary_role == ROLE_FRONTLOAD_DAMAGE and attack_count >= 10:
            tactical_fit = "Redundant Role"
            summary_headline = f"Attacks already saturated ({attack_count}/{deck_size})"
        elif ctype == "Power" and power_count >= 4:
            tactical_fit = "Redundant Role"
            summary_headline = f"Power density already high ({power_count} powers)"
        elif deck_size >= 22 and len(card_combos) == 0 and not is_critical_gap:
            tactical_fit = "Dilution Risk"
            summary_headline = f"Dilutes high-value card draws without clear synergy"
        else:
            tactical_fit = "Solid Addition"
            summary_headline = f"Functional card addition"

        # 5. Strategic Advice Summary
        pros = []
        cons = []

        if is_critical_gap:
            pros.append(f"Solves an urgent deck deficit: {gap_description}")

        for combo in card_combos:
            pros.append(f"Combos with {combo['partner']}: {combo['explanation']}")

        for rcombo in relic_combos:
            pros.append(f"Combos with relic {rcombo['relic']}: {rcombo['explanation']}")

        if tactical_fit == "Redundant Role":
            cons.append(f"Role saturation: {gap_description}")
        elif tactical_fit == "Dilution Risk":
            cons.append("Doesn't advance your current synergies; dilutes core deck draws")

        if hp_percent < 45.0:
            if ctype == "Power":
                cons.append("Low HP risk: Power setup may be too slow in immediate hallway fights")
            elif ROLE_BLOCK in roles:
                pros.append("Critical HP buffer: provides immediate survivability")

        return {
            "card": card,
            "primary_role": primary_role,
            "primary_role_label": primary_role_label,
            "tactical_fit": tactical_fit,
            "summary_headline": summary_headline,
            "role_audit": {
                "current_count": current_role_count,
                "deck_percentage": role_pct,
                "gap_description": gap_description,
                "is_critical": is_critical_gap,
            },
            "card_combos": card_combos,
            "relic_combos": relic_combos,
            "has_combos": (len(card_combos) > 0 or len(relic_combos) > 0),
            "pros": pros,
            "cons": cons,
        }
