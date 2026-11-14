"""Interface shared by Parton and the dummy: the right-click menu and the
hearts that show up when the cursor is over a character.

Both are tiny pixel drawings made here, at the characters' pixel size. The menu's
text uses the "Nanofon" pixel font in assets/ui (not included in the
repository, see README.md), at half that pixel size so the buttons stay
small. Without the font, the menu is the plain Windows one.
"""
import ctypes
import io
import os
import struct
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

# --- Settings ------------------------------------------------------------------
UI_SCALE = 4              # same pixel size as the characters (their SCALE)
TEXT_SCALE = 2            # the menu's text is drawn at this pixel size: half, to keep it small
FONT_SIZE = 8             # Nanofon is an 8 px pixel font: smaller sizes break its letters
KEY_COLOR = "#ff00fe"     # color that becomes transparent
TEXT_COLOR = (255, 244, 224, 255)
RED = (184, 50, 58, 255)          # button, and a full heart
LIGHT_RED = (232, 112, 122, 255)  # button under the cursor
DARK_RED = (122, 28, 35, 255)     # pressed button, and the buttons' bottom edge
GRAY = (87, 82, 77, 255)          # empty heart
GOLD = (255, 204, 64, 255)        # the "?" Parton shows when the dummy hits back
HEARTS_GAP = 4            # pixels between the top of the head and the hearts
HEART_GAP = 1             # between one heart and the next, in drawing pixels
HEAD_ROWS = 3             # the top rows of a sprite that are only its head

# A 5x5 heart: "#" is drawn. Half a heart is its left three columns.
HEART = (".#.#.",
         "#####",
         "#####",
         ".###.",
         "..#..")
HALF_HEART_COLUMNS = 3

# A 4x6 question mark, popped over a character's head (see Emote).
QUESTION = (".##.",
            "#..#",
            "...#",
            "..#.",
            "....",
            "..#.")
# A 2x6 exclamation mark, popped over Parton's head when he spots the cursor.
EXCLAMATION = ("##",
               "##",
               "##",
               "##",
               "..",
               "##")
# A 5x5 "Z", floating up while Parton sleeps.
SLEEP_Z = ("#####",
           "...#.",
           "..#..",
           ".#...",
           "#####")
SKY = (170, 205, 255, 255)        # the "Z"
EMOTE_SECONDS = 0.9       # how long an emote lasts
EMOTE_RISE = 40           # how far it floats up meanwhile, in screen pixels
EMOTE_FADE_FROM = 0.4     # share of its time it stays solid before fading out

FONT = Path(__file__).parent / "assets" / "ui" / "Nanofon.ttf"


def available():
    """True if the menu's pixel font is in assets/ui."""
    return FONT.exists()


def any_mouse_button_down():
    """True while the left, right or middle mouse button is held down, anywhere."""
    state = ctypes.windll.user32.GetAsyncKeyState
    return any(state(vk) & 0x8000 for vk in (0x01, 0x02, 0x04))


def mouse_pos():
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def work_area():
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


# --- Cursors ---------------------------------------------------------------------
# Drawn here, like everything else: an 8x8 drawing gets a 1-pixel outline in a
# dark blue (not black: dark enough to see on light backgrounds, softer than
# black on dark ones) and is scaled x3, to fill the standard 32x32 cursor.
CURSOR_SCALE = 3
CURSOR_SIZE = 32
CURSOR_OUTLINE = (40, 52, 74, 255)
CURSOR_PALETTE = {
    "b": (222, 230, 240, 255),   # blade
    "s": (150, 166, 188, 255),   # blade, shade
    "g": (232, 176, 48, 255),    # guard and pommel, gold
    "h": (128, 78, 44, 255),     # grip
    "k": (196, 128, 76, 255),    # glove
    "d": (150, 94, 52, 255),     # glove creases
    "c": (232, 176, 48, 255),    # cuff, gold
}
SWORD = ("bs......",             # its tip (top left) is the point that clicks
         "sbs.....",
         ".sbs....",
         "..sbs..g",
         "...sb.g.",
         ".....g..",
         "....g.h.",
         "...g...g")
