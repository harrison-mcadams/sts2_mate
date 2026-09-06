"""
Live Run Watcher for Slay the Spire 2.
Watches profile1/saves/current_run.save and history/*.run in the background
and provides real-time state updates to the companion UI.
"""

import glob
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from .save_parser import STS2SaveParser
from .paths import get_default_save_dir

DEFAULT_PROFILE_DIR = get_default_save_dir() or r"C:\Users\harri\AppData\Roaming\SlayTheSpire2\steam\76561199820060807\profile1\saves"


class STS2LiveWatcher:
    def __init__(self, profile_dir: Optional[str] = None, data_dir: str = "data", poll_interval: float = 1.0):
        self.profile_dir = profile_dir or get_default_save_dir() or DEFAULT_PROFILE_DIR
        self.data_dir = data_dir
        self.poll_interval = poll_interval
        self.parser = STS2SaveParser(data_dir=data_dir)

        self.current_save_path = os.path.join(self.profile_dir, "current_run.save")
        self.history_dir = os.path.join(self.profile_dir, "history")

        self.latest_state: Dict[str, Any] = {}
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []

        self._last_active_mtime: float = 0.0
        self._last_history_mtime: float = 0.0
        self._last_path_scan_time: float = 0.0

        # Perform initial state load
        self.check_updates(force=True)

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribes a listener to receive state updates."""
        self._subscribers.append(callback)

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            if self.latest_state:
                return dict(self.latest_state)

            has_profile = os.path.exists(os.path.join(self.profile_dir, "progress.save")) or os.path.exists(os.path.join(self.profile_dir, "prefs.save"))
            game_status = "MAIN_MENU" if has_profile else "WAITING_FOR_GAME"

            return {
                "is_active": False,
                "waiting_for_game": not has_profile,
                "game_status": game_status,
                "character": "Ironclad",
                "ascension": 0,
                "current_floor": 0,
                "current_act": 1,
                "current_hp": 80,
                "max_hp": 80,
                "hp_percent": 100.0,
                "gold": 99,
                "deck": [],
                "deck_size": 0,
                "deck_breakdown": {},
                "relics": [],
                "relic_count": 0,
                "potions": [],
                "card_reward_history": [],
                "recent_rooms": [],
                "monitored_path": self.profile_dir,
            }

    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        print(f"STS2 Live Watcher started. Monitoring {self.profile_dir}", flush=True)

    def stop(self) -> None:
        self.is_running = False

    def _watch_loop(self) -> None:
        while self.is_running:
            try:
                self.check_updates()
            except Exception as e:
                print(f"Error checking STS2 save updates: {e}", flush=True)
            time.sleep(self.poll_interval)

    def check_updates(self, force: bool = False) -> bool:
        """Checks if current_run.save or recent history files have changed."""
        now = time.time()

        # Check for current_run.save in monitored profile and any sibling profiles
        active_save_file: Optional[str] = None
        if os.path.exists(self.current_save_path):
            active_save_file = self.current_save_path
        else:
            # Check sibling profiles (e.g. profile2, profile3)
            parent_steam = os.path.dirname(os.path.normpath(self.profile_dir))
            if os.path.exists(parent_steam):
                for p_saves in glob.glob(os.path.join(parent_steam, "profile*", "saves")):
                    cand = os.path.join(p_saves, "current_run.save")
                    if os.path.exists(cand):
                        active_save_file = cand
                        self.profile_dir = p_saves
                        self.current_save_path = cand
                        self.history_dir = os.path.join(p_saves, "history")
                        break

        has_active = active_save_file is not None
        changed = False

        if has_active and active_save_file:
            try:
                mtime = os.path.getmtime(active_save_file)
                if force or mtime > self._last_active_mtime:
                    parsed = self.parser.parse_file(active_save_file, is_active=True)
                    if parsed:
                        self._last_active_mtime = mtime
                        parsed["game_status"] = "RUN_ACTIVE"
                        parsed["monitored_path"] = self.profile_dir
                        with self._lock:
                            self.latest_state = parsed
                        changed = True
                        print(f"\n[+] >>> LIVE RUN ACTIVE! Floor {parsed.get('current_floor', 1)} | HP: {parsed.get('current_hp')}/{parsed.get('max_hp')} | {parsed.get('character', 'Hero')} <<<", flush=True)
            except Exception as e:
                print(f"Error reading active run: {e}", flush=True)
        else:
            # Not currently in an active run; show latest completed run from history if available
            if force or self._last_active_mtime != 0.0:
                if self._last_active_mtime != 0.0:
                    print("\n[i] Run ended or returned to Main Menu.", flush=True)
                self._last_active_mtime = 0.0
                changed = True

            # Find latest run file in history
            run_files = glob.glob(os.path.join(self.history_dir, "*.run")) if os.path.exists(self.history_dir) else []
            if run_files:
                latest_rf = max(run_files, key=os.path.getmtime)
                mtime = os.path.getmtime(latest_rf)
                if force or mtime > self._last_history_mtime:
                    self._last_history_mtime = mtime
                    parsed = self.parser.parse_file(latest_rf, is_active=False)
                    if parsed:
                        parsed["game_status"] = "IDLE_LATEST_RUN"
                        parsed["monitored_path"] = self.profile_dir
                        with self._lock:
                            self.latest_state = parsed
                        changed = True
            else:
                # No run files in history
                if force:
                    with self._lock:
                        self.latest_state = self.get_state()
                    changed = True

        if changed:
            state = self.get_state()
            for cb in list(self._subscribers):
                try:
                    cb(state)
                except Exception:
                    pass

        return changed
