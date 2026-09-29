"""What GNOME knows about whether someone is at the laptop: seconds since the
last keyboard or mouse input, and whether the screen is locked. Both work on
Wayland, where apps can't watch input themselves."""
import logging

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)


class _GnomeQuery:
    """Calls one method on a GNOME D-Bus service; logs one warning if it can't."""

    NAME = PATH = INTERFACE = METHOD = UNAVAILABLE = ""
    TIMEOUT_MS = 250    # a healthy reply takes well under 1 ms; this runs every 5 s

    def __init__(self, proxy=None):
        self._warned = False
        self._proxy = proxy if proxy is not None else self._connect()

    def _connect(self):
        try:
            return Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES
                | Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS,
                None, self.NAME, self.PATH, self.INTERFACE, None)
        except GLib.Error as err:
            self._warn(err)
            return None

    def _query(self):
        """The method's result, or None when GNOME can't answer."""
        if self._proxy is None:
            return None
        try:
            reply = self._proxy.call_sync(self.METHOD, None, Gio.DBusCallFlags.NONE,
                                          self.TIMEOUT_MS, None)
        except GLib.Error as err:
            self._warn(err)
            return None
        return reply.unpack()[0]

    def _warn(self, err):
        if not self._warned:
            self._warned = True
            log.warning("%s: %s", self.UNAVAILABLE, err.message)


class IdleMonitor(_GnomeQuery):
    """Call it to get idle seconds, or None when GNOME's monitor isn't there."""

    NAME = INTERFACE = "org.gnome.Mutter.IdleMonitor"
    PATH = "/org/gnome/Mutter/IdleMonitor/Core"
    METHOD = "GetIdletime"
    UNAVAILABLE = "idle monitor unavailable, so only sleep counts as away and there's no buzz"

    def __call__(self):
        ms = self._query()
        return None if ms is None else ms / 1000.0


class LockMonitor(_GnomeQuery):
    """Call it to learn whether the screen is locked; False if GNOME can't say."""

    NAME = INTERFACE = "org.gnome.ScreenSaver"
    PATH = "/org/gnome/ScreenSaver"
    METHOD = "GetActive"
    UNAVAILABLE = "screen lock state unavailable, so a locked screen is treated as unlocked"

    def __call__(self):
        return bool(self._query())
