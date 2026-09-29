import os
import unittest

from gi.repository import GLib

from hourtracker.idle import IdleMonitor, LockMonitor


class FailingProxy:
    def call_sync(self, *args):
        raise GLib.Error("no idle monitor here")


class ReplyProxy:
    """Answers every D-Bus call with one fixed reply and records the method."""

    def __init__(self, reply):
        self.reply = reply
        self.methods = []

    def call_sync(self, method, *args):
        self.methods.append(method)
        return self.reply


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


class LockMonitorTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("DBUS_SESSION_BUS_ADDRESS"), "needs a desktop session")
    def test_reads_the_lock_state_from_gnome(self):
        self.assertIsInstance(LockMonitor()(), bool)

    def test_reports_a_locked_screen(self):
        proxy = ReplyProxy(GLib.Variant("(b)", (True,)))
        self.assertTrue(LockMonitor(proxy=proxy)())
        self.assertEqual(proxy.methods, ["GetActive"])

    def test_reports_an_unlocked_screen(self):
        self.assertFalse(LockMonitor(proxy=ReplyProxy(GLib.Variant("(b)", (False,))))())

    def test_errors_count_as_unlocked_and_warn_once(self):
        monitor = LockMonitor(proxy=FailingProxy())
        with self.assertLogs("hourtracker.idle", "WARNING") as logs:
            self.assertFalse(monitor())
            self.assertFalse(monitor())
        self.assertEqual(len(logs.records), 1)
