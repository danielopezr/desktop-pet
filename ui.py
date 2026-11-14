"""Styled interface shared by Parton and the dummy: the right-click menu and
the hearts that show up when the cursor is over a character.

Drawn with pieces of the free "Fantasy UI Kit Lite" by Willosuna and the
"Nanofon" pixel font, both in assets/ui (not included in the repository, see
README.md). Without them, the menu falls back to the plain Windows one and the
hearts are drawn as plain squares.
"""
import ctypes
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

# --- Settings ------------------------------------------------------------------
UI_SCALE = 4              # same pixel size as the characters (their SCALE)
FONT_SIZE = 8             # Nanofon is an 8 px pixel font
KEY_COLOR = "#ff00fe"     # color that becomes transparent
TEXT_COLOR = (255, 244, 224, 255)
TEXT_SHADOW = (122, 28, 35, 255)      # the buttons' darkest red
OUTLINE_MAX = 60          # pixels darker than this (on every channel) are the kit's outline
HEARTS_GAP = 4            # pixels between the top of the head and the hearts
HEART_GAP = 1             # between one heart and the next, in kit pixels
HEAD_ROWS = 3             # the top rows of a sprite that are only its head

UI = Path(__file__).parent / "assets" / "ui"
PIECES = ("button_ruby_normal", "button_ruby_hover", "button_ruby_pressed",
          "heart_full", "heart_half", "heart_empty")
FONT = UI / "Nanofon.ttf"
PANEL_BORDER = 6          # 9-slice border of the buttons, in kit pixels


def available():
    """True if the UI kit pieces and the font are in assets/ui."""
    return FONT.exists() and all((UI / f"{name}.png").exists() for name in PIECES)


_pieces = {}


def piece(name):
    if name not in _pieces:
        _pieces[name] = without_outline(Image.open(UI / f"{name}.png").convert("RGBA"))
    return _pieces[name]


def without_outline(image):
    """Drop the kit's black outline and drop shadow, to match the characters' flat style."""
    px = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = px[x, y]
            if a < 255 or max(r, g, b) < OUTLINE_MAX:
                px[x, y] = (0, 0, 0, 0)
    return image


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


def to_photo(image):
    """Scale a kit-sized image up and turn it into a PhotoImage.

    tkinter only supports full transparency: pixels at least half opaque are
    drawn solid, the rest become the key color.
    """
    image = image.resize((image.width * UI_SCALE, image.height * UI_SCALE), Image.NEAREST)
    bg = Image.new("RGBA", image.size, KEY_COLOR)
    bg.paste(image, mask=image.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
    return ImageTk.PhotoImage(bg.convert("RGB"))


def nine_slice(image, width, height, border=PANEL_BORDER):
    """Stretch `image` to width x height keeping its corners and borders intact."""
    w, h, b = image.width, image.height, border
    out = Image.new("RGBA", (width, height))
    xs = ((0, b, 0, b), (b, w - b, b, width - b), (w - b, w, width - b, width))
    ys = ((0, b, 0, b), (b, h - b, b, height - b), (h - b, h, height - b, height))
    for sx0, sx1, dx0, dx1 in xs:
        for sy0, sy1, dy0, dy1 in ys:
            if dx1 > dx0 and dy1 > dy0:
                part = image.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), Image.NEAREST)
                out.paste(part, (dx0, dy0))
    return out


# --- Text ----------------------------------------------------------------------
_font = None


def font():
    global _font
    if _font is None:
        _font = ImageFont.truetype(str(FONT), FONT_SIZE) if FONT.exists() else ImageFont.load_default()
    return _font


