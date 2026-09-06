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

# Auto-update from git repository if connected
git pull origin main --quiet 2>/dev/null || true

# Auto-create Desktop icon if not already present
if [ ! -f "$HOME/Desktop/STS2 Companion.desktop" ]; then
    bash "$SCRIPT_DIR/create_desktop_shortcut.sh" > /dev/null 2>&1 || true
fi

echo "[*] Launching Companion Server on local network..."
echo "[*] (Zero dependencies required - running with pure Python standard library)"
echo ""

# Clean up any previous server instances and ensure port 5050 is free
pkill -f "run.py" 2>/dev/null || true
fuser -k 5050/tcp 2>/dev/null || true
fuser -k 5051/tcp 2>/dev/null || true
sleep 0.3

# Ensure SteamOS firewall doesn't block port 5050 (non-interactive sudo if permitted)
if command -v iptables &> /dev/null; then
    sudo -n iptables -I INPUT -p tcp --dport 5050 -j ACCEPT 2>/dev/null || true
fi

# Run with PYTHONUNBUFFERED=1 and -u so all logs print to Konsole in real time
PYTHONUNBUFFERED=1 python3 -u run.py --network --no-browser
