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
