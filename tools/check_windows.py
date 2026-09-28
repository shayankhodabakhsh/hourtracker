"""Checks the running app's floating windows through X11 (smoke test).

    /usr/bin/python3 tools/check_windows.py
"""
import ctypes
import re
import subprocess
import sys

TITLES = {"Hour Tracker pill": "pill", "Hour Tracker balloon": "balloon"}
NEEDED = {"_NET_WM_STATE_ABOVE", "_NET_WM_STATE_STICKY",
          "_NET_WM_STATE_SKIP_TASKBAR", "_NET_WM_STATE_SKIP_PAGER"}
SHAPE_INPUT = 2


def find_windows():
    tree = subprocess.run(["xwininfo", "-root", "-tree"],
                          capture_output=True, text=True).stdout
    found = {}
    for line in tree.splitlines():
        match = re.match(r'\s*(0x[0-9a-f]+) "([^"]*)"', line)
        if match and match.group(2) in TITLES:
            found[TITLES[match.group(2)]] = int(match.group(1), 16)
    return found


def wm_state(xid):
    out = subprocess.run(["xprop", "-id", hex(xid), "_NET_WM_STATE"],
                         capture_output=True, text=True).stdout
    return set(re.findall(r"_NET_WM_STATE_\w+", out))


def input_rect_count(xid):
    x11 = ctypes.CDLL("libX11.so.6")
    xext = ctypes.CDLL("libXext.so.6")
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XFree.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xext.XShapeGetRectangles.restype = ctypes.c_void_p
    xext.XShapeGetRectangles.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    display = x11.XOpenDisplay(None)
    count, ordering = ctypes.c_int(), ctypes.c_int()
    rects = xext.XShapeGetRectangles(display, xid, SHAPE_INPUT,
                                     ctypes.byref(count), ctypes.byref(ordering))
    if rects:
        x11.XFree(rects)
    x11.XCloseDisplay(display)
    return count.value


def main():
    windows = find_windows()
    ok = True
    for name in ("pill", "balloon"):
        if name not in windows:
            print(f"FAIL {name}: window not found")
            ok = False
            continue
        missing = NEEDED - wm_state(windows[name])
        print(f"{'FAIL' if missing else 'ok  '} {name}: window states"
              + (f" missing {sorted(missing)}" if missing else ""))
        ok = ok and not missing
    if "balloon" in windows:
        count = input_rect_count(windows["balloon"])
        print(f"{'ok  ' if count > 1 else 'FAIL'} balloon: input shape has {count} rectangles")
        ok = ok and count > 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