FIST = (".k.k.k..",              # a closed hand: while holding a character
        "kkkkkkk.",
        "kdkdkdk.",
        "kkkkkkkk",
        "dddkkkkk",
        ".kkkkkk.",
        "..cccc..",
        "..cccc..")
# The pixel that clicks, in the drawing with its outline (the outline adds 1).
CURSOR_HOTSPOTS = {"sword": (1, 1), "fist": (4, 4)}
CURSOR_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Parton" / "cursors"


def cursor_drawing(rows):
    """An 8x8 drawing ("." is empty) with its outline around it."""
    core = Image.new("RGBA", (len(rows[0]) + 2, len(rows) + 2))
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell != ".":
                core.putpixel((x + 1, y + 1), CURSOR_PALETTE[cell])
    out = core.copy()
    for y in range(core.height):
        for x in range(core.width):
            if core.getpixel((x, y))[3]:
                continue
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < core.width and 0 <= ny < core.height and core.getpixel((nx, ny))[3]:
                    out.putpixel((x, y), CURSOR_OUTLINE)
                    break
    return out


def write_cursor(drawing, path, hotspot):
    """Save `drawing` as a Windows .cur file clicking at `hotspot` (drawing pixels)."""
    big = drawing.resize((drawing.width * CURSOR_SCALE, drawing.height * CURSOR_SCALE), Image.NEAREST)
    canvas = Image.new("RGBA", (CURSOR_SIZE, CURSOR_SIZE))
    canvas.paste(big, (0, 0))
    buffer = io.BytesIO()
    canvas.save(buffer, format="ICO", sizes=[(CURSOR_SIZE, CURSOR_SIZE)], bitmap_format="bmp")
    data = bytearray(buffer.getvalue())
    # A .cur is an .ico with type 2 and the hotspot where the .ico keeps its
    # planes and bit count (in the first, and only, image entry).
    struct.pack_into("<H", data, 2, 2)
    centre = CURSOR_SCALE // 2
    struct.pack_into("<HH", data, 6 + 4, hotspot[0] * CURSOR_SCALE + centre,
                     hotspot[1] * CURSOR_SCALE + centre)
    path.write_bytes(data)


_cursors = None


def cursor(name):
    """Tk cursor for "sword" (over a character) or "fist" (holding one).

    The .cur files are made at start-up in %APPDATA%\\Parton\\cursors; if that
    fails, Windows' own hand and move cursors stand in.
    """
    global _cursors
    if _cursors is None:
        try:
            CURSOR_DIR.mkdir(parents=True, exist_ok=True)
            _cursors = {}
            for key, rows in (("sword", SWORD), ("fist", FIST)):
                path = CURSOR_DIR / f"{key}.cur"
                write_cursor(cursor_drawing(rows), path, CURSOR_HOTSPOTS[key])
                _cursors[key] = "{@" + path.as_posix() + "}"   # braces: the path may have spaces
        except OSError:
            _cursors = {"sword": "hand2", "fist": "fleur"}
    return _cursors[name]


# --- Window helpers ------------------------------------------------------------------
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


def stack_below(window, above):
    """Put `window` right below the window of widget `above` in the window order."""
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
    user32.SetWindowPos(top_hwnd(window), top_hwnd(above), 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)


def hit_zone(master):
    """A nearly invisible window to put behind a character, shaped like it.

    A character's transparent pixels let the mouse through to the desktop;
    without this zone the cursor would turn back into the arrow at every gap
    in the pixel art, and clicks there would miss.
    """
    zone = tk.Toplevel(master)
    zone.overrideredirect(True)
    zone.attributes("-topmost", True)
    zone.attributes("-alpha", 0.01)
    zone.config(bg="black")
    return zone


def make_click_through(window):
    """Let the mouse pass through `window` (the hearts must not block clicks)."""
    user32 = ctypes.windll.user32
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    window.update_idletasks()
    hwnd = user32.GetAncestor(window.winfo_id(), 2)  # GA_ROOT
    style = user32.GetWindowLongW(hwnd, -20)         # GWL_EXSTYLE
    # WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x80 | 0x08000000)


