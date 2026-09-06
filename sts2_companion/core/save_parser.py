"""
Save and Run parser for Slay the Spire 2.
Parses both active runs (current_run.save) and completed runs (history/*.run).
Enriches raw game IDs with human-readable names and database descriptions.
"""

import json
import os
from typing import Any, Dict, List, Optional


class STS2SaveParser:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.cards_db: Dict[str, Dict[str, Any]] = {}
        self.relics_db: Dict[str, Dict[str, Any]] = {}
        self.powers_db: Dict[str, Dict[str, Any]] = {}
        self.potions_db: Dict[str, Dict[str, Any]] = {}
        self._load_databases()

    def _load_databases(self) -> None:
        cards_path = os.path.join(self.data_dir, "sts2_cards.json")
        relics_path = os.path.join(self.data_dir, "sts2_relics.json")
        powers_path = os.path.join(self.data_dir, "sts2_powers.json")
        potions_path = os.path.join(self.data_dir, "sts2_potions.json")

        if os.path.exists(cards_path):
            with open(cards_path, "r", encoding="utf-8") as f:
                self.cards_db = json.load(f)
        if os.path.exists(relics_path):
            with open(relics_path, "r", encoding="utf-8") as f:
                self.relics_db = json.load(f)
        if os.path.exists(powers_path):
            with open(powers_path, "r", encoding="utf-8") as f:
                self.powers_db = json.load(f)
        if os.path.exists(potions_path):
            with open(potions_path, "r", encoding="utf-8") as f:
                self.potions_db = json.load(f)

    def get_card_info(self, card_id: str) -> Dict[str, Any]:
        """Returns enriched card info or a fallback dictionary."""
        if card_id in self.cards_db:
            return dict(self.cards_db[card_id])
        # Clean ID e.g. CARD.STRIKE_IRONCLAD -> Strike
        raw_name = card_id.replace("CARD.", "").replace("_", " ").title()
        return {
            "id": card_id,
            "key": card_id.replace("CARD.", ""),
            "name": raw_name,
            "card_type": "Attack" if "Strike" in raw_name or "Bash" in raw_name else "Skill",
            "character": "unknown",
            "description": "",
            "cost": 1,
            "rarity": "Common",
        }

    def get_relic_info(self, relic_id: str) -> Dict[str, Any]:
        """Returns enriched relic info or a fallback dictionary."""
        if relic_id in self.relics_db:
            return dict(self.relics_db[relic_id])
        raw_name = relic_id.replace("RELIC.", "").replace("_", " ").title()
        return {
            "id": relic_id,
            "key": relic_id.replace("RELIC.", ""),
            "name": raw_name,
            "description": "",
            "flavor": "",
        }

    def parse_run(self, raw_data: Dict[str, Any], is_active: bool = False, file_path: str = "") -> Dict[str, Any]:
        """Parses raw JSON from current_run.save or a .run history file."""
        player_raw = (raw_data.get("players") or [{}])[0]

        # Basic run stats
        ascension = raw_data.get("ascension", 0)
        game_mode = raw_data.get("game_mode", "standard")
        win = raw_data.get("win", False)
        abandoned = raw_data.get("was_abandoned", False)
        killed_by = raw_data.get("killed_by_encounter") or raw_data.get("killed_by_event") or "NONE"
        seed = raw_data.get("seed", "")
        start_time = raw_data.get("start_time", 0)
        run_time = raw_data.get("run_time", 0)
        acts = raw_data.get("acts", [])

        # Player stats
        raw_char = player_raw.get("character", "UNKNOWN")
        character_name = raw_char.replace("CHARACTER.", "").title()
        current_hp = player_raw.get("current_hp", 0)
        max_hp = player_raw.get("max_hp", 0)
        gold = player_raw.get("gold", 0)

        # Enriched relics
        raw_relics = player_raw.get("relics", [])
        enriched_relics = []
        for r in raw_relics:
            rid = r.get("id", "")
            rinfo = self.get_relic_info(rid)
            rinfo["floor_added"] = r.get("floor_added_to_deck", 0)
            rinfo["props"] = r.get("props", {})
            enriched_relics.append(rinfo)

        # Enriched deck
        raw_deck = player_raw.get("deck", [])
        enriched_deck = []
        deck_types = {"Attack": 0, "Skill": 0, "Power": 0, "Curse": 0, "Status": 0}
        
        for c in raw_deck:
            cid = c.get("id", "")
            cinfo = self.get_card_info(cid)
            cinfo["upgrade_level"] = c.get("current_upgrade_level", 0)
            cinfo["is_upgraded"] = cinfo["upgrade_level"] > 0
            if cinfo["is_upgraded"]:
                cinfo["display_name"] = f"{cinfo['name']}+"
            else:
                cinfo["display_name"] = cinfo["name"]
            cinfo["floor_added"] = c.get("floor_added_to_deck", 0)
            cinfo["enchantment"] = c.get("enchantment")
            enriched_deck.append(cinfo)
            ctype = cinfo.get("card_type", "Skill")
            deck_types[ctype] = deck_types.get(ctype, 0) + 1

        # Enriched potions
        raw_potions = player_raw.get("potions", [])
        enriched_potions = []
        for p in raw_potions:
            pid = p.get("id", "")
            if pid:
                pname = pid.replace("POTION.", "").replace("_", " ").title()
                enriched_potions.append({"id": pid, "name": pname})

        # Map point history and card rewards offered
        map_history = raw_data.get("map_point_history", [])
        recent_rooms = []
        all_card_choices = []
        total_floors = 0

        for act_idx, act_rooms in enumerate(map_history):
            for room_idx, room in enumerate(act_rooms):
                total_floors += 1
                room_type = room.get("map_point_type", "unknown")
                pstats = (room.get("player_stats") or [{}])[0]
                room_hp = pstats.get("current_hp", current_hp)
                room_max_hp = pstats.get("max_hp", max_hp)

                choices = pstats.get("card_choices", [])
                parsed_choices = []
                for ch in choices:
                    card_obj = ch.get("card", {})
                    cid = card_obj.get("id", "")
                    cinfo = self.get_card_info(cid)
                    cinfo["was_picked"] = ch.get("was_picked", False)
                    parsed_choices.append(cinfo)

                if parsed_choices:
                    all_card_choices.append({
                        "floor": total_floors,
                        "act": act_idx + 1,
                        "room_type": room_type,
                        "options": parsed_choices,
                        "picked": [c["name"] for c in parsed_choices if c.get("was_picked")],
                    })

                recent_rooms.append({
                    "floor": total_floors,
                    "act": act_idx + 1,
                    "room_type": room_type,
                    "hp": room_hp,
                    "max_hp": room_max_hp,
                    "choices_count": len(parsed_choices),
                })

        current_floor = raw_data.get("floor_reached", total_floors)
        current_act_index = raw_data.get("current_act_index", len(map_history) - 1 if map_history else 0)

        # Check if there is an unpicked card reward
        latest_unpicked_reward = None
        if is_active:
            # 1. From latest room in map_history
            if all_card_choices:
                latest = all_card_choices[-1]
                if not latest.get("picked"):
                    latest_unpicked_reward = latest.get("options", [])

            # 2. Check top-level or player-level reward structures if not found in map_history
            if not latest_unpicked_reward:
                for container in [raw_data, player_raw]:
                    for rkey in ["rewards", "pending_rewards", "combat_rewards", "card_rewards", "active_rewards"]:
                        rval = container.get(rkey)
                        if isinstance(rval, list):
                            for r_item in rval:
                                if isinstance(r_item, dict):
                                    cards_opt = r_item.get("cards") or r_item.get("options")
                                    if isinstance(cards_opt, list) and cards_opt:
                                        parsed_opts = []
                                        for c in cards_opt:
                                            cid = c.get("id") if isinstance(c, dict) else str(c)
                                            if cid:
                                                parsed_opts.append(self.get_card_info(cid))
                                        if parsed_opts:
                                            latest_unpicked_reward = parsed_opts
                                            break
                        if latest_unpicked_reward:
                            break

        return {
            "is_active": is_active,
            "file_path": file_path,
            "character": character_name,
            "raw_character": raw_char,
            "ascension": ascension,
            "current_floor": current_floor,
            "current_act": current_act_index + 1,
            "current_hp": current_hp,
            "max_hp": max_hp,
            "hp_percent": round((current_hp / max_hp * 100), 1) if max_hp > 0 else 0,
            "gold": gold,
            "deck": enriched_deck,
            "deck_size": len(enriched_deck),
            "deck_breakdown": deck_types,
            "relics": enriched_relics,
            "relic_count": len(enriched_relics),
            "potions": enriched_potions,
            "win": win,
            "was_abandoned": abandoned,
            "killed_by": killed_by,
            "seed": seed,
            "start_time": start_time,
            "run_time": run_time,
            "card_reward_history": all_card_choices,
            "pending_reward": latest_unpicked_reward,
            "recent_rooms": recent_rooms[-8:] if recent_rooms else [],
        }

    def parse_file(self, file_path: str, is_active: bool = False) -> Optional[Dict[str, Any]]:
        """Reads and parses a save or run file from disk."""
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            return self.parse_run(raw_data, is_active=is_active, file_path=file_path)
        except Exception as e:
            print(f"Error parsing save file {file_path}: {e}")
            return None
