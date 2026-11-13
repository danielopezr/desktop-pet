"""Build assets/dummy/sword.cur from cursor_sword.png in the "Pixel Cursors & Icons"
pack by Willosuna (Downloads/pixel-cursors-icons-r4.zip).

The sword is 10x10 px; scaled x3 (30 px) it fits the standard Windows cursor
(32x32), so Tkinter shows it at its own size with no tricks.
"""
import io
import struct
import zipfile
from pathlib import Path

from PIL import Image

ZIP = Path.home() / "Downloads" / "pixel-cursors-icons-r4.zip"
DST = Path(__file__).parent / "assets" / "dummy" / "sword.cur"
CANVAS = 32               # standard Windows cursor size
SCALE = 3                 # 10 px -> 30 px
OFFSET = (0, 0)           # placed at the top left, where the tip ends up
TIP = (0, 0)              # corner of the tip in the flipped drawing (10x10)

with zipfile.ZipFile(ZIP) as z:
    sword = Image.open(io.BytesIO(z.read("x1/cursor_sword.png"))).convert("RGBA")
# The original points to the top right; flip it so it points to the top left,
# like the normal Windows arrow.
sword = sword.transpose(Image.FLIP_LEFT_RIGHT)

big = sword.resize((sword.width * SCALE, sword.height * SCALE), Image.NEAREST)
canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
canvas.paste(big, OFFSET)
canvas.save(DST, format="ICO", sizes=[(CANVAS, CANVAS)], bitmap_format="bmp")

# A .cur file is an .ico with type 2 and the hotspot in the planes/bitcount fields.
hotspot = (OFFSET[0] + TIP[0] * SCALE + 2, OFFSET[1] + TIP[1] * SCALE + 2)
data = bytearray(DST.read_bytes())
struct.pack_into("<H", data, 2, 2)
struct.pack_into("<HH", data, 6 + 4, *hotspot)
DST.write_bytes(data)
print("ok", DST, "hotspot", hotspot)
