"""
Player History Miner for Slay the Spire 2.
Mines all completed .run files in the player's saves history to extract personal
card pick rates, win rates, character masteries, and death patterns.
"""

import glob
import json
import os
from typing import Any, Dict, List, Optional
from .save_parser import STS2SaveParser
from .paths import get_default_save_dir

_default_save = get_default_save_dir()
DEFAULT_HISTORY_PATH = os.path.join(_default_save, "history") if _default_save else r"C:\Users\harri\AppData\Roaming\SlayTheSpire2\steam\76561199820060807\profile1\saves\history"


class STS2HistoryMiner:
    def __init__(self, history_dir: str = DEFAULT_HISTORY_PATH, data_dir: str = "data"):
        self.history_dir = history_dir
        self.data_dir = data_dir
        self.parser = STS2SaveParser(data_dir=data_dir)
        self.stats_cache_file = os.path.join(data_dir, "sts2_player_stats.json")

    def mine_all(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Parses all .run files in history and computes aggregate player metrics."""
        if not force_refresh and os.path.exists(self.stats_cache_file):
            try:
                with open(self.stats_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        if not os.path.exists(self.history_dir):
            return {"total_runs": 0, "runs": []}

        run_files = glob.glob(os.path.join(self.history_dir, "*.run"))
        print(f"Mining {len(run_files)} Slay the Spire 2 run files...")

        total_runs = 0
        total_wins = 0
        character_stats: Dict[str, Dict[str, Any]] = {}
        card_stats: Dict[str, Dict[str, Any]] = {}  # card_id -> {offered, picked, won_with, character}
        death_encounters: Dict[str, int] = {}
        recent_runs: List[Dict[str, Any]] = []

        # Sort files by filename or mtime
        run_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

        for rf in run_files:
            run = self.parser.parse_file(rf, is_active=False)
            if not run:
                continue

            total_runs += 1
            char = run["character"]
            is_win = run["win"]
            if is_win:
                total_wins += 1

            # Character stats
            if char not in character_stats:
                character_stats[char] = {
                    "character": char,
                    "runs": 0,
                    "wins": 0,
                    "win_rate": 0.0,
                    "highest_ascension": 0,
                    "avg_floor": 0.0,
                    "total_floors": 0,
                }
            cs = character_stats[char]
            cs["runs"] += 1
            if is_win:
                cs["wins"] += 1
            cs["highest_ascension"] = max(cs["highest_ascension"], run["ascension"])
            cs["total_floors"] += run["current_floor"]

            # Death encounters
            if not is_win and run["killed_by"] and run["killed_by"] != "NONE":
                death_encounters[run["killed_by"]] = death_encounters.get(run["killed_by"], 0) + 1

            # Cards in final deck
            deck_card_ids = set(c["id"] for c in run["deck"])
            for cid in deck_card_ids:
                if cid not in card_stats:
                    cinfo = self.parser.get_card_info(cid)
                    card_stats[cid] = {
                        "id": cid,
                        "name": cinfo["name"],
                        "character": cinfo["character"],
                        "card_type": cinfo.get("card_type", "Skill"),
                        "offered_count": 0,
                        "picked_count": 0,
                        "drafted_runs": 0,
                        "won_with_count": 0,
                    }
                card_stats[cid]["drafted_runs"] += 1
                if is_win:
                    card_stats[cid]["won_with_count"] += 1

            # Card choices offered and picked
            for choice_event in run["card_reward_history"]:
                for opt in choice_event.get("options", []):
                    cid = opt["id"]
                    if cid not in card_stats:
                        card_stats[cid] = {
                            "id": cid,
                            "name": opt["name"],
                            "character": opt.get("character", "unknown"),
                            "card_type": opt.get("card_type", "Skill"),
                            "offered_count": 0,
                            "picked_count": 0,
                            "drafted_runs": 0,
                            "won_with_count": 0,
                        }
                    card_stats[cid]["offered_count"] += 1
                    if opt.get("was_picked"):
                        card_stats[cid]["picked_count"] += 1

            # Store recent run summaries
            if len(recent_runs) < 20:
                recent_runs.append({
                    "file": os.path.basename(rf),
                    "character": char,
                    "ascension": run["ascension"],
                    "floor": run["current_floor"],
                    "win": is_win,
                    "killed_by": run["killed_by"],
                    "deck_size": run["deck_size"],
                    "relics": [r["name"] for r in run["relics"]],
                    "timestamp": run["start_time"],
                })

        # Calculate percentages
        for char, cs in character_stats.items():
            if cs["runs"] > 0:
                cs["win_rate"] = round((cs["wins"] / cs["runs"]) * 100, 1)
                cs["avg_floor"] = round(cs["total_floors"] / cs["runs"], 1)

        for cid, cs in card_stats.items():
            offered = cs["offered_count"]
            picked = cs["picked_count"]
            drafted = cs["drafted_runs"]
            won = cs["won_with_count"]

            cs["pick_rate"] = round((picked / offered * 100), 1) if offered > 0 else 0.0
            cs["win_rate"] = round((won / drafted * 100), 1) if drafted > 0 else 0.0

        overall_win_rate = round((total_wins / total_runs * 100), 1) if total_runs > 0 else 0.0

        stats = {
            "total_runs": total_runs,
            "total_wins": total_wins,
            "overall_win_rate": overall_win_rate,
            "characters": character_stats,
            "card_stats": card_stats,
            "top_lethal_encounters": sorted(death_encounters.items(), key=lambda x: x[1], reverse=True)[:10],
            "recent_runs": recent_runs,
        }

        with open(self.stats_cache_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

        print(f"Player history mining complete! Total runs: {total_runs}, Win rate: {overall_win_rate}%")
        return stats

    def get_card_personal_stats(self, card_id: str) -> Optional[Dict[str, Any]]:
        """Returns personal pick rate and win rate for a given card ID."""
        stats = self.mine_all(force_refresh=False)
        return stats.get("card_stats", {}).get(card_id)
