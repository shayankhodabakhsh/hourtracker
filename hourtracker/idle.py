"""Seconds since the last keyboard or mouse input, from GNOME's idle monitor.
It works on Wayland, where apps can't watch input themselves."""
import logging

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)


class IdleMonitor:
    """Call it to get idle seconds, or None when GNOME's monitor isn't there."""

    def __init__(self, proxy=None):
        self._warned = False
        self._proxy = proxy if proxy is not None else self._connect()

    def _connect(self):
        try:
            return Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES
                | Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS,
                None,
                "org.gnome.Mutter.IdleMonitor",
                "/org/gnome/Mutter/IdleMonitor/Core",
                "org.gnome.Mutter.IdleMonitor",
                None)
        except GLib.Error as err:
            self._warn(err)
            return None

    def __call__(self):
        if self._proxy is None:
            return None
        try:
            reply = self._proxy.call_sync("GetIdletime", None,
                                          Gio.DBusCallFlags.NONE, 1000, None)
        except GLib.Error as err:
            self._warn(err)
            return None
        return reply.unpack()[0] / 1000.0

    def _warn(self, err):
        if not self._warned:
            self._warned = True
            log.warning("idle monitor unavailable, so only sleep counts as away "
                        "and there's no buzz: %s", err.message)
