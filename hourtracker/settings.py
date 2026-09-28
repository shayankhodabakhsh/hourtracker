"""Settings stored as a small JSON file, with safe defaults."""
import json
import logging
import os

log = logging.getLogger(__name__)

DEFAULTS = {
    "pill_pos": None,            # [x, y] in logical pixels; None = default spot
    "balloon_pos": None,
    "balloon_color": "matte_black",
    "balloon_visible": True,
    "nudge_enabled": True,       # buzz when the timer looks forgotten
    "nudge_minutes": 3,
    "away_minutes": 15,
    "week_start": "auto",        # "auto", "sunday", or "monday"
}


def _valid(key, value) -> bool:
    if key.endswith("_pos"):
        return value is None or (isinstance(value, list) and len(value) == 2
                                 and all(type(v) in (int, float) for v in value))
    if key.endswith("_minutes"):
        return type(value) is int and value >= 1
    return type(value) is type(DEFAULTS[key])


class Settings:
    def __init__(self, path: str):
        self.path = path
        self._data = dict(DEFAULTS)
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, ValueError):
            loaded = {}
        if isinstance(loaded, dict):
            self._data.update({key: value for key, value in loaded.items()
                               if key in DEFAULTS and _valid(key, value)})

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value
        self._save()

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            log.exception("could not save settings")
