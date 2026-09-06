"""
Card Reward Decision Evaluator for Slay the Spire 2.
Scores candidate card choices against the player's active deck, relics, floor/act context,
and personal historical performance to produce prioritized recommendations and skip advice.
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
    ROLE_ORB,
    ROLE_SUMMON,
    calculate_relic_synergy,
    infer_card_roles,
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
        Evaluates a set of offered cards in the context of an active run.
        Returns ranked choices with scores, pros/cons, upgrade priority, and skip advice.
        """
        floor = active_run.get("current_floor", 1)
        act = active_run.get("current_act", 1)
        character = active_run.get("character", "Ironclad")
        deck = active_run.get("deck", [])
        relics = active_run.get("relics", [])
        current_hp = active_run.get("current_hp", 80)
        max_hp = active_run.get("max_hp", 80)
        hp_percent = active_run.get("hp_percent", 100.0)

        deck_card_ids = [c.get("id") for c in deck]
        relic_ids = set(r.get("id") for r in relics)

        # Analyze current deck profile
        deck_roles: Dict[str, int] = {}
        for c in deck:
            c_info = self.cards_db.get(c.get("id"), c)
            for role in infer_card_roles(c_info):
                deck_roles[role] = deck_roles.get(role, 0) + 1

        attack_count = sum(1 for c in deck if c.get("card_type") == "Attack")
        skill_count = sum(1 for c in deck if c.get("card_type") == "Skill")
        power_count = sum(1 for c in deck if c.get("card_type") == "Power")
        deck_size = len(deck)

        evaluated_options = []

        for cid in offered_card_ids:
            cinfo = self.cards_db.get(cid)
            if not cinfo:
                # Fallback info
                cinfo = {
                    "id": cid,
                    "name": cid.replace("CARD.", "").replace("_", " ").title(),
                    "card_type": "Skill",
                    "description": "",
                    "character": character.lower(),
                }

            score, pros, cons, upgrade_advice = self._score_card(
                card=cinfo,
                act=act,
                floor=floor,
                deck_size=deck_size,
                attack_count=attack_count,
                skill_count=skill_count,
                power_count=power_count,
                deck_roles=deck_roles,
                deck_card_ids=deck_card_ids,
                relic_ids=relic_ids,
                hp_percent=hp_percent,
                character=character,
            )

            # Personal stats modifier
            p_stats = self.player_stats.get("card_stats", {}).get(cid)
            personal_note = None
            if p_stats:
                p_win_rate = p_stats.get("win_rate", 0.0)
                p_pick_rate = p_stats.get("pick_rate", 0.0)
                drafted = p_stats.get("drafted_runs", 0)
                if drafted >= 5:
                    if p_win_rate >= 15.0:
                        score += 0.8
                        pros.append(f"High personal win rate ({p_win_rate}% across {drafted} runs)")
                    elif p_win_rate <= 2.0 and drafted >= 10:
                        score -= 0.6
                        cons.append(f"Low personal win rate ({p_win_rate}% in your history)")
                personal_note = {
                    "pick_rate": p_pick_rate,
                    "win_rate": p_win_rate,
                    "drafted_runs": drafted,
                }

            evaluated_options.append({
                "card": cinfo,
                "score": round(score, 2),
                "pros": pros,
                "cons": cons,
                "upgrade_priority": upgrade_advice,
                "personal_stats": personal_note,
            })

        # Sort options descending by score
        evaluated_options.sort(key=lambda x: x["score"], reverse=True)

        # Skip evaluation
        # In early Act 1, skip is generally avoided unless deck is bloated or all choices are awful.
        # In Act 2 & 3, if deck is already functional and cards don't fill gaps, skip is high value.
        skip_score = 5.0
        skip_reasons = []

        if deck_size >= 25:
            skip_score += 1.5
            skip_reasons.append("Deck is already large (25+ cards); drawing key powers/combo pieces is paramount")
        elif deck_size >= 20 and act >= 2:
            skip_score += 0.8
            skip_reasons.append("Solid deck size; avoid diluting your high-value cards")

        top_option = evaluated_options[0] if evaluated_options else None
        should_skip = False

        if top_option and top_option["score"] < skip_score:
            should_skip = True
            verdict = f"SKIP RECOMMENDED: None of the offered cards sufficiently improve your deck ({top_option['card']['name']} scored {top_option['score']:.1f} vs Skip threshold {skip_score:.1f})."
        elif top_option:
            verdict = f"RECOMMENDATION: Pick **{top_option['card']['name']}** (Score: {top_option['score']:.1f}/10)."
        else:
            verdict = "No card options offered."

        return {
            "verdict": verdict,
            "should_skip": should_skip,
            "skip_threshold": round(skip_score, 1),
            "skip_reasons": skip_reasons,
            "top_choice": top_option["card"]["name"] if (top_option and not should_skip) else "SKIP",
            "ranked_options": evaluated_options,
            "context_summary": {
                "act": act,
                "floor": floor,
                "character": character,
                "deck_size": deck_size,
                "attacks": attack_count,
                "skills": skill_count,
                "powers": power_count,
                "hp_percent": hp_percent,
            }
        }

    def _score_card(
        self,
        card: Dict[str, Any],
        act: int,
        floor: int,
        deck_size: int,
        attack_count: int,
        skill_count: int,
        power_count: int,
        deck_roles: Dict[str, int],
        deck_card_ids: List[str],
        relic_ids: Set[str],
        hp_percent: float,
        character: str,
    ) -> Tuple[float, List[str], List[str], str]:
        score = 5.0  # Base neutral score
        pros: List[str] = []
        cons: List[str] = []
        roles = infer_card_roles(card)
        ctype = card.get("card_type", "Skill")
        name = card.get("name", "")

        # 1. Floor & Act Immediate Need
        if act == 1:
            if floor <= 6:
                # Early Act 1: desperately need frontloaded damage to kill Gremlin Nob / Sentinels / Elites
                if ROLE_FRONTLOAD_DAMAGE in roles or ctype == "Attack":
                    score += 2.2
                    pros.append("High priority early Act 1 attack to survive upcoming Elites (Nob/Sentinels/Parasite)")
                elif ROLE_SCALING_DAMAGE in roles or ctype == "Power":
                    score -= 0.5
                    cons.append("Slow in early hallway fights; may be a dead draw before Elites")
            else:
                # Mid/Late Act 1: balance damage with block and preparation for the Act 1 Boss
                if ROLE_BLOCK in roles and deck_roles.get(ROLE_BLOCK, 0) < 6:
                    score += 1.8
                    pros.append("Needed block addition before the Act 1 Boss encounter")
        elif act == 2:
            # Act 2: AOE is king (multi-enemy encounters like Birds, Thieves, Gremlin Leader)
            if ROLE_AOE_DAMAGE in roles:
                score += 2.0
                pros.append("Crucial Act 2 AOE to handle multi-enemy encounters")
            if ROLE_BLOCK in roles:
                score += 1.2
                pros.append("Sturdy mitigation against hard-hitting Act 2 threats")
        elif act >= 3:
            # Act 3+: Scaling damage, energy acceleration, and consistent card draw
            if ROLE_SCALING_DAMAGE in roles or ROLE_SCALING_DEFENSE in roles:
                score += 2.0
                pros.append("Essential scaling for Act 3 Elites and Spire Bosses")
            if ROLE_DRAW in roles:
                score += 1.5
                pros.append("Card draw consistency to cycle your deck every turn")

        # 2. Deck Role & Balance
        if ctype == "Attack":
            if attack_count >= 11 and deck_size < 22:
                score -= 1.4
                cons.append("Deck already saturated with attacks; risks low block turns")
        elif ctype == "Skill" and ROLE_BLOCK in roles:
            if skill_count < 7:
                score += 1.3
                pros.append("Helps balance your defense-to-offense ratio")
        elif ctype == "Power":
            if power_count >= 5:
                score -= 0.8
                cons.append("Multiple powers in deck already; beware of slow setup hands")

        # 3. Specific Synergies with Existing Deck
        # Strength synergy
        if ROLE_STRENGTH in roles or "CARD.INFLAME" in deck_card_ids or "CARD.SPOT_WEAKNESS" in deck_card_ids:
            if "multi_hit" in roles or ROLE_FRONTLOAD_DAMAGE in roles:
                score += 1.4
                pros.append("Synergizes strongly with Strength scaling")

        # Exhaust synergy
        if ROLE_EXHAUST in roles:
            if any(cid in deck_card_ids for cid in ["CARD.FEEL_NO_PAIN", "CARD.DARK_EMBRACE", "CARD.CORRUPTION"]):
                score += 2.0
                pros.append("Direct synergy with active Exhaust engines (Feel No Pain / Dark Embrace / Corruption)")

        # Poison synergy
        if ROLE_POISON in roles:
            if deck_roles.get(ROLE_POISON, 0) > 0:
                score += 1.6
                pros.append("Reinforces your existing Poison engine")
            else:
                score -= 0.6
                cons.append("Single poison card without dedicated poison support scales slowly")

        # Osty / Summon synergy (Necrobinder)
        if ROLE_SUMMON in roles and character.lower() == "necrobinder":
            score += 1.5
            pros.append("Key Necrobinder summon mechanic; empowers Osty actions")

        # Card Draw is almost always premium
        if ROLE_DRAW in roles:
            score += 1.3
            pros.append("Card draw speeds up finding your best cards on pivotal turns")

        # 4. Relic Synergies
        relic_bonus, relic_notes = calculate_relic_synergy(card, relic_ids)
        score += relic_bonus
        pros.extend(relic_notes)

        # 5. Health Context
        if hp_percent < 45.0:
            if ROLE_BLOCK in roles or "heal" in card.get("description", "").lower():
                score += 1.2
                pros.append("Immediate survivability boost needed at critical HP (<45%)")
            elif ctype == "Power":
                score -= 1.0
                cons.append("Risky pick while low on HP; may not have time to set up")

        # 6. Upgrade Priority Assessment
        if ctype == "Power":
            upgrade_advice = "High (Powers benefit greatly from cost reduction or doubled scaling)"
        elif ROLE_DRAW in roles or ROLE_ENERGY in roles:
            upgrade_advice = "High (Increases card draw or removes energy choking)"
        elif ctype == "Attack":
            upgrade_advice = "Medium (Solid damage boost, upgrade if primary damage dealer)"
        else:
            upgrade_advice = "Normal"

        return score, pros, cons, upgrade_advice
