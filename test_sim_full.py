import sys
import os

# Simulate linux
sys.platform = 'linux'

from sts2_companion.core.paths import get_default_game_dir, get_default_save_dir
print("Testing save dir resolution...")
sdir = get_default_save_dir()
print("Resolved save dir:", sdir)

from sts2_companion.core.watcher import STS2LiveWatcher
watcher = STS2LiveWatcher(profile_dir=sdir)
state = watcher.get_state()
print("Initial state game_status:", state.get("game_status"))

from sts2_companion.web.standalone import run_standalone_server
print("All modules imported and initialized successfully!")
