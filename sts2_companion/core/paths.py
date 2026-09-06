"""
Cross-platform path discovery for Slay the Spire 2 on Windows, Steam Deck (SteamOS/Linux), and macOS.
AppID: 2868840
"""

import glob
import os
import re
import sys
from typing import List, Optional

STS2_STEAM_APPID = "2868840"


def _resolve_case_insensitive(base: str, parts: List[str]) -> List[str]:
    """Walks directory parts matching case-insensitively, supporting '*' wildcard."""
    if not os.path.exists(base):
        return []
    current_dirs = [base]
    for part in parts:
        next_dirs = []
        for cdir in current_dirs:
            if not os.path.isdir(cdir):
                continue
            try:
                entries = os.listdir(cdir)
            except Exception:
                continue
            if part == "*":
                for e in entries:
                    full = os.path.join(cdir, e)
                    if os.path.isdir(full):
                        next_dirs.append(full)
            else:
                p_lower = part.lower()
                for e in entries:
                    if e.lower() == p_lower:
                        full = os.path.join(cdir, e)
                        if os.path.isdir(full):
                            next_dirs.append(full)
        current_dirs = next_dirs
        if not current_dirs:
            break
    return current_dirs


def _get_linux_steam_libraries() -> List[str]:
    """Finds all Steam library directories on Linux/SteamOS."""
    home = os.path.expanduser("~")
    vdf_candidates = [
        os.path.join(home, ".local/share/Steam/steamapps/libraryfolders.vdf"),
        os.path.join(home, ".steam/steam/steamapps/libraryfolders.vdf"),
        os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/libraryfolders.vdf"),
    ]

    libraries = [
        os.path.join(home, ".local/share/Steam"),
        os.path.join(home, ".steam/steam"),
        os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam"),
    ]

    for vdf in vdf_candidates:
        if os.path.exists(vdf):
            try:
                with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                matches = re.findall(r'"path"\s+"([^"]+)"', content)
                for m in matches:
                    if m not in libraries:
                        libraries.append(m)
            except Exception:
                pass

    # Check SD card mounts on Steam Deck
    for sd in glob.glob("/run/media/**/steamapps", recursive=True):
        p = os.path.dirname(sd)
        if p not in libraries:
            libraries.append(p)

    return libraries


def get_default_game_dir() -> Optional[str]:
    """Finds the Slay the Spire 2 game installation directory."""
    if "STS2_GAME_DIR" in os.environ and os.path.exists(os.environ["STS2_GAME_DIR"]):
        return os.environ["STS2_GAME_DIR"]

    candidates = []
    if sys.platform == "win32":
        candidates.extend([
            r"C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2",
            r"C:\Steam\steamapps\common\Slay the Spire 2",
            r"D:\Steam\steamapps\common\Slay the Spire 2",
            r"D:\SteamLibrary\steamapps\common\Slay the Spire 2",
            r"E:\SteamLibrary\steamapps\common\Slay the Spire 2",
        ])
    else:
        for lib in _get_linux_steam_libraries():
            common_dir = os.path.join(lib, "steamapps/common")
            if os.path.exists(common_dir):
                resolved = _resolve_case_insensitive(common_dir, ["slay the spire 2"])
                candidates.extend(resolved)

    for path in candidates:
        if os.path.exists(path) and (
            os.path.exists(os.path.join(path, "SlayTheSpire2.pck")) or
            os.path.exists(os.path.join(path, "sts2.dll"))
        ):
            return path

    return candidates[0] if candidates else None


def get_default_save_dir() -> Optional[str]:
    """Finds the Slay the Spire 2 active/history saves directory (profile1/saves)."""
    if "STS2_SAVE_DIR" in os.environ and os.path.exists(os.environ["STS2_SAVE_DIR"]):
        return os.environ["STS2_SAVE_DIR"]

    existing_candidates: List[str] = []

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            base = os.path.join(appdata, "SlayTheSpire2", "steam")
            matches = glob.glob(os.path.join(base, "*", "profile1", "saves"))
            existing_candidates.extend(matches)
    else:
        # Linux / Steam Deck Proton prefix
        # Check standard Proton prefix for AppID 2868840
        for lib in _get_linux_steam_libraries():
            compat_dir = os.path.join(lib, "steamapps/compatdata")
            if not os.path.exists(compat_dir):
                continue

            # Check 2868840 specifically first
            sts2_compat = os.path.join(compat_dir, STS2_STEAM_APPID)
            if os.path.exists(sts2_compat):
                drive_c = os.path.join(sts2_compat, "pfx/drive_c")
                resolved = _resolve_case_insensitive(drive_c, ["users", "*", "appdata", "roaming", "slaythespire2", "steam", "*", "profile1", "saves"])
                existing_candidates.extend(resolved)

            # Also check any other folder in compatdata that might be STS2 (e.g. non-steam or custom)
            for sub in os.listdir(compat_dir):
                if sub == STS2_STEAM_APPID:
                    continue
                pfx_c = os.path.join(compat_dir, sub, "pfx/drive_c")
                if os.path.exists(pfx_c):
                    resolved = _resolve_case_insensitive(pfx_c, ["users", "*", "appdata", "roaming", "slaythespire2", "steam", "*", "profile1", "saves"])
                    existing_candidates.extend(resolved)

        # Check native Linux directory as fallback
        home = os.path.expanduser("~")
        native_dir = os.path.join(home, ".config/SlayTheSpire2/profile1/saves")
        if os.path.exists(native_dir):
            existing_candidates.append(native_dir)

    # Prioritize directories that actually have save files in them
    for path in existing_candidates:
        if os.path.exists(path):
            if os.path.exists(os.path.join(path, "current_run.save")) or os.path.exists(os.path.join(path, "progress.save")):
                return path

    if existing_candidates:
        return existing_candidates[0]

    # Fallback to standard Steam Deck Proton path if none exist yet
    home = os.path.expanduser("~")
    return os.path.join(
        home,
        f".local/share/Steam/steamapps/compatdata/{STS2_STEAM_APPID}/pfx/drive_c/users/steamuser/AppData/Roaming/SlayTheSpire2/steam/76561199820060807/profile1/saves"
    )
