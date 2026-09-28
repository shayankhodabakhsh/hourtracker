#!/bin/sh
# Adds Hour Tracker to the app grid. Use --uninstall to remove it again
# (your study history in ~/.local/share/hour-tracker is kept).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ENTRY="$APPS/hour-tracker.desktop"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/hour-tracker.desktop"

if [ "$1" = "--uninstall" ]; then
    rm -f "$ENTRY" "$AUTOSTART"
    echo "Removed Hour Tracker from the app grid."
    exit 0
fi

if ! /usr/bin/python3 -c "import gi; gi.require_foreign('cairo')" 2>/dev/null; then
    echo "Hour Tracker needs one more package. Install it with:"
    echo "    sudo apt install python3-gi-cairo"
    exit 1
fi

mkdir -p "$APPS"
cat > "$ENTRY" <<EOF
[Desktop Entry]
Type=Application
Name=Hour Tracker
Comment=Track your study hours, with a balloon to fidget with
Exec="$HERE/hour-tracker"
Icon=$HERE/data/hour-tracker.svg
Terminal=false
Categories=Education;
StartupWMClass=hour-tracker
EOF
echo "Installed. Open Hour Tracker from the app grid."
