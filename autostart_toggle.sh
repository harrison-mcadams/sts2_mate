#!/usr/bin/env bash
set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/sts2_companion.desktop"

mkdir -p "$AUTOSTART_DIR"

if [ "d1" == "--disable" ]; then
    rm -f "$AUTOSTART_FILE"
    echo "[+] STS2 Companion auto-start DISABLED."
    exit 0
fi

cat <<EOF > "$AUTOSTART_FILE"
[Desktop Entry]
Name=STS2 Companion Background Service
Comment=Silently runs STS2 Companion Server in background for handheld play
Exec=bash -c "cd '$SCRIPT_DIR' && bash steamdeck_background.sh"
Terminal=false
Type=Application
Categories=Game;Utility;
XOGOUT-AUTOSTART=true
EOF

chmod +x "$AUTOSTART_FILE"
echo "[+] STS2 Companion auto-start ENABLED!"
echo "   The companion server will now start automatically when you boot your Steam Deck."
echo "   To disable: bash autostart_toggle.sh --disable"
