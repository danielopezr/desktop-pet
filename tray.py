"""Capu's icon in the system tray, next to the clock.

Clicking it (left or right) opens the same menu as right-clicking Capu or
the dummy, so they can be brought back, and the program closed, even when
neither of them is on the screen. If Explorer restarts (and with it the
taskbar), the icon is put back.

Plain Windows calls through ctypes: the icon's messages arrive at a hidden
window of this thread, and Tk's own event loop delivers them. They arrive in
the middle of a Tk call, where calling Tk again would crash Python: so a click
is only noted there, and a Tk timer picks it up a moment later.
"""
import ctypes
import io
import traceback
from ctypes import wintypes

from PIL import Image

# Our own handles to the DLLs, so the types set here don't change anyone else's calls.
user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CALLBACK_MESSAGE = 0x8000 + 1     # WM_APP + 1: what the icon sends our window
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
NIM_ADD, NIM_DELETE = 0, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
SM_CXSMICON = 49                  # size of a small icon (the tray's), in pixels
CLASS_NAME = "CapuTrayWindow"
POLL_MS = 50                      # how often Tk looks for a click on the icon

LRESULT = wintypes.LPARAM
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HICON), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HICON)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.CreateIconFromResourceEx.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL,
                                            wintypes.DWORD, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.CreateIconFromResourceEx.restype = wintypes.HICON
user32.DestroyIcon.argtypes = [wintypes.HICON]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

_icons = {}                       # our hidden window -> its TrayIcon
_registered = False


@WNDPROC
def _window_proc(hwnd, msg, wparam, lparam):
    icon = _icons.get(hwnd)
    if icon is not None:
        try:
            icon.on_message(msg, lparam)
        except Exception:                 # an error here must not reach Windows
            traceback.print_exc()
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _register_class():
    """The hidden windows' class, registered once per program."""
    global _registered
    if not _registered:
        wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=_window_proc,
                         hInstance=kernel32.GetModuleHandleW(None), lpszClassName=CLASS_NAME)
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        _registered = True


def make_icon(images):
    """A Windows icon at the tray's size from `images` ({size: image}).

    It takes the biggest drawing that fits and centers it, never scaling it,
    so the pixel art stays crisp at any screen scaling.
    """
    size = user32.GetSystemMetrics(SM_CXSMICON) or 16
    fitting = [s for s in images if s <= size]
    image = images[max(fitting)] if fitting else images[min(images)].resize((size, size), Image.NEAREST)
    canvas = Image.new("RGBA", (size, size))
    canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
    png = io.BytesIO()
    canvas.save(png, format="PNG")
    data = png.getvalue()
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    icon = user32.CreateIconFromResourceEx(buffer, len(data), True, 0x00030000, size, size, 0)
    if not icon:
        raise ctypes.WinError(ctypes.get_last_error())
    return icon


class TrayIcon:
    """The icon, with `tooltip`; `on_click()` is called (from Tk's loop) when it is clicked."""

    def __init__(self, master, images, tooltip, on_click):
        self.master = master
        self.on_click = on_click
        self.clicked = False                  # noted by the icon's message, seen by poll
        _register_class()
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, tooltip, 0, 0, 0, 0, 0,
                                           None, None, kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        _icons[self.hwnd] = self
        # Sent to every window when the taskbar comes back after Explorer restarts.
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.hicon = make_icon(images)
        self.data = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=self.hwnd, uID=1,
                                    uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP,
                                    uCallbackMessage=CALLBACK_MESSAGE, hIcon=self.hicon,
                                    szTip=tooltip[:127])
        self.add()
        self.poll_job = None
        self.poll()

    def add(self):
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.data))

    def on_message(self, msg, lparam):
        """A message for our window (no Tk calls here: see the top of this file)."""
        if msg == CALLBACK_MESSAGE and lparam & 0xFFFF in (WM_LBUTTONUP, WM_RBUTTONUP):
            self.clicked = True
        elif msg == self.taskbar_created:
            self.add()

    def poll(self):
        if self.clicked:
            self.clicked = False
            self.on_click()
        self.poll_job = self.master.after(POLL_MS, self.poll)

    def remove(self):
        """Take the icon out of the tray (else it lingers until the mouse goes over it)."""
        if self.hwnd is None:
            return
        if self.poll_job:
            try:
                self.master.after_cancel(self.poll_job)
            except Exception:                 # Tk already gone
                pass
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.data))
        user32.DestroyIcon(self.hicon)
        _icons.pop(self.hwnd, None)
        user32.DestroyWindow(self.hwnd)
        self.hwnd = None
