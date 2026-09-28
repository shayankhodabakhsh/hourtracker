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
