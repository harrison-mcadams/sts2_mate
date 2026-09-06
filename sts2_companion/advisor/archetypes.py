"""
Archetype definitions, card roles, and tag inferences for Slay the Spire 2.
"""

from typing import Any, Dict, List, Set, Tuple

# Core strategic roles
ROLE_FRONTLOAD_DAMAGE = "frontload_damage"
ROLE_AOE_DAMAGE = "aoe_damage"
ROLE_SCALING_DAMAGE = "scaling_damage"
ROLE_BLOCK = "block"
ROLE_SCALING_DEFENSE = "scaling_defense"
ROLE_DRAW = "draw"
ROLE_ENERGY = "energy"
ROLE_EXHAUST = "exhaust"
ROLE_POISON = "poison"
ROLE_SHIV = "shiv"
ROLE_STRENGTH = "strength"
ROLE_VULNERABLE = "vulnerable"
ROLE_WEAK = "weak"
ROLE_ORB = "orb"
ROLE_SUMMON = "summon"
ROLE_RETAIN = "retain"


def infer_card_roles(card: Dict[str, Any]) -> Set[str]:
    """Infers functional strategic roles from card text and metadata."""
    roles = set()
    name = card.get("name", "").lower()
    desc = card.get("description", "").lower()
    raw_desc = card.get("description_raw", "").lower()
    ctype = card.get("card_type", "Skill")

    # Frontload / Direct Damage
    if ctype == "Attack":
        roles.add(ROLE_FRONTLOAD_DAMAGE)
        if any(w in desc or w in name for w in ["all enemies", "all other enemies", "to all", "flurry", "spray", "whirlwind", "cleave"]):
            roles.add(ROLE_AOE_DAMAGE)
        if any(w in desc for w in ["times", "twice", "3 times", "4 times", "x times"]):
            roles.add("multi_hit")

    # Scaling Damage
    if any(w in desc for w in ["strength", "for each", "permanently", "increases", "damage this combat"]):
        roles.add(ROLE_SCALING_DAMAGE)
        if "strength" in desc:
            roles.add(ROLE_STRENGTH)

    # Block & Defense
    if "block" in desc:
        roles.add(ROLE_BLOCK)
        if any(w in desc for w in ["dexterity", "metallicize", "barricade", "plated armor", "next turn"]):
            roles.add(ROLE_SCALING_DEFENSE)

    # Draw & Filter
    if any(w in desc for w in ["draw", "discard", "scry", "into your hand"]):
        roles.add(ROLE_DRAW)

    # Energy
    if any(w in desc for w in ["[energy]", "gain energy", "energy next turn"]):
        roles.add(ROLE_ENERGY)

    # Exhaust
    if "exhaust" in desc:
        roles.add(ROLE_EXHAUST)

    # Debuffs
    if "vulnerable" in desc:
        roles.add(ROLE_VULNERABLE)
    if "weak" in desc:
        roles.add(ROLE_WEAK)

    # Specific mechanics
    if "poison" in desc:
        roles.add(ROLE_POISON)
    if "shiv" in desc:
        roles.add(ROLE_SHIV)
    if any(w in desc for w in ["summon", "osty", "minion"]):
        roles.add(ROLE_SUMMON)
    if any(w in desc for w in ["channel", "evoke", "lightning", "frost", "plasma", "dark orb", "focus"]):
        roles.add(ROLE_ORB)
    if "retain" in desc:
        roles.add(ROLE_RETAIN)

    return roles


def calculate_relic_synergy(card: Dict[str, Any], relic_ids: Set[str]) -> Tuple[float, List[str]]:
    """Calculates synergy score and explanations between a candidate card and active relics."""
    from typing import Tuple
    bonus = 0.0
    notes = []
    roles = infer_card_roles(card)
    cid = card.get("id", "")
    ctype = card.get("card_type", "Skill")

    # Akabeko (Heavy first-turn attack)
    if "RELIC.AKABEKO" in relic_ids:
        if ctype == "Attack":
            if "multi_hit" in roles:
                bonus += 1.5
                notes.append("Synergizes with Akabeko Vigor for multi-hit burst")
            else:
                bonus += 0.8
                notes.append("Benefits from Akabeko opening turn burst")

    # Lantern / Energy Relics
    energy_relics = {"RELIC.LANTERN", "RELIC.ANCIENT_TEA_SET", "RELIC.HAPPY_FLOWER", "RELIC.ENERGY_REPUTATION"}
    if relic_ids.intersection(energy_relics):
        if card.get("cost", 1) >= 2:
            bonus += 0.6
            notes.append("High-cost card enabled by active energy relics")

    # Shuriken / Kunai / Ornamental Fan (Play 3 attacks)
    ninja_relics = {"RELIC.SHURIKEN", "RELIC.KUNAI", "RELIC.ORNAMENTAL_FAN"}
    if relic_ids.intersection(ninja_relics):
        if ctype == "Attack" and card.get("cost", 1) <= 1:
            bonus += 1.2
            notes.append("Low-cost attack triggers Ninja relics (3 attacks/turn)")

    # Dead Branch / Charon's Ashes (Exhaust synergies)
    exhaust_relics = {"RELIC.DEAD_BRANCH", "RELIC.CHARONS_ASHES"}
    if relic_ids.intersection(exhaust_relics) and ROLE_EXHAUST in roles:
        bonus += 2.0
        notes.append("High synergy with active Exhaust relics")

    # Snecko Eye (High cost cards)
    if "RELIC.SNECKO_EYE" in relic_ids:
        if card.get("cost", 1) >= 2:
            bonus += 1.8
            notes.append("High natural cost benefits greatly from Snecko Eye randomized cost")

    # Bronze Scales (Thorns / Defensive stalls)
    if "RELIC.BRONZE_SCALES" in relic_ids and ROLE_BLOCK in roles:
        bonus += 0.4
        notes.append("Pairs with passive Bronze Scales damage while turtling")

    return bonus, notes
