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
