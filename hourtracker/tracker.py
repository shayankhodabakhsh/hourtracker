"""The study timer's state machine. There's no GTK here: the clock and the
idle source are passed in, so tests can move time forward instantly."""
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import stats

log = logging.getLogger(__name__)


def _clock_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")

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
    def __init__(self, store, clock=time.time, idle=lambda: None, locked=lambda: False,
                 away_after=15 * 60, nudge_after=3 * 60):
        self.store = store
        self.clock = clock
        self.idle = idle                # () -> seconds since the last input, or None
        self.locked = locked            # () -> True while the screen is locked
        self.away_after = away_after
        self.nudge_after = nudge_after
        self.nudge_enabled = True
        self.running = False
        self.pending = None             # an Away waiting for "were you studying?"
        self.nudge = None               # while the buzz is open: when the stretch began
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

    def start(self) -> None:
        """Start timing from now."""
        if self.running:
            return
        now = self.clock()
        self.running = True
        self._start = now
        self._session_id = None
        self._saved_end = self._start
        self._last_active = now
        self.pending = None                 # an unanswered question counts as "yes"
        self._silence_nudge()
        self._save(now)
        self._emit(self.on_change)

    def pause(self) -> None:
        """Stop timing. An open away question stays open, so No still works."""
        if not self.running:
            return
        self._save(self.clock())
        self.running = False
        self._session_id = None
        self._silence_nudge()
        self._emit(self.on_change)

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
        self._emit(self.on_change)

    def answer_nudge(self, start: bool) -> None:
        """Reply to the buzz. Start counts from zero, like the play button."""
        if self.nudge is None:
            return
        if start:
            self.start()
        else:
            self._silence_nudge()
            self._emit(self.on_change)

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
        locked = self.locked()
        idle = None if slept else self.idle()     # idle time leaves out sleep
        if locked:
            came_back = self._last_active         # nobody studies at a locked screen
        else:
            came_back = now if idle is None else now - idle
        if came_back - self._last_active >= self.away_after:
            self._returned(self._last_active, came_back)
        self._last_active = max(self._last_active, came_back)
        if self.running:
            if slept or now - self._last_save >= CHECKPOINT_SECONDS:
                self._save(now)
        elif not locked and idle is not None and idle < ACTIVE_SECONDS:
            self._maybe_nudge(now)

    def _returned(self, left: float, came_back: float) -> None:
        """Back after a long break, or the laptop woke up."""
        if self.running:
            log.info("away %s to %s: asking whether it was study time",
                     _clock_time(left), _clock_time(came_back))
            self.pending = Away(left, came_back)  # replaces an unanswered one
        else:
            log.info("back at the laptop at %s", _clock_time(came_back))
            self._active_since = came_back
            self._nudge_armed = True
            self.nudge = None                     # an old buzz is stale now
            self.pending = None                   # so is an old question: it counts
        self._emit(self.on_change)

    def _maybe_nudge(self, now: float) -> None:
        if (self.nudge_enabled and self._nudge_armed and self.nudge is None
                and now - self._active_since >= self.nudge_after):
            log.info("at the laptop since %s with the timer off: reminding",
                     _clock_time(self._active_since))
            self.nudge = self._active_since
            self._nudge_armed = False
            self._emit(self.on_nudge)
            self._emit(self.on_change)

    def _silence_nudge(self) -> None:
        """No buzz until the next stretch at the laptop."""
        self.nudge = None
        self._nudge_armed = False

    def _emit(self, callback) -> None:
        """Tell the UI something changed. A UI failure must not stop timekeeping."""
        try:
            callback()
        except Exception:
            log.exception("UI callback failed")

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
