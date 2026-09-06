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


def _get_linux_steam_libraries() -> List[str]:
    """Finds all Steam library directories from libraryfolders.vdf on Linux/SteamOS."""
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

    # Also check /run/media mounts (SD cards on Steam Deck)
    sd_mounts = glob.glob("/run/media/**/steamapps", recursive=True)
    for s in sd_mounts:
        parent = os.path.dirname(s)
        if parent not in libraries:
            libraries.append(parent)

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
        # Linux / Steam Deck
        for lib in _get_linux_steam_libraries():
            candidates.append(os.path.join(lib, "steamapps/common/Slay the Spire 2"))

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
    potential_candidates: List[str] = []

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            base = os.path.join(appdata, "SlayTheSpire2", "steam")
            matches = glob.glob(os.path.join(base, "*", "profile1", "saves"))
            existing_candidates.extend(matches)
            potential_candidates.append(os.path.join(base, "profile1", "saves"))
    else:
        # Linux / Steam Deck Proton prefix
        for lib in _get_linux_steam_libraries():
            pattern = os.path.join(
                lib,
                f"steamapps/compatdata/{STS2_STEAM_APPID}/pfx/drive_c/users/*/AppData/Roaming/SlayTheSpire2/steam/*/profile1/saves"
            )
            matches = glob.glob(pattern)
            existing_candidates.extend(matches)

            potential_candidates.append(os.path.join(
                lib,
                f"steamapps/compatdata/{STS2_STEAM_APPID}/pfx/drive_c/users/steamuser/AppData/Roaming/SlayTheSpire2/steam/76561199820060807/profile1/saves"
            ))

        # Check native Linux directory as secondary
        home = os.path.expanduser("~")
        native_dir = os.path.join(home, ".config/SlayTheSpire2/profile1/saves")
        if os.path.exists(native_dir):
            existing_candidates.append(native_dir)
        else:
            potential_candidates.append(native_dir)

    # Return existing directory if found on disk
    for path in existing_candidates:
        if os.path.exists(path):
            return path

    # Otherwise return most probable candidate
    return potential_candidates[0] if potential_candidates else None
