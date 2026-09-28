# Hour Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Hour Tracker v1 for Ubuntu GNOME on Wayland: a floating study-timer
pill with day, week, and month stats, an away check, a forgot-to-start buzz, and a
draggable, squishable balloon toy.

**Architecture:** One single-instance GTK 3 app in Python, run through XWayland so
its borderless windows can float on top and position themselves. Pure logic (time
math, storage, the timer state machine, spring physics, drawing) lives in GTK-free
modules with unit tests. Thin GTK windows sit on top and are checked with PNG
snapshots and a live smoke test.

**Tech Stack:** System Python 3.14 (`/usr/bin/python3`), PyGObject (GTK 3.24, Gio,
libnotify), pycairo plus `python3-gi-cairo`, SQLite (stdlib), `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-28-hour-tracker-design.md`

## Global Constraints

- Repo root: `/home/shayan-khodabakhsh/Timer`, remote
  `git@github.com:shayankhodabakhsh/hourtracker.git`. Work on branch `v1`.
- Always run Python as `/usr/bin/python3`. The `python3` on PATH is conda's and has
  no GTK bindings.
- Run tests from the repo root: `/usr/bin/python3 -m unittest -v` for everything,
  or `/usr/bin/python3 -m unittest tests.test_stats -v` for one module. There's no
  pytest.
- Dependencies: standard library, PyGObject, and pycairo only. Nothing from pip.
- GTK 3 only (`gi.require_version("Gtk", "3.0")`). `GDK_BACKEND=x11` is set only in
  `hourtracker/__main__.py` and in `tools/` scripts, before GTK is imported.
- The Ubuntu package `python3-gi-cairo` must be installed before Task 8. The user
  installs it with `sudo apt install python3-gi-cairo`. Check it with
  `/usr/bin/python3 -c "import gi; gi.require_foreign('cairo')"`.
- Names: app "Hour Tracker"; package `hourtracker`; launcher `hour-tracker`; app ID
  `io.github.shayankhodabakhsh.HourTracker`; data
  `~/.local/share/hour-tracker/hours.db`; settings
  `~/.config/hour-tracker/settings.json`; autostart
  `~/.config/autostart/hour-tracker.desktop`.
- Defaults: tick 5 s, checkpoint 30 s, suspend gap 60 s, away threshold 15 min,
  buzz delay 3 min, and "active" means input within the last 60 s.
- UI text, exactly:
  - Away question: `Away {fmt_duration}. Were you studying?`, with buttons `Yes` and
    `No`.
  - Buzz question: `Studying? The timer is off.`, with buttons `Start` and
    `Not now`.
  - Notification: title `Studying?`, body `Your study timer is off.`, actions
    `Start` and `Not now`.
  - Pill menu: `Stats`, `Show balloon`, `Remind me to start`, `Start at login`,
    `Quit`.
  - Balloon menu: `Color` (`Matte black`, `Electric blue`, `Army green`,
    `Fire red`) and `Hide balloon`.
  - Stats window: cards `Today`, `This week`, `This month`; toggle `Week` and
    `Month`; empty chart `No study time yet`.
- Every commit message ends with the trailer
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, passed as a second `-m`.
- Tasks 8 to 12 open real windows on the desktop for a second or two. That's
  expected.

## File Structure

```
hour-tracker              launcher script (runs the system Python)
install.sh                app-grid entry (and --uninstall)
README.md
data/hour-tracker.svg     app icon
hourtracker/
  __init__.py             APP_ID, APP_NAME, PROGRAM
  __main__.py             entry point: sets GDK_BACKEND=x11, runs the app
  stats.py                pure time math and formatting
  store.py                SQLite sessions
  tracker.py              timer state machine: checkpoints, away check, buzz
  settings.py             JSON settings
  autostart.py            start-at-login entry
  idle.py                 GNOME idle time over D-Bus
  physics.py              damped spring
  balloon_art.py          Cairo drawing of the balloon
  floating.py             floating-window base class and position clamping
  balloon.py              the balloon window
  pill.py                 the timer pill window
  notifier.py             forgot-to-start notification
  stats_window.py         stats window and bar chart
  app.py                  Gtk.Application wiring
tests/                    one unittest module per logic module
tools/
  render_preview.py       balloon poses to PNG contact sheets
  snapshot.py             shows one real window briefly and saves a PNG
  check_windows.py        X11 checks on the running app's windows
```

---

### Task 1: Package skeleton and time math

**Files:**
- Create: `hourtracker/__init__.py`, `hourtracker/stats.py`, `tests/__init__.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: nothing.
- Produces (`hourtracker`): `APP_ID: str`, `APP_NAME: str`, `PROGRAM: str`.
- Produces (`hourtracker.stats`): `MONDAY = 0`, `SUNDAY = 6`;
  `local_midnight(d: date) -> float`; `local_date(ts: float) -> date`;
  `day_totals(sessions, first: date, days: int) -> list[float]`;
  `week_start(d: date, first_weekday: int) -> date`;
  `add_months(d: date, n: int) -> date`;
  `period(view: str, anchor: date, first_weekday: int) -> tuple[date, int]`;
  `shift(view: str, anchor: date, steps: int) -> date`;
  `period_label(view: str, first: date, days: int) -> str`;
  `fmt_clock(seconds: float) -> str`; `fmt_duration(seconds: float) -> str`;
  `locale_first_weekday() -> int`; `resolve_first_weekday(setting: str) -> int`.
  Views are the strings `"week"` and `"month"`.

- [ ] **Step 1: Create the package skeleton**

`hourtracker/__init__.py`:

```python
"""Hour Tracker: a floating study timer, plus a balloon to fidget with."""

APP_ID = "io.github.shayankhodabakhsh.HourTracker"
APP_NAME = "Hour Tracker"
PROGRAM = "hour-tracker"
```

`tests/__init__.py`: an empty file.

- [ ] **Step 2: Write the failing tests**

`tests/test_stats.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_stats -v`
Expected: FAIL with `ImportError: cannot import name 'stats' from 'hourtracker'`.

- [ ] **Step 4: Write the implementation**

`hourtracker/stats.py`:

```python
"""Time math for study totals. Pure functions: no GTK, no database.

Timestamps are Unix seconds. Local dates come from naive datetimes, which
Python converts with the system time zone rules, so daylight-saving days
come out as 23 or 25 hours long.
"""
import calendar
import subprocess
from datetime import date, datetime, time, timedelta

MONDAY, SUNDAY = 0, 6


def local_midnight(d: date) -> float:
    """Unix time of 00:00 local time on date d."""
    return datetime.combine(d, time()).timestamp()


def local_date(ts: float) -> date:
    """Local calendar date of Unix time ts."""
    return datetime.fromtimestamp(ts).date()


def day_totals(sessions, first: date, days: int) -> list[float]:
    """Seconds studied on each of `days` local dates starting at `first`.

    `sessions` is an iterable of (start, end) pairs. A session that crosses
    midnight is split between the days; time outside the range is ignored.
    """
    edges = [local_midnight(first + timedelta(days=i)) for i in range(days + 1)]
    totals = [0.0] * days
    for start, end in sessions:
        for i in range(days):
            totals[i] += max(0.0, min(end, edges[i + 1]) - max(start, edges[i]))
    return totals


def week_start(d: date, first_weekday: int) -> date:
    """First day of the week containing d (first_weekday: 0=Monday ... 6=Sunday)."""
    return d - timedelta(days=(d.weekday() - first_weekday) % 7)


def add_months(d: date, n: int) -> date:
    """First day of the month that is n months after d's month."""
    index = d.year * 12 + d.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def period(view: str, anchor: date, first_weekday: int) -> tuple[date, int]:
    """(first day, number of days) of the "week" or "month" containing anchor."""
    if view == "week":
        return week_start(anchor, first_weekday), 7
    return anchor.replace(day=1), calendar.monthrange(anchor.year, anchor.month)[1]


def shift(view: str, anchor: date, steps: int) -> date:
    """Anchor moved by whole weeks or months (negative steps go back)."""
    if view == "week":
        return anchor + timedelta(weeks=steps)
    return add_months(anchor, steps)


def period_label(view: str, first: date, days: int) -> str:
    """'Sep 27 – Oct 3' for a week, 'September 2026' for a month."""
    if view == "month":
        return f"{first:%B %Y}"
    last = first + timedelta(days=days - 1)
    return f"{first:%b} {first.day} – {last:%b} {last.day}"


