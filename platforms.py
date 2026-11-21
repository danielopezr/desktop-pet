"""Where Capu and the dummy can stand besides the taskbar: the tops of the
open windows.

Only the stretches of each top edge that can be seen count: where a window in
front covers it, there is nothing to stand on. Any app window on show covers
the ones behind it, but only windows that are neither maximized nor tiny can
be stood on. Minimized and hidden windows (or ones on another virtual
desktop) don't count at all, nor do the desktop, the taskbar, tool windows
and this program's own windows.
"""
import ctypes
import os
from ctypes import wintypes

# Our own handles to the DLLs, so the types set here don't change anyone else's calls.
user32 = ctypes.WinDLL("user32")
dwmapi = ctypes.WinDLL("dwmapi")

DWMWA_EXTENDED_FRAME_BOUNDS = 9   # the window as drawn, without its invisible resize borders
DWMWA_CLOAKED = 14                # hidden by Windows (another virtual desktop, a suspended app)
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
MIN_SIZE = (150, 80)              # smaller windows (pop-ups, widgets) are no place to stand
BORDER = 1                        # the thin line Windows draws along a window's top: feet go on it

ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [ENUM_PROC, wintypes.LPARAM]
for name in ("IsWindowVisible", "IsIconic", "IsZoomed", "GetWindowTextLengthW"):
    getattr(user32, name).argtypes = [wintypes.HWND]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def window_frame(hwnd):
    """(left, top, right, bottom) of app window `hwnd` as it shows on the screen,
    or None if it isn't one on show (see the top of this file)."""
    if (not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd)
            or user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW
            or not user32.GetWindowTextLengthW(hwnd)):
        return None
    cloaked = wintypes.DWORD()
    if (dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                     ctypes.sizeof(cloaked)) == 0 and cloaked.value):
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return None
    name = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, name, 64)
    if name.value in SKIP_CLASSES:
        return None
    rect = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect),
                                    ctypes.sizeof(rect)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def can_stand_on(hwnd, rect):
    left, top, right, bottom = rect
    return (not user32.IsZoomed(hwnd)
            and right - left >= MIN_SIZE[0] and bottom - top >= MIN_SIZE[1])


def window_rect(hwnd):
    """(left, top, right, bottom) of window `hwnd`, or None if it is nothing to stand on."""
    rect = window_frame(hwnd)
    return rect if rect and can_stand_on(hwnd, rect) else None


def top_row(rect):
    """The screen row something standing on a window with this `rect` stands on."""
    return rect[1] + BORDER


def window_rects():
    """[(hwnd, (left, top, right, bottom), can be stood on)] of the app windows on
    show, from the one in front to the one at the back."""
    found = []

    @ENUM_PROC
    def collect(hwnd, _):
        rect = window_frame(hwnd)
        if rect:
            found.append((hwnd, rect, can_stand_on(hwnd, rect)))
        return True

    user32.EnumWindows(collect, 0)            # top to bottom, in the order they are stacked
    return found


def uncovered(span, cover):
    """What is left of the stretch `span` (left, right) outside `cover`."""
    left, right = span
    c0, c1 = cover
    if c1 <= left or c0 >= right:
        return [span]
    return [part for part in ((left, c0), (c1, right)) if part[1] > part[0]]


def ledges(windows, area, min_width):
    """The stretches of the windows' top edges that can be seen: [(hwnd, left, right, y)],
    `y` the screen row to stand on.

    `windows` is window_rects(): the ones in front cover the top edges behind
    them (even those that can't be stood on). Only edges inside `area` (left,
    top, right, bottom: screen pixels) count, cut to its sides, and only
    stretches at least `min_width` wide.
    """
    area_left, area_top, area_right, area_bottom = area
    out = []
    for i, (hwnd, rect, standable) in enumerate(windows):
        left, top, right, _ = rect
        if not standable or not area_top <= top < area_bottom:
            continue
        pieces = [(max(left, area_left), min(right, area_right))]
        for _, (o_left, o_top, o_right, o_bottom), _ in windows[:i]:
            if o_top <= top < o_bottom:          # a window in front, across this edge
                pieces = [p for piece in pieces for p in uncovered(piece, (o_left, o_right))]
        out += [(hwnd, a, b, top_row(rect)) for a, b in pieces if b - a >= min_width]
    return out


def walls(windows, area):
    """The sides of the windows that can be seen, as walls: [(hwnd, x, top, bottom, face)].

    `x` is the screen column of the side and `top`..`bottom` the screen rows it
    spans, cut by the windows in front of it and by `area` (left, top, right,
    bottom); `face` is the way it faces: -1 for a window's left side (something
    to its left touches it), 1 for its right side. Only the windows that can be
    stood on count, the same as for the ledges.
    """
    area_left, area_top, area_right, area_bottom = area
    out = []
    for i, (hwnd, rect, standable) in enumerate(windows):
        left, top, right, bottom = rect
        if not standable:
            continue
        for x, face in ((left, -1), (right, 1)):
            if not area_left < x < area_right:
                continue
            pieces = [(max(top, area_top), min(bottom, area_bottom))]
            for _, (o_left, o_top, o_right, o_bottom), _ in windows[:i]:
                if o_left < x < o_right:         # a window in front, across this side
                    pieces = [p for piece in pieces for p in uncovered(piece, (o_top, o_bottom))]
            out += [(hwnd, x, a, b, face) for a, b in pieces if b > a]
    return out


def landing(ledges, x, before, after):
    """What something at `x` lands on, going down from height `before` to `after`
    (above the taskbar): (height, window), with None for the taskbar; or None if
    it hasn't reached anything. `ledges` are (height, left, right, window), the
    highest first."""
    for height, left, right, hwnd in ledges:
        if after <= height <= before and left <= x <= right:
            return height, hwnd
    return (0.0, None) if after <= 0 else None


def stands_on(ledges, hwnd, x, height):
    """True if `ledges` still have window `hwnd`'s top under `x`, at `height`."""
    return any(h == hwnd and left <= x <= right and abs(top - height) <= 2
               for top, left, right, h in ledges)
