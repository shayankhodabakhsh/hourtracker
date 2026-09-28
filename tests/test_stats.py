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
