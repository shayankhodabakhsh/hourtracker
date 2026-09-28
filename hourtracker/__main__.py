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