def fmt_clock(seconds: float) -> str:
    """Hours and minutes like '1:05', rounded down."""
    minutes = int(max(0.0, seconds) // 60)
    return f"{minutes // 60}:{minutes % 60:02d}"


def fmt_duration(seconds: float) -> str:
    """'2h 05m', '45m', or '0m', rounded down."""
    hours, minutes = divmod(int(max(0.0, seconds) // 60), 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def locale_first_weekday() -> int:
    """First weekday of the current LC_TIME locale (0=Monday ... 6=Sunday).

    glibc gives a reference date (week-1stday) and a 1-based offset from it
    (first_weekday). Falls back to Monday if `locale` can't be read.
    """
    try:
        out = subprocess.run(["locale", "week-1stday", "first_weekday"],
                             capture_output=True, text=True, timeout=2,
                             check=True).stdout.split()
        reference = datetime.strptime(out[0], "%Y%m%d").date()
        return (reference.weekday() + int(out[1]) - 1) % 7
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return MONDAY


def resolve_first_weekday(setting: str) -> int:
    """Map the week_start setting ('auto', 'sunday', 'monday') to a weekday."""
    if setting == "sunday":
        return SUNDAY
    if setting == "monday":
        return MONDAY
    return locale_first_weekday()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_stats -v`
Expected: `Ran 16 tests` and `OK`.

- [ ] **Step 6: Commit**

```bash
git add hourtracker/__init__.py hourtracker/stats.py tests/__init__.py tests/test_stats.py
git commit -m "feat: add time math for daily, weekly, and monthly totals" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Session storage

**Files:**
- Create: `hourtracker/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces (`hourtracker.store.Store`): `Store(path: str)` (`":memory:"` allowed; parent
  folders are created); `begin(ts: float) -> int`;
  `extend(session_id: int, ts: float) -> None` (the end only moves forward);
  `remove_range(a: float, b: float) -> None`;
  `sessions_between(a: float, b: float) -> list[tuple[float, float]]` (sessions
  overlapping `[a, b)`, oldest first); `close() -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:

```python
import os
import tempfile
import unittest

from hourtracker.store import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def add(self, start, end):
        session_id = self.store.begin(start)
        self.store.extend(session_id, end)
        return session_id

    def sessions(self):
        return self.store.sessions_between(0, 1000)

    def test_begin_and_extend(self):
        self.add(100, 200)
        self.assertEqual(self.sessions(), [(100.0, 200.0)])

    def test_extend_never_moves_backward(self):
        session_id = self.add(100, 200)
        self.store.extend(session_id, 150)
        self.assertEqual(self.sessions(), [(100.0, 200.0)])

    def test_sessions_between_only_returns_overlaps(self):
        self.add(100, 200)
        self.add(300, 400)
        self.assertEqual(self.store.sessions_between(150, 300), [(100.0, 200.0)])

    def test_remove_range_inside_splits_the_session(self):
        self.add(100, 400)
        self.store.remove_range(200, 300)
        self.assertEqual(self.sessions(), [(100.0, 200.0), (300.0, 400.0)])

    def test_remove_range_covering_a_session_deletes_it(self):
        self.add(100, 200)
        self.store.remove_range(50, 250)
        self.assertEqual(self.sessions(), [])

    def test_remove_range_clips_the_end(self):
        self.add(100, 300)
        self.store.remove_range(200, 400)
        self.assertEqual(self.sessions(), [(100.0, 200.0)])

    def test_remove_range_clips_the_start(self):
        self.add(100, 300)
        self.store.remove_range(0, 200)
        self.assertEqual(self.sessions(), [(200.0, 300.0)])

    def test_remove_range_touches_several_sessions(self):
        self.add(100, 200)
        self.add(300, 400)
        self.store.remove_range(150, 350)
        self.assertEqual(self.sessions(), [(100.0, 150.0), (350.0, 400.0)])

    def test_remove_range_without_overlap_changes_nothing(self):
        self.add(100, 200)
        self.store.remove_range(300, 400)
        self.store.remove_range(250, 250)
        self.assertEqual(self.sessions(), [(100.0, 200.0)])


class PersistenceTest(unittest.TestCase):
    def test_sessions_survive_reopening(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "hours.db")
            store = Store(path)
            store.extend(store.begin(100), 200)
            store.close()
            reopened = Store(path)
            self.assertEqual(reopened.sessions_between(0, 1000), [(100.0, 200.0)])
            reopened.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_store -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hourtracker.store'`.

- [ ] **Step 3: Write the implementation**

`hourtracker/store.py`:

```python
"""SQLite storage for study sessions: (start, end) pairs in Unix seconds."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id    INTEGER PRIMARY KEY,
    start REAL NOT NULL,
    end   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_start ON sessions (start);
"""


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def begin(self, ts: float) -> int:
        """Record a new session starting (and, for now, ending) at ts."""
        with self._db:
            return self._db.execute(
                "INSERT INTO sessions (start, end) VALUES (?, ?)", (ts, ts)).lastrowid

    def extend(self, session_id: int, ts: float) -> None:
        """Move a session's end forward to ts. It never moves backward."""
        with self._db:
            self._db.execute("UPDATE sessions SET end = max(end, ?) WHERE id = ?",
                             (ts, session_id))

    def remove_range(self, a: float, b: float) -> None:
        """Cut the time between a and b out of every session, splitting a
        session in two when the cut falls in its middle."""
        if b <= a:
            return
        with self._db:
            rows = self._db.execute(
                "SELECT id, start, end FROM sessions WHERE start < ? AND end > ?",
                (b, a)).fetchall()
            for session_id, start, end in rows:
                if a <= start and end <= b:
                    self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                elif start < a and b < end:
                    self._db.execute("UPDATE sessions SET end = ? WHERE id = ?",
                                     (a, session_id))
                    self._db.execute("INSERT INTO sessions (start, end) VALUES (?, ?)",
                                     (b, end))
                elif start < a:
                    self._db.execute("UPDATE sessions SET end = ? WHERE id = ?",
                                     (a, session_id))
                else:
                    self._db.execute("UPDATE sessions SET start = ? WHERE id = ?",
                                     (b, session_id))

    def sessions_between(self, a: float, b: float) -> list[tuple[float, float]]:
        """(start, end) of every session overlapping [a, b), oldest first."""
        return self._db.execute(
            "SELECT start, end FROM sessions WHERE start < ? AND end > ? ORDER BY start",
            (b, a)).fetchall()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_store -v`
Expected: `Ran 10 tests` and `OK`.

- [ ] **Step 5: Commit**

```bash
git add hourtracker/store.py tests/test_store.py
git commit -m "feat: store study sessions in SQLite" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Timer state machine (checkpoints, away check, buzz)

**Files:**
- Create: `hourtracker/tracker.py`
- Test: `tests/test_tracker.py`

**Interfaces:**
- Consumes: `Store` (Task 2); `stats.local_midnight`, `stats.day_totals` (Task 1).
- Produces (`hourtracker.tracker`): constants `TICK_SECONDS = 5`,
  `CHECKPOINT_SECONDS = 30`, `SUSPEND_GAP_SECONDS = 60`, `ACTIVE_SECONDS = 60`.
  `Away(start: float, end: float)`, a frozen dataclass with property `seconds`.
  `Tracker(store, clock=time.time, idle=lambda: None, away_after=900, nudge_after=180)`
  with:
  - Attributes: `running: bool`; `pending: Away | None`; `nudge: float | None` (the
    time a Start would count from); `nudge_enabled: bool`; `clock`; `on_change: () -> None`;
    `on_nudge: () -> None`.
  - Methods: `start(at: float | None = None)`, `pause()`, `toggle()`,
    `answer_away(studying: bool)`, `answer_nudge(start: bool)`, `tick()`,
    `sessions_between(a, b) -> list[tuple[float, float]]`,
    `day_totals(first: date, days: int) -> list[float]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_tracker.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_tracker -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hourtracker.tracker'`.

- [ ] **Step 3: Write the implementation**

`hourtracker/tracker.py`:

```python
"""The study timer's state machine. There's no GTK here: the clock and the
idle source are passed in, so tests can move time forward instantly."""
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, timedelta

from . import stats

log = logging.getLogger(__name__)

TICK_SECONDS = 5            # how often the app calls tick()
CHECKPOINT_SECONDS = 30     # how often a running session is written to disk
SUSPEND_GAP_SECONDS = 60    # a longer gap between ticks means the laptop slept
ACTIVE_SECONDS = 60         # input this recent means someone is at the laptop


@dataclass(frozen=True)
class Away:
    """A stretch with no input (or asleep) while the timer was running."""
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return self.end - self.start


class Tracker:
    def __init__(self, store, clock=time.time, idle=lambda: None,
                 away_after=15 * 60, nudge_after=3 * 60):
        self.store = store
        self.clock = clock
        self.idle = idle                # () -> seconds since the last input, or None
        self.away_after = away_after
        self.nudge_after = nudge_after
        self.nudge_enabled = True
        self.running = False
        self.pending = None             # an Away waiting for "were you studying?"
        self.nudge = None               # set while the forgot-to-start buzz is open
        self.on_change = lambda: None   # something the UI shows has changed
        self.on_nudge = lambda: None    # the timer looks forgotten: buzz
        now = clock()
        self._session_id = None
        self._start = now
        self._saved_end = now
        self._last_save = now
        self._last_tick = now
        self._last_active = now
        self._active_since = now        # start of the current stretch at the laptop
        self._nudge_armed = True

    # Controls -----------------------------------------------------------

    def start(self, at=None) -> None:
        """Start timing now, or from an earlier moment `at`."""
        if self.running:
            return
        now = self.clock()
        self.running = True
        self._start = now if at is None else min(at, now)
        self._session_id = None
        self._saved_end = self._start
        self._last_active = now
        self._silence_nudge()
        self._save(now)
        self.on_change()

    def pause(self) -> None:
        if not self.running:
            return
        self._save(self.clock())
        self.running = False
        self._session_id = None
        self._silence_nudge()
        self.on_change()

    def toggle(self) -> None:
        if self.running:
            self.pause()
        else:
            self.start()

    def answer_away(self, studying: bool) -> None:
        """Reply to "were you studying?". No cuts the stretch out and pauses."""
        away, self.pending = self.pending, None
        if away is None:
            return
        if not studying:
            self.pause()
            try:
                self.store.remove_range(away.start, away.end)
            except sqlite3.Error:
                log.exception("could not remove the away time")
        self.on_change()

    def answer_nudge(self, start: bool) -> None:
        """Reply to the buzz. Start counts from the beginning of the stretch."""
        since = self.nudge
        if since is None:
            return
        if start:
            self.start(at=since)
        else:
            self._silence_nudge()
            self.on_change()

    # Reading ------------------------------------------------------------

    def sessions_between(self, a: float, b: float) -> list[tuple[float, float]]:
        """Saved sessions, plus the part of the running one not saved yet."""
        rows = list(self.store.sessions_between(a, b))
        if self.running:
            unsaved = self._saved_end if self._session_id is not None else self._start
            rows.append((unsaved, self.clock()))
        return rows

    def day_totals(self, first: date, days: int) -> list[float]:
        """Seconds studied on each of `days` dates from `first`, live."""
        a = stats.local_midnight(first)
        b = stats.local_midnight(first + timedelta(days=days))
        return stats.day_totals(self.sessions_between(a, b), first, days)

    # The 5-second heartbeat ---------------------------------------------

    def tick(self) -> None:
        """Notices sleep and away time, saves progress, and buzzes when the
        timer looks forgotten. The app calls this every TICK_SECONDS."""
        now = self.clock()
        gap = now - self._last_tick
        self._last_tick = now
        if gap < 0:                               # the clock was set back
            self._last_active = self._last_save = now
            return
        slept = gap > SUSPEND_GAP_SECONDS
        idle = None if slept else self.idle()     # idle time leaves out sleep
        came_back = now if idle is None else now - idle
        if came_back - self._last_active >= self.away_after:
            self._returned(self._last_active, came_back)
        self._last_active = max(self._last_active, came_back)
        if self.running:
            if slept or now - self._last_save >= CHECKPOINT_SECONDS:
                self._save(now)
        elif idle is not None and idle < ACTIVE_SECONDS:
            self._maybe_nudge(now)

    def _returned(self, left: float, came_back: float) -> None:
        """Back after a long break, or the laptop woke up."""
        if self.running:
            self.pending = Away(left, came_back)  # replaces an unanswered one
        else:
            self._active_since = came_back
            self._nudge_armed = True
            self.nudge = None                     # an old buzz is stale now
        self.on_change()

    def _maybe_nudge(self, now: float) -> None:
        if (self.nudge_enabled and self._nudge_armed and self.nudge is None
                and now - self._active_since >= self.nudge_after):
            self.nudge = self._active_since
            self._nudge_armed = False
            self.on_nudge()
            self.on_change()

    def _silence_nudge(self) -> None:
        """No buzz until the next stretch at the laptop."""
        self.nudge = None
        self._nudge_armed = False

    def _save(self, now: float) -> None:
        """Write the running session to disk; if that fails, retry next time."""
        self._last_save = now
        try:
            if self._session_id is None:
                self._session_id = self.store.begin(self._start)
            self.store.extend(self._session_id, now)
            self._saved_end = now
        except sqlite3.Error:
            log.exception("could not save the session; will retry")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_tracker -v`
Expected: `Ran 24 tests` and `OK`.

- [ ] **Step 5: Commit**

```bash
git add hourtracker/tracker.py tests/test_tracker.py
git commit -m "feat: add the timer state machine with away check and forgot-to-start buzz" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Settings and start at login

**Files:**
- Create: `hourtracker/settings.py`, `hourtracker/autostart.py`
- Test: `tests/test_settings.py`, `tests/test_autostart.py`

**Interfaces:**
- Consumes: nothing.
- Produces (`hourtracker.settings`): `DEFAULTS: dict`; `Settings(path: str)` with
  `settings[key]` to read and `settings[key] = value` to set and save immediately.
  Keys: `pill_pos`, `balloon_pos` (`[x, y]` or `None`), `balloon_color` (str),
  `balloon_visible` (bool), `nudge_enabled` (bool), `nudge_minutes` (int),
  `away_minutes` (int), `week_start` (str).
- Produces (`hourtracker.autostart`): `entry_path() -> str`, `is_enabled() -> bool`,
  `set_enabled(enabled: bool, launcher: str) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_settings.py`:

```python
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
```

`tests/test_autostart.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_settings tests.test_autostart -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hourtracker.settings'` (and
`hourtracker.autostart`).

- [ ] **Step 3: Write the implementation**

`hourtracker/settings.py`:

```python
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
```

`hourtracker/autostart.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_settings tests.test_autostart -v`
Expected: `Ran 7 tests` and `OK`.

- [ ] **Step 5: Commit**

```bash
git add hourtracker/settings.py hourtracker/autostart.py tests/test_settings.py tests/test_autostart.py
git commit -m "feat: add JSON settings and the start-at-login entry" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: GNOME idle monitor, then push the core

**Files:**
- Create: `hourtracker/idle.py`
- Test: `tests/test_idle.py`

**Interfaces:**
- Consumes: nothing (Gio from PyGObject).
- Produces (`hourtracker.idle.IdleMonitor`): `IdleMonitor(proxy=None)`. Calling it
  returns seconds since the last input as a `float`, or `None` when GNOME's monitor
  isn't reachable. It logs one warning at most. `proxy` is for tests: any object
  with a `call_sync(...)` method.

- [ ] **Step 1: Write the failing tests**

`tests/test_idle.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_idle -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hourtracker.idle'`.

- [ ] **Step 3: Write the implementation**

`hourtracker/idle.py`:

```python
"""Seconds since the last keyboard or mouse input, from GNOME's idle monitor.
It works on Wayland, where apps can't watch input themselves."""
import logging

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)


class IdleMonitor:
    """Call it to get idle seconds, or None when GNOME's monitor isn't there."""

    def __init__(self, proxy=None):
        self._warned = False
        self._proxy = proxy if proxy is not None else self._connect()

    def _connect(self):
        try:
            return Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES
                | Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS,
                None,
                "org.gnome.Mutter.IdleMonitor",
                "/org/gnome/Mutter/IdleMonitor/Core",
                "org.gnome.Mutter.IdleMonitor",
                None)
        except GLib.Error as err:
            self._warn(err)
            return None

    def __call__(self):
        if self._proxy is None:
            return None
        try:
            reply = self._proxy.call_sync("GetIdletime", None,
                                          Gio.DBusCallFlags.NONE, 1000, None)
        except GLib.Error as err:
            self._warn(err)
            return None
        return reply.unpack()[0] / 1000.0

    def _warn(self, err):
        if not self._warned:
            self._warned = True
            log.warning("idle monitor unavailable, so only sleep counts as away "
                        "and there's no buzz: %s", err.message)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_idle -v`
Expected: `Ran 2 tests` and `OK`. Outside a desktop session it shows `OK (skipped=1)`.

- [ ] **Step 5: Run the whole suite**

Run: `/usr/bin/python3 -m unittest -v`
Expected: `Ran 59 tests` and `OK`.

- [ ] **Step 6: Commit and push the core**

```bash
git add hourtracker/idle.py tests/test_idle.py
git commit -m "feat: read idle time from GNOME's idle monitor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin v1
```

---

### Task 6: Spring physics and balloon drawing

**Files:**
- Create: `hourtracker/physics.py`, `hourtracker/balloon_art.py`, `tools/render_preview.py`
- Test: `tests/test_physics.py`, `tests/test_balloon_art.py`

**Interfaces:**
- Consumes: pycairo only (no GTK, and `python3-gi-cairo` isn't needed here).
- Produces (`hourtracker.physics.Spring`): `Spring(stiffness, damping, limit=1.0)`
  with attributes `value`, `velocity`, `target`; `kick(velocity, max_velocity)`,
  `step(dt)`, `settle()`, and the property `settled`.
- Produces (`hourtracker.balloon_art`): `WIDTH = 150`, `HEIGHT = 215`,
  `CENTER_X = 75`, `CENTER_Y = 72`, `RX = 42`, `RY = 50`; `Palette` (fields `label`,
  `base`, `light`, `dark`, `face`, `gloss`); `PALETTES` (dict with keys
  `matte_black`, `electric_blue`, `army_green`, `fire_red`);
  `DEFAULT_COLOR = "matte_black"`;
  `draw_balloon(cr, palette, squash=0.0, tilt=0.0, squint=False)`;
  `input_rects(step=4, pad=3) -> list[tuple[int, int, int, int]]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_physics.py`:

```python
import unittest

from hourtracker.physics import Spring


def simulate(spring, seconds, fps=60):
    """Run the spring and return the largest |value| seen."""
    peak = 0.0
    for _ in range(int(seconds * fps)):
        spring.step(1 / fps)
        peak = max(peak, abs(spring.value))
    return peak


def squish_spring():
    return Spring(stiffness=220, damping=7, limit=0.3)


class SpringTest(unittest.TestCase):
    def test_a_kick_wobbles_then_settles(self):
        spring = squish_spring()
        spring.kick(3.2, max_velocity=4.0)
        self.assertGreater(simulate(spring, 1.5), 0.1)
        self.assertTrue(spring.settled)

    def test_it_overshoots_like_jelly(self):
        spring = squish_spring()
        spring.kick(3.2, max_velocity=4.0)
        values = []
        for _ in range(60):
            spring.step(1 / 60)
            values.append(spring.value)
        self.assertLess(min(values), -0.02)    # swings past rest the other way

    def test_rapid_kicks_are_capped(self):
        spring = squish_spring()
        for _ in range(20):
            spring.kick(3.2, max_velocity=4.0)
        self.assertEqual(spring.velocity, 4.0)
        self.assertLessEqual(simulate(spring, 1.0), 0.3)

    def test_follows_a_target(self):
        spring = Spring(stiffness=60, damping=6, limit=0.4)
        spring.target = 0.3
        simulate(spring, 4.0)
        self.assertAlmostEqual(spring.value, 0.3, places=2)
```

`tests/test_balloon_art.py`:

```python
import unittest

import cairo

from hourtracker import balloon_art as art


def render(**pose):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, art.WIDTH, art.HEIGHT)
    art.draw_balloon(cairo.Context(surface), art.PALETTES[art.DEFAULT_COLOR], **pose)
    surface.flush()
    return surface


def alpha(surface, x, y):
    # ARGB32 is stored little-endian as B, G, R, A.
    return surface.get_data()[y * surface.get_stride() + x * 4 + 3]


def body_width(surface):
    columns = [x for x in range(art.WIDTH) if alpha(surface, x, art.CENTER_Y) > 128]
    return max(columns) - min(columns)


class BalloonArtTest(unittest.TestCase):
    def test_body_is_opaque_and_corners_are_transparent(self):
        surface = render()
        self.assertEqual(alpha(surface, art.CENTER_X, art.CENTER_Y - 30), 255)
        self.assertEqual(alpha(surface, 0, 0), 0)
        self.assertEqual(alpha(surface, art.WIDTH - 1, art.HEIGHT - 1), 0)

    def test_squash_makes_it_wider(self):
        self.assertGreater(body_width(render(squash=0.2)), body_width(render()) + 10)

    def test_every_palette_and_pose_draws(self):
        for palette in art.PALETTES.values():
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, art.WIDTH, art.HEIGHT)
            art.draw_balloon(cairo.Context(surface), palette,
                             squash=-0.15, tilt=0.3, squint=True)

    def test_input_rects_cover_the_body_but_not_the_corners(self):
        rects = art.input_rects()

        def inside(px, py):
            return any(x <= px < x + w and y <= py < y + h for x, y, w, h in rects)

        self.assertTrue(inside(art.CENTER_X, art.CENTER_Y))
        self.assertFalse(inside(2, 2))
        self.assertFalse(inside(art.WIDTH - 2, art.HEIGHT - 2))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_physics tests.test_balloon_art -v`
Expected: FAIL with `ModuleNotFoundError` for `hourtracker.physics` and
`hourtracker.balloon_art`.

- [ ] **Step 3: Write the spring**

`hourtracker/physics.py`:

```python
"""A damped spring, used to make the balloon squish, wobble, and sway."""


class Spring:
    """Pulls `value` toward `target` and overshoots a little, like jelly."""

    def __init__(self, stiffness: float, damping: float, limit: float = 1.0):
        self.stiffness = stiffness
        self.damping = damping
        self.limit = limit          # |value| never goes past this
        self.value = 0.0
        self.velocity = 0.0
        self.target = 0.0

    def kick(self, velocity: float, max_velocity: float) -> None:
        """Add a push. Repeated pushes stack, up to max_velocity."""
        self.velocity = max(-max_velocity, min(max_velocity, self.velocity + velocity))

    def step(self, dt: float) -> None:
        """Advance the simulation by dt seconds, in small sub-steps."""
        steps = max(1, int(dt / 0.004))
        h = dt / steps
        for _ in range(steps):
            force = (-self.stiffness * (self.value - self.target)
                     - self.damping * self.velocity)
            self.velocity += force * h
            self.value = max(-self.limit, min(self.limit, self.value + self.velocity * h))

    @property
    def settled(self) -> bool:
        """Close enough to rest that another frame wouldn't show a change."""
        return abs(self.value - self.target) < 0.002 and abs(self.velocity) < 0.03

    def settle(self) -> None:
        self.value, self.velocity = self.target, 0.0
```

- [ ] **Step 4: Write the balloon drawing**

`hourtracker/balloon_art.py`:

```python
"""Draws the balloon with Cairo. Pure drawing: no windows, no GTK."""
import math
from dataclasses import dataclass

import cairo

WIDTH, HEIGHT = 150, 215        # drawing area, in logical pixels
CENTER_X, CENTER_Y = 75, 72     # middle of the body at rest
RX, RY = 42, 50                 # half-width and half-height of the body
STRING_RGBA = (0.62, 0.62, 0.66, 0.9)


@dataclass(frozen=True)
class Palette:
    label: str
    base: tuple     # body color (r, g, b), each 0..1
    light: tuple    # lit upper-left side
    dark: tuple     # shaded edge and knot
    face: tuple     # eyes and smile
    gloss: float    # highlight strength: low looks matte, high looks shiny


PALETTES = {
    "matte_black": Palette("Matte black", (0.17, 0.17, 0.19), (0.34, 0.35, 0.38),
                           (0.07, 0.07, 0.08), (0.96, 0.96, 0.96), 0.14),
    "electric_blue": Palette("Electric blue", (0.10, 0.42, 0.95), (0.40, 0.66, 1.00),
                             (0.03, 0.19, 0.52), (1.00, 1.00, 1.00), 0.45),
    "army_green": Palette("Army green", (0.33, 0.37, 0.18), (0.52, 0.57, 0.31),
                          (0.17, 0.20, 0.08), (0.95, 0.94, 0.85), 0.25),
    "fire_red": Palette("Fire red", (0.84, 0.13, 0.13), (1.00, 0.40, 0.34),
                        (0.44, 0.04, 0.04), (1.00, 1.00, 1.00), 0.42),
}
DEFAULT_COLOR = "matte_black"


def draw_balloon(cr, palette, squash=0.0, tilt=0.0, squint=False):
    """Draw the balloon into a WIDTH x HEIGHT area.

    squash > 0 flattens it (wider and shorter); squash < 0 stretches it.
    tilt is a lean in radians; positive leans the top to the right.
    squint turns the eyes into happy arcs.
    """
    knot_depth = (RY + 7) * (1 - squash * 0.85)
    knot_x = CENTER_X - math.sin(tilt) * knot_depth
    knot_y = CENTER_Y + math.cos(tilt) * knot_depth
    _draw_string(cr, knot_x, knot_y, tilt)
    cr.save()
    cr.translate(CENTER_X, CENTER_Y)
    cr.rotate(tilt)
    cr.scale(1 + squash, 1 - squash * 0.85)
    _draw_knot(cr, palette)
    _draw_body(cr, palette)
    _draw_face(cr, palette, squint)
    cr.restore()


def input_rects(step=4, pad=3):
    """Horizontal strips (x, y, w, h) covering the resting body and knot, so
    clicks anywhere else in the window pass through to what's underneath."""
    rects = []
    y = CENTER_Y - RY - pad
    bottom = CENTER_Y + RY + 8 + pad
    while y < bottom:
        half = _half_width(y + step / 2 - CENTER_Y) + pad
        rects.append((int(CENTER_X - half), int(y), int(2 * half) + 1, step))
        y += step
    return rects


def _half_width(dy):
    """Approximate half-width of the body at height dy from its center."""
    if abs(dy) >= RY:
        return 6.0 if RY <= dy <= RY + 8 else 0.0    # the knot, or nothing
    return max(6.0, RX * math.sqrt(1 - (dy / RY) ** 2))


def _draw_string(cr, x0, y0, tilt):
    """A thin curly string that trails behind when the balloon leans."""
    length = HEIGHT - y0 - 8
    x1 = x0 + tilt * 60
    cr.save()
    cr.set_source_rgba(*STRING_RGBA)
    cr.set_line_width(1.3)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(x0, y0)
    cr.curve_to(x0 - 9 + tilt * 10, y0 + length * 0.3,
                x1 + 9 + tilt * 30, y0 + length * 0.62,
                x1, y0 + length)
    cr.stroke()
    cr.restore()


def _draw_knot(cr, palette):
    cr.move_to(-5.5, RY + 7)
    cr.line_to(5.5, RY + 7)
    cr.line_to(0, RY - 2)
    cr.close_path()
    cr.set_source_rgb(*palette.dark)
    cr.fill()


def _body_path(cr):
    """Egg shape, rounder on top and narrowing toward the knot."""
    cr.move_to(0, -RY)
    cr.curve_to(RX * 0.56, -RY, RX, -RY * 0.56, RX, -RY * 0.08)
    cr.curve_to(RX, RY * 0.46, RX * 0.46, RY * 0.92, 0, RY)
    cr.curve_to(-RX * 0.46, RY * 0.92, -RX, RY * 0.46, -RX, -RY * 0.08)
    cr.curve_to(-RX, -RY * 0.56, -RX * 0.56, -RY, 0, -RY)
    cr.close_path()


def _draw_body(cr, palette):
    _body_path(cr)
    shade = cairo.RadialGradient(-RX * 0.35, -RY * 0.45, 2, 0, 0, RY * 1.25)
    shade.add_color_stop_rgb(0.0, *palette.light)
    shade.add_color_stop_rgb(0.55, *palette.base)
    shade.add_color_stop_rgb(1.0, *palette.dark)
    cr.set_source(shade)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 0.16)    # faint rim, so it shows on dark desktops
    cr.set_line_width(1.2)
    cr.stroke()
    cr.save()                            # soft highlight on the upper left
    cr.translate(-RX * 0.42, -RY * 0.5)
    cr.rotate(-0.55)
    cr.scale(RX * 0.2, RY * 0.3)
    glow = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    glow.add_color_stop_rgba(0, 1, 1, 1, palette.gloss)
    glow.add_color_stop_rgba(1, 1, 1, 1, 0)
    cr.set_source(glow)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


def _draw_face(cr, palette, squint):
    cr.set_source_rgb(*palette.face)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    eye_y = -RY * 0.1
    for x in (-RX * 0.34, RX * 0.34):
        if squint:
            cr.set_line_width(2.8)
            cr.move_to(x - 5, eye_y + 2)
            cr.line_to(x, eye_y - 3)
            cr.line_to(x + 5, eye_y + 2)
            cr.stroke()
        else:
            cr.save()
            cr.translate(x, eye_y)
            cr.scale(4.2, 6.0)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            cr.fill()
    cr.set_line_width(3.0)
    cr.arc(0, RY * 0.05, RX * 0.36, math.radians(25), math.radians(155))
    cr.stroke()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_physics tests.test_balloon_art -v`
Expected: `Ran 8 tests` and `OK`.

- [ ] **Step 6: Add the preview tool**

`tools/render_preview.py`:

```python
"""Render every balloon color in several poses to PNG contact sheets.

    /usr/bin/python3 tools/render_preview.py [OUTDIR]
"""
import os
import sys

import cairo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from hourtracker import balloon_art as art  # noqa: E402

POSES = {
    "rest": {},
    "squished": {"squash": 0.22, "squint": True},
    "stretched": {"squash": -0.15},
    "lean_left": {"tilt": -0.3},
    "lean_right": {"tilt": 0.3},
}
BACKGROUNDS = {"dark": (0.12, 0.12, 0.13), "light": (0.96, 0.96, 0.95)}
SCALE = 2


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    for bg_name, bg in BACKGROUNDS.items():
        for color, palette in art.PALETTES.items():
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                         art.WIDTH * SCALE * len(POSES),
                                         art.HEIGHT * SCALE)
            cr = cairo.Context(surface)
            cr.set_source_rgb(*bg)
            cr.paint()
            cr.scale(SCALE, SCALE)
            for i, pose in enumerate(POSES.values()):
                cr.save()
                cr.translate(i * art.WIDTH, 0)
                art.draw_balloon(cr, palette, **pose)
                cr.restore()
            path = os.path.join(outdir, f"balloon_{color}_{bg_name}.png")
            surface.write_to_png(path)
            print(path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/previews")
```

- [ ] **Step 7: Look at the balloon**

Run: `/usr/bin/python3 tools/render_preview.py build/previews`
Expected: 8 PNG paths printed. Open `build/previews/balloon_matte_black_dark.png` and
`balloon_matte_black_light.png`. Check: a charcoal egg-shaped balloon with a soft
highlight and a faint rim visible on the dark background, white oval eyes and a
smile, squinting `^ ^` eyes in the squished pose, a knot, and a string that trails
opposite the lean. If anything looks off (clipped string, face off-center),
adjust the constants in `balloon_art.py` and re-run the tests and the preview.

- [ ] **Step 8: Commit**

```bash
git add hourtracker/physics.py hourtracker/balloon_art.py tools/render_preview.py tests/test_physics.py tests/test_balloon_art.py
git commit -m "feat: draw the balloon with Cairo and add spring physics" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Floating window base

**Files:**
- Create: `hourtracker/floating.py`
- Test: `tests/test_floating.py`

**Interfaces:**
- Consumes: `Settings` (Task 4) through `settings[key]` and `settings[key] = value`.
- Produces (`hourtracker.floating`): `DRAG_THRESHOLD = 4`;
  `clamp_to_workareas(x, y, width, height, areas) -> tuple[x, y]`;
  `workareas(display) -> list[tuple[int, int, int, int]]` (primary monitor first);
  `FloatingWindow(settings, pos_key, default_pos)` (a `Gtk.Window`), where
  `default_pos(width, height, area) -> (x, y)`. It has `place()` and the override
  hooks `on_click(event)` and `on_menu(event)`. It clears its background to
  transparent in its first `draw` handler, and subclasses connect their own `draw`
  after that.

- [ ] **Step 1: Write the failing tests**

`tests/test_floating.py`:

```python
import unittest

from hourtracker.floating import clamp_to_workareas

LAPTOP = (67, 32, 1853, 1168)      # the real layout: dock on the left, top bar above,
MONITOR = (1920, 0, 1920, 1080)    # and an external monitor to the right
AREAS = [LAPTOP, MONITOR]


class ClampTest(unittest.TestCase):
    def test_a_visible_spot_is_kept(self):
        self.assertEqual(clamp_to_workareas(500, 400, 100, 50, AREAS), (500, 400))

    def test_behind_the_dock_moves_right(self):
        self.assertEqual(clamp_to_workareas(10, 400, 100, 50, AREAS), (67, 400))

    def test_off_the_right_edge_comes_back(self):
        self.assertEqual(clamp_to_workareas(3900, 100, 100, 50, AREAS), (3740, 100))

    def test_below_the_shorter_monitor_moves_up(self):
        self.assertEqual(clamp_to_workareas(2500, 1150, 100, 50, AREAS), (2500, 1030))

    def test_unplugged_monitor_falls_back_to_the_laptop(self):
        self.assertEqual(clamp_to_workareas(2500, 300, 100, 50, [LAPTOP]), (1820, 300))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_floating -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hourtracker.floating'`.

- [ ] **Step 3: Write the implementation**

`hourtracker/floating.py`:

```python
"""Borderless windows that float above everything, on every workspace.

GNOME on Wayland won't let apps place their own windows or keep them on top,
so the app runs through XWayland (GDK_BACKEND=x11, set in __main__), where
both still work.
"""
import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

DRAG_THRESHOLD = 4      # pixels a press may wander before it becomes a drag


def clamp_to_workareas(x, y, width, height, areas):
    """Move a window at (x, y) so it sits fully inside the work area nearest
    its center. `areas` is a list of (x, y, width, height)."""
    cx, cy = x + width / 2, y + height / 2

    def distance(area):
        ax, ay, aw, ah = area
        dx = max(ax - cx, 0, cx - (ax + aw))
        dy = max(ay - cy, 0, cy - (ay + ah))
        return dx * dx + dy * dy

    ax, ay, aw, ah = min(areas, key=distance)
    return (max(ax, min(x, ax + aw - width)), max(ay, min(y, ay + ah - height)))


def workareas(display):
    """Work areas (screen minus top bar and dock) of all monitors, primary first."""
    monitors = [display.get_monitor(i) for i in range(display.get_n_monitors())]
    primary = display.get_primary_monitor() or monitors[0]
    monitors.sort(key=lambda monitor: monitor != primary)
    return [(r.x, r.y, r.width, r.height) for r in (m.get_workarea() for m in monitors)]


class FloatingWindow(Gtk.Window):
    """Transparent, undecorated, always on top, on every workspace, and never
    focused. Tells a click from a drag and remembers where it was left.

    Subclasses override on_click(event) and on_menu(event)."""

    def __init__(self, settings, pos_key, default_pos):
        super().__init__()
        self._settings = settings
        self._pos_key = pos_key
        self._default_pos = default_pos     # (width, height, area) -> (x, y)
        self._press = None                  # (x_root, y_root) while button 1 is down
        self._save_id = 0
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_app_paintable(True)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.stick()
        visual = self.get_screen().get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.BUTTON1_MOTION_MASK)
        self.connect("draw", self._clear)
        self.connect("button-press-event", self._on_press)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("button-release-event", self._on_release)
        self.connect("configure-event", self._on_configure)
        self.get_screen().connect("monitors-changed", lambda _screen: self.place())

    def place(self):
        """Move to the saved spot (or the default one), kept on-screen."""
        width, height = self.get_size()
        areas = workareas(self.get_display())
        saved = self._settings[self._pos_key]
        x, y = saved if saved else self._default_pos(width, height, areas[0])
        x, y = clamp_to_workareas(x, y, width, height, areas)
        self.move(int(x), int(y))

    def on_click(self, event):
        """Button 1 was pressed and released without dragging."""

    def on_menu(self, event):
        """Right-click."""

    @staticmethod
    def _clear(_widget, cr):
        cr.save()
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.restore()
        return False

    def _on_press(self, _widget, event):
        if event.type != Gdk.EventType.BUTTON_PRESS:    # skip double-click extras
            return True
        if event.button == Gdk.BUTTON_SECONDARY:
            self.on_menu(event)
            return True
        if event.button == Gdk.BUTTON_PRIMARY:
            self._press = (event.x_root, event.y_root)
            return True
        return False

    def _on_motion(self, _widget, event):
        if self._press is None:
            return False
        x0, y0 = self._press
        if max(abs(event.x_root - x0), abs(event.y_root - y0)) > DRAG_THRESHOLD:
            self._press = None
            self.begin_move_drag(Gdk.BUTTON_PRIMARY, int(x0), int(y0), event.time)
        return True

    def _on_release(self, _widget, event):
        if event.button == Gdk.BUTTON_PRIMARY and self._press is not None:
            self._press = None
            self.on_click(event)
            return True
        return False

    def _on_configure(self, _widget, _event):
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(600, self._save_position)
        return False

    def _save_position(self):
        self._save_id = 0
        self._settings[self._pos_key] = list(self.get_position())
        return GLib.SOURCE_REMOVE
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_floating -v`
Expected: `Ran 5 tests` and `OK`.

- [ ] **Step 5: Commit**

```bash
git add hourtracker/floating.py tests/test_floating.py
git commit -m "feat: add the floating window base with drag, click, and position memory" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Balloon window

**Files:**
- Create: `hourtracker/balloon.py`, `tools/snapshot.py`

**Interfaces:**
- Consumes: `FloatingWindow` (Task 7); `balloon_art` and `Spring` (Task 6);
  `Settings` keys `balloon_pos` and `balloon_color` (Task 4).
- Produces (`hourtracker.balloon`): `BalloonWindow(settings, on_hide)`, where
  `on_hide: () -> None` runs when the user picks "Hide balloon". The window title is
  `Hour Tracker balloon`. Also `default_position(width, height, area)`.
- Produces (`tools/snapshot.py`): `TARGETS` registry, the `@target` decorator,
  `scratch_settings()`, and the `balloon` target. Usage:
  `/usr/bin/python3 tools/snapshot.py TARGET OUT.png`.

- [ ] **Step 1: Check that GTK can hand Cairo contexts to Python**

Run: `/usr/bin/python3 -c "import gi; gi.require_foreign('cairo'); print('ok')"`
Expected: `ok`. If it fails, stop and ask the user to run
`sudo apt install python3-gi-cairo`.

- [ ] **Step 2: Write the balloon window**

`hourtracker/balloon.py`:

```python
"""The fidget balloon: drag it around and click it to squish it. It has
nothing to do with the timer."""
import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import balloon_art as art
from .floating import FloatingWindow
from .physics import Spring

SQUISH_KICK = 3.2          # velocity added per click
SQUISH_MAX = 4.0           # caps stacked clicks (peak squash about 0.27)
LEAN_PER_SPEED = 0.0003    # radians of lean per pixel/second of drag speed
MAX_LEAN = 0.4


def default_position(width, height, area):
    ax, ay, aw, ah = area
    return ax + aw - width - 48, ay + ah - height - 24


class BalloonWindow(FloatingWindow):
    def __init__(self, settings, on_hide):
        super().__init__(settings, "balloon_pos", default_position)
        self._on_hide = on_hide
        self.squash = Spring(stiffness=220, damping=7, limit=0.3)
        self.lean = Spring(stiffness=60, damping=6, limit=MAX_LEAN)
        self._frame_id = 0
        self._last_frame = None
        self._last_move = None      # (x, time) of the previous window position
        self._speed = 0.0
        self._still_id = 0
        self._menu = None
        self.set_title("Hour Tracker balloon")
        self.set_size_request(art.WIDTH, art.HEIGHT)
        self.connect("draw", self._on_draw)
        self.connect("realize", self._on_realize)
        self.connect("configure-event", self._on_moved)

    # Clicks and drags ---------------------------------------------------

    def on_click(self, _event):
        self.squash.kick(SQUISH_KICK, SQUISH_MAX)
        self._animate()

    def _on_moved(self, _widget, event):
        """While being dragged, lean away from the motion like a real balloon."""
        now = GLib.get_monotonic_time() / 1e6
        if self._last_move is not None:
            x0, t0 = self._last_move
            if 0 < now - t0 < 0.2 and event.x != x0:
                speed = (event.x - x0) / (now - t0)
                self._speed = 0.6 * self._speed + 0.4 * speed
                self.lean.target = max(-MAX_LEAN,
                                       min(MAX_LEAN, -self._speed * LEAN_PER_SPEED))
                self._animate()
        self._last_move = (event.x, now)
        if self._still_id:
            GLib.source_remove(self._still_id)
        self._still_id = GLib.timeout_add(120, self._on_still)
        return False

    def _on_still(self):
        """Stopped moving: swing back upright."""
        self._still_id = 0
        self._speed = 0.0
        self.lean.target = 0.0
        self._animate()
        return GLib.SOURCE_REMOVE

    # Animation, only while something moves -------------------------------

    def _animate(self):
        if not self._frame_id:
            self._last_frame = None
            self._frame_id = self.add_tick_callback(self._on_frame)

    def _on_frame(self, _widget, clock):
        now = clock.get_frame_time() / 1e6
        dt = 0.0 if self._last_frame is None else min(now - self._last_frame, 0.05)
        self._last_frame = now
        self.squash.step(dt)
        self.lean.step(dt)
        done = self.squash.settled and self.lean.settled and not self._still_id
        if done:
            self.squash.settle()
            self.lean.settle()
        self.queue_draw()
        if done:
            self._frame_id = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _on_draw(self, _widget, cr):
        palette = art.PALETTES.get(self._settings["balloon_color"],
                                   art.PALETTES[art.DEFAULT_COLOR])
        art.draw_balloon(cr, palette, squash=self.squash.value, tilt=self.lean.value,
                         squint=self.squash.value > 0.08)
        return False

    def _on_realize(self, _widget):
        rects = [cairo.RectangleInt(*rect) for rect in art.input_rects()]
        self.input_shape_combine_region(cairo.Region(rects))

    # Menu ---------------------------------------------------------------

    def on_menu(self, event):
        menu = Gtk.Menu()
        color_item = Gtk.MenuItem(label="Color")
        colors = Gtk.Menu()
        group = None
        for key, palette in art.PALETTES.items():
            item = Gtk.RadioMenuItem(label=palette.label)
            if group is None:
                group = item
            else:
                item.join_group(group)
            item.set_active(key == self._settings["balloon_color"])
            item.connect("toggled", self._on_color, key)
            colors.append(item)
        color_item.set_submenu(colors)
        menu.append(color_item)
        hide = Gtk.MenuItem(label="Hide balloon")
        hide.connect("activate", lambda _item: self._on_hide())
        menu.append(hide)
        menu.show_all()
        self._menu = menu                   # keep it alive while it's open
        menu.popup_at_pointer(event)

    def _on_color(self, item, key):
        if item.get_active():
            self._settings["balloon_color"] = key
            self.queue_draw()
```

- [ ] **Step 3: Write the snapshot tool with a balloon target**

`tools/snapshot.py`:

```python
"""Show one window for a moment and save a PNG of it, for visual checks.

    /usr/bin/python3 tools/snapshot.py TARGET OUT.png

Each target function builds, shows, and returns a window.
"""
import os
import sys
import tempfile

os.environ["GDK_BACKEND"] = "x11"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import gi  # noqa: E402

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from hourtracker.settings import Settings  # noqa: E402

TARGETS = {}


def target(fn):
    TARGETS[fn.__name__] = fn
    return fn


def scratch_settings():
    return Settings(os.path.join(tempfile.mkdtemp(), "settings.json"))


@target
def balloon():
    from hourtracker.balloon import BalloonWindow
    window = BalloonWindow(scratch_settings(), on_hide=lambda: None)
    window.place()
    window.show_all()
    return window


def capture(window, path):
    gdk_window = window.get_window()
    width, height = gdk_window.get_width(), gdk_window.get_height()
    pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, width, height)
    pixbuf.savev(path, "png", [], [])
    print(f"{path}: {pixbuf.get_width()}x{pixbuf.get_height()}")


def main(name, path):
    window = TARGETS[name]()

    def shoot():
        capture(window, path)
        Gtk.main_quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(700, shoot)
    Gtk.main()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

- [ ] **Step 4: Snapshot the balloon**

Run: `mkdir -p build && /usr/bin/python3 tools/snapshot.py balloon build/balloon.png`
Expected: `build/balloon.png: 300x430` (logical 150×215 at scale 2). Open the PNG and
check: the balloon on a transparent background, with no black or white rectangle
around it.

- [ ] **Step 5: Run the whole suite**

Run: `/usr/bin/python3 -m unittest -v`
Expected: `Ran 72 tests` and `OK`.

- [ ] **Step 6: Commit**

```bash
git add hourtracker/balloon.py tools/snapshot.py
git commit -m "feat: add the floating balloon toy that squishes and leans" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Timer pill

**Files:**
- Create: `hourtracker/pill.py`
- Modify: `tools/snapshot.py` (add pill targets after the `balloon` target)

**Interfaces:**
- Consumes: `FloatingWindow` (Task 7); `fmt_clock`, `fmt_duration` (Task 1); an
  `Away`-like object with `.seconds` (Task 3).
- Produces (`hourtracker.pill`): `PillWindow(settings, on_toggle, on_open_stats,
  on_answer, menu_factory)`, where `on_toggle: () -> None`,
  `on_open_stats: () -> None`, `on_answer: (kind: str, yes: bool) -> None` with kind
  `"away"` or `"nudge"`, and `menu_factory: () -> Gtk.Menu`. Methods:
  `update(running: bool, today_seconds: float, away=None, nudge_since=None)` and
  `buzz()`. The window title is `Hour Tracker pill`. Also `default_position`.

- [ ] **Step 1: Write the pill**

`hourtracker/pill.py`:

```python
"""The floating timer pill: play/pause, today's total, and a row for the two
questions (were you away studying? did you forget to start?)."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .floating import FloatingWindow
from .stats import fmt_clock, fmt_duration

CSS = b"""
.pill {
    background-color: rgba(28, 28, 30, 0.9);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 16px;
    padding: 3px 12px 3px 3px;
    color: #eeeeee;
}
.pill-time { font-size: 13px; font-weight: bold; }
.pill.paused .pill-time { color: rgba(238, 238, 238, 0.55); }
.pill button {
    min-width: 24px;
    min-height: 24px;
    padding: 0 6px;
    border-radius: 12px;
    border: none;
    box-shadow: none;
    background: none;
    color: #eeeeee;
    font-size: 12px;
}
.pill button:hover { background-color: rgba(255, 255, 255, 0.14); }
.pill .answer { background-color: rgba(255, 255, 255, 0.10); margin-top: 4px; }
.pill .question { font-size: 12px; margin: 6px 2px 0 9px; }
"""

BUZZ_OFFSETS = (7, -7, 6, -6, 4, -4, 2, 0)     # pixels, 40 ms apart


def default_position(width, height, area):
    ax, ay, aw, ah = area
    return ax + aw - width - 24, ay + 16


class PillWindow(FloatingWindow):
    def __init__(self, settings, on_toggle, on_open_stats, on_answer, menu_factory):
        super().__init__(settings, "pill_pos", default_position)
        self._on_open_stats = on_open_stats
        self._on_answer = on_answer
        self._menu_factory = menu_factory
        self._menu = None
        self._question = None           # "away", "nudge", or None
        self._buzz_id = 0
        self.set_title("Hour Tracker pill")

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._box.get_style_context().add_class("pill")
        top = Gtk.Box(spacing=6)
        self._play = Gtk.Button()
        self._play.set_relief(Gtk.ReliefStyle.NONE)
        self._play.set_can_focus(False)
        self._play.connect("clicked", lambda _button: on_toggle())
        self._icon = Gtk.Image()
        self._play.add(self._icon)
        self._time = Gtk.Label(label="0:00")
        self._time.get_style_context().add_class("pill-time")
        top.pack_start(self._play, False, False, 0)
        top.pack_start(self._time, False, False, 0)
        self._box.pack_start(top, False, False, 0)

        self._revealer = Gtk.Revealer()
        self._revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._revealer.connect("notify::child-revealed", self._on_revealed)
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._question_label = Gtk.Label(xalign=0)
        self._question_label.get_style_context().add_class("question")
        buttons = Gtk.Box(spacing=6, homogeneous=True)
        buttons.set_margin_start(6)
        buttons.set_margin_bottom(3)
        self._yes = self._answer_button(True)
        self._no = self._answer_button(False)
        buttons.pack_start(self._yes, True, True, 0)
        buttons.pack_start(self._no, True, True, 0)
        row.pack_start(self._question_label, False, False, 0)
        row.pack_start(buttons, False, False, 0)
        self._revealer.add(row)
        self._box.pack_start(self._revealer, False, False, 0)
        self.add(self._box)

    def _answer_button(self, yes):
        button = Gtk.Button()
        button.set_can_focus(False)
        button.get_style_context().add_class("answer")
        button.connect("clicked", lambda _button: self._on_answer(self._question, yes))
        return button

    def update(self, running, today_seconds, away=None, nudge_since=None):
        """Show the timer state and whichever question is open."""
        icon = ("media-playback-pause-symbolic" if running
                else "media-playback-start-symbolic")
        self._icon.set_from_icon_name(icon, Gtk.IconSize.BUTTON)
        self._play.set_tooltip_text("Pause" if running else "Start")
        self._time.set_text(fmt_clock(today_seconds))
        style = self._box.get_style_context()
        if running:
            style.remove_class("paused")
        else:
            style.add_class("paused")
        if away is not None:
            self._ask("away", f"Away {fmt_duration(away.seconds)}. Were you studying?",
                      "Yes", "No")
        elif nudge_since is not None:
            self._ask("nudge", "Studying? The timer is off.", "Start", "Not now")
        else:
            self._question = None
            self._revealer.set_reveal_child(False)

    def _ask(self, kind, text, yes, no):
        self._question = kind
        self._question_label.set_text(text)
        self._yes.set_label(yes)
        self._no.set_label(no)
        self._revealer.set_reveal_child(True)

    def _on_revealed(self, revealer, _pspec):
        if not revealer.get_child_revealed():
            self.resize(1, 1)           # shrink back to just the pill

    def buzz(self):
        """Shake side to side, like a phone buzzing."""
        if self._buzz_id or not self.get_visible():
            return
        x, y = self.get_position()
        offsets = iter(BUZZ_OFFSETS)

        def step():
            dx = next(offsets, None)
            if dx is None:
                self._buzz_id = 0
                return GLib.SOURCE_REMOVE
            self.move(x + dx, y)
            return GLib.SOURCE_CONTINUE

        self._buzz_id = GLib.timeout_add(40, step)

    def on_click(self, _event):
        self._on_open_stats()

    def on_menu(self, event):
        self._menu = self._menu_factory()
        self._menu.popup_at_pointer(event)
```

- [ ] **Step 2: Add pill targets to the snapshot tool**

In `tools/snapshot.py`, add these functions right after the `balloon` target:

```python
def _pill(**state):
    from hourtracker.pill import PillWindow
    window = PillWindow(scratch_settings(), on_toggle=lambda: None,
                        on_open_stats=lambda: None,
                        on_answer=lambda kind, yes: None, menu_factory=lambda: None)
    window.update(**state)
    window.place()
    window.show_all()
    return window


@target
def pill():
    return _pill(running=False, today_seconds=84 * 60)


@target
def pill_running():
    return _pill(running=True, today_seconds=84 * 60)


@target
def pill_away():
    from hourtracker.tracker import Away
    return _pill(running=True, today_seconds=84 * 60, away=Away(0, 23 * 60))


@target
def pill_nudge():
    return _pill(running=False, today_seconds=0, nudge_since=0)
```

- [ ] **Step 3: Snapshot the pill in each state**

Run:

```bash
for t in pill pill_running pill_away pill_nudge; do /usr/bin/python3 tools/snapshot.py $t build/$t.png; done
```

Expected: four PNG paths. Open them and check:
- `pill`: a dark rounded pill with a play icon and a dimmed `1:24`.
- `pill_running`: a pause icon and a bright `1:24`.
- `pill_away`: `Away 23m. Were you studying?` with `Yes` and `No`.
- `pill_nudge`: `Studying? The timer is off.` with `Start` and `Not now`.

There should be no square background behind the rounded corners.

- [ ] **Step 4: Commit**

```bash
git add hourtracker/pill.py tools/snapshot.py
git commit -m "feat: add the floating timer pill with question row and buzz" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Forgot-to-start notification

**Files:**
- Create: `hourtracker/notifier.py`

**Interfaces:**
- Consumes: `APP_NAME` (Task 1); libnotify (`Notify` 0.7).
- Produces (`hourtracker.notifier.Notifier`): `Notifier(on_answer)`, where
  `on_answer: (start: bool) -> None`. Methods: `show_nudge()`, which replaces any
  open one, and `close()`.

- [ ] **Step 1: Write the notifier**

`hourtracker/notifier.py`:

```python
"""The forgot-to-start notification. GNOME shows it as a banner with two
buttons, and keeps it in the notification list until answered."""
import logging

import gi

gi.require_version("Notify", "0.7")
from gi.repository import GLib, Notify  # noqa: E402

from . import APP_NAME

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, on_answer):
        self._on_answer = on_answer         # called with True (start) or False
        self._current = None
        self._ready = Notify.init(APP_NAME)

    def show_nudge(self):
        if not self._ready:
            return
        self.close()
        note = Notify.Notification.new("Studying?", "Your study timer is off.",
                                       "media-playback-start-symbolic")
        note.add_action("start", "Start", self._on_action, None)
        note.add_action("later", "Not now", self._on_action, None)
        note.connect("closed", self._on_closed)
        try:
            note.show()
            self._current = note
        except GLib.Error as err:
            log.warning("could not show a notification: %s", err.message)

    def close(self):
        note, self._current = self._current, None
        if note is not None:
            try:
                note.close()
            except GLib.Error:
                pass

    def _on_action(self, note, action, *_data):
        if note is self._current:
            self._current = None
        self._on_answer(action == "start")

    def _on_closed(self, note):
        if note is self._current:
            self._current = None
```

- [ ] **Step 2: Try it on the desktop**

Run:

```bash
/usr/bin/python3 - <<'EOF'
import sys; sys.path.insert(0, ".")
from gi.repository import GLib
from hourtracker.notifier import Notifier
loop = GLib.MainLoop()
def answered(start):
    print("answered:", "start" if start else "not now"); loop.quit()
n = Notifier(answered)
n.show_nudge()
GLib.timeout_add_seconds(20, loop.quit)
loop.run()
EOF
```

Expected: a GNOME notification "Studying?" / "Your study timer is off." with
**Start** and **Not now** buttons. Clicking one prints `answered: start` or
`answered: not now`. If nobody clicks within 20 s, the script ends silently.
That's fine.

- [ ] **Step 3: Commit**

```bash
git add hourtracker/notifier.py
git commit -m "feat: add the forgot-to-start notification" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Stats window

**Files:**
- Create: `hourtracker/stats_window.py`
- Modify: `tools/snapshot.py` (add `stats` and `stats_month` targets)
- Test: `tests/test_stats_window.py`

**Interfaces:**
- Consumes: `Tracker.day_totals` and `Tracker.clock` (Task 3); `stats.period`,
  `shift`, `period_label`, `fmt_duration`, `local_date` (Task 1).
- Produces (`hourtracker.stats_window`): `nice_max(values) -> float`;
  `bar_index(x, width, count) -> int | None`;
  `StatsWindow(tracker, first_weekday)` with `refresh()`, `set_view("week" | "month")`,
  and `today() -> date`. Closing it hides it, and while shown it refreshes every 30 s.

- [ ] **Step 1: Write the failing tests**

`tests/test_stats_window.py`:

```python
import unittest

from hourtracker.stats_window import bar_index, nice_max


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_stats_window -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hourtracker.stats_window'`.

- [ ] **Step 3: Write the stats window**

`hourtracker/stats_window.py`:

```python
"""The stats window: today, this week, this month, and a bar chart you can
switch between weeks and months."""
import math
from datetime import timedelta

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import APP_NAME
from .stats import fmt_duration, local_date, period, period_label, shift

CSS = b"""
.card { background-color: alpha(@theme_fg_color, 0.07); border-radius: 10px; padding: 10px 12px; }
.card-caption { font-size: 12px; opacity: 0.65; }
.card-value { font-size: 20px; font-weight: bold; }
"""
LABEL_HEIGHT, HEAD_HEIGHT = 18, 16      # chart margins below and above the bars


def nice_max(values) -> float:
    """Top of the chart scale: the next whole hour above the tallest bar (1h minimum)."""
    top = max(values, default=0.0)
    return max(3600.0, math.ceil(top / 3600.0) * 3600.0)


def bar_index(x, width, count):
    """Which bar a horizontal position falls on, or None outside the chart."""
    if count <= 0 or not 0 <= x < width:
        return None
    return int(x / (width / count))


def _rounded_top_rect(cr, x, y, w, h, r):
    r = min(r, h)
    cr.move_to(x, y + h)
    cr.line_to(x, y + r)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.line_to(x + w - r, y)
    cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
    cr.line_to(x + w, y + h)
    cr.close_path()


class StatsWindow(Gtk.Window):
    def __init__(self, tracker, first_weekday):
        super().__init__(title=APP_NAME)
        self._tracker = tracker
        self._first_weekday = first_weekday
        self._view = "week"
        self._anchor = self.today()
        self._first = self._anchor
        self._totals = []               # seconds per day in the shown period
        self._refresh_id = 0
        self.set_default_size(460, 380)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.set_titlebar(Gtk.HeaderBar(title=APP_NAME, show_close_button=True))

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        cards = Gtk.Box(spacing=10, homogeneous=True)
        self._today_value = self._card(cards, "Today")
        self._week_value = self._card(cards, "This week")
        self._month_value = self._card(cards, "This month")
        content.pack_start(cards, False, False, 0)

        nav = Gtk.Box(spacing=4)
        self._prev = self._icon_button("go-previous-symbolic", lambda: self._move(-1))
        self._next = self._icon_button("go-next-symbolic", lambda: self._move(1))
        self._label = Gtk.Label()
        nav.pack_start(self._prev, False, False, 0)
        nav.pack_start(self._label, False, False, 6)
        nav.pack_start(self._next, False, False, 0)
        switch = Gtk.Box()
        switch.get_style_context().add_class("linked")
        week = Gtk.RadioButton(label="Week", draw_indicator=False)
        month = Gtk.RadioButton(label="Month", draw_indicator=False, group=week)
        week.connect("toggled", self._on_view, "week")
        month.connect("toggled", self._on_view, "month")
        self._view_buttons = {"week": week, "month": month}
        switch.pack_start(week, False, False, 0)
        switch.pack_start(month, False, False, 0)
        nav.pack_end(switch, False, False, 0)
        content.pack_start(nav, False, False, 0)

        self._chart = Gtk.DrawingArea()
        self._chart.set_size_request(-1, 170)
        self._chart.set_has_tooltip(True)
        self._chart.connect("draw", self._draw_chart)
        self._chart.connect("query-tooltip", self._on_tooltip)
        content.pack_start(self._chart, True, True, 0)
        self.add(content)

        self.connect("delete-event", self._on_close)
        self.connect("show", lambda _window: self._start_refreshing())
        self.connect("hide", lambda _window: self._stop_refreshing())

    # Building blocks ----------------------------------------------------

    def _card(self, parent, caption):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.get_style_context().add_class("card")
        title = Gtk.Label(label=caption, xalign=0)
        title.get_style_context().add_class("card-caption")
        value = Gtk.Label(label="0m", xalign=0)
        value.get_style_context().add_class("card-value")
        card.pack_start(title, False, False, 0)
        card.pack_start(value, False, False, 0)
        parent.pack_start(card, True, True, 0)
        return value

    def _icon_button(self, icon, callback):
        button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.connect("clicked", lambda _button: callback())
        return button

    # State --------------------------------------------------------------

    def today(self):
        return local_date(self._tracker.clock())

    def set_view(self, view):
        self._view_buttons[view].set_active(True)

    def _on_view(self, button, view):
        if button.get_active():
            self._view = view
            self._anchor = self.today()
            self.refresh()

    def _move(self, steps):
        self._anchor = shift(self._view, self._anchor, steps)
        self.refresh()

    def refresh(self):
        today = self.today()
        week_first, _ = period("week", today, self._first_weekday)
        month_first, month_days = period("month", today, self._first_weekday)
        self._today_value.set_text(fmt_duration(self._tracker.day_totals(today, 1)[0]))
        self._week_value.set_text(fmt_duration(sum(self._tracker.day_totals(week_first, 7))))
        self._month_value.set_text(
            fmt_duration(sum(self._tracker.day_totals(month_first, month_days))))
        self._first, days = period(self._view, self._anchor, self._first_weekday)
        self._totals = self._tracker.day_totals(self._first, days)
        self._label.set_text(period_label(self._view, self._first, days))
        self._next.set_sensitive(self._first + timedelta(days=days) <= today)
        self._chart.queue_draw()

    def _on_close(self, *_args):
        self.hide()
        return True

    def _start_refreshing(self):
        self.refresh()
        if not self._refresh_id:
            self._refresh_id = GLib.timeout_add_seconds(30, self._on_timer)

    def _stop_refreshing(self):
        if self._refresh_id:
            GLib.source_remove(self._refresh_id)
            self._refresh_id = 0

    def _on_timer(self):
        self.refresh()
        return GLib.SOURCE_CONTINUE

    # Chart --------------------------------------------------------------

    def _draw_chart(self, widget, cr):
        count = len(self._totals)
        if count == 0:
            return False
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        style = widget.get_style_context()
        fg = style.get_color(Gtk.StateFlags.NORMAL)
        found, accent = style.lookup_color("theme_selected_bg_color")
        if not found:
            accent = Gdk.RGBA(0.21, 0.52, 0.89, 1.0)
        top = nice_max(self._totals)
        chart_h = height - LABEL_HEIGHT - HEAD_HEIGHT
        slot = width / count
        bar_w = slot * (0.6 if count <= 7 else 0.68)
        today = self.today()

        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
        cr.rectangle(0, HEAD_HEIGHT, width, 1)
        cr.rectangle(0, HEAD_HEIGHT + chart_h, width, 1)
        cr.fill()
        self._text(cr, widget, fmt_duration(top), width, 0, fg, 0.55, "right")
        if not any(self._totals):
            self._text(cr, widget, "No study time yet", width / 2,
                       HEAD_HEIGHT + chart_h / 2 - 8, fg, 0.55, "center")

        for i, seconds in enumerate(self._totals):
            day = self._first + timedelta(days=i)
            is_today = day == today
            color = accent if is_today else fg
            if seconds > 0:
                h = max(2.0, seconds / top * chart_h)
                x = i * slot + (slot - bar_w) / 2
                _rounded_top_rect(cr, x, HEAD_HEIGHT + chart_h - h, bar_w, h,
                                  min(4.0, bar_w / 2))
                cr.set_source_rgba(color.red, color.green, color.blue,
                                   1.0 if is_today else 0.3)
                cr.fill()
            if count <= 7 or day.day in (1, 5, 10, 15, 20, 25) or i == count - 1:
                text = f"{day:%a}" if count <= 7 else str(day.day)
                self._text(cr, widget, text, i * slot + slot / 2,
                           height - LABEL_HEIGHT + 2, color,
                           1.0 if is_today else 0.6, "center")
        return False

    def _text(self, cr, widget, text, x, y, color, alpha, align):
        layout = widget.create_pango_layout(text)
        font = layout.get_context().get_font_description().copy()
        font.set_size(9 * Pango.SCALE)
        layout.set_font_description(font)
        text_w, _text_h = layout.get_pixel_size()
        if align == "center":
            x -= text_w / 2
        elif align == "right":
            x -= text_w
        cr.move_to(x, y)
        cr.set_source_rgba(color.red, color.green, color.blue, alpha)
        PangoCairo.show_layout(cr, layout)

    def _on_tooltip(self, widget, x, _y, _keyboard, tooltip):
        index = bar_index(x, widget.get_allocated_width(), len(self._totals))
        if index is None:
            return False
        day = self._first + timedelta(days=index)
        tooltip.set_text(f"{day:%a, %b} {day.day} · {fmt_duration(self._totals[index])}")
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_stats_window -v`
Expected: `Ran 2 tests` and `OK`.

- [ ] **Step 5: Add stats targets to the snapshot tool**

In `tools/snapshot.py`, add after the pill targets:

```python
def _sample_stats_window():
    import random
    import time
    from datetime import timedelta
    from hourtracker.stats import SUNDAY, local_date, local_midnight
    from hourtracker.stats_window import StatsWindow
    from hourtracker.store import Store
    from hourtracker.tracker import Tracker
    store = Store(":memory:")
    today = local_date(time.time())
    rng = random.Random(7)
    for back in range(1, 40):
        start = local_midnight(today - timedelta(days=back)) + 9 * 3600
        store.extend(store.begin(start), start + rng.randint(0, 5 * 3600))
    store.extend(store.begin(time.time() - 5400), time.time())
    return StatsWindow(Tracker(store), SUNDAY)


@target
def stats():
    window = _sample_stats_window()
    window.show_all()
    return window


@target
def stats_month():
    window = _sample_stats_window()
    window.show_all()
    window.set_view("month")
    return window
```

- [ ] **Step 6: Snapshot the stats window**

Run:

```bash
/usr/bin/python3 tools/snapshot.py stats build/stats.png && /usr/bin/python3 tools/snapshot.py stats_month build/stats_month.png
```

Expected: two PNG paths. Open them and check: the header bar reads "Hour Tracker";
three cards (Today `1h 30m`, This week, This month); the period label (for
example `Sep 27 – Oct 3`, or `September 2026` in the month shot); `‹ ›` buttons;
a linked Week and Month toggle; bars with today's in the accent color; day labels
(`Sun`…`Sat`, or 1, 5, 10, …). The whole window is in the dark theme.

- [ ] **Step 7: Commit**

```bash
git add hourtracker/stats_window.py tests/test_stats_window.py tools/snapshot.py
git commit -m "feat: add the stats window with totals and a week/month chart" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Wire up the app, then smoke test and push

**Files:**
- Create: `hourtracker/app.py`, `hourtracker/__main__.py`, `hour-tracker`,
  `tools/check_windows.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `hourtracker.app.HourTrackerApp` (a `Gtk.Application`);
  `python3 -m hourtracker`; the executable launcher `./hour-tracker`;
  `tools/check_windows.py`, which exits 0 when the pill and balloon are above,
  sticky, and skip the taskbar and pager, and the balloon has an input shape.

- [ ] **Step 1: Write the app**

`hourtracker/app.py`:

```python
"""Hour Tracker: wires the tracker to the pill, the balloon, the stats window,
and the forgot-to-start notification."""
import os
import signal

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import APP_ID, autostart
from .balloon import BalloonWindow
from .idle import IdleMonitor
from .notifier import Notifier
from .pill import PillWindow
from .settings import Settings
from .stats import local_date, resolve_first_weekday
from .stats_window import StatsWindow
from .store import Store
from .tracker import TICK_SECONDS, Tracker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "hour-tracker")
ICON = os.path.join(ROOT, "data", "hour-tracker.svg")


def _xdg(var, fallback, *parts):
    base = os.environ.get(var) or os.path.expanduser(fallback)
    return os.path.join(base, "hour-tracker", *parts)


class HourTrackerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.tracker = None
        self._shown = False

    def do_startup(self):
        Gtk.Application.do_startup(self)
        if os.path.exists(ICON):
            Gtk.Window.set_default_icon_from_file(ICON)
        self.settings = Settings(_xdg("XDG_CONFIG_HOME", "~/.config", "settings.json"))
        self.store = Store(_xdg("XDG_DATA_HOME", "~/.local/share", "hours.db"))
        self.tracker = Tracker(self.store, idle=IdleMonitor(),
                               away_after=self.settings["away_minutes"] * 60,
                               nudge_after=self.settings["nudge_minutes"] * 60)
        self.tracker.nudge_enabled = self.settings["nudge_enabled"]
        self.tracker.on_change = self.refresh
        self.tracker.on_nudge = self._buzz
        self.notifier = Notifier(on_answer=lambda start: self.answer("nudge", start))
        self.pill = PillWindow(self.settings, on_toggle=self.tracker.toggle,
                               on_open_stats=self.show_stats, on_answer=self.answer,
                               menu_factory=self._build_menu)
        self.balloon = BalloonWindow(self.settings,
                                     on_hide=lambda: self.set_balloon_visible(False))
        self.stats = StatsWindow(self.tracker,
                                 resolve_first_weekday(self.settings["week_start"]))
        for window in (self.pill, self.balloon, self.stats):
            self.add_window(window)
        GLib.timeout_add_seconds(TICK_SECONDS, self._tick)
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_signal)

    def do_activate(self):
        if self._shown:                 # launched again: open the stats
            self.show_stats()
            return
        self._shown = True
        self.refresh()
        self.pill.place()
        self.pill.show_all()
        if self.settings["balloon_visible"]:
            self.balloon.place()
            self.balloon.show_all()

    def do_shutdown(self):
        if self.tracker is not None:
            self.tracker.on_change = lambda: None
            self.tracker.pause()        # ends a running session right now
            self.notifier.close()
            self.store.close()
        Gtk.Application.do_shutdown(self)

    def _on_signal(self):
        self.quit()
        return GLib.SOURCE_REMOVE

    # Keeping the UI current ----------------------------------------------

    def _tick(self):
        self.tracker.tick()
        self._update_pill()
        return GLib.SOURCE_CONTINUE

    def _update_pill(self):
        today = local_date(self.tracker.clock())
        self.pill.update(self.tracker.running, self.tracker.day_totals(today, 1)[0],
                         away=self.tracker.pending, nudge_since=self.tracker.nudge)

    def refresh(self):
        self._update_pill()
        if self.stats.get_visible():
            self.stats.refresh()
        if self.tracker.nudge is None:
            self.notifier.close()

    # Actions ------------------------------------------------------------

    def answer(self, kind, yes):
        if kind == "away":
            self.tracker.answer_away(studying=yes)
        elif kind == "nudge":
            self.tracker.answer_nudge(start=yes)

    def _buzz(self):
        self.pill.buzz()
        self.notifier.show_nudge()

    def show_stats(self):
        self.stats.show_all()
        self.stats.present_with_time(Gtk.get_current_event_time())

    def set_balloon_visible(self, visible):
        self.settings["balloon_visible"] = visible
        if visible:
            self.balloon.place()
            self.balloon.show_all()
        else:
            self.balloon.hide()

    def _set_nudge(self, enabled):
        self.settings["nudge_enabled"] = enabled
        self.tracker.nudge_enabled = enabled

    def _build_menu(self):
        menu = Gtk.Menu()

        def add(label, callback, active=None):
            if active is None:
                item = Gtk.MenuItem(label=label)
                item.connect("activate", lambda _item: callback())
            else:
                item = Gtk.CheckMenuItem(label=label, active=active)
                item.connect("toggled", lambda item: callback(item.get_active()))
            menu.append(item)

        add("Stats", self.show_stats)
        add("Show balloon", self.set_balloon_visible, self.balloon.get_visible())
        add("Remind me to start", self._set_nudge, self.settings["nudge_enabled"])
        add("Start at login", lambda on: autostart.set_enabled(on, LAUNCHER),
            autostart.is_enabled())
        menu.append(Gtk.SeparatorMenuItem())
        add("Quit", self.quit)
        menu.show_all()
        return menu
```

- [ ] **Step 2: Write the entry point and launcher**

`hourtracker/__main__.py`:

```python
"""Run with: /usr/bin/python3 -m hourtracker"""
import logging
import os
import sys

# The floating windows need XWayland (see floating.py). This must happen
# before GTK is imported anywhere.
os.environ["GDK_BACKEND"] = "x11"


def main():
    logging.basicConfig(level=logging.INFO,
                        format="hour-tracker: %(levelname)s %(message)s")
    import gi
    from gi.repository import GLib
    from hourtracker import PROGRAM
    GLib.set_prgname(PROGRAM)           # names the windows' WM_CLASS
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk
    Gdk.set_program_class(PROGRAM)
    from hourtracker.app import HourTrackerApp
    return HourTrackerApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
```

`hour-tracker` (then `chmod +x hour-tracker`):

```sh
#!/bin/sh
# Starts Hour Tracker with the system Python, which has the GTK bindings.
# (The python3 on PATH may be conda's, which doesn't.)
cd "$(dirname "$(readlink -f "$0")")" || exit 1
exec /usr/bin/python3 -m hourtracker "$@"
```

- [ ] **Step 3: Write the window checker**

`tools/check_windows.py`:

```python
"""Checks the running app's floating windows through X11 (smoke test).

    /usr/bin/python3 tools/check_windows.py
"""
import ctypes
import re
import subprocess
import sys

TITLES = {"Hour Tracker pill": "pill", "Hour Tracker balloon": "balloon"}
NEEDED = {"_NET_WM_STATE_ABOVE", "_NET_WM_STATE_STICKY",
          "_NET_WM_STATE_SKIP_TASKBAR", "_NET_WM_STATE_SKIP_PAGER"}
SHAPE_INPUT = 2


def find_windows():
    tree = subprocess.run(["xwininfo", "-root", "-tree"],
                          capture_output=True, text=True).stdout
    found = {}
    for line in tree.splitlines():
        match = re.match(r'\s*(0x[0-9a-f]+) "([^"]*)"', line)
        if match and match.group(2) in TITLES:
            found[TITLES[match.group(2)]] = int(match.group(1), 16)
    return found


def wm_state(xid):
    out = subprocess.run(["xprop", "-id", hex(xid), "_NET_WM_STATE"],
                         capture_output=True, text=True).stdout
    return set(re.findall(r"_NET_WM_STATE_\w+", out))


def input_rect_count(xid):
    x11 = ctypes.CDLL("libX11.so.6")
    xext = ctypes.CDLL("libXext.so.6")
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XFree.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xext.XShapeGetRectangles.restype = ctypes.c_void_p
    xext.XShapeGetRectangles.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    display = x11.XOpenDisplay(None)
    count, ordering = ctypes.c_int(), ctypes.c_int()
    rects = xext.XShapeGetRectangles(display, xid, SHAPE_INPUT,
                                     ctypes.byref(count), ctypes.byref(ordering))
    if rects:
        x11.XFree(rects)
    x11.XCloseDisplay(display)
    return count.value


def main():
    windows = find_windows()
    ok = True
    for name in ("pill", "balloon"):
        if name not in windows:
            print(f"FAIL {name}: window not found")
            ok = False
            continue
        missing = NEEDED - wm_state(windows[name])
        print(f"{'FAIL' if missing else 'ok  '} {name}: window states"
              + (f" missing {sorted(missing)}" if missing else ""))
        ok = ok and not missing
    if "balloon" in windows:
        count = input_rect_count(windows["balloon"])
        print(f"{'ok  ' if count > 1 else 'FAIL'} balloon: input shape has {count} rectangles")
        ok = ok and count > 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the whole suite**

Run: `/usr/bin/python3 -m unittest -v`
Expected: `Ran 74 tests` and `OK`.

- [ ] **Step 5: Live smoke test with throwaway data**

Run:

```bash
chmod +x hour-tracker
SCRATCH="$(mktemp -d)"
XDG_DATA_HOME="$SCRATCH/data" XDG_CONFIG_HOME="$SCRATCH/config" ./hour-tracker > "$SCRATCH/log.txt" 2>&1 &
APP_PID=$!
sleep 3
/usr/bin/python3 tools/check_windows.py; echo "check exit: $?"
./hour-tracker; sleep 2                   # second launch: opens the stats window
xwininfo -root -tree | grep -c '"Hour Tracker"'
kill -TERM "$APP_PID"; sleep 1
kill -0 "$APP_PID" 2>/dev/null && echo "still running" || echo "exited"
echo "--- log:"; cat "$SCRATCH/log.txt"
```

Expected:
- `ok   pill: window states`, `ok   balloon: window states`,
  `ok   balloon: input shape has N rectangles` (N > 1), and `check exit: 0`.
- After the second launch, the grep count is at least `1` (the stats window).
- `exited` after SIGTERM.
- A log with no tracebacks. A single idle-monitor warning is acceptable only
  outside a desktop session.

- [ ] **Step 6: Commit and push**

```bash
git add hourtracker/app.py hourtracker/__main__.py hour-tracker tools/check_windows.py
git commit -m "feat: wire up the app with the pill, balloon, stats, and buzz" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 13: Installer, icon, README, and final check

**Files:**
- Create: `install.sh`, `data/hour-tracker.svg`, `README.md`

**Interfaces:**
- Consumes: the launcher `hour-tracker` (Task 12).
- Produces: `./install.sh` writes `~/.local/share/applications/hour-tracker.desktop`,
  and `./install.sh --uninstall` removes it and the autostart entry.

- [ ] **Step 1: Write the icon**

`data/hour-tracker.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <radialGradient id="shade" cx="0.35" cy="0.3" r="0.8">
      <stop offset="0" stop-color="#57595f"/>
      <stop offset="0.55" stop-color="#2b2b30"/>
      <stop offset="1" stop-color="#111113"/>
    </radialGradient>
  </defs>
  <path d="M64 100 C58 110 70 114 64 124" stroke="#9e9ea8" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <path d="M58 100 L70 100 L64 92 Z" fill="#111113"/>
  <path d="M64 8 C83 8 100 22 100 46 C100 70 84 92 64 96 C44 92 28 70 28 46 C28 22 45 8 64 8 Z" fill="url(#shade)"/>
  <ellipse cx="50" cy="30" rx="7" ry="11" fill="#ffffff" fill-opacity="0.16" transform="rotate(-30 50 30)"/>
  <ellipse cx="52" cy="50" rx="4.5" ry="6.5" fill="#f5f5f5"/>
  <ellipse cx="76" cy="50" rx="4.5" ry="6.5" fill="#f5f5f5"/>
  <path d="M51 63 Q64 75 77 63" stroke="#f5f5f5" stroke-width="4" fill="none" stroke-linecap="round"/>
</svg>
```

- [ ] **Step 2: Write the installer**

`install.sh` (then `chmod +x install.sh`):

```sh
#!/bin/sh
# Adds Hour Tracker to the app grid. Use --uninstall to remove it again
# (your study history in ~/.local/share/hour-tracker is kept).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ENTRY="$APPS/hour-tracker.desktop"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/hour-tracker.desktop"

if [ "$1" = "--uninstall" ]; then
    rm -f "$ENTRY" "$AUTOSTART"
    echo "Removed Hour Tracker from the app grid."
    exit 0
fi

if ! /usr/bin/python3 -c "import gi; gi.require_foreign('cairo')" 2>/dev/null; then
    echo "Hour Tracker needs one more package. Install it with:"
    echo "    sudo apt install python3-gi-cairo"
    exit 1
fi

mkdir -p "$APPS"
cat > "$ENTRY" <<EOF
[Desktop Entry]
Type=Application
Name=Hour Tracker
Comment=Track your study hours, with a balloon to fidget with
Exec="$HERE/hour-tracker"
Icon=$HERE/data/hour-tracker.svg
Terminal=false
Categories=Education;Utility;
StartupWMClass=hour-tracker
EOF
echo "Installed. Open Hour Tracker from the app grid."
```

- [ ] **Step 3: Write the README**

`README.md`:

````markdown
# Hour Tracker

A minimal study-hour tracker for Ubuntu (GNOME), plus a balloon to fidget with.

- **Timer pill**: floats above your windows and shows today's study time. Click
  the play/pause button to start or pause, click the time for stats, drag it
  anywhere, and right-click for the menu.
- **Away check**: after 15+ minutes with no keyboard or mouse input (or with the
  laptop asleep), it asks whether you were studying. "No" removes that time.
- **Forgot-to-start buzz**: after 3 minutes of using the laptop with the timer
  off, the pill shakes and a notification asks if you're studying. "Start"
  counts from when you sat down.
- **Stats**: today, this week, and this month, with a week/month bar chart.
- **Balloon**: a matte black balloon you can drag around and squish. It's only a
  toy.

## Requirements

Ubuntu with GNOME (built on 26.04 with Wayland) and one extra package:

```bash
sudo apt install python3-gi-cairo
```

## Run

```bash
./hour-tracker
```

`./install.sh` adds it to the app grid, and `./install.sh --uninstall` removes it.
To start it at login, right-click the pill and turn on "Start at login".

## Your data

- Study sessions: `~/.local/share/hour-tracker/hours.db` (SQLite)
- Settings: `~/.config/hour-tracker/settings.json`

## Development

Use `/usr/bin/python3`, which has the GTK bindings. A conda or venv Python may not.

```bash
/usr/bin/python3 -m unittest -v
/usr/bin/python3 tools/render_preview.py build/previews
/usr/bin/python3 tools/snapshot.py pill build/pill.png
```

Design and plan: `docs/superpowers/`.

## Roadmap

Phase 2: focus tracking. The app will learn how long you usually stay focused and
suggest a focus/break rhythm that fits you.
````

- [ ] **Step 4: Install and check the desktop entry**

Run:

```bash
chmod +x install.sh && ./install.sh && (desktop-file-validate ~/.local/share/applications/hour-tracker.desktop && echo "entry valid" || true)
```

Expected: `Installed. Open Hour Tracker from the app grid.` and then `entry valid`
(or no output from the validator if it isn't installed).

- [ ] **Step 5: Final full check**

Run: `/usr/bin/python3 -m unittest -v && git status --short`
Expected: `Ran 74 tests` and `OK`. `git status` lists only the three new files and
`install.sh`.

- [ ] **Step 6: Commit and push**

```bash
git add install.sh data/hour-tracker.svg README.md
git commit -m "feat: add installer, icon, and README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```
