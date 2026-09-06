"""
Archetype definitions, card roles, and synergy linkages for Slay the Spire 2.
Surfaces qualitative deck gap audits and explicit card-to-card / relic-to-card combos.
"""

from typing import Any, Dict, List, Set, Tuple

# Core strategic problem-solving roles
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

ROLE_LABELS = {
    ROLE_AOE_DAMAGE: "Area of Effect (AOE)",
    ROLE_FRONTLOAD_DAMAGE: "Single-Target Damage",
    ROLE_BLOCK: "Block & Mitigation",
    ROLE_SCALING_DAMAGE: "Scaling Damage",
    ROLE_SCALING_DEFENSE: "Scaling Defense",
    ROLE_DRAW: "Card Draw & Velocity",
    ROLE_ENERGY: "Energy Economy",
    ROLE_EXHAUST: "Exhaust Engine",
    ROLE_STRENGTH: "Strength Scaling",
    ROLE_VULNERABLE: "Vulnerable Infliction",
    ROLE_WEAK: "Weak Mitigation",
    ROLE_POISON: "Poison Scaling",
    ROLE_SHIV: "Shiv Swarm",
    ROLE_ORB: "Orb Mechanics",
    ROLE_SUMMON: "Minion / Companion",
}


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
        if any(w in desc or w in name for w in [
            "all enemies", "all other enemies", "to all", "flurry", "spray",
            "whirlwind", "cleave", "thunderclap", "immolate", "combust"
        ]):
            roles.add(ROLE_AOE_DAMAGE)
        if any(w in desc for w in ["times", "twice", "3 times", "4 times", "x times"]):
            roles.add("multi_hit")

    # Scaling Damage
    if any(w in desc for w in ["strength", "for each", "permanently", "increases", "damage this combat", "ritual"]):
        roles.add(ROLE_SCALING_DAMAGE)
        if "strength" in desc:
            roles.add(ROLE_STRENGTH)

    # Block & Defense
    if "block" in desc or "shield" in desc:
        roles.add(ROLE_BLOCK)
        if any(w in desc for w in ["dexterity", "metallicize", "barricade", "plated armor", "next turn", "entrench"]):
            roles.add(ROLE_SCALING_DEFENSE)

    # Draw & Filter
    if any(w in desc for w in ["draw", "discard", "scry", "into your hand", "retrieve"]):
        roles.add(ROLE_DRAW)

    # Energy
    if any(w in desc for w in ["[energy]", "gain energy", "energy next turn", "gain [e]"]):
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