def to_photo(image, scale=UI_SCALE):
    """Scale a drawing up (to the characters' pixel size) and turn it into a PhotoImage.

    tkinter only supports full transparency: pixels at least half opaque are
    drawn solid, the rest become the key color.
    """
    image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
    bg = Image.new("RGBA", image.size, KEY_COLOR)
    bg.paste(image, mask=image.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
    return ImageTk.PhotoImage(bg.convert("RGB"))


# --- Text ----------------------------------------------------------------------
_font = None


def font():
    global _font
    if _font is None:
        _font = ImageFont.truetype(str(FONT), FONT_SIZE)
    return _font


def text_image(text):
    """`text` in the pixel font, one image pixel per font pixel.

    Every string gets the same height, so the text lines up from row to row.
    """
    width = int(font().getlength(text)) + 4
    canvas = Image.new("RGBA", (width, 24), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.fontmode = "1"                                   # crisp pixels, no smoothing
    draw.text((1, 4), text, font=font(), fill=TEXT_COLOR)
    left, _, right, _ = canvas.getbbox() or (0, 0, 1, 1)
    top, bottom = _text_rows()
    return canvas.crop((left, top, right, bottom))


_rows = None


def _text_rows():
    """Rows used by any text (from capitals down to descenders)."""
    global _rows
    if _rows is None:
        canvas = Image.new("L", (64, 24))
        draw = ImageDraw.Draw(canvas)
        draw.fontmode = "1"
        draw.text((1, 4), "Hgy", font=font(), fill=255)
        _, top, _, bottom = canvas.getbbox()
        _rows = (top, bottom)
    return _rows


# --- Right-click menu ------------------------------------------------------------
class PopupMenu:
    """A column of small flat red buttons.

    `items` is a list of (label, action); None between them leaves a wider gap.
    It closes when an option is picked, on Escape, or on a click anywhere else.
    """
    ROW_GAP = 1           # between buttons, in drawing pixels (UI_SCALE)
    SEP_GAP = 3           # gap left by a separator, in drawing pixels
    PAD_X = 8             # from the button's sides to its text, in screen pixels
    PAD_Y = 3             # above and below the text, in screen pixels

    def __init__(self, master, items, x, y, on_choose, flip=True):
        self.on_choose = on_choose
        self.closed = False
        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-transparentcolor", KEY_COLOR)
        self.window.config(bg=KEY_COLOR)

        # Text at TEXT_SCALE; the buttons, in whole drawing pixels around it.
        s = UI_SCALE
        labels = [text_image(label) for label, _ in (i for i in items if i)]
        labels = [t.resize((t.width * TEXT_SCALE, t.height * TEXT_SCALE), Image.NEAREST)
                  for t in labels]
        button_w = -(-(max(t.width for t in labels) + 2 * self.PAD_X) // s)
        button_h = -(-(labels[0].height + 2 * self.PAD_Y) // s) + 1   # + the bottom edge

        # Lay the rows out, in drawing pixels.
        self.rows = []                       # (top, action, {state: photo})
        y_px = 0
        label_iter = iter(labels)
        for item in items:
            if item is None:
                y_px += self.SEP_GAP
                continue
            label = next(label_iter)
            photos = {state: to_photo(self.button(state, button_w, button_h, label), scale=1)
                      for state in ("normal", "hover", "pressed")}
            self.rows.append((y_px, item[1], photos))
            y_px += button_h + self.ROW_GAP
        width, height = button_w, y_px - self.ROW_GAP

        self.width, self.height = width * s, height * s
        self.row_height = button_h * s
        self.canvas = tk.Canvas(self.window, width=self.width, height=self.height,
                                bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.items = [self.canvas.create_image(0, top * s, image=photos["normal"], anchor="nw")
                      for top, _, photos in self.rows]
        self.hovered = self.pressed = None

        self.canvas.bind("<Motion>", lambda e: self.hover(self.row_at(e.y)))
        self.canvas.bind("<Leave>", lambda e: self.hover(None))
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.window.bind("<Escape>", lambda e: self.close())

        # Open at the cursor, kept inside the work area (above the cursor if
        # there is no room below it, unless `flip` is off: then it is just
        # moved up enough to fit, to reopen where the last menu was).
        left, top, right, bottom = work_area()
        if flip and y + self.height > bottom:
            y -= self.height
        x = min(max(x, left), right - self.width)
        y = min(max(y, top), bottom - self.height)
        self.x, self.y = x, y
        self.window.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.window.lift()
        self.window.focus_force()
        self.buttons_down = self.mouse_buttons_down()  # the right click that opened it
        self.watch()

    @staticmethod
    def button(state, width, height, label):
        """A flat button with rounded corners and a darker bottom edge, at screen size.

        `width` and `height` are in drawing pixels; `label` is already at screen
        size. Pressed, the button is all dark and its text sinks one text pixel.
        """
        pressed = state == "pressed"
        image = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(image)
        face = {"normal": RED, "hover": LIGHT_RED, "pressed": DARK_RED}[state]
        draw.rectangle((0, 0, width - 1, height - 1), fill=face)
        draw.line((0, height - 1, width - 1, height - 1), fill=DARK_RED)
        for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
            image.putpixel(corner, (0, 0, 0, 0))
        s = UI_SCALE
        image = image.resize((width * s, height * s), Image.NEAREST)
        face = (height - 1) * s                            # above the bottom edge
        x = (width * s - label.width) // 2
        y = (face - label.height) // 2 + (TEXT_SCALE if pressed else 0)
        image.alpha_composite(label, (x, y))
        return image

    def row_at(self, y):
        for index, (top, _, _) in enumerate(self.rows):
            if 0 <= y - top * UI_SCALE < self.row_height:
                return index
        return None

    def show_state(self, index):
        if index is None:
            return
        state = ("pressed" if index == self.pressed == self.hovered
                 else "hover" if index == self.hovered else "normal")
        self.canvas.itemconfig(self.items[index], image=self.rows[index][2][state])

    def hover(self, index):
        old, self.hovered = self.hovered, index
        self.show_state(old)
        self.show_state(index)

    def press(self, event):
        self.pressed = self.row_at(event.y)
        self.hover(self.pressed)

    def release(self, event):
        index = self.row_at(event.y)
        chosen = index is not None and index == self.pressed
        self.pressed = None
        self.show_state(index)
        if chosen:
            self.close()
            self.on_choose(self.rows[index][1])

    @staticmethod
    def mouse_buttons_down():
        return any_mouse_button_down()

    def watch(self):
        """Close on a new click outside the menu."""
        if self.closed:
            return
        down = self.mouse_buttons_down()
        if down and not self.buttons_down:
            mx, my = mouse_pos()
            if not (self.x <= mx < self.x + self.width and self.y <= my < self.y + self.height):
                self.close()
                return
        self.buttons_down = down
        self.window.after(30, self.watch)

    def close(self):
        if not self.closed:
            self.closed = True
            self.window.destroy()


# --- Hearts ----------------------------------------------------------------------------
class Emote:
    """A little drawing (like QUESTION) that pops over a character's head,
    floats up and fades away. It follows the character while it lasts and
    lets the mouse through."""

    def __init__(self, master, drawing, color, rise=None, seconds=None, fade_in=0.0):
        self.rise = EMOTE_RISE if rise is None else rise
        self.seconds = EMOTE_SECONDS if seconds is None else seconds
        self.fade_in = fade_in                # share of its time it takes to appear (0: at once)
        self.drift = 0
        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-transparentcolor", KEY_COLOR)
        self.window.config(bg=KEY_COLOR)
        image = Image.new("RGBA", (len(drawing[0]), len(drawing)))
        for y, row in enumerate(drawing):
            for x, cell in enumerate(row):
                if cell == "#":
                    image.putpixel((x, y), color)
        self.photo = to_photo(image)
        tk.Label(self.window, image=self.photo, bg=KEY_COLOR, bd=0).pack()
        self.window.withdraw()
        make_click_through(self.window)
        self.job = None

    def show(self, head, drift=0):
        """Pop it over the head: `head()` gives the screen (x, y) of the top of the
        head, asked again on every frame so it follows the character. On its way
        up it floats `drift` pixels sideways (a diagonal)."""
        if self.job:
            self.window.after_cancel(self.job)
        self.head = head
        self.drift = drift
        self.start = time.perf_counter()
        self.window.attributes("-alpha", 0.0 if self.fade_in else 1.0)
        self.window.deiconify()
        self.window.lift()
        self.step()

    def step(self):
        t = (time.perf_counter() - self.start) / self.seconds
        if t >= 1:
            self.job = None
            self.window.withdraw()
            return
        x, y = self.head()
        x += self.drift * t
        w, h = self.photo.width(), self.photo.height()
        self.window.geometry(f"{w}x{h}+{round(x - w / 2)}+{round(y - HEARTS_GAP - h - self.rise * t)}")
        fade = max(0.0, (t - EMOTE_FADE_FROM) / (1 - EMOTE_FADE_FROM))
        appear = min(1.0, t / self.fade_in) if self.fade_in else 1.0
        self.window.attributes("-alpha", appear * (1.0 - fade))
        self.job = self.window.after(16, self.step)


def head_center(mask, rows=HEAD_ROWS):
    """x of the middle of the head in a sprite's silhouette (white = solid).

    Uses the top few rows of the drawing, which are only the head: lower down,
    an arm or a weapon would pull the middle to one side.
    """
    _, top, _, _ = mask.getbbox()
    left, _, right, _ = mask.crop((0, top, mask.width, top + rows)).getbbox()
    return (left + right) / 2


def heart_states(hp, maximum):
    """"full", "half" or "empty" for each heart: every heart is two hits."""
    return ["full" if hp >= 2 * i + 2 else "half" if hp == 2 * i + 1 else "empty"
            for i in range(maximum // 2)]


class Hearts:
    """A row of hearts above a character, shown while the cursor is over it.

    Each heart is two hits: a hit turns a full heart into a half one, the next
    one empties it. It lets the mouse through, so it never gets in the way of
    clicks.
    """

    def __init__(self, master):
        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-transparentcolor", KEY_COLOR)
        self.window.config(bg=KEY_COLOR)
        self.label = tk.Label(self.window, bg=KEY_COLOR, bd=0)
        self.label.pack()
        self.window.withdraw()
        make_click_through(self.window)
        self.photos = {}                     # (hp, max) -> PhotoImage
        self.current = None
        self.visible = False

    def image(self, hp, maximum):
        if (hp, maximum) not in self.photos:
            self.photos[hp, maximum] = to_photo(self.draw(hp, maximum))
        return self.photos[hp, maximum]

    @staticmethod
    def draw(hp, maximum):
        """The row of hearts: full ones red, empty ones gray, half ones split."""
        states = heart_states(hp, maximum)
        w, h = len(HEART[0]), len(HEART)
        out = Image.new("RGBA", (len(states) * (w + HEART_GAP) - HEART_GAP, h))
        for i, state in enumerate(states):
            red_columns = {"full": w, "half": HALF_HEART_COLUMNS, "empty": 0}[state]
            for y, row in enumerate(HEART):
                for x, cell in enumerate(row):
                    if cell == "#":
                        out.putpixel((i * (w + HEART_GAP) + x, y), RED if x < red_columns else GRAY)
        return out

    def show(self, center_x, head_y, hp, maximum):
        """Show it centered over `center_x`, just above the screen row `head_y`."""
        photo = self.image(hp, maximum)
        if photo is not self.current:
            self.label.config(image=photo)
            self.current = photo
        w, h = photo.width(), photo.height()
        left, top, right, _ = work_area()
        x = min(max(round(center_x - w / 2), left), right - w)
        y = max(round(head_y - HEARTS_GAP - h), top)
        self.window.geometry(f"{w}x{h}+{x}+{y}")
        if not self.visible:
            self.visible = True
            self.window.deiconify()
            self.window.lift()

    def hide(self):
        if self.visible:
            self.visible = False
            self.window.withdraw()
