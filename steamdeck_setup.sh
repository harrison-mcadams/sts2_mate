#!/usr/bin/env bash
# ==============================================================================
# Slay the Spire 2 Companion App (sts2_mate) - Steam Deck Setup Script
# ==============================================================================

set -e

echo "=================================================="
echo "  STS2 Mate - Steam Deck Setup & Runner"
echo "=================================================="

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "[!] Error: python3 could not be found. Please ensure Python is installed."
    exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Install minimal requirement (Flask) in user space if not already installed
if ! python3 -c "import flask" &> /dev/null; then
    echo "[*] Installing Flask..."
    python3 -m pip install --user flask
fi

echo "[*] Launching Companion Server on local network..."
echo "[*] You can access the HUD from your phone, tablet, or Steam Deck browser."
echo ""

# Run with --network so you can open on phone/tablet on same Wi-Fi
python3 run.py --network --no-browser
