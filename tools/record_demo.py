"""Record the demo GIF shown in the README (docs/demo.gif).

Usage: python tools/record_demo.py [output.gif]

It runs a scripted scene: Parton chases the cursor and swings at it on the
ground and in the air, the cursor hits the dummy and throws it at Parton, who
dodges it, and the dummy hits Parton back while he trains.

Nothing is captured from the screen: every frame is drawn from the program's
own images (characters, hearts, "!" and "?") on a plain backdrop, with the
simulated cursor drawn on top. The real mouse is never moved, and the real
settings and cursor files are left alone. Parton and the dummy show up on the
screen for about 15 seconds while it records. It needs the sprites (see
README.md).
"""
import ctypes
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "demo.gif"
TMP = Path(tempfile.mkdtemp())
ctypes.windll.shcore.SetProcessDpiAwareness(2)

from PIL import Image, ImageDraw, ImageTk

import dummy
import parton
import platforms
import ui

random.seed(7)
cursor = [0.0, 0.0]
for module in (parton, dummy, ui):
    module.mouse_pos = lambda: (int(cursor[0]), int(cursor[1]))
parton.SETTINGS_FILE = TMP / "settings.json"
ui.CURSOR_DIR = TMP / "cursors"
if parton.missing_sprites() or not dummy.available():
    sys.exit("The sprites are missing from assets/ (see README.md).")
parton.fullscreen_app_open = lambda: False
platforms.window_rects = lambda: []          # a plain backdrop: no windows to stand on
platforms.window_rect = lambda hwnd: None
parton.EVADE_CHANCE = 1.0
parton.COUNTER_CHANCE = 0.0
parton.TRAIN_CHANCE = 0.0          # it only trains when the script says so

app = parton.App()
p, d = app.parton, app.dummy
app.settings["training"] = True

# The dummy's current frame (tkinter doesn't hand it back).
d_frame = [None]
_show = d.show_frame
def show_frame(frame):
    d_frame[0] = frame
    _show(frame)
d.show_frame = show_frame
d.show_frame(d.idle[0])

left, top, right, bottom = ui.work_area()
SCENE = (left, bottom - 340, left + 1000, bottom + 36)   # what the GIF shows
FRAME_MS = 60

# --- Drawing ---------------------------------------------------------------------
def backdrop():
    w, h = SCENE[2] - SCENE[0], SCENE[3] - SCENE[1]
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, w, h - 36), fill=(56, 66, 92))             # a plain desktop
    draw.rectangle((0, h - 36, w, h), fill=(24, 26, 34))          # a plain taskbar
    return img

BACKDROP = backdrop()
ARROW = ("#.......",
         "##......",
         "#w#.....",
         "#ww#....",
         "#www#...",
         "#wwww#..",
         "#ww###..",
         "#.#.....")


def arrow_image():
    im = Image.new("RGBA", (8, 8))
    for y, row in enumerate(ARROW):
        for x, c in enumerate(row):
            if c == "#":
                im.putpixel((x, y), ui.CURSOR_OUTLINE)
            elif c == "w":
                im.putpixel((x, y), (240, 240, 240, 255))
    return im.resize((24, 24), Image.NEAREST), (0, 0)


