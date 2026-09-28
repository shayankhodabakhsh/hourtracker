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
