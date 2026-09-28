"""Start at login, through an XDG autostart entry."""
import os

ENTRY = """[Desktop Entry]
Type=Application
Name=Hour Tracker
Exec="{launcher}"
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
"""


def entry_path() -> str:
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(config, "autostart", "hour-tracker.desktop")


def is_enabled() -> bool:
    return os.path.exists(entry_path())


def set_enabled(enabled: bool, launcher: str) -> None:
    path = entry_path()
    if enabled:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(ENTRY.format(launcher=launcher))
    elif os.path.exists(path):
        os.remove(path)
