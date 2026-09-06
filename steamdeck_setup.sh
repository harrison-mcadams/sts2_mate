#!/usr/bin/env bash
# ==============================================================================
# Slay the Spire 2 Companion App (sts2_mate) - Steam Deck Launcher
# ==============================================================================

set -e

echo "=================================================="
echo "  STS2 Mate - Steam Deck Runner"
echo "=================================================="

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "[!] Error: python3 could not be found."
    exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "[*] Launching Companion Server on local network..."
echo "[*] (Zero dependencies required - running with pure Python standard library)"
echo ""

# Run with --network so you can open on phone/tablet on same Wi-Fi
python3 run.py --network --no-browser
