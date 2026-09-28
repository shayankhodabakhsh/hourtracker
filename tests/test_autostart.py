import os
import tempfile
import unittest
from unittest import mock

from hourtracker import autostart

LAUNCHER = "/opt/hours/hour-tracker"


class AutostartTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_enable_writes_an_entry_that_runs_the_launcher(self):
        autostart.set_enabled(True, LAUNCHER)
        self.assertTrue(autostart.is_enabled())
        with open(autostart.entry_path(), encoding="utf-8") as f:
            self.assertIn(f'Exec="{LAUNCHER}"', f.read())

    def test_disable_removes_the_entry(self):
        autostart.set_enabled(True, LAUNCHER)
        autostart.set_enabled(False, LAUNCHER)
        self.assertFalse(autostart.is_enabled())

    def test_disable_when_already_off_is_fine(self):
        autostart.set_enabled(False, LAUNCHER)
        self.assertFalse(autostart.is_enabled())
