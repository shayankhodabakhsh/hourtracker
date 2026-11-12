import os
import time
import unittest
from datetime import date
from unittest import mock

from hourtracker import stats
from hourtracker.stats import MONDAY, SUNDAY


class NewYorkTime(unittest.TestCase):
    """Runs tests in America/New_York so daylight-saving days are predictable."""

    @classmethod
    def setUpClass(cls):
        cls._old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/New_York"
        time.tzset()

    @classmethod
    def tearDownClass(cls):
        if cls._old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = cls._old_tz
        time.tzset()


class DayTotalsTest(NewYorkTime):
    def test_session_across_midnight_is_split(self):
        midnight = stats.local_midnight(date(2026, 9, 29))
        totals = stats.day_totals([(midnight - 1800, midnight + 1800)], date(2026, 9, 28), 2)
        self.assertEqual(totals, [1800.0, 1800.0])

    def test_spring_forward_day_has_23_hours(self):
        day = date(2026, 3, 8)
        whole = (stats.local_midnight(day), stats.local_midnight(date(2026, 3, 9)))
        self.assertEqual(stats.day_totals([whole], day, 1), [23 * 3600.0])

    def test_fall_back_day_has_25_hours(self):
        day = date(2026, 11, 1)
        whole = (stats.local_midnight(day), stats.local_midnight(date(2026, 11, 2)))
        self.assertEqual(stats.day_totals([whole], day, 1), [25 * 3600.0])

    def test_time_outside_the_range_is_ignored(self):
        start = stats.local_midnight(date(2026, 9, 28))
        sessions = [(start - 7200, start - 3600), (start - 600, start + 600)]
        self.assertEqual(stats.day_totals(sessions, date(2026, 9, 28), 1), [600.0])

    def test_local_date(self):
        ts = stats.local_midnight(date(2026, 9, 28)) + 60
        self.assertEqual(stats.local_date(ts), date(2026, 9, 28))


class PeriodTest(unittest.TestCase):
    def test_week_start(self):
        monday = date(2026, 9, 28)
        self.assertEqual(stats.week_start(monday, SUNDAY), date(2026, 9, 27))
        self.assertEqual(stats.week_start(monday, MONDAY), monday)
        self.assertEqual(stats.week_start(date(2026, 9, 27), MONDAY), date(2026, 9, 21))

    def test_add_months_crosses_years(self):
        self.assertEqual(stats.add_months(date(2026, 12, 15), 1), date(2027, 1, 1))
        self.assertEqual(stats.add_months(date(2026, 1, 31), -1), date(2025, 12, 1))

    def test_period(self):
        self.assertEqual(stats.period("week", date(2026, 9, 28), SUNDAY),
                         (date(2026, 9, 27), 7))
        self.assertEqual(stats.period("month", date(2026, 9, 28), SUNDAY),
                         (date(2026, 9, 1), 30))
        self.assertEqual(stats.period("month", date(2028, 2, 10), SUNDAY),
                         (date(2028, 2, 1), 29))

    def test_shift(self):
        self.assertEqual(stats.shift("week", date(2026, 9, 28), -1), date(2026, 9, 21))
        self.assertEqual(stats.shift("month", date(2026, 9, 28), 1), date(2026, 10, 1))

    def test_period_label(self):
        self.assertEqual(stats.period_label("week", date(2026, 9, 27), 7), "Sep 27 – Oct 3")
        self.assertEqual(stats.period_label("month", date(2026, 9, 1), 30), "September 2026")


class FormatTest(unittest.TestCase):
    def test_fmt_clock(self):
        self.assertEqual(stats.fmt_clock(0), "0:00")
        self.assertEqual(stats.fmt_clock(59), "0:00")
        self.assertEqual(stats.fmt_clock(84 * 60), "1:24")
        self.assertEqual(stats.fmt_clock(10 * 3600), "10:00")
        self.assertEqual(stats.fmt_clock(-5), "0:00")

    def test_fmt_duration(self):
        self.assertEqual(stats.fmt_duration(0), "0m")
        self.assertEqual(stats.fmt_duration(45 * 60), "45m")
        self.assertEqual(stats.fmt_duration(135 * 60), "2h 15m")
        self.assertEqual(stats.fmt_duration(61 * 60), "1h 01m")


