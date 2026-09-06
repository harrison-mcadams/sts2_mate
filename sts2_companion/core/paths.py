"""
Cross-platform path discovery for Slay the Spire 2 on Windows, Steam Deck (SteamOS/Linux), and macOS.
AppID: 2868840
"""

import glob
import os
import sys
from typing import List, Optional

STS2_STEAM_APPID = "2868840"


def get_default_game_dir() -> Optional[str]:
    """Finds the Slay the Spire 2 game installation directory."""
    # Check environment variable first
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
        # Linux / Steam Deck / SteamOS
        home = os.path.expanduser("~")
        candidates.extend([
            os.path.join(home, ".local/share/Steam/steamapps/common/Slay the Spire 2"),
            os.path.join(home, ".steam/steam/steamapps/common/Slay the Spire 2"),
            os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Slay the Spire 2"),
        ])
        # Check SD card mounts on Steam Deck
        sd_cards = glob.glob("/run/media/*/steamapps/common/Slay the Spire 2")
        candidates.extend(sd_cards)

    for path in candidates:
        if os.path.exists(path) and (
            os.path.exists(os.path.join(path, "SlayTheSpire2.pck")) or
            os.path.exists(os.path.join(path, "sts2.dll"))
        ):
            return path

    return candidates[0] if candidates else None


def get_default_save_dir() -> Optional[str]:
    """Finds the Slay the Spire 2 active/history saves directory (profile1/saves)."""
    # Check environment variable first
    if "STS2_SAVE_DIR" in os.environ and os.path.exists(os.environ["STS2_SAVE_DIR"]):
        return os.environ["STS2_SAVE_DIR"]

    candidates: List[str] = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            base = os.path.join(appdata, "SlayTheSpire2", "steam")
            matches = glob.glob(os.path.join(base, "*", "profile1", "saves"))
            candidates.extend(matches)
            candidates.append(os.path.join(base, "profile1", "saves"))
    else:
        # Linux / Steam Deck Proton prefix
        home = os.path.expanduser("~")
        proton_patterns = [
            os.path.join(home, f".local/share/Steam/steamapps/compatdata/{STS2_STEAM_APPID}/pfx/drive_c/users/steamuser/AppData/Roaming/SlayTheSpire2/steam/*/profile1/saves"),
            os.path.join(home, f".steam/steam/steamapps/compatdata/{STS2_STEAM_APPID}/pfx/drive_c/users/steamuser/AppData/Roaming/SlayTheSpire2/steam/*/profile1/saves"),
            os.path.join(home, f".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata/{STS2_STEAM_APPID}/pfx/drive_c/users/steamuser/AppData/Roaming/SlayTheSpire2/steam/*/profile1/saves"),
        ]
        for pat in proton_patterns:
            matches = glob.glob(pat)
            candidates.extend(matches)

        # Check SD card compatdata mounts on Steam Deck
        sd_proton = glob.glob(f"/run/media/*/steamapps/compatdata/{STS2_STEAM_APPID}/pfx/drive_c/users/steamuser/AppData/Roaming/SlayTheSpire2/steam/*/profile1/saves")
        candidates.extend(sd_proton)

        # Check native Linux paths if any
        candidates.append(os.path.join(home, ".config/SlayTheSpire2/profile1/saves"))

    for path in candidates:
        if os.path.exists(path):
            return path

    return candidates[0] if candidates else None