def text_image(text, color=TEXT_COLOR, shadow=True):
    """Text in the pixel font, kit-sized, with a drop shadow if asked.

    Every string gets the same height, so the text lines up from row to row.
    """
    f = font()
    width = int(f.getlength(text)) + 4
    canvas = Image.new("RGBA", (width, 24), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.fontmode = "1"                                   # crisp pixels, no smoothing
    if shadow:
        draw.text((1, 5), text, font=f, fill=TEXT_SHADOW)
    draw.text((1, 4), text, font=f, fill=color)
    left, _, right, _ = canvas.getbbox() or (0, 0, 1, 1)
    top, bottom = _text_rows()
    return canvas.crop((left, top, right, bottom))


_rows = None


def _text_rows():
    """Rows used by any text, shadow included (from capitals and descenders)."""
    global _rows
    if _rows is None:
        canvas = Image.new("L", (64, 24))
        draw = ImageDraw.Draw(canvas)
        draw.fontmode = "1"
        for dy in (0, 1):
            draw.text((1, 4 + dy), "HÁgy", font=font(), fill=255)
        _, top, _, bottom = canvas.getbbox()
        _rows = (top, bottom)
    return _rows


# --- Right-click menu ------------------------------------------------------------
class PopupMenu:
    """A column of the kit's ruby buttons, without a panel behind them.

    `items` is a list of (label, action); None between them leaves a wider gap.
    It closes when an option is picked, on Escape, or on a click anywhere else.
    """
    ROW_GAP = 2           # between buttons, in kit pixels
    SEP_GAP = 5           # gap left by a separator
    MIN_BUTTON = 48       # narrowest button, in kit pixels
    BUTTON_H = 15         # button height, in kit pixels (the kit draws them 19 tall)
    VK_BUTTONS = (0x01, 0x02, 0x04)  # left, right and middle mouse buttons

    def __init__(self, master, items, x, y, on_choose):
        self.on_choose = on_choose
        self.closed = False
        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-transparentcolor", KEY_COLOR)
        self.window.config(bg=KEY_COLOR)

        labels = [text_image(label) for label, _ in (i for i in items if i)]
        button_w = max([self.MIN_BUTTON] + [t.width + 2 * (PANEL_BORDER + 2) for t in labels])
        button_h = self.BUTTON_H

        # Lay the rows out, in kit pixels.
        self.rows = []                       # (top, action, {state: photo})
        y_kit = 0
        label_iter = iter(labels)
        for item in items:
            if item is None:
                y_kit += self.SEP_GAP
                continue
            label = next(label_iter)
            photos = {state: to_photo(self.button(state, button_w, button_h, label))
                      for state in ("normal", "hover", "pressed")}
            self.rows.append((y_kit, item[1], photos))
            y_kit += button_h + self.ROW_GAP
        width, height = button_w, y_kit - self.ROW_GAP

        s = UI_SCALE
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
        """A ruby button with its label centered (pressed: one pixel lower)."""
        image = nine_slice(piece(f"button_ruby_{state}"), width, height)
        face = height - 4                                  # the bottom rows are its shadow
        x = (width - label.width) // 2
        y = (face - label.height) // 2 + (1 if state == "pressed" else 0)
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
        self.styled = available()
        self.photos = {}                     # (hp, max) -> PhotoImage
        self.current = None
        self.visible = False

    def image(self, hp, maximum):
        if (hp, maximum) not in self.photos:
            draw = self.draw_styled if self.styled else self.draw_plain
            self.photos[hp, maximum] = to_photo(draw(hp, maximum))
        return self.photos[hp, maximum]

    @staticmethod
    def draw_styled(hp, maximum):
        hearts = [piece(f"heart_{state}") for state in heart_states(hp, maximum)]
        w, h = hearts[0].size
        out = Image.new("RGBA", (len(hearts) * (w + HEART_GAP) - HEART_GAP, h))
        for i, heart in enumerate(hearts):
            out.alpha_composite(heart, (i * (w + HEART_GAP), 0))
        return out

    @staticmethod
    def draw_plain(hp, maximum):
        """Without the kit: little squares, red, half red or gray."""
        red, gray = (184, 50, 58, 255), (87, 82, 77, 255)
        states = heart_states(hp, maximum)
        out = Image.new("RGBA", (len(states) * 7 - 1, 6))
        draw = ImageDraw.Draw(out)
        for i, state in enumerate(states):
            x = i * 7
            draw.rectangle((x, 0, x + 5, 5), fill=red if state == "full" else gray)
            if state == "half":
                draw.rectangle((x, 0, x + 2, 5), fill=red)
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
