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
    """Finds Steam library directories on Linux/SteamOS without slow recursive disk crawling."""
    home = os.path.expanduser("~")
    vdf_candidates = [
        os.path.join(home, ".local/share/Steam/steamapps/libraryfolders.vdf"),
        os.path.join(home, ".steam/steam/steamapps/libraryfolders.vdf"),
        os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/libraryfolders.vdf"),
    ]

    libraries = [
        os.path.join(home, ".local/share/Steam"),
        os.path.join(home, ".steam/steam"),
    ]

    # Fast VDF parser
    for vdf in vdf_candidates:
        if os.path.exists(vdf):
            try:
                with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                matches = re.findall(r'"path"\s+"([^"]+)"', content)
                for m in matches:
                    if m not in libraries and os.path.isdir(m):
                        libraries.append(m)
            except Exception:
                pass

    # Fast check of standard Steam Deck SD card mount points
    if os.path.exists("/run/media"):
        for sub in ["/run/media", "/run/media/deck"]:
            if os.path.exists(sub):
                try:
                    for d in os.listdir(sub):
                        full = os.path.join(sub, d)
                        if os.path.isdir(full) and os.path.exists(os.path.join(full, "steamapps")):
                            if full not in libraries:
                                libraries.append(full)
                except Exception:
                    pass

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

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            base = os.path.join(appdata, "SlayTheSpire2", "steam")
            matches = glob.glob(os.path.join(base, "*", "profile1", "saves"))
            if matches:
                return matches[0]
            return os.path.join(base, "profile1", "saves")
    else:
        home = os.path.expanduser("~")

        # 1. Native Linux build: ~/.local/share/SlayTheSpire2/steam/<account_id>/profile1/saves
        native_base = os.path.join(home, ".local/share/SlayTheSpire2/steam")
        if os.path.exists(native_base):
            matches = glob.glob(os.path.join(native_base, "*", "profile*", "saves"))
            if matches:
                for m in matches:
                    if os.path.exists(os.path.join(m, "current_run.save")) or os.path.exists(os.path.join(m, "progress.save")):
                        return m
                return matches[0]

        # 2. Steam Cloud Userdata: ~/.local/share/Steam/userdata/<account_id>/2868840/remote/profile1/saves
        for ubase in [os.path.join(home, ".local/share/Steam/userdata"), os.path.join(home, ".steam/steam/userdata")]:
            if os.path.exists(ubase):
                matches = glob.glob(os.path.join(ubase, "*", STS2_STEAM_APPID, "remote", "profile*", "saves"))
                if matches:
                    for m in matches:
                        if os.path.exists(os.path.join(m, "current_run.save")) or os.path.exists(os.path.join(m, "progress.save")):
                            return m
                    return matches[0]

        # 3. Proton Wine prefix (if running Windows build through Proton)
        for lib in _get_linux_steam_libraries():
            sts2_compat = os.path.join(lib, f"steamapps/compatdata/{STS2_STEAM_APPID}/pfx/drive_c")
            if os.path.exists(sts2_compat):
                resolved = _resolve_case_insensitive(
                    sts2_compat,
                    ["users", "*", "appdata", "roaming", "slaythespire2", "steam", "*", "profile*", "saves"]
                )
                for r in resolved:
                    if os.path.exists(r):
                        return r

        # Fallback default: native path
        return os.path.join(home, ".local/share/SlayTheSpire2/steam/76561199820060807/profile1/saves")
