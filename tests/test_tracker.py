import sqlite3
import unittest

from hourtracker import stats
from hourtracker.store import Store
from hourtracker.tracker import TICK_SECONDS, Away, Tracker

T0 = 1_790_000_000.0


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


class Idle:
    """Seconds since the last keyboard or mouse input, as GNOME reports it."""

    def __init__(self):
        self.seconds = 0.0

    def __call__(self):
        return self.seconds


class TrackerTestCase(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.idle = Idle()
        self.store = Store(":memory:")
        self.tracker = Tracker(self.store, clock=self.clock, idle=self.idle)

    def tearDown(self):
        self.store.close()

    def advance(self, seconds, active=True):
        """Let time pass in ticks. Active means the user keeps typing."""
        for _ in range(int(seconds // TICK_SECONDS)):
            self.clock.now += TICK_SECONDS
            self.idle.seconds = 0.0 if active else self.idle.seconds + TICK_SECONDS
            self.tracker.tick()

    def saved(self):
        return self.store.sessions_between(0, T0 * 2)

    def total(self):
        return sum(end - start for start, end in self.tracker.sessions_between(0, T0 * 2))


class TimingTest(TrackerTestCase):
    def test_start_and_pause_record_a_session(self):
        self.tracker.start()
        self.advance(600)
        self.tracker.pause()
        self.assertEqual(self.saved(), [(T0, T0 + 600)])
        self.assertFalse(self.tracker.running)

    def test_running_session_is_saved_every_30_seconds(self):
        self.tracker.start()
        self.advance(25)
        self.assertEqual(self.saved(), [(T0, T0)])
        self.advance(5)
        self.assertEqual(self.saved(), [(T0, T0 + 30)])

    def test_live_total_includes_unsaved_time(self):
        self.tracker.start()
        self.advance(20)
        self.assertEqual(self.total(), 20)

    def test_toggle(self):
        self.tracker.toggle()
        self.assertTrue(self.tracker.running)
        self.tracker.toggle()
        self.assertFalse(self.tracker.running)

    def test_clock_set_back_loses_nothing(self):
        self.tracker.start()
        self.advance(600)
        self.clock.now -= 3600
        self.tracker.tick()
        self.assertIsNone(self.tracker.pending)
        self.assertEqual(self.saved(), [(T0, T0 + 600)])

    def test_day_totals_include_the_running_session(self):
        self.tracker.start()
        self.advance(300)
        self.assertEqual(self.tracker.day_totals(stats.local_date(T0), 1), [300.0])

    def test_ui_is_told_about_changes(self):
        changes = []
        self.tracker.on_change = lambda: changes.append(1)
        self.tracker.start()
        self.tracker.pause()
        self.assertEqual(len(changes), 2)


class AwayTest(TrackerTestCase):
    def test_no_question_for_a_break_just_under_15_minutes(self):
        self.tracker.start()
        self.advance(890, active=False)
        self.advance(5)                        # back after 14:55
        self.assertIsNone(self.tracker.pending)

    def test_asks_after_15_minutes_away(self):
        self.tracker.start()
        self.advance(895, active=False)
        self.advance(5)                        # back after exactly 15:00
        self.assertEqual(self.tracker.pending, Away(T0, T0 + 900))

    def test_yes_keeps_the_time(self):
        self.tracker.start()
        self.advance(895, active=False)
        self.advance(5)
        self.tracker.answer_away(studying=True)
        self.assertIsNone(self.tracker.pending)
        self.assertTrue(self.tracker.running)
        self.assertEqual(self.total(), 900)

    def test_no_removes_the_away_time_and_pauses(self):
        self.tracker.start()
        self.advance(600)                      # studying until T0+600
        self.advance(895, active=False)
        self.advance(5)                        # back at T0+1500
        self.tracker.answer_away(studying=False)
        self.assertFalse(self.tracker.running)
        self.assertEqual(self.saved(), [(T0, T0 + 600)])

    def test_no_after_pausing_still_removes_the_stretch(self):
        self.tracker.start()
        self.advance(600)
        self.advance(895, active=False)
        self.advance(5)                        # question: T0+600 .. T0+1500
        self.tracker.pause()
        self.assertIsNotNone(self.tracker.pending)
        self.tracker.answer_away(studying=False)
        self.assertFalse(self.tracker.running)
        self.assertEqual(self.saved(), [(T0, T0 + 600)])

    def test_starting_again_counts_an_open_question(self):
        self.tracker.start()
        self.advance(895, active=False)
        self.advance(5)                        # question: T0 .. T0+900
        self.tracker.pause()
        self.tracker.start()
        self.assertIsNone(self.tracker.pending)
        self.assertEqual(self.total(), 900)

    def test_a_new_stretch_while_paused_counts_an_open_question(self):
        self.tracker.start()
        self.advance(895, active=False)
        self.advance(5)                        # question: T0 .. T0+900
        self.tracker.pause()
        self.advance(895, active=False)
        self.advance(5)                        # back again after another break
        self.assertIsNone(self.tracker.pending)
        self.assertEqual(self.total(), 900)

    def test_sleeping_laptop_asks_on_wake(self):
        self.tracker.start()
        self.advance(60)
        self.clock.now += 3600                 # lid closed for an hour
        self.tracker.tick()
        self.assertEqual(self.tracker.pending, Away(T0 + 60, T0 + 3660))

    def test_short_sleep_counts_silently(self):
        self.tracker.start()
        self.advance(60)
        self.clock.now += 300
        self.tracker.tick()
        self.assertIsNone(self.tracker.pending)
        self.assertEqual(self.saved(), [(T0, T0 + 360)])

    def test_new_break_replaces_an_unanswered_question(self):
        self.tracker.start()
        self.advance(895, active=False)
        self.advance(5)                        # first question: T0 .. T0+900
        self.advance(100)
        self.advance(895, active=False)
        self.advance(5)                        # second: T0+1000 .. T0+1900
        self.assertEqual(self.tracker.pending, Away(T0 + 1000, T0 + 1900))

    def test_no_questions_while_paused(self):
        self.advance(2000, active=False)
        self.advance(5)
        self.assertIsNone(self.tracker.pending)

    def test_without_idle_monitor_only_sleep_is_detected(self):
        tracker = Tracker(self.store, clock=self.clock, idle=lambda: None)
        tracker.start()
        for _ in range(400):                   # 2000 s of ticks
            self.clock.now += TICK_SECONDS
            tracker.tick()
        self.assertIsNone(tracker.pending)


class NudgeTest(TrackerTestCase):
    def setUp(self):
        super().setUp()
        self.buzzes = 0
        self.tracker.on_nudge = self.count_buzz

    def count_buzz(self):
        self.buzzes += 1

    def test_buzzes_after_3_minutes_of_use_with_the_timer_off(self):
        self.advance(175)
        self.assertIsNone(self.tracker.nudge)
        self.advance(5)
        self.assertEqual(self.tracker.nudge, T0)
        self.assertEqual(self.buzzes, 1)

    def test_buzzes_only_once_per_stretch(self):
        self.advance(600)
        self.assertEqual(self.buzzes, 1)

    def test_start_counts_from_when_you_sat_down(self):
        self.advance(180)
        self.tracker.answer_nudge(start=True)
        self.assertTrue(self.tracker.running)
        self.assertIsNone(self.tracker.nudge)
        self.assertEqual(self.total(), 180)

    def test_not_now_stays_quiet_until_the_next_break(self):
        self.advance(180)
        self.tracker.answer_nudge(start=False)
        self.advance(600)                      # now T0+780
        self.assertEqual(self.buzzes, 1)
        self.advance(895, active=False)        # a 15 minute break
        self.advance(185)                      # back at T0+1680, 3 min of use
        self.assertEqual(self.buzzes, 2)
        self.assertEqual(self.tracker.nudge, T0 + 1680)

    def test_no_buzz_while_away_from_the_laptop(self):
        self.advance(1000, active=False)
        self.assertEqual(self.buzzes, 0)

    def test_no_buzz_after_a_manual_pause(self):
        self.tracker.start()
        self.advance(60)
        self.tracker.pause()
        self.advance(600)
        self.assertEqual(self.buzzes, 0)

    def test_buzz_can_be_turned_off(self):
        self.tracker.nudge_enabled = False
        self.advance(600)
        self.assertEqual(self.buzzes, 0)

    def test_waking_the_laptop_starts_a_new_stretch(self):
        self.advance(180)
        self.tracker.answer_nudge(start=False)
        self.clock.now += 3600                 # asleep for an hour
        self.tracker.tick()
        self.advance(180)
        self.assertEqual(self.buzzes, 2)


class FlakyStore(Store):
    """A store whose writes can be made to fail, like a locked database."""

    def __init__(self):
        super().__init__(":memory:")
        self.failing = False

    def extend(self, session_id, ts):
        if self.failing:
            raise sqlite3.OperationalError("database is locked")
        super().extend(session_id, ts)


class RobustnessTest(TrackerTestCase):
    def test_a_failed_save_is_retried_at_the_next_checkpoint(self):
        store = FlakyStore()
        self.addCleanup(store.close)
        self.tracker = Tracker(store, clock=self.clock, idle=self.idle)
        self.tracker.start()
        store.failing = True
        with self.assertLogs("hourtracker.tracker", "ERROR"):
            self.advance(60)
        store.failing = False
        self.advance(30)
        self.assertEqual(store.sessions_between(0, T0 * 2), [(T0, T0 + 90)])

    def test_a_failing_ui_callback_does_not_stop_an_answer(self):
        def broken():
            raise RuntimeError("window gone")
        self.tracker.start()
        self.advance(600)
        self.advance(895, active=False)
        self.tracker.on_change = broken
        with self.assertLogs("hourtracker.tracker", "ERROR"):
            self.advance(5)              # the question opens; the UI update fails
            self.tracker.answer_away(studying=False)
        self.assertFalse(self.tracker.running)
        self.assertEqual(self.saved(), [(T0, T0 + 600)])
