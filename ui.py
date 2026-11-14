"""Interface shared by Parton and the dummy: the right-click menu and the
hearts that show up when the cursor is over a character.

Both are tiny pixel drawings made here, at the characters' pixel size, in the
colors of the ruby buttons from Willosuna's "Fantasy UI Kit Lite". The menu's
text uses the "Nanofon" pixel font in assets/ui (not included in the
repository, see README.md), at half that pixel size so the buttons stay
small. Without the font, the menu is the plain Windows one.
"""
import ctypes
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

FONT = Path(__file__).parent / "assets" / "ui" / "Nanofon.ttf"


def available():
    """True if the menu's pixel font is in assets/ui."""
    return FONT.exists()


def mouse_pos():
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def work_area():
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


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
    VK_BUTTONS = (0x01, 0x02, 0x04)  # left, right and middle mouse buttons

    def __init__(self, master, items, x, y, on_choose):
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
                                bg=KEY_COLOR, highlightthickness=0, bd=0, cursor="hand2")
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
        # there is no room below it).
        left, top, right, bottom = work_area()
        if y + self.height > bottom:
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

    @classmethod
    def mouse_buttons_down(cls):
        state = ctypes.windll.user32.GetAsyncKeyState
        return any(state(vk) & 0x8000 for vk in cls.VK_BUTTONS)

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
