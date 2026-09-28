"""Hour Tracker: wires the tracker to the pill, the balloon, the stats window,
and the forgot-to-start notification."""
import logging
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

log = logging.getLogger(__name__)

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
        try:
            self.tracker.tick()
            self._update_pill()
        except Exception:
            log.exception("tick failed; trying again in %d s", TICK_SECONDS)
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
