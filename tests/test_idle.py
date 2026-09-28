import os
import unittest

from gi.repository import GLib

from hourtracker.idle import IdleMonitor


class FailingProxy:
    def call_sync(self, *args):
        raise GLib.Error("no idle monitor here")


class IdleMonitorTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("DBUS_SESSION_BUS_ADDRESS"), "needs a desktop session")
    def test_reads_idle_seconds_from_gnome(self):
        seconds = IdleMonitor()()
        self.assertIsInstance(seconds, float)
        self.assertGreaterEqual(seconds, 0.0)

    def test_errors_give_none_and_warn_once(self):
        monitor = IdleMonitor(proxy=FailingProxy())
        with self.assertLogs("hourtracker.idle", "WARNING") as logs:
            self.assertIsNone(monitor())
            self.assertIsNone(monitor())
        self.assertEqual(len(logs.records), 1)
