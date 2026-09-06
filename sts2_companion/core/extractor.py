"""
Slay the Spire 2 Game Data Extractor.
Extracts Cards, Relics, Powers, Potions, Keywords, and Metadata directly from STS2 game assets.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from .pck_reader import GodotPckReader
from .paths import get_default_game_dir

DEFAULT_GAME_PATH = get_default_game_dir() or r"C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2"
DEFAULT_PCK_PATH = os.path.join(DEFAULT_GAME_PATH, "SlayTheSpire2.pck")


def clean_bbcode(text: str) -> str:
    """Removes or normalizes Godot BBCode formatting tags."""
    if not text:
        return ""
    # Remove color/style tags like [gold], [/gold], [sine], [/sine], etc.
    clean = re.sub(r"\[/?(?:[a-zA-Z0-9_]+|#[0-9a-fA-F]{3,8})\]", "", text)
    return clean.strip()


def format_card_description(desc: str) -> str:
    """Simplifies dynamic template placeholders for human readability."""
    if not desc:
        return ""
    # Replace {Field:diff()} -> {Field}
    desc = re.sub(r"\{([A-Za-z0-9_]+):diff\(\)\}", r"{\1}", desc)
    # Replace {Field:plural:singular|plural} -> {Field}
    desc = re.sub(r"\{([A-Za-z0-9_]+):plural:([^|}]+)\|([^}]+)\}", r"{\1} \3", desc)
    # Replace {Energy:energyIcons()} -> [Energy]
    desc = re.sub(r"\{Energy:energyIcons\(\)\}", "[Energy]", desc)
    desc = re.sub(r"\{energyPrefix:energyIcons\(([0-9]+)\)\}", r"\1 [Energy]", desc)
    return clean_bbcode(desc)


class STS2Extractor:
    def __init__(self, pck_path: str = DEFAULT_PCK_PATH):
        self.pck_path = pck_path
        self.reader = GodotPckReader(pck_path)

    def extract_all(self, output_dir: str = "data") -> Dict[str, Any]:
        os.makedirs(output_dir, exist_ok=True)
        print(f"Extracting STS2 data from: {self.pck_path}...")

        cards = self.extract_cards()
        relics = self.extract_relics()
        powers = self.extract_powers()
        potions = self.extract_potions()
        keywords = self.extract_keywords()
        metadata = self.extract_metadata()

        cards_file = os.path.join(output_dir, "sts2_cards.json")
        relics_file = os.path.join(output_dir, "sts2_relics.json")
        powers_file = os.path.join(output_dir, "sts2_powers.json")
        potions_file = os.path.join(output_dir, "sts2_potions.json")
        keywords_file = os.path.join(output_dir, "sts2_keywords.json")
        metadata_file = os.path.join(output_dir, "sts2_metadata.json")

        with open(cards_file, "w", encoding="utf-8") as f:
            json.dump(cards, f, indent=2, ensure_ascii=False)
        with open(relics_file, "w", encoding="utf-8") as f:
            json.dump(relics, f, indent=2, ensure_ascii=False)
        with open(powers_file, "w", encoding="utf-8") as f:
            json.dump(powers, f, indent=2, ensure_ascii=False)
        with open(potions_file, "w", encoding="utf-8") as f:
            json.dump(potions, f, indent=2, ensure_ascii=False)
        with open(keywords_file, "w", encoding="utf-8") as f:
            json.dump(keywords, f, indent=2, ensure_ascii=False)
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print(f"Successfully extracted: {len(cards)} cards, {len(relics)} relics, "
              f"{len(powers)} powers, {len(potions)} potions to {output_dir}/")

        return {
            "cards_count": len(cards),
            "relics_count": len(relics),
            "powers_count": len(powers),
            "potions_count": len(potions),
        }

    def _get_card_character_map(self) -> Dict[str, str]:
        """Maps lowercase card IDs to characters by examining sprite atlas directories."""
        char_map = {}
        for path in self.reader.entries:
            if "images/atlases/card_atlas.sprites/" in path and path.endswith(".tres"):
                parts = path.split("images/atlases/card_atlas.sprites/")[1].split("/")
                if len(parts) >= 2:
                    character = parts[0]  # e.g., ironclad, silent, defect, necrobinder, regent, colorless, curse, status
                    filename = parts[-1].replace(".tres", "")
                    char_map[filename.lower()] = character
        return char_map

    def extract_cards(self) -> Dict[str, Dict[str, Any]]:
        raw_text = self.reader.get_text("localization/eng/cards.json")
        if not raw_text:
            raise ValueError("Could not find localization/eng/cards.json in PCK")
        loc_data = json.loads(raw_text)

        char_map = self._get_card_character_map()

        # Group titles and descriptions by base key
        cards: Dict[str, Dict[str, Any]] = {}
        for key, val in loc_data.items():
            if "." not in key:
                continue
            base_id, prop = key.split(".", 1)
            if base_id.startswith("MOCK_"):
                continue
            card_run_id = f"CARD.{base_id}"

            if card_run_id not in cards:
                cards[card_run_id] = {
                    "id": card_run_id,
                    "key": base_id,
                    "name": "",
                    "description_raw": "",
                    "description": "",
                    "character": "unknown",
                    "card_type": "Skill",  # fallback
                    "rarity": "Common",
                    "cost": 1,
                }

            if prop == "title":
                cards[card_run_id]["name"] = val
            elif prop == "description":
                cards[card_run_id]["description_raw"] = val
                cards[card_run_id]["description"] = format_card_description(val)

        # Infer character and card type
        for card_id, c in cards.items():
            k_lower = c["key"].lower()
            # Check character map
            if k_lower in char_map:
                c["character"] = char_map[k_lower]
            else:
                # Try underscores to no-underscores or vice versa
                k_no_us = k_lower.replace("_", "")
                for mapped_name, mapped_char in char_map.items():
                    if mapped_name.replace("_", "") == k_no_us:
                        c["character"] = mapped_char
                        break

            # Infer card type from description
            raw_d = c["description_raw"].lower()
            if "deal " in raw_d or "{damage" in raw_d or "attack" in raw_d:
                c["card_type"] = "Attack"
            elif "whenever you play" in raw_d or "at the start of each turn" in raw_d or "at the end of your turn" in raw_d or "at the start of your turn" in raw_d:
                c["card_type"] = "Power"
            elif c["character"] == "curse":
                c["card_type"] = "Curse"
            elif c["character"] == "status":
                c["card_type"] = "Status"
            else:
                c["card_type"] = "Skill"

        return cards

    def extract_relics(self) -> Dict[str, Dict[str, Any]]:
        raw_text = self.reader.get_text("localization/eng/relics.json")
        if not raw_text:
            raise ValueError("Could not find localization/eng/relics.json in PCK")
        loc_data = json.loads(raw_text)

        relics: Dict[str, Dict[str, Any]] = {}
        for key, val in loc_data.items():
            if "." not in key:
                continue
            base_id, prop = key.split(".", 1)
            relic_run_id = f"RELIC.{base_id}"

            if relic_run_id not in relics:
                relics[relic_run_id] = {
                    "id": relic_run_id,
                    "key": base_id,
                    "name": "",
                    "description_raw": "",
                    "description": "",
                    "flavor": "",
                }

            if prop == "title":
                relics[relic_run_id]["name"] = val
            elif prop == "description":
                relics[relic_run_id]["description_raw"] = val
                relics[relic_run_id]["description"] = format_card_description(val)
            elif prop == "flavor":
                relics[relic_run_id]["flavor"] = clean_bbcode(val)

        return relics

    def extract_powers(self) -> Dict[str, Dict[str, Any]]:
        raw_text = self.reader.get_text("localization/eng/powers.json")
        if not raw_text:
            return {}
        loc_data = json.loads(raw_text)

        powers: Dict[str, Dict[str, Any]] = {}
        for key, val in loc_data.items():
            if "." not in key:
                continue
            base_id, prop = key.split(".", 1)
            power_id = f"POWER.{base_id}"

            if power_id not in powers:
                powers[power_id] = {
                    "id": power_id,
                    "key": base_id,
                    "name": "",
                    "description": "",
                }

            if prop == "title":
                powers[power_id]["name"] = val
            elif prop == "description":
                powers[power_id]["description"] = format_card_description(val)

        return powers

    def extract_potions(self) -> Dict[str, Dict[str, Any]]:
        raw_text = self.reader.get_text("localization/eng/potions.json")
        if not raw_text:
            return {}
        loc_data = json.loads(raw_text)

        potions: Dict[str, Dict[str, Any]] = {}
        for key, val in loc_data.items():
            if "." not in key:
                continue
            base_id, prop = key.split(".", 1)
            potion_id = f"POTION.{base_id}"

            if potion_id not in potions:
                potions[potion_id] = {
                    "id": potion_id,
                    "key": base_id,
                    "name": "",
                    "description": "",
                }

            if prop == "title":
                potions[potion_id]["name"] = val
            elif prop == "description":
                potions[potion_id]["description"] = format_card_description(val)

        return potions

    def extract_keywords(self) -> Dict[str, str]:
        raw_text = self.reader.get_text("localization/eng/card_keywords.json")
        if not raw_text:
            return {}
        return json.loads(raw_text)

    def extract_metadata(self) -> Dict[str, Any]:
        chars_raw = self.reader.get_text("localization/eng/characters.json")
        monsters_raw = self.reader.get_text("localization/eng/monsters.json")
        encounters_raw = self.reader.get_text("localization/eng/encounters.json")
        events_raw = self.reader.get_text("localization/eng/events.json")

        return {
            "characters": json.loads(chars_raw) if chars_raw else {},
            "monsters": json.loads(monsters_raw) if monsters_raw else {},
            "encounters": json.loads(encounters_raw) if encounters_raw else {},
            "events": json.loads(events_raw) if events_raw else {},
        }
