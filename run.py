"""
Slay the Spire 2 Companion App (sts2_mate) Entrypoint.
"""

import argparse
import os
import socket
import sys
import webbrowser
from sts2_companion.core.extractor import STS2Extractor
from sts2_companion.core.miner import STS2HistoryMiner
from sts2_companion.core.paths import get_default_game_dir, get_default_save_dir

try:
    from sts2_companion.web.app import create_app
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

from sts2_companion.web.standalone import run_standalone_server


def get_local_ip() -> str:
    """Finds the machine's local LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def main():
    parser = argparse.ArgumentParser(description="STS2 Mate - Slay the Spire 2 Companion App")
    parser.add_argument("--port", type=int, default=5050, help="Web companion server port (default: 5050)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--network", action="store_true", help="Bind to 0.0.0.0 (access from phone/tablet on same Wi-Fi, great for Steam Deck)")
    parser.add_argument("--save-dir", type=str, default=None, help="Custom path to profile1/saves directory")
    parser.add_argument("--game-dir", type=str, default=None, help="Custom path to Slay the Spire 2 game installation")
    parser.add_argument("--sync-game", action="store_true", help="Force re-extract cards & relics from STS2 files")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    if args.network:
        args.host = "0.0.0.0"

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    cards_file = os.path.join(data_dir, "sts2_cards.json")
    effective_save_dir = args.save_dir or get_default_save_dir()
    effective_game_dir = args.game_dir or get_default_game_dir()

    print("\n" + "=" * 60, flush=True)
    print("        [+] SLAY THE SPIRE 2 COMPANION APP (sts2_mate)", flush=True)
    print("=" * 60, flush=True)

    # 1. Sync / Extract STS2 Game Data if needed
    if args.sync_game or not os.path.exists(cards_file):
        print("\n[1/3] Initializing / Re-syncing in-house STS2 Game Database...")
        try:
            pck_path = os.path.join(effective_game_dir, "SlayTheSpire2.pck") if effective_game_dir else None
            extractor = STS2Extractor(pck_path=pck_path) if pck_path else STS2Extractor()
            extractor.extract_all(output_dir=data_dir)
        except Exception as e:
            print(f"[!] Warning: Failed to extract game data: {e}")
            if not os.path.exists(cards_file):
                print("[!] Error: No cached database found. Exiting.")
                sys.exit(1)
    else:
        print("\n[1/3] In-house STS2 Game Database verified.")

    # 2. Mine Player History Runs
    print("[2/3] Checking player history runs & win rate statistics...")
    history_dir = os.path.join(effective_save_dir, "history") if effective_save_dir else None
    miner = STS2HistoryMiner(history_dir=history_dir, data_dir=data_dir) if history_dir else STS2HistoryMiner(data_dir=data_dir)
    stats = miner.mine_all(force_refresh=False)
    print(f"      Mined {stats.get('total_runs', 0)} completed runs. Overall win rate: {stats.get('overall_win_rate', 0)}%")

    # 3. Create Web Application
    print("[3/3] Starting Live Watcher and Companion Server...")
    local_ip = get_local_ip()
    local_url = f"http://127.0.0.1:{args.port}"
    lan_url = f"http://{local_ip}:{args.port}"

    print(f"\nCompanion HUD is active:")
    print(f"   -> Local URL:   {local_url}")
    if args.host == "0.0.0.0":
        print(f"   -> Network URL: {lan_url} (Open this on your phone/tablet!)")
    print(f"   - Monitoring Saves: {effective_save_dir}")
    print("   Press Ctrl+C to stop.\n" + "=" * 60 + "\n")

    if not args.no_browser and args.host != "0.0.0.0":
        webbrowser.open(local_url)

    if HAS_FLASK:
        app = create_app(data_dir=data_dir, save_dir=effective_save_dir)
        app.run(host=args.host, port=args.port, debug=False)
    else:
        print("[*] Running with pure Python built-in server (zero external dependencies required).")
        run_standalone_server(host=args.host, port=args.port, data_dir=data_dir, save_dir=effective_save_dir)


if __name__ == "__main__":
    main()