class WeekStartSettingTest(unittest.TestCase):
    def fake_locale(self, stdout):
        return mock.patch("subprocess.run", return_value=mock.Mock(stdout=stdout))

    def test_us_locale_starts_on_sunday(self):
        with self.fake_locale("19971130\n1\n"):
            self.assertEqual(stats.locale_first_weekday(), SUNDAY)

    def test_european_locale_starts_on_monday(self):
        with self.fake_locale("19971130\n2\n"):
            self.assertEqual(stats.locale_first_weekday(), MONDAY)

    def test_unreadable_locale_falls_back_to_monday(self):
        with mock.patch("subprocess.run", side_effect=OSError):
            self.assertEqual(stats.locale_first_weekday(), MONDAY)

    def test_explicit_settings(self):
        self.assertEqual(stats.resolve_first_weekday("sunday"), SUNDAY)
        self.assertEqual(stats.resolve_first_weekday("monday"), MONDAY)


class SittingsTest(NewYorkTime):
    DAY = date(2026, 11, 12)

    def at(self, hhmm, day=None):
        return stats.sitting_times(day or self.DAY, hhmm, "23:59")[0]

    def test_day_sittings_by_start_day_and_hides_slips(self):
        rows = [(1, self.at("16:23"), self.at("16:53"), None),
                (2, self.at("10:57"), self.at("12:23"), None),
                (3, self.at("15:00"), self.at("15:00") + 30, None),          # a slip
                (4, self.at("23:00", date(2026, 11, 11)), self.at("01:00"), None)]
        self.assertEqual([r[0] for r in stats.day_sittings(rows, self.DAY)], [2, 1])

    def test_fmt_span(self):
        a, b = stats.sitting_times(self.DAY, "19:24", "09:27")
        self.assertEqual(stats.fmt_span(a, b), "19:24 – 09:27 (next day)")
        a, b = stats.sitting_times(self.DAY, "14:53", "16:53")
        self.assertEqual(stats.fmt_span(a, b), "14:53 – 16:53")
        self.assertEqual(stats.fmt_span(a, b, running=True), "14:53 – now")

    def test_parse_hhmm(self):
        self.assertEqual(stats.parse_hhmm("14:53"), 14 * 60 + 53)
        self.assertEqual(stats.parse_hhmm(" 9:05 "), 9 * 60 + 5)
        for bad in ("24:00", "12:60", "1253", "ab:cd", ""):
            self.assertIsNone(stats.parse_hhmm(bad), bad)

    def test_sitting_times_end_before_start_is_next_day(self):
        a, b = stats.sitting_times(self.DAY, "19:24", "21:16")
        self.assertEqual(b - a, 112 * 60)
        a, b = stats.sitting_times(self.DAY, "23:30", "00:30")
        self.assertEqual(b - a, 3600)
        with self.assertRaises(ValueError):
            stats.sitting_times(self.DAY, "7pm", "21:00")

    def test_sitting_problem(self):
        a, b = 1000.0, 4600.0
        self.assertIsNone(stats.sitting_problem(a, b, [(0, 1000), (4600, 5000)], 9999))
        self.assertIn("overlaps", stats.sitting_problem(a, b, [(4000, 5000)], 9999))
        self.assertIn("future", stats.sitting_problem(a, b, [], 4000))
        self.assertIn("minute", stats.sitting_problem(a, a + 30, [], 9999))
        self.assertIn("24 hours", stats.sitting_problem(a, a + 25 * 3600, [], 1e12))

    def test_subject_totals_clip_to_range_and_sort(self):
        rows = [(1, 0, 100, "Calc"), (2, 100, 400, "Bio", True),
                (3, 400, 500, None), (4, 900, 2000, "Calc")]
        self.assertEqual(stats.subject_totals(rows, 50, 1000),
                         [("Bio", 300.0), ("Calc", 150.0), (None, 100.0)])
