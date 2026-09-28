import json
import os
import tempfile
import unittest

from hourtracker.settings import DEFAULTS, Settings


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "config", "settings.json")

    def write(self, text):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_missing_file_gives_defaults(self):
        self.assertEqual(Settings(self.path)["balloon_color"], DEFAULTS["balloon_color"])

    def test_corrupt_file_gives_defaults(self):
        self.write("{not json")
        self.assertEqual(Settings(self.path)["away_minutes"], 15)

    def test_values_are_saved_and_reloaded(self):
        Settings(self.path)["pill_pos"] = [120, 40]
        self.assertEqual(Settings(self.path)["pill_pos"], [120, 40])

    def test_wrong_types_and_unknown_keys_are_ignored(self):
        self.write(json.dumps({"away_minutes": "soon", "balloon_pos": [1],
                               "mystery": 1, "balloon_visible": False}))
        settings = Settings(self.path)
        self.assertEqual(settings["away_minutes"], 15)
        self.assertIsNone(settings["balloon_pos"])
        self.assertFalse(settings["balloon_visible"])
        with self.assertRaises(KeyError):
            settings["mystery"]

    def test_minutes_must_be_at_least_one(self):
        self.write(json.dumps({"away_minutes": 0, "nudge_minutes": -2}))
        settings = Settings(self.path)
        self.assertEqual(settings["away_minutes"], 15)
        self.assertEqual(settings["nudge_minutes"], 3)
