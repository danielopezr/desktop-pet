"""The glow of Capu's lantern, in a window of its own.

The characters' windows show each pixel or don't (see screen.py): nothing in
between, so a soft light can't go in them. The glow is a layered window with
see-through pixels instead, in front of Capu's: it lights up everything
around the lantern, Capu himself too, and the mouse goes through it.

Its light is mostly added to what is under it (it brightens it, as light
does, instead of covering it like a veil), with a little warm tint so it
still shows on white windows, where adding light changes nothing. Windows
blends it like that when a pixel has more color than alpha (premultiplied).

It is drawn in rings as big as the sprites' pixels, to go with the pixel art,
and made stronger or weaker as a whole (see Glow.show).
"""
import ctypes
from ctypes import wintypes

from PIL import Image

COLOR = (255, 196, 104)                          # warm lamp light
# (out to this share of the radius, light added, tint): both shares of COLOR, at full strength
RINGS = ((0.30, 0.34, 0.10), (0.55, 0.22, 0.06), (0.76, 0.12, 0.03), (0.95, 0.05, 0.0))

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020                   # the mouse goes through it
WS_EX_TOOLWINDOW = 0x00000080                    # no taskbar button
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
ULW_ALPHA = 2
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
HWND_TOPMOST = -1

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HICON)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                       ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
                                       ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [wintypes.HWND]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

_window_proc = WNDPROC(lambda hwnd, msg, wparam, lparam: user32.DefWindowProcW(hwnd, msg, wparam, lparam))
CLASS_NAME = "CapuLanternGlow"
_registered = False


def glow_image(radius, pixel):
    """The glow at full strength, as an RGBA image of side 2 * radius * pixel in
    rings (RINGS) made of squares `pixel` screen pixels wide, the sprites' pixels.
    Its colors are premultiplied, as Windows takes them: each is what it adds to
    the screen, and alpha how much it covers of what is under it (the tint)."""
    side = 2 * radius
    small = Image.new("RGBA", (side, side))
    px = small.load()
    for y in range(side):
        for x in range(side):
            d = ((x + 0.5 - radius) ** 2 + (y + 0.5 - radius) ** 2) ** 0.5 / radius
            ring = next((r for r in RINGS if d <= r[0]), None)
            if ring:
                _, add, tint = ring
                px[x, y] = tuple(min(255, round(c * (add + tint))) for c in COLOR) + (round(255 * tint),)
    return small.resize((side * pixel, side * pixel), Image.NEAREST)


def premultiplied_bgra(image):
    """The bytes Windows wants for a layered window: blue, green, red and alpha
    (the image's colors are premultiplied already, see glow_image)."""
    raw = image.convert("RGBA").tobytes()
    out = bytearray(len(raw))
    out[0::4], out[1::4], out[2::4], out[3::4] = raw[2::4], raw[1::4], raw[0::4], raw[3::4]
    return bytes(out)


def light_up(screen, glow, x, y, strength):
    """Draw `glow` (see glow_image) on the RGB image `screen`, its top left corner
    at (x, y), at `strength` (0 to 1), blended as Windows blends it: what is under
    it times (1 - alpha), plus its color."""
    box = (x, y, x + glow.width, y + glow.height)
    under = screen.crop(box).convert("RGB")
    src, dst = glow.tobytes(), bytearray(under.tobytes())
    for i in range(0, len(dst), 3):
        j = i // 3 * 4
        keep = 1 - src[j + 3] * strength / 255
        for c in range(3):
            dst[i + c] = min(255, round(dst[i + c] * keep + src[j + c] * strength))
    screen.paste(Image.frombytes("RGB", under.size, bytes(dst)), box[:2])


class Glow:
    """The lantern's light: show it centered somewhere, as strong as asked, or hide it."""

    def __init__(self, radius, pixel):
        global _registered
        self.image = glow_image(radius, pixel)
        self.width, self.height = self.image.size
        self.shown = False
        self.spot = None                          # (x, y, alpha 0-255) last put on the screen
        instance = kernel32.GetModuleHandleW(None)
        if not _registered:
            wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=_window_proc,
                             hInstance=instance, lpszClassName=CLASS_NAME)
            user32.RegisterClassExW(ctypes.byref(wc))
            _registered = True
        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE,
            CLASS_NAME, "", WS_POPUP, 0, 0, self.width, self.height, None, None, instance, None)
        # Its picture, once: a bitmap Windows blends onto the screen.
        header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=self.width,
                                  biHeight=-self.height, biPlanes=1, biBitCount=32)
        bits = ctypes.c_void_p()
        self.dc = gdi32.CreateCompatibleDC(None)
        self.bitmap = gdi32.CreateDIBSection(self.dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        data = premultiplied_bgra(self.image)
        ctypes.memmove(bits, data, len(data))
        self.old_bitmap = gdi32.SelectObject(self.dc, self.bitmap)

    def show(self, x, y, strength):
        """Light centered on screen point (x, y), `strength` from 0 (off) to 1 (full)."""
        alpha = max(0, min(255, round(255 * strength)))
        spot = (round(x - self.width / 2), round(y - self.height / 2), alpha)
        if spot != self.spot:
            blend = BLENDFUNCTION(0, 0, alpha, 1)          # AC_SRC_OVER, AC_SRC_ALPHA
            user32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(wintypes.POINT(spot[0], spot[1])),
                                       ctypes.byref(wintypes.SIZE(self.width, self.height)), self.dc,
                                       ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA)
            self.spot = spot
        if not self.shown:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.shown = True
            self.raise_()

    def raise_(self):
        """In front of everything (of Capu too: it lights him up)."""
        if self.shown:
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def hide(self):
        if self.shown:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            self.shown = False

    def draw_on(self, screen, x, y, strength):
        """Draw the light on RGB image `screen` centered on (x, y), as it shows on the
        screen (to draw it elsewhere, as in the demo GIF)."""
        light_up(screen, self.image, round(x - self.width / 2), round(y - self.height / 2), strength)

    def destroy(self):
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            gdi32.SelectObject(self.dc, self.old_bitmap)
            gdi32.DeleteObject(self.bitmap)
            gdi32.DeleteDC(self.dc)
            self.hwnd = None
