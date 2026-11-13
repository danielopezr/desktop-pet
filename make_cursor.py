"""Build assets/cursor/sword.cur from cursor_sword.png in the "Pixel Cursors & Icons"
pack by Willosuna (pixel-cursors-icons-r4.zip).

Usage: python make_cursor.py [path/to/pixel-cursors-icons-r4.zip]
Without a path, it looks for the zip in Downloads and in Pictures/Assets.

The sword is 10x10 px; scaled x3 (30 px) it fits the standard Windows cursor
(32x32), so Tkinter shows it at its own size with no tricks.
"""
import io
import struct
import sys
import zipfile
from pathlib import Path

from PIL import Image

ZIP_NAME = "pixel-cursors-icons-r4.zip"
SEARCH = [Path.home() / "Downloads", Path.home() / "Pictures" / "Assets"]
DST = Path(__file__).parent / "assets" / "cursor" / "sword.cur"
CANVAS = 32               # standard Windows cursor size
SCALE = 3                 # 10 px -> 30 px
OFFSET = (0, 0)           # placed at the top left, where the tip ends up
TIP = (0, 0)              # corner of the tip in the flipped drawing (10x10)

if len(sys.argv) > 1:
    ZIP = Path(sys.argv[1])
    if not ZIP.exists():
        sys.exit(f"Not found: {ZIP}")
else:
    ZIP = next((folder / ZIP_NAME for folder in SEARCH if (folder / ZIP_NAME).exists()), None)
    if ZIP is None:
        sys.exit(f"{ZIP_NAME} not found in " + " or ".join(str(f) for f in SEARCH)
                 + ". Pass its path: python make_cursor.py path/to/" + ZIP_NAME)

with zipfile.ZipFile(ZIP) as z:
    sword = Image.open(io.BytesIO(z.read("x1/cursor_sword.png"))).convert("RGBA")
# The original points to the top right; flip it so it points to the top left,
# like the normal Windows arrow.
sword = sword.transpose(Image.FLIP_LEFT_RIGHT)

big = sword.resize((sword.width * SCALE, sword.height * SCALE), Image.NEAREST)
canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
canvas.paste(big, OFFSET)
DST.parent.mkdir(parents=True, exist_ok=True)
canvas.save(DST, format="ICO", sizes=[(CANVAS, CANVAS)], bitmap_format="bmp")

# A .cur file is an .ico with type 2 and the hotspot in the planes/bitcount fields.
hotspot = (OFFSET[0] + TIP[0] * SCALE + 2, OFFSET[1] + TIP[1] * SCALE + 2)
data = bytearray(DST.read_bytes())
struct.pack_into("<H", data, 2, 2)
struct.pack_into("<HH", data, 6 + 4, *hotspot)
DST.write_bytes(data)
print("ok", DST, "hotspot", hotspot)
