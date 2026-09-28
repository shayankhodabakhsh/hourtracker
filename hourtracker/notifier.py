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
