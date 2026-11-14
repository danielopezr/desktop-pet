"""What Parton, the dummy and the interface share to draw on the screen: where
the cursor and the taskbar are, and turning pixel art into Tk images."""
import ctypes
from ctypes import wintypes

from PIL import Image, ImageTk

KEY_COLOR = "#ff00fe"         # color that becomes transparent


def work_area():
    """Windows work area (screen minus the taskbar), in physical pixels."""
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def mouse_pos():
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def solid_mask(image):
    """White where `image` is at least half opaque, black elsewhere."""
    return image.getchannel("A").point(lambda a: 255 if a >= 128 else 0)


def to_photo(image, scale):
    """Scale a drawing up `scale` times and turn it into a PhotoImage.

    tkinter only supports full transparency: pixels at least half opaque are
    drawn solid, the rest become the key color.
    """
    image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
    bg = Image.new("RGBA", image.size, KEY_COLOR)
    bg.paste(image, mask=solid_mask(image))
    return ImageTk.PhotoImage(bg.convert("RGB"))
