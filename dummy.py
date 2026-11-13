"""Training dummy that lives next to Parton, in the same program.

- Sits in the bottom-left corner of the screen, standing on the taskbar.
- Left click hits it (the cursor turns into a sword over it); Parton hits it too.
- On the 17th hit it breaks and disappears; it can be revived from the menu.
- Right click: the shared menu (see App in parton.py).
"""
import ctypes
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageTk

# --- Settings ------------------------------------------------------------------
SCALE = 4                 # 80x48 px frames; same pixel size as Parton
FRAME_W, FRAME_H = 80, 48
HITS_TO_DIE = 17
HIT_FRAME_MS = 60
BREAK_FRAME_MS = 90
RUBBLE_VISIBLE_MS = 1_500  # how long the remains stay before it disappears
MARGIN = 8                # distance from the screen edge
KEY_COLOR = "#ff00fe"     # color that becomes transparent

ASSETS = Path(__file__).parent / "assets" / "dummy"
SPRITES = ASSETS / "sprites"
SWORD_CURSOR = ASSETS / "sword.cur"
SHEETS = ("IDLE", "HIT", "BREAKING")


def available():
    """True if the dummy's sprites are in place (otherwise Parton runs alone)."""
    return all((SPRITES / f"{name}.png").exists() for name in SHEETS)