def cursor_image(name):
    im = ui.cursor_drawing(ui.SWORD if name == "sword" else ui.FIST)
    hx, hy = ui.CURSOR_HOTSPOTS[name]
    s = ui.CURSOR_SCALE
    return im.resize((im.width * s, im.height * s), Image.NEAREST), (hx * s + s // 2, hy * s + s // 2)


CURSORS = {"arrow": arrow_image(), "sword": cursor_image("sword"), "fist": cursor_image("fist")}


def photo_rgba(photo, alpha=1.0):
    img = ImageTk.getimage(photo).convert("RGBA")
    px = img.load()
    key = (255, 0, 254)
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, _ = px[x, y]
            px[x, y] = (0, 0, 0, 0) if (r, g, b) == key else (r, g, b, round(255 * alpha))
    return img


_cache = {}
def cached_rgba(photo):
    key = str(photo)
    if key not in _cache:
        _cache[key] = photo_rgba(photo)
    return _cache[key]


def over(widget_shape, origin):
    mask, (ox, oy) = widget_shape, origin
    x, y = int(cursor[0] - ox), int(cursor[1] - oy)
    return 0 <= x < mask.width and 0 <= y < mask.height and mask.getpixel((x, y))


def cursor_name():
    if p.state == "held" or d.state == "held":
        return "fist"
    if p.hitbox_shown:
        shape, (ox, oy) = p.hit_shapes[p.facing]
        if over(shape, (p.hitbox.winfo_rootx(), p.hitbox.winfo_rooty())):
            return "sword"
    if d.can_be_hit():
        wx, wy = d.window_pos()
        if over(d.body_shape, (wx + d.body[0], wy + d.body[1])):
            return "sword"
    return "arrow"


frames = []
stamps = []


def capture():
    img = BACKDROP.copy().convert("RGBA")
    def put(rgba, x, y):
        img.alpha_composite(rgba, (round(x - SCENE[0]), round(y - SCENE[1])))
    if d.on_screen() and d_frame[0] is not None:
        wx, wy = d.window_pos()
        put(cached_rgba(d_frame[0]), wx, wy)
    if p.on_screen() and p.shown is not None:
        put(cached_rgba(p.shown), p.root.winfo_rootx(), p.root.winfo_rooty())
    for hearts in (d.hearts, p.hearts):
        if hearts.visible and hearts.current is not None:
            put(cached_rgba(hearts.current), hearts.window.winfo_rootx(), hearts.window.winfo_rooty())
    for emote in (p.alert, p.question):
        if emote.job is not None:
            alpha = float(emote.window.attributes("-alpha"))
            put(photo_rgba(emote.photo, alpha), emote.window.winfo_rootx(), emote.window.winfo_rooty())
    image, (hx, hy) = CURSORS[cursor_name()]
    put(image, cursor[0] - hx, cursor[1] - hy)
    frames.append(img.convert("RGB"))
    stamps.append(time.perf_counter())


# --- The script --------------------------------------------------------------------
moves = []   # (start s, end s, from fn, to fn) cursor tweens


def move_to(target, seconds):
    start = (cursor[0], cursor[1])
    t0 = time.perf_counter()
    def step():
        t = min((time.perf_counter() - t0) / seconds, 1.0)
        tx, ty = target() if callable(target) else target
        e = t * t * (3 - 2 * t)                    # ease in and out
        cursor[0] = start[0] + (tx - start[0]) * e
        cursor[1] = start[1] + (ty - start[1]) * e
        if t < 1:
            app.root.after(15, step)
    step()


class Click:
    def __init__(self, x, y):
        self.x_root, self.y_root = x, y


def dummy_point(fx, fy):
    """A point on the dummy's body box, as fractions of it."""
    wx, wy = d.window_pos()
    bx0, by0, bx1, by1 = d.body
    return wx + bx0 + (bx1 - bx0) * fx, wy + by0 + (by1 - by0) * fy


def click_dummy(fx, fy):
    x, y = dummy_point(fx, fy)
    cursor[:] = [x, y]
    d.press(Click(x, y))
    app.root.after(70, lambda: d.release(None))


def parton_body():
    return p.x, bottom - p.y - p.body_height / 2


timeline = []
def at(ms, fn):
    timeline.append((ms, fn))


def setup():
    lo, hi = p.bounds()
    p.x = d.center_x() + 620
    p.facing = -1
    p.set_state("idle", idle_seconds=1.0)
    cursor[:] = [p.x + 380, bottom - 420]          # out of its sight


at(0, setup)
at(700, lambda: move_to(lambda: (p.x - 260, bottom - 70), 0.8))          # it sees it: chase, swing
at(2600, lambda: move_to(lambda: (p.x - parton.ATTACK_REACH * 0.6, bottom - 175), 0.35))  # too high: jump
at(4300, lambda: app.settings.update(calm=True))                        # calm: the cursor goes elsewhere
at(4300, lambda: move_to(lambda: dummy_point(0.62, 0.45), 1.0))         # over the dummy: its hearts
at(5600, lambda: click_dummy(0.62, 0.42))
at(6000, lambda: click_dummy(0.18, 0.14))
at(6400, lambda: click_dummy(0.55, 0.12))
at(6800, lambda: click_dummy(0.40, 0.60))


def grab_dummy():
    x, y = dummy_point(0.5, 0.45)
    cursor[:] = [x, y]
    d.press(Click(x, y))                                               # held long enough: a grab


def fling():
    move_to((cursor[0] + 330, cursor[1] - 140), 0.16)
    app.root.after(170, lambda: d.release(None))


at(7400, grab_dummy)
at(7800, fling)                                                        # thrown at Parton: he dodges
at(8600, lambda: move_to((left + 520, bottom - 300), 0.6))


def train():
    parton.COUNTER_CHANCE = 1.0
    p.set_state("train")


at(9700, train)                                                        # trains; the dummy hits back: "?"
at(12100, lambda: setattr(parton, "COUNTER_CHANCE", 0.0))
at(12400, lambda: move_to(parton_body, 0.7))                           # over Parton: his hearts
END_MS = 14600


def start():
    t0 = time.perf_counter()
    for ms, fn in timeline:
        app.root.after(ms, fn)
    def tick():
        capture()
        if (time.perf_counter() - t0) * 1000 < END_MS:
            app.root.after(FRAME_MS, tick)
        else:
            save()
    tick()


def save():
    path = OUTPUT
    path.parent.mkdir(parents=True, exist_ok=True)
    # One palette for the whole GIF, from a strip of frames across it: every
    # sprite color makes it in (the backdrop is flat, so it needs only two).
    sample = Image.new("RGB", (frames[0].width, frames[0].height * 8))
    for i in range(8):
        sample.paste(frames[i * (len(frames) - 1) // 7], (0, i * frames[0].height))
    palette = sample.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    pal = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    durations = [round((b - a) * 1000) for a, b in zip(stamps, stamps[1:])] + [FRAME_MS]
    durations = [max(20, round(ms / 10) * 10) for ms in durations]   # GIF counts in 10 ms
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=durations, loop=0,
                optimize=True, disposal=1)
    print(f"{path}: {len(frames)} frames, {frames[0].width}x{frames[0].height}, "
          f"{sum(durations) / 1000:.1f} s, {path.stat().st_size // 1024} KB")
    app.root.destroy()


app.root.after(600, start)
app.run()
