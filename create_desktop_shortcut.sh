#!/usr/bin/env bash
# =======================================================================
# Creates One-Touch Desktop Icon and Steam Application Entry for Steam Deck
# =======================================================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
DESKTOP_DIR="$HOME/Desktop"
APPS_DIR="$HOME/.local/share/applications"

mkdir -p "$DESKTOP_DIR"
mkdir -p "$APPS_DIR"

# 1. Desktop Icon (Interactive in Konsole on double-tap)
DESKTOP_FILE="$DESKTOP_DIR/STS2 Companion.desktop"
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Name=STS2 Companion
Comment=Slay the Spire 2 Live Card Advisor & HUD
Exec=konsole --noclose -e bash -c "cd '$SCRIPT_DIR' && bash steamdeck_setup.sh"
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Game;Utility;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

# 2. System Application Menu Entry (allows right-click -> 'Add to Steam')
APP_FILE="$APPS_DIR/sts2_companion.desktop"
cp "$DESKTOP_FILE" "$APP_FILE"
chmod +x "$APP_FILE"

# 3. Background Autostart Runner script
BACKGROUND_RUNNERN_SCRIPT="$SCRIPT_DIR/steamdeck_background.sh"
cat <<EOF > "$BACKGROUND_RUNNERN_SCRIPT"
#!/usr/bin/env bash
cd '$SCRIPT_DIR'
git pull origin main --quiet 2>/dev/null || true
pkill -f "run.py" 2>/dev/null || true
fuser -k 5050/tcp 2>/dev/null || true
sleep 0.3
PYTHONUNBUFFERED=1 nohup python3 -u run.py --network --no-browser > /tmp/sts2_companion.log 2>&1 &
EOF
chmod +x "$BACKGROUND_RUNNERN_SCRIPT"

echo "================================================="
echo "  [+] STS2 Companion Shortcut Created!"
echo "================================================="
echo "1. Icon added to your Desktop: 'STS2 Companion'"
echo "   -> Double-tap it on the touchscreen to launch!"
echo "2. App added to Applications Menu"
echo "   -> In Steam, you can click: Games -> Add a Non-Steam Game -> STS2 Companion"
echo "================================================="