def find_card_combos(candidate_card: Dict[str, Any], deck_cards: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Identifies direct, explicit card-to-card synergies between an offered card and cards currently in the deck.
    """
    combos = []
    c_name = candidate_card.get("name", "")
    c_desc = candidate_card.get("description", "").lower()
    c_type = candidate_card.get("card_type", "Skill")
    c_roles = infer_card_roles(candidate_card)

    deck_names = {c.get("name", ""): c for c in deck_cards}
    deck_ids = {c.get("id", ""): c for c in deck_cards}

    # 1. Strength Scaling Synergies
    strength_cards = [name for name in ["Inflame", "Spot Weakness", "Demon Form", "Limit Break", "Vajra"] if name in deck_names]
    if "multi_hit" in c_roles and strength_cards:
        combos.append({
            "partner": ", ".join(strength_cards),
            "type": "Strength Multiplier",
            "explanation": f"Scales multiple times per hit with your {', '.join(strength_cards)}"
        })
    elif c_name in ["Heavy Blade", "Sword Boomerang", "Twin Strike", "Pummel"] and strength_cards:
        combos.append({
            "partner": ", ".join(strength_cards),
            "type": "Strength Scaling",
            "explanation": f"Turns active Strength into massive single-turn burst"
        })
    elif ROLE_STRENGTH in c_roles:
        multi_hit_attacks = [c.get("name") for c in deck_cards if "multi_hit" in infer_card_roles(c)]
        if multi_hit_attacks:
            combos.append({
                "partner": ", ".join(set(multi_hit_attacks[:3])),
                "type": "Damage Amplification",
                "explanation": f"Directly powers up your multi-hit attacks ({', '.join(set(multi_hit_attacks[:3]))})"
            })

    # 2. Exhaust Engine Synergies
    exhaust_triggers = [name for name in ["Dark Embrace", "Feel No Pain", "Corruption", "Sentinel"] if name in deck_names]
    if ROLE_EXHAUST in c_roles and exhaust_triggers:
        combos.append({
            "partner": ", ".join(exhaust_triggers),
            "type": "Exhaust Engine",
            "explanation": f"Triggers card draw / block bonuses from {', '.join(exhaust_triggers)}"
        })
    elif c_name in ["Dark Embrace", "Feel No Pain"]:
        exhaust_sources = [c.get("name") for c in deck_cards if "exhaust" in c.get("description", "").lower()]
        if exhaust_sources:
            combos.append({
                "partner": ", ".join(set(exhaust_sources[:3])),
                "type": "Engine Payoff",
                "explanation": f"Generates recurring value from your {len(exhaust_sources)} exhaust cards"
            })

    # 3. Block Synergy (Body Slam / Barricade / Entrench)
    heavy_block_cards = [c.get("name") for c in deck_cards if any(w in c.get("name", "").lower() for w in ["blood wall", "impervious", "power through", "flame barrier"])]
    if c_name == "Body Slam" and heavy_block_cards:
        combos.append({
            "partner": ", ".join(set(heavy_block_cards)),
            "type": "Defense-to-Damage",
            "explanation": f"Converts high block from {', '.join(set(heavy_block_cards))} directly into 0-cost damage"
        })
    elif c_name in ["Barricade", "Entrench"] and heavy_block_cards:
        combos.append({
            "partner": ", ".join(set(heavy_block_cards)),
            "type": "Block Retention",
            "explanation": f"Preserves and compounds the high block generated by {', '.join(set(heavy_block_cards))}"
        })

    # 4. Vulnerable Enablers & Heavy Damage
    if ROLE_VULNERABLE in c_roles:
        big_attacks = [c.get("name") for c in deck_cards if c.get("card_type") == "Attack" and c.get("cost", 1) >= 2]
        if big_attacks:
            combos.append({
                "partner": ", ".join(set(big_attacks[:2])),
                "type": "Damage Amplification",
                "explanation": f"Increases damage of your heavy attacks ({', '.join(set(big_attacks[:2]))}) by +50%"
            })

    # 5. Energy Producers & High Cost Spells
    if ROLE_ENERGY in c_roles:
        expensive_cards = [c.get("name") for c in deck_cards if c.get("cost", 1) >= 2]
        if expensive_cards:
            combos.append({
                "partner": ", ".join(set(expensive_cards[:3])),
                "type": "Energy Acceleration",
                "explanation": f"Smoothly finances your high-cost cards ({', '.join(set(expensive_cards[:3]))})"
            })
    elif candidate_card.get("cost", 1) >= 2:
        energy_sources = [c.get("name") for c in deck_cards if ROLE_ENERGY in infer_card_roles(c)]
        if energy_sources:
            combos.append({
                "partner": ", ".join(set(energy_sources)),
                "type": "Energy Supported",
                "explanation": f"High energy cost supported by your {', '.join(set(energy_sources))}"
            })

    # 6. Card Draw & Consistency
    if ROLE_DRAW in c_roles:
        high_impact_cards = [c.get("name") for c in deck_cards if c.get("card_type") in ["Power", "Attack"] and c.get("cost", 1) >= 2]
        if high_impact_cards:
            combos.append({
                "partner": ", ".join(set(high_impact_cards[:2])),
                "type": "Cycle & Velocity",
                "explanation": f"Digs to consistently draw your core cards ({', '.join(set(high_impact_cards[:2]))})"
            })

    return combos


def find_relic_combos(candidate_card: Dict[str, Any], relics: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Identifies direct synergies between an offered card and equipped relics.
    """
    combos = []
    c_name = candidate_card.get("name", "")
    c_type = candidate_card.get("card_type", "Skill")
    c_roles = infer_card_roles(candidate_card)
    c_cost = candidate_card.get("cost", 1)

    relic_map = {r.get("id", ""): r.get("name", r.get("id", "").replace("RELIC.", "").replace("_", " ").title()) for r in relics}

    # Akabeko
    if "RELIC.AKABEKO" in relic_map and c_type == "Attack":
        if "multi_hit" in c_roles:
            combos.append({
                "relic": relic_map["RELIC.AKABEKO"],
                "explanation": "Grants +8 Vigor damage to the first hit on Turn 1"
            })
        elif ROLE_AOE_DAMAGE in c_roles:
            combos.append({
                "relic": relic_map["RELIC.AKABEKO"],
                "explanation": "Grants +8 damage to ALL enemies on your opening turn"
            })
        else:
            combos.append({
                "relic": relic_map["RELIC.AKABEKO"],
                "explanation": "Empowers this attack with +8 damage on Turn 1"
            })

    # Ninja Relics (Kunai, Shuriken, Ornamental Fan)
    ninja_hits = [rname for rid, rname in relic_map.items() if rid in ["RELIC.SHURIKEN", "RELIC.KUNAI", "RELIC.ORNAMENTAL_FAN"]]
    if ninja_hits and c_type == "Attack" and c_cost <= 1:
        combos.append({
            "relic": ", ".join(ninja_hits),
            "explanation": f"Efficient low-cost attack triggers your 3-attack/turn relics ({', '.join(ninja_hits)})"
        })

    # Snecko Eye
    if "RELIC.SNECKO_EYE" in relic_map:
        if c_cost >= 2:
            combos.append({
                "relic": relic_map["RELIC.SNECKO_EYE"],
                "explanation": "2+ cost card heavily favored by Snecko Eye randomized cost & +2 draw"
            })
        elif c_cost == 0:
            combos.append({
                "relic": relic_map["RELIC.SNECKO_EYE"],
                "explanation": "Warning: 0-cost card can be randomized to higher cost by Snecko Eye"
            })

    # Dead Branch / Charon's Ashes
    exhaust_relics = [rname for rid, rname in relic_map.items() if rid in ["RELIC.DEAD_BRANCH", "RELIC.CHARONS_ASHES"]]
    if exhaust_relics and ROLE_EXHAUST in c_roles:
        combos.append({
            "relic": ", ".join(exhaust_relics),
            "explanation": f"Directly triggers your active exhaust relics ({', '.join(exhaust_relics)})"
        })

    # Vajra
    if "RELIC.VAJRA" in relic_map and c_type == "Attack":
        if "multi_hit" in c_roles:
            combos.append({
                "relic": relic_map["RELIC.VAJRA"],
                "explanation": "Passive +1 Strength multiplies across each hit"
            })

    return combos
