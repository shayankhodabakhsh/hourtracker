"""Hour Tracker: wires the tracker to the pill, the balloon, the stats window,
and the forgot-to-start notification."""
import logging
import os
import signal
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import APP_ID, autostart
from .balloon import BalloonWindow
from .idle import IdleMonitor, LockMonitor
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
        self.tracker = Tracker(self.store, idle=IdleMonitor(), locked=LockMonitor(),
                               away_after=self.settings["away_minutes"] * 60,
                               nudge_after=self.settings["nudge_minutes"] * 60,
                               auto_pause_after=self.settings["auto_pause_minutes"] * 60)
        self.tracker.nudge_enabled = self.settings["nudge_enabled"]
        self.tracker.subject = self.settings["subject"] or None
        self.tracker.on_change = self.refresh
        self.tracker.on_nudge = self._buzz
        self.tracker.on_auto_pause = self._auto_paused
        self.notifier = Notifier(on_answer=lambda start: self.answer("nudge", start))
        self.pill = PillWindow(self.settings, on_toggle=self.tracker.toggle,
                               on_open_stats=self.show_stats, on_answer=self.answer,
                               menu_factory=self._build_menu)
        self.balloon = BalloonWindow(self.settings,
                                     on_hide=lambda: self.set_balloon_visible(False))
        self.stats = StatsWindow(self.tracker,
                                 resolve_first_weekday(self.settings["week_start"]),
                                 goal_seconds=self.settings["daily_goal_minutes"] * 60)
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
        if (self.tracker.subject or "") != self.settings["subject"]:
            self.settings["subject"] = self.tracker.subject or ""
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

    def _auto_paused(self, left):
        self.notifier.show_info(f"Timer paused at {datetime.fromtimestamp(left):%H:%M}",
                                "You were away, so that time isn't counted.")

    def _ask_subject(self):
        dialog = Gtk.Dialog(title="New subject", modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        entry = Gtk.Entry(activates_default=True, placeholder_text="e.g. Calculus")
        box = dialog.get_content_area()
        box.set_border_width(10)
        box.add(entry)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK and entry.get_text().strip():
            self.tracker.set_subject(entry.get_text().strip())
        dialog.destroy()

    def _subject_menu(self):
        menu = Gtk.Menu()
        current = self.tracker.subject
        names = self.store.subjects()
        if current and current not in names:
            names.insert(0, current)
        group = None
        for name, value in [(n, n) for n in names] + [("None", None)]:
            item = Gtk.RadioMenuItem(label=name, group=group, active=value == current)
            group = group or item
            item.connect("toggled", lambda item, v=value:
                         item.get_active() and self.tracker.set_subject(v))
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        new = Gtk.MenuItem(label="New subject…")
        new.connect("activate", lambda _item: GLib.idle_add(self._ask_subject))
        menu.append(new)
        return menu

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
        if not enabled:                 # and close a buzz that's already open
            self.tracker.answer_nudge(start=False)

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
        subject = Gtk.MenuItem(label=f"Subject: {self.tracker.subject or 'none'}")
        subject.set_submenu(self._subject_menu())
        menu.append(subject)
        add("Show balloon", self.set_balloon_visible, self.balloon.get_visible())
        add("Remind me to start", self._set_nudge, self.settings["nudge_enabled"])
        add("Start at login", lambda on: autostart.set_enabled(on, LAUNCHER),
            autostart.is_enabled())
        menu.append(Gtk.SeparatorMenuItem())
        add("Quit", self.quit)
        menu.show_all()
        return menu
