import unittest
from datetime import date

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk  # noqa: E402

from hourtracker.stats import SUNDAY, local_midnight  # noqa: E402
from hourtracker.stats_window import bar_index, nice_max  # noqa: E402


class ChartMathTest(unittest.TestCase):
    def test_scale_rounds_up_to_whole_hours(self):
        self.assertEqual(nice_max([]), 3600)
        self.assertEqual(nice_max([0, 0]), 3600)
        self.assertEqual(nice_max([1800, 5400]), 7200)
        self.assertEqual(nice_max([7200]), 7200)

    def test_bar_index(self):
        self.assertEqual(bar_index(0, 700, 7), 0)
        self.assertEqual(bar_index(350, 700, 7), 3)
        self.assertEqual(bar_index(699, 700, 7), 6)
        self.assertIsNone(bar_index(-1, 700, 7))
        self.assertIsNone(bar_index(700, 700, 7))
        self.assertIsNone(bar_index(10, 700, 0))


class FakeChart:
    def __init__(self, width):
        self.width = width

    def get_allocated_width(self):
        return self.width


class FakeTooltip:
    text = None

    def set_text(self, text):
        self.text = text


@unittest.skipIf(Gdk.Display.get_default() is None, "needs a display")
class StatsWindowTest(unittest.TestCase):
    def setUp(self):
        from hourtracker.stats_window import StatsWindow
        from hourtracker.store import Store
        from hourtracker.tracker import Tracker
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        noon = local_midnight(date(2026, 9, 28)) + 12 * 3600    # a Monday
        self.window = StatsWindow(Tracker(self.store, clock=lambda: noon), SUNDAY)
        self.addCleanup(self.window.destroy)
        self.window.refresh()

    def test_next_arrow_only_works_for_past_periods(self):
        self.assertEqual(self.window._label.get_text(), "Sep 27 – Oct 3")
        self.assertFalse(self.window._next.get_sensitive())
        self.window._move(-1)
        self.assertEqual(self.window._label.get_text(), "Sep 20 – Sep 26")
        self.assertTrue(self.window._next.get_sensitive())

    def test_month_view_covers_the_calendar_month(self):
        self.window.set_view("month")
        self.assertEqual(self.window._label.get_text(), "September 2026")
        self.assertEqual(len(self.window._totals), 30)

    def test_tooltip_names_the_hovered_day(self):
        start = local_midnight(date(2026, 9, 27)) + 9 * 3600      # Sunday 9:00
        self.store.extend(self.store.begin(start), start + 3600)
        self.window.refresh()
        tooltip = FakeTooltip()
        self.assertTrue(self.window._on_tooltip(FakeChart(700), 50, 0, False, tooltip))
        self.assertEqual(tooltip.text, "Sun, Sep 27 · 1h 00m")