def work_area():
    """Windows work area (screen minus the taskbar), in physical pixels."""
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def raw_frames(name):
    sheet = Image.open(SPRITES / f"{name}.png").convert("RGBA")
    return [sheet.crop((i * FRAME_W, 0, (i + 1) * FRAME_W, FRAME_H))
            for i in range(sheet.width // FRAME_W)]


def solid_mask(frame):
    return frame.getchannel("A").point(lambda a: 255 if a >= 128 else 0)


def content_box(names):
    """Box around the visible content of every animation.

    Cropping the frames to it removes the transparent space on the sides and
    under the feet, so the dummy stands right on the taskbar.
    """
    boxes = [solid_mask(f).getbbox() for n in names for f in raw_frames(n)]
    boxes = [b for b in boxes if b]
    return (min(b[0] for b in boxes), 0,
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def body_box(names, box):
    """Box around the dummy's body (without the flying pieces), relative to `box`."""
    boxes = [solid_mask(f.crop(box)).getbbox() for n in names for f in raw_frames(n)]
    boxes = [b for b in boxes if b]
    return tuple(v * SCALE for v in (min(b[0] for b in boxes), min(b[1] for b in boxes),
                                      max(b[2] for b in boxes), max(b[3] for b in boxes)))


def body_mask(names, box, body):
    """The dummy's silhouette on screen: the union of every pose in `names`.

    One-pixel gaps (the jagged edges of the pixel art) are closed so the cursor
    doesn't flicker along the outline, without making the silhouette bigger.
    """
    mask = None
    for frame in (f.crop(box) for n in names for f in raw_frames(n)):
        m = solid_mask(frame)
        mask = m if mask is None else ImageChops.lighter(mask, m)
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    mask = mask.resize((mask.width * SCALE, mask.height * SCALE), Image.NEAREST)
    return mask.crop(body)


def top_hwnd(widget):
    """HWND of the Windows window that contains `widget`."""
    user32 = ctypes.windll.user32
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    widget.update_idletasks()
    return user32.GetAncestor(widget.winfo_id(), 2)  # GA_ROOT


def shape_window(hwnd, mask):
    """Clip window `hwnd` to the white pixels of `mask` (only there it gets the mouse)."""
    gdi32 = ctypes.windll.gdi32
    gdi32.CreateRectRgn.restype = wintypes.HRGN
    gdi32.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    ctypes.windll.user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    region = gdi32.CreateRectRgn(0, 0, 0, 0)
    w, h = mask.size
    px = mask.load()
    for y in range(h):
        x = 0
        while x < w:
            if px[x, y]:
                start = x
                while x < w and px[x, y]:
                    x += 1
                run = gdi32.CreateRectRgn(start, y, x, y + 1)
                gdi32.CombineRgn(region, region, run, 2)  # RGN_OR
                gdi32.DeleteObject(run)
            else:
                x += 1
    ctypes.windll.user32.SetWindowRgn(hwnd, region, True)  # Windows takes ownership of the region


def load_frames(name, box):
    frames = []
    for frame in raw_frames(name):
        frame = frame.crop(box)
        frame = frame.resize((frame.width * SCALE, frame.height * SCALE), Image.NEAREST)
        # tkinter only supports full transparency: semi-transparent pixels become
        # opaque or invisible, and the background is painted with the key color.
        bg = Image.new("RGBA", frame.size, KEY_COLOR)
        bg.paste(frame, mask=solid_mask(frame))
        frames.append(ImageTk.PhotoImage(bg.convert("RGB")))
    return frames


class TrainingDummy:
    def __init__(self, master, app):
        self.master = master
        self.app = app
        self.window = tk.Toplevel(master)
        self.window.title("Dummy")
        self.window.overrideredirect(True)          # no border or title bar
        self.window.attributes("-topmost", True)    # always on top
        self.window.attributes("-transparentcolor", KEY_COLOR)
        self.window.config(bg=KEY_COLOR)

        box = content_box(SHEETS)
        self.width = (box[2] - box[0]) * SCALE
        self.height = (box[3] - box[1]) * SCALE
        self.body = body_box(["IDLE", "HIT"], box)
        self.body_shape = body_mask(["IDLE", "HIT"], box, self.body)
        self.idle = load_frames("IDLE", box)
        self.hit = load_frames("HIT", box)
        self.breaking = load_frames("BREAKING", box)

        # Hit zone: a nearly invisible window behind the body. The dummy's
        # transparent pixels let the mouse through to the desktop; without this
        # zone, the cursor would jump to the arrow at every gap in the pixel art.
        self.hitbox = tk.Toplevel(master)
        self.hitbox.overrideredirect(True)
        self.hitbox.attributes("-topmost", True)
        self.hitbox.attributes("-alpha", 0.01)
        self.hitbox.config(bg="black")

        self.label = tk.Label(self.window, bg=KEY_COLOR, bd=0)
        self.label.pack()

        # Sword cursor over the dummy (the hand if the file is missing).
        cursor = f"@{SWORD_CURSOR.as_posix()}" if SWORD_CURSOR.exists() else "hand2"
        for widget in (self.label, self.hitbox):
            widget.config(cursor=cursor)
            widget.bind("<Button-1>", lambda _e: self.take_hit())
            widget.bind("<Button-3>", app.show_menu)

        self.hits = 0
        self.alive = True       # standing (not broken)
        self.gone = False       # broken and already gone from the screen
        self.hidden = False     # hidden from the menu
        self.anim_job = None

        self.place_bottom_left()
        shape_window(top_hwnd(self.hitbox), self.body_shape)  # hits only on the silhouette
        self.show_frame(self.idle[0])
        self.keep_on_top()

    # --- State seen by Parton and the menu ----------------------------------------
    def standing(self):
        """Standing and visible: Parton can train on it."""
        return self.alive and not self.hidden

    def on_screen(self):
        """Something of it is on the screen (standing, or breaking)."""
        return not self.gone and not self.hidden

    def center_x(self):
        """Screen x of the middle of its body."""
        left, _, _, _ = work_area()
        return left + MARGIN + (self.body[0] + self.body[2]) / 2

    def body_span(self):
        """Screen x where its body starts and ends."""
        left, _, _, _ = work_area()
        return left + MARGIN + self.body[0], left + MARGIN + self.body[2]

    def body_top(self):
        """Height of the top of its body above the taskbar, in pixels."""
        return self.height - self.body[1]

    # --- Menu actions ------------------------------------------------------------
    def hide(self):
        self.hidden = True
        self.window.withdraw()
        self.hitbox.withdraw()

    def unhide(self):
        self.hidden = False
        self.window.deiconify()
        if self.alive:
            self.hitbox.deiconify()
        self.place_bottom_left()

    def revive(self):
        self.cancel_anim()
        self.hits = 0
        self.alive, self.gone, self.hidden = True, False, False
        self.show_frame(self.idle[0])
        self.window.deiconify()
        self.hitbox.deiconify()
        self.place_bottom_left()

    # --- Window ----------------------------------------------------------------
    def place_bottom_left(self):
        left, _, _, bottom = work_area()
        x, y = left + MARGIN, bottom - self.height
        self.window.geometry(f"{self.width}x{self.height}+{x}+{y}")
        bx0, by0, bx1, by1 = self.body
        self.hitbox.geometry(f"{bx1 - bx0}x{by1 - by0}+{x + bx0}+{y + by0}")

    def stack_hitbox_below(self):
        """Put the hit zone right below the dummy in the window order."""
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wintypes.UINT]
        # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        user32.SetWindowPos(top_hwnd(self.hitbox), top_hwnd(self.label),
                            0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)

    def keep_on_top(self):
        # Re-assert "always on top" and the position (in case the taskbar changes).
        if self.standing():
            self.hitbox.attributes("-topmost", True)
            self.window.attributes("-topmost", True)
            self.place_bottom_left()
            self.stack_hitbox_below()
        self.master.after(5_000, self.keep_on_top)

    def show_frame(self, frame):
        self.label.config(image=frame)

    # --- Animations ------------------------------------------------------------
    def play(self, frames, delay, on_done=None, index=0):
        if index < len(frames):
            self.show_frame(frames[index])
            self.anim_job = self.master.after(
                delay, self.play, frames, delay, on_done, index + 1)
        else:
            self.anim_job = None
            if on_done:
                on_done()

    def cancel_anim(self):
        if self.anim_job:
            self.master.after_cancel(self.anim_job)
            self.anim_job = None

    def take_hit(self):
        """A hit from the cursor or from Parton."""
        if not self.standing():
            return
        self.hits += 1
        self.cancel_anim()
        if self.hits >= HITS_TO_DIE:
            self.die()
        else:
            self.play(self.hit, HIT_FRAME_MS, on_done=lambda: self.show_frame(self.idle[0]))

    def die(self):
        # It breaks and, after a moment, disappears until it is revived.
        self.alive = False
        self.hitbox.withdraw()  # the remains can't be hit
        self.play(self.breaking, BREAK_FRAME_MS,
                  on_done=lambda: self.master.after(RUBBLE_VISIBLE_MS, self.vanish))

    def vanish(self):
        if self.alive:          # revived in the meantime
            return
        self.gone = True
        self.window.withdraw()
        self.app.check_empty()
