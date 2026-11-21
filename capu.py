"""Capu: a desktop pet for Windows, together with a training dummy (dummy.py),
both in this one program.

- Lives at the bottom of the screen, standing on the taskbar.
- Idles for a while and then runs to a random spot.
- If it sees the cursor nearby (left or right, not too high), it runs to it
  and swings its lantern with attack 1 or attack 2, at random. If the cursor
  is above the lantern's vertical reach, it tries to jump at it.
- If the cursor is right on top of it, it dashes back to get the lantern's
  distance and then attacks.
- If the cursor is within reach sideways but too high for the lantern, it jumps
  to try to reach it, and swings in the air if it gets close enough.
- Left click and hold to pick it up; release it anywhere and it falls back
  down to the taskbar. Let go while moving the cursor and it is thrown in
  that direction, as fast as the cursor was moving.
- A quick left click hits it; on the sixth hit it dies and disappears.
- Now and then, when the dummy is close enough, Capu goes to it and hits it
  a few times.
- When the dummy is thrown at it, it usually dodges: it jumps over a dummy
  coming from the side and dashes away from one falling on it.
- When it spots the cursor and starts chasing it, a "!" pops over its head.
- If the mouse hasn't moved or clicked for a minute (and nothing has hit it),
  it dozes off where it stands, with "Z"s floating up; bringing the cursor
  near (the taskbar under it counts) wakes it up ("!"), and so does hitting
  it or picking it up. A cursor that creeps up slowly doesn't wake it until
  it touches it. In calm mode the cursor never wakes it: only a hit,
  picking it up or "Wake Capu" in the menu do. However it wakes up, a "!"
  pops over its head; woken by a hit, it also hops aside, startled,
  keeping its eyes on the cursor. In calm mode, a cursor that keeps rubbing
  over it for a couple of seconds wakes it up ("!"): it gets up, looks
  around, dazed, walks a little way off and goes back to sleep there.
- Now and then, when Capu hits the dummy, it swings back and hits him,
  knocking him back a little; a puzzled "?" floats up from his head.
- Right click on either of them: menu to revive, hide or show each one, put
  Capu to sleep or wake him up, open
  the settings (calm mode, do not disturb, training, dummy fights back) or
  exit. If neither is left on the screen, the program closes.
- Calm mode: it ignores the cursor (no chasing or attacking).
- Do not disturb: both hide while a full-screen app (a game, a video, a
  presentation) is in front, and come back when it closes.
- An icon in the system tray opens the same menu, also with nobody on the
  screen.
- It walks on the open windows: now and then it jumps up onto the top of one
  nearby, lands on them when thrown or falling, rides along when a window is
  moved, and falls off (unhurt) when the window closes, is covered or it walks
  off the edge.

Every animation is listed in ANIMATIONS. The sprites are not included in the
repository (see README.md): put Capu's sprite sheets in assets/capu/sprites.
"""
import ctypes
import json
import math
import os
import random
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox

from PIL import Image, ImageChops, ImageFilter

import dummy as training_dummy
import light
import platforms
import tray
import ui
from screen import KEY_COLOR, mouse_pos, solid_mask, to_photo, work_area
from physics import (FALL_DAMAGE_SPEED, GRAVITY, IMPACT_BOUNCE, IMPACT_SPEED, WALL_BOUNCE, CursorTrail,
                     fly_step, is_drag, throw_velocity)

# --- Settings ------------------------------------------------------------------
SCALE = 4                     # the character is ~27x22 px in the original sprite
FRAME = 144                   # each frame of the sprite sheets is 144x144
WALK_SPEED = 76               # pixels per second while wandering: its walk (each step matches it)
RUN_SPEED = 160               # pixels per second while running somewhere (to train, to climb)
CHASE_SPEED = 260             # pixels per second while chasing the cursor
IDLE_SECONDS = (2.0, 7.0)     # how long it stays idle (min, max)
MIN_RUN_DISTANCE = 150        # each wander is at least this long...
MAX_WANDER = 600              # ...and at most this long, in pixels
TICK_MS = 16                  # update rate (~60 fps)

# Vision and attack (screen pixels, measured from the character's body)
VISION_RANGE = 450            # horizontal distance at which it sees the cursor
VISION_HEIGHT = 250           # how far above the taskbar it can see the cursor
LOSE_RANGE = 600              # beyond this distance it stops chasing
ATTACK_REACH = 35 * SCALE     # lantern reach (its swing gets up to 33 px ahead)
ATTACK_HEIGHT = 19 * SCALE    # top of the slash above its feet (sprite: 1-19 px)
SLASH_CENTER = 10 * SCALE     # middle of the slash above its feet: where it aims
# How far ahead of its body center the slash gets is measured from the sprites
# (see slash_reach): about 33 px.
ATTACK_PAUSE = 0.35           # pause between swings, in seconds
TOO_CLOSE = 20 * SCALE        # cursor on top of it: the lantern would miss
DASH_SPEED = 550              # pixels per second when dashing back
JUMP_MAX_HEIGHT = 160         # highest jump, in pixels (it jumps just enough to aim)
JUMP_MIN_HEIGHT = 40          # lowest jump, in pixels
JUMP_DRIFT = 140              # sideways speed while in the air, towards the cursor
JUMP_PAUSE = 0.6              # pause after landing before jumping again, in seconds
AIR_ATTACK_FRAME_MS = 45      # the air swing plays faster than the ground one
AIR_ATTACK_FIRST_FRAME = 2    # in the air it skips the wind-up (planted feet): straight to the slash
AIR_ATTACK_LAST_FRAME = 6     # ...and after this frame it skips the recovery and just falls
AIR_ATTACK_GRAVITY = 0.3      # while swinging it keeps falling, but floatier (share of gravity)

# Gravity, throwing and click-vs-drag settings are shared with the dummy: see physics.py.

# Getting hit
HITS_TO_DIE = 6               # hits it takes before dying (even: two hits per heart)
DEATH_LINGER = 1.5            # seconds it lies there after dying, before disappearing
HEAL_DELAY = 10.0             # seconds without being hit before it starts healing
HEAL_INTERVAL = 6.0           # then it heals one hit every this many seconds
FLEE_AT = 2                   # with this many hits left (or fewer) it flees the cursor
FLEE_DASH_DISTANCE = 200      # if the cursor is closer than this, it dashes away
FLEE_JUMP_HEIGHT = 90         # height of the dodging hops while fleeing, in pixels
FLEE_JUMPS_PER_SECOND = (0.6, 2.0)  # how often it hops: cursor far, cursor close

# Dozing off
SLEEP_AFTER = 60.0            # seconds without the mouse moving before it falls asleep
Z_EVERY = 0.9                 # a new "Z" starts floating up this often while it sleeps...
Z_SECONDS = 1.8               # ...and each lasts this long, so two are rising at a time
Z_RISE = 64                   # how far each "Z" floats up, in pixels (leaves a gap between two)
Z_DRIFT = 22                  # and how far sideways, towards where it faces (a diagonal)
WAKE_PAUSE = 0.35             # after waking up it stands still this long before reacting
SNEAK_SPEED = 350             # a cursor slower than this (pixels per second) sneaks up on it: only touching it wakes it
STARTLE_PUSH = 300            # woken by a hit it hops aside, away from the cursor (sideways speed)...
STARTLE_LIFT = 720            # ...this high (upward speed: about a 100 px hop), facing the cursor
NUDGE_SECONDS = 2.0           # calm mode: this long of the cursor moving over it, asleep, bothers it...
GROGGY_LOOKS = 3              # ...so it gets up and looks one way and the other, this many times...
GROGGY_LOOK_SECONDS = 0.5     # ...this long each, dazed...
SHUFFLE_DISTANCE = 120        # ...then walks this far away from the cursor...
SHUFFLE_SPEED = 53            # ...this slowly (pixels per second)...
SHUFFLE_FRAME_MS = 150        # ...with its walk played slowly to match, and naps again

# Training on the dummy
TRAIN_CHANCE = 0.4            # chance of training instead of wandering, after idling
TRAIN_RANGE = 600             # only if the dummy is at most this far, in pixels
TRAIN_SWINGS = (1, 3)         # how many swings per training session (min, max)
TRAIN_PAUSE = 0.5             # pause between swings, in seconds
TRAIN_GAP = ATTACK_REACH * 0.8  # distance from the dummy it swings from

# Walking on windows
PLATFORM_SCAN_MS = 200        # how often it looks at where the open windows are
LEDGE_MIN = 100               # narrowest stretch of a window's top it stands on, in pixels
CLIMB_CHANCE = 0.35           # chance of jumping up onto a window instead of wandering, after idling
CLIMB_MIN = 60                # it only jumps up onto window tops at least this high above it...
CLIMB_HEIGHT = 450            # ...and at most this high, in pixels
CLIMB_RANGE = 700             # ...and at most this far to either side
CLIMB_OVERSHOOT = 40          # it jumps this much higher than the window top, to land on it
STAY_CHANCE = 0.6             # on a window, chance of wandering along it (else anywhere: maybe off it)
WALK_OFF_SPEED = 120          # sideways speed it keeps as it walks off the edge of a window
SIT_CHANCE = 0.3              # on a window, chance of going to sit on one of its edges instead of wandering
SIT_SECONDS = (6.0, 15.0)     # how long it sits there, legs dangling (min, max)

# The lantern's light (see light.py)
LIGHT_RADIUS = 16             # sprite pixels from the lantern to the edge of its glow
LIGHT_STRENGTH = 0.75         # how strong it shines, from 0 to 1...
LIGHT_STATES = {"attack": 1.0, "air_attack": 1.0, "celebrate": 1.0,   # ...brighter as it swings or cheers...
                "doze": 0.5, "sleep": 0.35}                           # ...dimmer as it dozes off and sleeps
LIGHT_FLICKER = 0.12          # how much it wavers, like a flame (share of its strength)
LIGHT_FLICKER_MS = 110        # how often it changes how much
LIGHT_RAISE_SECONDS = 0.5     # how often its light is put back in front of it (if anything came over it)

# Parkour: the screen's edges and the windows' sides are walls (only in the air)
WALL_BOUNCE_SPEED = 900       # thrown at a wall this fast (sideways) or more, it bounces off it; slower,
                              # it grabs it and slides...
WALL_SLIDE_SPEED = 140        # ...down at this speed, in pixels per second...
WALL_HOLD = 0.7               # ...for this long, and then jumps off it, back into the screen
WALL_JUMP = (420, 700)        # sideways and upward speed of that jump off a wall
WALL_CLING = 0.12             # on a wall before each jump off it (the first two frames of its jump)
CORNER_CHANCE = 0.5           # chance of climbing onto a window by its corner (else it jumps straight on top)
PARKOUR_CHANCE = 0.5          # chance of going up a gap between walls, wall to wall, even if one jump would do
KICK_RISE = 150               # height it gains with each jump from wall to wall, in pixels
KICK_TIME = 0.35              # seconds each of those jumps takes
MIN_GAP = 120                 # a gap between two walls it goes up must be at least this wide...
MAX_GAP = 320                 # ...and at most this wide, in pixels
MAX_KICKS = 8                 # ...and need at most this many jumps
HANG_SECONDS = (0.3, 0.7)     # how long it hangs from a window's corner before pulling itself up
LEDGE_REACH = 9.5             # sprite pixels from its body center to the corner it hangs from
                              # (where sprite-lab draws the window in "Ledge Grab"/"Ledge Climb")
SLASH_FRAMES = {"attack1": (3,), "attack2": (3, 9)}  # frames where the slash lands

# Dodging the dummy when it is thrown at Capu
EVADE_CHANCE = 0.75           # chance of dodging each throw of the dummy at it
EVADE_MARGIN = 0.06           # it dodges at the last moment: when waiting this much longer would be too late
EVADE_LOOKAHEAD = 1.2         # how far ahead it follows the dummy's flight, in seconds
EVADE_JUMP_HEIGHT = 260       # how high it jumps over the dummy, in pixels
EVADE_DASH_DISTANCE = 260     # how far it dashes out of the way, in pixels
KNOCKBACK_FACTOR = 0.6        # share of the dummy's speed that pushes Capu when it hits him
KNOCKBACK_MAX = 900           # cap on that push, in pixels per second
KNOCKBACK_LIFT = 450          # the push also pops him up a little (upward speed)

# The dummy hitting back
COUNTER_CHANCE = 0.2          # chance that a hit from Capu makes the dummy swing back at him
COUNTER_DELAY_MS = 250        # the swing back comes this long after his hit
COUNTER_REACH = 40            # it only reaches Capu if he is this close to it, in pixels
COUNTER_PUSH = 450            # how hard it pushes him away (sideways speed)
COUNTER_LIFT = 350            # and how much it pops him up (upward speed)
EVADE_STATES = ("idle", "run", "train", "chase", "flee", "attack", "dodge")  # it can dodge from these

# Menu settings, saved between runs
SETTINGS_FILE = Path(os.environ.get("APPDATA", Path.home())) / "Capu" / "settings.json"
DEFAULT_SETTINGS = {
    "calm": False,            # ignore the cursor: no chasing or attacking it
    "do_not_disturb": True,   # hide while a full-screen app is in front
    "training": True,         # go and hit the dummy now and then
    "dummy_hits_back": True,  # the dummy sometimes hits Capu back
    "windows": True,          # climb onto and walk on the open windows
    "light": True,            # its lantern lights up what is around it
}
SETTING_LABELS = {"calm": "Calm mode", "do_not_disturb": "Do not disturb",
                  "training": "Training", "dummy_hits_back": "Dummy hits back",
                  "windows": "Walk on windows", "light": "Lantern light"}
FULLSCREEN_CHECK_MS = 1000    # how often "do not disturb" looks for a full-screen app

# The icon in the system tray: Capu drawn pixel for pixel, with a light
# outline so it shows on a dark taskbar too. At 16 px only its head fits.
TRAY_OUTLINE = ui.TEXT_COLOR
TRAY_HEAD = 14                # sprite pixels of its head in the smallest icon (16 with the outline)
TRAY_SIZES = (16, 32, 48)

SPRITES = Path(__file__).parent / "assets" / "capu" / "sprites"

# name: (file, milliseconds per frame, loops)
ANIMATIONS = {
    "idle":    ("Idle.png",     130, True),
    "run":     ("Run.png",       80, True),
    "attack1": ("Attack 1.png",  70, False),
    "attack2": ("Attack 2.png",  70, False),
    "dash":    ("Dash.png",      60, True),
    "jump":    ("Jump.png",     100, True),
    "fall":    ("Fall.png",     100, True),
    "hurt":    ("Hurt.png",      70, False),
    "death":   ("Death.png",     90, False),
    "doze":    ("Doze.png",     150, False),
    "sleep":   ("Sleep.png",    900, True),
    "wall_slide":  ("Wall Slide.png",   90, True),
    "wall_jump":   ("Wall Jump.png",    60, False),
    "ledge_grab":  ("Ledge Grab.png",  140, True),
    "ledge_climb": ("Ledge Climb.png",  70, False),
    "celebrate":   ("Celebrate.png",    80, False),
    "walk":        ("Walk.png",        105, True),
    "sit_down":    ("Sit Down.png",     90, False),
    "stand_up":    ("Sit Down.png",     90, False),   # sitting down, played backwards
    "sit":         ("Sit.png",         150, True),
}
REVERSED = {"stand_up"}       # animations whose sheet plays backwards
USED = tuple(ANIMATIONS)


def load_settings():
    """The saved settings, with the defaults for anything missing or unreadable."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        settings.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS})
    except (OSError, ValueError, AttributeError):
        pass
    return settings


def save_settings(settings):
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass                                  # not saved: it still works for this run


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def fullscreen_app_open():
    """True if the window in front covers the whole main screen (a game, a video,
    a presentation). The desktop, the taskbar and this program's own windows don't count."""
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return False
    name = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, name, 64)
    if name.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        return False
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info))  # nearest
    m = info.rcMonitor
    # A maximized window covers the whole screen too when the taskbar hides
    # itself, but its frame sticks out past the screen's edges; a real
    # full-screen window ends right on them.
    if user32.IsZoomed(hwnd) and rect.left < m.left and rect.top < m.top:
        return False
    on_main_screen = info.dwFlags & 1                 # MONITORINFOF_PRIMARY: where they live
    return bool(on_main_screen and rect.left <= m.left and rect.top <= m.top
                and rect.right >= m.right and rect.bottom >= m.bottom)


def missing_sprites():
    files = dict.fromkeys(file for file, _, _ in ANIMATIONS.values())
    return [file for file in files if not (SPRITES / file).exists()]


def raw_frames(file):
    sheet = Image.open(SPRITES / file).convert("RGBA")
    return [sheet.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME))
            for i in range(sheet.width // FRAME)]


def sheet_frames(name):
    """The frames of animation `name`, uncropped (in the order they play)."""
    frames = raw_frames(ANIMATIONS[name][0])
    return frames[::-1] if name in REVERSED else frames


def union_bbox(frames):
    boxes = [b for b in (solid_mask(f).getbbox() for f in frames) if b]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def crop_box():
    """Crop shared by every animation, symmetric around the body.

    Being symmetric keeps the character in place when the sprite is flipped
    to face left. Also returns the ground line: the row its feet rest on in
    most idle and run frames (a stray frame goes one pixel lower and must not
    leave the rest floating).
    """
    all_frames = [f for name in ANIMATIONS for f in sheet_frames(name)]
    x0, y0, x1, y1 = union_bbox(all_frames)
    bx0, _, bx1, _ = union_bbox(raw_frames(ANIMATIONS["idle"][0]))
    center = (bx0 + bx1) / 2
    half = max(center - x0, x1 - center)
    body_half = (bx1 - bx0) / 2
    bottoms = [solid_mask(f).getbbox()[3] for name in ("idle", "run")
               for f in raw_frames(ANIMATIONS[name][0])]
    ground = max(set(bottoms), key=bottoms.count)
    return (round(center - half), y0, round(center + half), y1), body_half, ground


def animation_frames(name, box):
    """The frames of animation `name`, cropped to `box`."""
    return [f.crop(box) for f in sheet_frames(name)]


NOSE = (0xE9, 0xA3, 0xA3)     # Capu's pink nose: no other part of the sprites is that color
NOSE_TO_TOP = 8               # rows from its nose up to the tips of its hood's ears
HOOD_HALF = 6                 # its hood spans this far to each side of the nose (13 px)


def nose(frame):
    """(left, top, right) of its head in `frame` found from its nose, or None if
    the nose doesn't show.

    Its head (hood and face) never changes shape, so the nose marks the middle of its head and how far
    up it starts. It doesn't show when everything flashes white (getting hurt)
    or when it fades away.
    """
    px = frame.load()
    for y in range(frame.height):
        for x in range(frame.width):
            r, g, b, a = px[x, y]
            if a >= 128 and (r, g, b) == NOSE:
                return x - HOOD_HALF, y - NOSE_TO_TOP, x + HOOD_HALF + 1
    return None


def nose_at(frame):
    """(x, y) of its nose in `frame`."""
    left, top, _ = nose(frame)
    return left + HOOD_HALF, top + NOSE_TO_TOP


LANTERN_GLASS = {(0xFA, 0xD0, 0x58), (0xFF, 0xEE, 0xB2)}   # the flame and the lit glass
LANTERN_IRON = (0x48, 0x4C, 0x53)                         # the lantern's sides


def lantern_at(frame):
    """(x, y) of the middle of its lantern's glass in `frame`, or None if no lit
    lantern shows (dying, a white flash). The glass is the flame's colors with
    the lantern's iron on both sides: not the yellow trails of a swing."""
    width, height = frame.size
    data = frame.load()
    def iron(x, y):
        return 0 <= x < width and data[x, y][3] and data[x, y][:3] == LANTERN_IRON
    xs, ys = [], []
    for y in range(height):
        for x in range(width):
            r, g, b, a = data[x, y]
            if a and (r, g, b) in LANTERN_GLASS and any(iron(x - d, y) for d in (1, 2, 3)) \
                    and any(iron(x + d, y) for d in (1, 2, 3)):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return sum(xs) / len(xs) + 0.5, sum(ys) / len(ys) + 0.5


def head_mark(frame):
    """(left, top, right) of its head in `frame`, or None if it doesn't show (see nose)."""
    return nose(frame)


def head_offset(frame):
    """How far the middle of its head (around its nose) is from the middle of
    `frame`, in screen pixels (facing right), or None if its head doesn't show."""
    h = head_mark(frame)
    return None if h is None else ((h[0] + h[2]) / 2 - frame.width / 2) * SCALE


def head_top_row(frame):
    """The row of `frame` where its head starts (the tips of its hood's ears), or None."""
    h = head_mark(frame)
    return None if h is None else h[1]


def slash_reach(box):
    """How far ahead of its body center (sprite pixels) its swing gets in the
    frames where it lands (the shortest of them): the lantern at the end of its
    staff. `box` is the crop from crop_box."""
    center = (box[0] + box[2]) / 2
    reach = []
    for name, picks in SLASH_FRAMES.items():
        frames = raw_frames(ANIMATIONS[name][0])
        reach += [solid_mask(frames[i]).getbbox()[2] - 1 - center for i in picks]
    return min(reach)


def sit_edge(frame, ground):
    """Sitting on the edge of a window (`frame`, uncropped, facing right), the
    column where the window's side is: the first one of what hangs below its seat
    (its legs, the hem of its cloak). `ground` is the row its feet stand on."""
    below = solid_mask(frame).crop((0, ground, frame.width, frame.height)).getbbox()
    return below[0]


def fill_gaps(values, fallback):
    """Frames where the head doesn't show take it from the frame before (or `fallback`)."""
    out, last = [], None
    for v in values:
        last = v if v is not None else last
        out.append(fallback if last is None else last)
    return out


def hit_shape(frames, facing):
    """Its silhouette on screen over `frames` (facing 1: right, -1: left), cropped
    to the body, and where that crop sits in its window.

    One-pixel gaps (the jagged edges of the pixel art) are closed so the cursor
    doesn't flicker along the outline, without making the silhouette bigger.
    """
    mask = None
    for frame in frames:
        m = solid_mask(frame)
        mask = m if mask is None else ImageChops.lighter(mask, m)
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    if facing == -1:
        mask = mask.transpose(Image.FLIP_LEFT_RIGHT)
    mask = mask.resize((mask.width * SCALE, mask.height * SCALE), Image.NEAREST)
    x0, y0, x1, y1 = mask.getbbox()
    return mask.crop((x0, y0, x1, y1)), (x0, y0)


def icon_image(image, size):
    """`image` cropped to what is drawn in it, outlined and scaled up by whole
    pixels to fit a `size` square, in the middle of it."""
    image = image.crop(solid_mask(image).getbbox())
    framed = Image.new("RGBA", (image.width + 2, image.height + 2))
    framed.paste(image, (1, 1))
    image = ui.outline(framed, TRAY_OUTLINE)
    scale = max(1, min(size // image.width, size // image.height))
    image = image.resize((image.width * scale, image.height * scale), Image.NEAREST)
    square = Image.new("RGBA", (size, size))
    square.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
    return square


def tray_images(box):
    """Its icon for the system tray, {size: image}: its idle pose, or only its
    head (its hood, down) where the whole of it doesn't fit."""
    frame = animation_frames("idle", box)[0]
    left, top, right = head_mark(frame)
    middle = (left + right) // 2
    half = TRAY_HEAD // 2
    head = frame.crop((middle - half, top, middle + half, top + TRAY_HEAD))
    whole = solid_mask(frame).getbbox()
    return {size: icon_image(frame if max(whole[2] - whole[0], whole[3] - whole[1]) + 2 <= size
                             else head, size)
            for size in TRAY_SIZES}


class App:
    """Owns both characters, the right-click menu they share and the tray icon.

    The program lives on while its tray icon is there, even with nobody on
    the screen: the icon opens the same menu.
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()                      # only the characters' windows show
        self.menu = None                          # the styled menu, while it is open
        self.settings = load_settings()
        self.away = False                         # hidden by "do not disturb"
        self.ledges = []                          # window tops to stand on: (height, left, right, window)
        self.walls = []                           # window sides: (x, low, high, face, window), see all_walls
        self.dummy = training_dummy.TrainingDummy(self.root, self) if training_dummy.available() else None
        self.capu = Capu(self.root, self)
        try:
            self.tray = tray.TrayIcon(self.root, tray_images(self.capu.box), "Capu",
                                      self.tray_clicked)
        except OSError:
            self.tray = None                      # no tray: right-clicking them still works
        self.root.bind("<Destroy>", self.on_destroy, add="+")
        self.watch_fullscreen()
        self.scan_platforms()

    def scan_platforms(self):
        """Now and then: where the tops of the open windows are (both of them
        stand on them), and whether each one still has its footing."""
        try:
            self.ledges, self.walls = [], []
            if self.settings["windows"] and not self.away:
                left, top, right, bottom = work_area()
                windows = platforms.window_rects()
                found = platforms.ledges(windows, (left, top, right, bottom), LEDGE_MIN)
                self.ledges = sorted(((bottom - y, l, r, hwnd) for hwnd, l, r, y in found),
                                     reverse=True)            # the highest first
                self.walls = [(x, bottom - b, bottom - a, face, hwnd)        # heights above the taskbar
                              for hwnd, x, a, b, face in platforms.walls(windows, (left, top, right, bottom))]
            for _, c in self.characters():
                c.check_footing()
        finally:
            self.root.after(PLATFORM_SCAN_MS, self.scan_platforms)

    def ledges_for(self, room):
        """The window tops with `room` pixels free above them, up to the top of the screen."""
        _, top, _, bottom = work_area()
        return [ledge for ledge in self.ledges if ledge[0] + room <= bottom - top]

    def all_walls(self):
        """The walls: the windows' sides and the screen's edges, as (x, low, high, face, window).
        `x` is the screen column, `low`..`high` the heights above the taskbar it
        spans and `face` the way it faces (-1: touched from its left, 1: from its
        right); the screen's edges have no window."""
        left, top, right, bottom = work_area()
        return self.walls + [(left, 0.0, bottom - top, 1, None), (right, 0.0, bottom - top, -1, None)]

    def on_destroy(self, event):
        """The program is closing: take its icon out of the tray."""
        if event.widget is self.root and self.tray:
            self.tray.remove()
            self.tray = None
        if event.widget is self.root and self.capu.glow is not None:
            self.capu.glow.destroy()              # its own window: Tk doesn't close it

    def tray_clicked(self):
        """The tray icon: the main menu, at the cursor (above the taskbar)."""
        self.open_menu(*mouse_pos())

    def characters(self):
        return [(name, c) for name, c in (("Capu", self.capu), ("dummy", self.dummy)) if c]

    def menu_items(self):
        """(label, action) for each character: revive the dead, hide or show the
        living, and put Capu to sleep (or wake him up)."""
        items = []
        for name, c in self.characters():
            if not c.alive:
                items.append((f"Revive {name}", c.revive))
            elif c.hidden:
                items.append((f"Show {name}", c.unhide))
            else:
                items.append((f"Hide {name}", c.hide))
                if c is self.capu:
                    items.append(("Wake Capu", c.wake) if c.asleep() else ("Sleep Capu", c.sleep_now))
        return items

    def setting_items(self):
        """(label, action) that switches each setting on or off."""
        return [(f"{label}: {'on' if self.settings[key] else 'off'}",
                 lambda k=key: self.toggle(k))
                for key, label in SETTING_LABELS.items()]

    def toggle(self, key):
        self.settings[key] = not self.settings[key]
        save_settings(self.settings)
        if key == "do_not_disturb":
            self.check_fullscreen()               # switched off: they come back right away

    def watch_fullscreen(self):
        self.check_fullscreen()
        self.root.after(FULLSCREEN_CHECK_MS, self.watch_fullscreen)

    def check_fullscreen(self):
        """Do not disturb: hide both while a full-screen app is in front."""
        away = self.settings["do_not_disturb"] and fullscreen_app_open()
        if away != self.away:
            self.away = away
            if away and self.menu:
                self.menu.close()
            for _, c in self.characters():
                c.set_away(away)

    def show_menu(self, event):
        """Right click: the main menu, at the cursor."""
        self.open_menu(event.x_root, event.y_root)

    def open_menu(self, x, y, flip=True):
        """Menu built on the spot, so it always matches what is on the screen.

        Pixel-art if the font is in assets/ui; otherwise the plain Windows menu.
        """
        if self.menu:
            self.menu.close()
        if ui.available():
            items = self.menu_items() + [("Settings", self.in_place(self.open_settings)),
                                         None, ("Exit", self.root.destroy)]
            self.menu = ui.PopupMenu(self.root, items, x, y, self.do, flip)
            return
        menu = tk.Menu(self.root, tearoff=0)
        for label, action in self.menu_items():
            menu.add_command(label=label, command=lambda a=action: self.do(a))
        settings = tk.Menu(menu, tearoff=0)
        for label, action in self.setting_items():
            settings.add_command(label=label, command=lambda a=action: self.do(a))
        menu.add_cascade(label="Settings", menu=settings)
        menu.add_separator()
        menu.add_command(label="Exit", command=self.root.destroy)
        menu.tk_popup(x, y)

    def open_settings(self, x, y):
        """The settings submenu, where the menu was. It stays open after switching one."""
        if self.menu:
            self.menu.close()
        items = [(label, self.in_place(lambda x, y, a=action: (a(), self.open_settings(x, y))))
                 for label, action in self.setting_items()]
        items += [None, ("Back", self.in_place(lambda x, y: self.open_menu(x, y, flip=False)))]
        self.menu = ui.PopupMenu(self.root, items, x, y, self.do, flip=False)

    def in_place(self, open_next):
        """An action that opens `open_next` where the current menu is."""
        return lambda: open_next(self.menu.x, self.menu.y)

    def do(self, action):
        action()
        self.check_empty()

    def check_empty(self):
        """With nobody left on the screen and no tray icon, there is nothing to
        right-click: close. Unless the dummy is about to come back on its own.
        """
        if self.tray is None and not any(c.on_screen() or c.respawning()
                                         for _, c in self.characters()):
            self.root.destroy()

    def run(self):
        self.root.mainloop()


class Capu:
    def __init__(self, master, app):
        self.app = app
        self.root = tk.Toplevel(master)
        self.root.title("Capu")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", KEY_COLOR)
        self.root.config(bg=KEY_COLOR)

        box, body_half, ground = crop_box()
        self.box = box                            # its crop of the sprites (the tray icon uses it)
        self.width = (box[2] - box[0]) * SCALE
        self.height = (box[3] - box[1]) * SCALE
        self.ground = (ground - box[1]) * SCALE   # height of the feet inside the window
        self.body_half = body_half * SCALE
        self.slash_reach = slash_reach(box) * SCALE   # how far ahead of its body center the slash gets
        idle_top = union_bbox(raw_frames(ANIMATIONS["idle"][0]))[1]
        self.body_height = (ground - idle_top) * SCALE   # from its feet to the top of its head
        # Where its head is in every frame, from its body center, facing right:
        # the hearts and the "!" and "?" go over it (it moves when it runs or swings).
        # ...and how high the top of its head is, above its feet (lower when it slumps).
        idle_frame = animation_frames("idle", box)[0]
        idle_offset = head_offset(idle_frame)
        # The sprite isn't centered on its body (the lantern hangs behind it): flipped
        # to face the other way, the body would jump twice this far (see turn).
        self.turn_shift = idle_offset
        idle_height = self.ground - head_top_row(idle_frame) * SCALE
        self.head_offsets, self.head_heights = {}, {}
        # Hanging from a corner it is drawn down and to one side of where it will
        # stand on the window: how far (screen pixels, facing right), from its nose.
        (ix, iy), (gx, gy) = (nose_at(sheet_frames(n)[0]) for n in ("idle", "ledge_grab"))
        self.hang_shift = ((gx - ix) * SCALE, (gy - iy) * SCALE)
        # Sitting on the edge of a window, its legs hang past the window's side:
        # how far that side is from its body center (screen pixels).
        self.sit_reach = (sit_edge(sheet_frames("sit")[0], ground) - (box[0] + box[2]) / 2) * SCALE
        for name in ANIMATIONS:
            frames = animation_frames(name, box)
            self.head_offsets[name] = fill_gaps([head_offset(f) for f in frames], idle_offset)
            rows = fill_gaps([head_top_row(f) for f in frames], None)
            self.head_heights[name] = [idle_height if r is None else self.ground - r * SCALE
                                       for r in rows]
        # Where its lantern is in every frame (screen pixels in its window, facing
        # right; None where no lit lantern shows): its light goes there.
        self.lanterns = {}
        for name in ANIMATIONS:
            spots = [lantern_at(f) for f in animation_frames(name, box)]
            self.lanterns[name] = [None if s is None else (s[0] * SCALE, s[1] * SCALE) for s in spots]
        try:
            self.glow = light.Glow(LIGHT_RADIUS, SCALE)
        except OSError:
            self.glow = None                      # no light, but everything else works
        self.light_spot = None                    # (x, y, strength) of its light on the screen now
        self.flicker = self.flicker_to = 1.0      # how much the flame's light wavers now / next
        self.next_flicker = 0.0
        # Its own dice: the flame flickers on the clock, and that mustn't change
        # what comes out of the ones everything else uses (same seed, same choices).
        self.flicker_rng = random.Random()
        self.next_raise = 0.0                     # when to put its light back in front of it
        self.sit_left = 0.0                       # how much longer it sits on the edge of a window
        self.sit_facing = 1                       # ...and which one (1: its right edge, -1: its left)
        self.impact_done = True                   # only a fresh throw can hit the dummy
        self.celebrate_pending = False

        # Frames facing right (original) and left (flipped).
        self.frames = {}
        for name in ANIMATIONS:
            raw = animation_frames(name, box)
            self.frames[name] = {
                1: [to_photo(f, SCALE) for f in raw],
                -1: [to_photo(f.transpose(Image.FLIP_LEFT_RIGHT), SCALE) for f in raw],
            }

        self.label = tk.Label(self.root, bg=KEY_COLOR, bd=0)
        self.label.pack()

        # Hit zone behind it, shaped like its idle pose (one shape per side it
        # faces): the mouse doesn't slip through the gaps in its pixel art.
        # Hanging and climbing it is drawn away from where it stands: those get their own.
        idle_frames = [f.crop(box) for f in raw_frames(ANIMATIONS["idle"][0])]
        self.hit_shapes = {None: {facing: hit_shape(idle_frames, facing) for facing in (1, -1)}}
        for name in ("ledge_grab", "ledge_climb", "sit_down", "sit", "stand_up"):
            frames = animation_frames(name, box)
            self.hit_shapes[name] = {facing: hit_shape(frames, facing) for facing in (1, -1)}
        self.hitbox = ui.hit_zone(master)
        self.hitbox_facing = None             # the side its current shape faces...
        self.hitbox_kind = None               # ...and whose shape it is (None: the idle pose)
        self.hitbox_shown = False

        # Sword cursor over it; a closed hand while holding it.
        for widget in (self.label, self.hitbox):
            widget.bind("<Button-3>", app.show_menu)
            widget.bind("<ButtonPress-1>", self.press)
            widget.bind("<ButtonRelease-1>", self.release)
        self.pressed = None                       # (time, x, y) of a left click in progress
        self.dummy = app.dummy                    # None if the dummy's sprites are missing
        self.away = False                         # hidden by "do not disturb"
        self.evade_roll = 0                       # the last dummy throw it decided to dodge or not
        self.evade_planned = False                # ...and whether it will dodge that one
        self.hearts = ui.Hearts(master)         # shown while the cursor is over it
        self.question = ui.Emote(master, ui.QUESTION, ui.GOLD)  # puzzled when the dummy hits back
        self.alert = ui.Emote(master, ui.EXCLAMATION, ui.GOLD)  # "!" when it spots the cursor
        self.on_cursor = False                    # in the middle of a chase after the cursor
        # "Z"s while asleep: two, taking turns, so a new one rises while the last fades.
        self.zzz = [ui.Emote(master, ui.SLEEP_Z, ui.SKY, rise=Z_RISE, seconds=Z_SECONDS,
                             fade_in=0.15) for _ in range(2)]
        self.next_z = 0                           # which of them goes next
        self.next_emote = 0.0                     # when the next "Z" is due
        self.last_mouse = None                    # where the mouse was, and when it last moved
        self.last_mouse_move = time.perf_counter()
        self.mouse_trail = CursorTrail()          # how fast the mouse is moving (sneaking up on it asleep)
        self.slept_at = 0.0
        self.wake_guard = False                   # put to sleep from the menu: see sleeping()
        self.nudged = 0.0                         # calm mode: how long the cursor has bothered it asleep
        self.shown = None
        self.anim = None
        self.spawn()
        self.last = time.perf_counter()
        self.tick()
        self.keep_on_top()

    def spawn(self):
        """Start fresh: full health, standing somewhere on the taskbar."""
        lo, hi = self.bounds()
        self.x = random.uniform(lo, hi)           # body center, in screen pixels
        self.y = 0.0                              # height of its feet above the taskbar
        self.floor = 0.0                          # ...and of what it stands on (or last stood on)
        self.platform = None                      # the window it stands on (None: the taskbar)
        self.platform_rect = None                 # ...and where that window was last seen
        self.vx = self.vy = 0.0                   # speed, positive is right / up
        self.climb_plan = ("leap", None)          # how it goes up onto a window (see ledge_to_climb)
        self.route = []                           # parkour: the steps still ahead (see chimney)
        self.flight = None                        # ...and the jump it is in (see launch)
        self.wall = None                          # the wall it slides down (see grab_wall)
        self.wall_left = self.cling = self.hang_left = 0.0
        self.facing = random.choice((1, -1))
        self.hits = 0
        self.alive = True
        self.gone = False                         # dead and already gone from the screen
        self.hidden = False                       # hidden from the menu
        self.closing = False
        self.last_hurt = self.last_heal = 0.0     # when it was last hit / last healed
        self.training = False                     # in the middle of a session on the dummy
        self.attack_target = "cursor"
        self.set_cursor("sword")
        self.set_state("idle")

    # --- Menu actions ------------------------------------------------------------
    def on_screen(self):
        return not self.gone and not self.hidden

    def respawning(self):
        return False                              # Capu only comes back from the menu

    def hide(self):
        self.hidden = True
        self.pressed = None
        self.root.withdraw()
        self.show_hitbox(False)
        self.hide_emotes()

    def hide_emotes(self):
        """Off the screen, nothing is left floating where its head was (nor its light)."""
        for emote in (self.alert, self.question, *self.zzz):
            emote.hide()
        if self.glow is not None:
            self.glow.hide()
            self.light_spot = None

    def unhide(self):
        self.hidden = False
        self.show_window()

    def revive(self):
        self.spawn()
        self.show_window()

    def show_window(self):
        """Put it back on the screen, unless "do not disturb" is keeping it away."""
        if not self.away:
            self.root.deiconify()

    def set_away(self, away):
        """Hide it while a full-screen app is open ("do not disturb"), and bring it back."""
        if away == self.away:
            return
        self.away = away
        if away:
            if self.state == "held":             # dropped if it was being held
                self.state, self.vx, self.vy = "dropped", 0.0, 0.0
                self.set_cursor("sword")
            self.show_hitbox(False)
            self.pressed = None
            self.root.withdraw()
            self.hearts.hide()
            self.hide_emotes()
        elif not self.hidden and not self.gone:
            self.root.deiconify()

    def vanish(self):
        """After dying and lying there a moment, it disappears until revived."""
        if self.alive:                            # revived in the meantime
            return
        self.gone = True
        self.root.withdraw()
        self.hide_emotes()
        self.app.check_empty()

    # --- Helpers ---------------------------------------------------------------
    def bounds(self):
        """How far the body center can go without leaving the screen."""
        left, _, right, _ = work_area()
        return left + self.body_half, right - self.body_half

    def sees_mouse(self, max_range):
        """(horizontal distance, height above the taskbar) of the cursor if seen, else None.

        In calm mode it never sees it, so it doesn't chase or attack it.
        """
        if self.app.settings["calm"]:
            return None
        return self.cursor_in_sight(max_range)

    def cursor_in_sight(self, max_range, taskbar=False):
        """Like sees_mouse, but also in calm mode.

        With `taskbar`, a cursor down on the taskbar under it counts too (or
        anywhere below the window it stands on): it can't chase it there, but it
        notices it (waking up). Heights are measured from what it stands on.
        """
        mx, my = mouse_pos()
        _, _, _, bottom = work_area()
        dx, height = mx - self.x, bottom - my - self.floor   # above what it stands on
        low = -float("inf") if taskbar else -5
        if abs(dx) <= max_range and low <= height <= VISION_HEIGHT:
            return dx, height
        return None

    def dummy_in_range(self):
        """True if training is on and the dummy is standing close enough to go and hit it."""
        return (self.app.settings["training"] and self.dummy_standing()
                and self.platform is None and self.y == 0   # it is down on the taskbar too
                and abs(self.dummy.center_x() - self.x) <= TRAIN_RANGE)

    def dummy_standing(self):
        """The dummy is standing still down on the taskbar, where it can be trained on."""
        return self.dummy is not None and self.dummy.standing()

    def slash_hits_dummy(self):
        """True if a slash right now reaches the dummy, whatever it was aimed at."""
        if self.dummy is None or not self.dummy.can_be_hit():
            return False
        d0, d1 = self.dummy.body_span()
        a, b = sorted((self.x, self.x + self.facing * self.slash_reach))
        if b < d0 or a > d1:                 # not in front of it, or too far
            return False
        low, high = self.dummy.body_heights()  # the dummy may be held or flying
        return self.y <= high and self.y + ATTACK_HEIGHT >= low

    def point_on_dummy(self, height):
        """Screen point where Capu strikes the dummy: on the side of its body
        that faces him, `height` pixels above his feet."""
        _, _, _, bottom = work_area()
        return self.dummy.surface_point(bottom - self.y - height,
                                        from_left=self.x < self.dummy.center_x())

    def face_dummy(self):
        self.facing = 1 if self.dummy.center_x() > self.x else -1

    # --- States ----------------------------------------------------------------
    def set_state(self, state, idle_seconds=None, target="cursor"):
        self.state = state
        # "!" when a new chase starts: not between swings of the same one. The
        # chase is over once it calms down, wanders, trains, celebrates or flees.
        if state == "chase":
            if not self.on_cursor:
                self.alert.show(self.head_top)
            self.on_cursor = True
        elif (state in ("run", "train", "celebrate", "flee", "climb", "to_edge", "sit")
              or (state == "idle" and idle_seconds is None)):
            self.on_cursor = False
        if state in ("chase", "flee", "run", "jump", "dodge", "evade", "doze", "groggy", "shuffle",
                     "climb", "leap", "falling", "to_edge", "sit"):
            self.training = False            # the cursor or a wander interrupts training
        if state in ("idle", "run"):
            self.set_anim("walk" if state == "run" else state, restart=True)   # it wanders walking
        # A short pause (after a swing or a jump): it keeps still and doesn't react.
        self.pausing = state == "idle" and idle_seconds is not None
        if state == "idle":
            self.idle_left = idle_seconds if idle_seconds is not None else random.uniform(*IDLE_SECONDS)
        elif state == "run":
            self.start_run()
        elif state in ("chase", "flee"):
            self.set_anim("run")
        elif state == "attack":
            self.attack_target = target
            self.set_anim(random.choice(("attack1", "attack2")), restart=True)
        elif state == "train":
            self.training = True
            self.target = self.train_target()
            self.set_anim("run")
        elif state == "dodge":
            self.set_anim("dash", restart=True)
        elif state == "jump":
            self.start_jump()
        elif state == "celebrate":
            self.vy = 0.0
            self.set_anim("celebrate", restart=True)   # its victory pose, where it stands
        elif state == "doze":
            self.start_doze()
        elif state == "sleep":
            self.set_anim("sleep", restart=True)
        elif state == "groggy":
            self.looks_left = GROGGY_LOOKS
            self.look_left = GROGGY_LOOK_SECONDS
            self.set_anim("idle", restart=True)
        elif state == "shuffle":
            self.start_shuffle()
        elif state == "climb":
            self.target = (self.takeoff_x(self.climb_to) if self.climb_plan[0] == "leap"
                           else self.climb_plan[1])
            self.set_anim("run")
        elif state == "to_edge":
            self.set_anim("walk")            # to the edge on the sit_facing side (see sit_spot)
        elif state == "sit":
            self.set_anim("sit_down", restart=True)
        elif state in ("leap", "falling"):
            self.set_anim("jump" if self.vy > 0 else "fall", restart=True)
        elif state == "air_attack":
            # It keeps its jump's arc (no stopping dead in the air) and goes
            # straight into the slash.
            self.air_swung = True
            self.set_anim("attack1", restart=True, frame_ms=AIR_ATTACK_FRAME_MS,
                          start=AIR_ATTACK_FIRST_FRAME)

    def start_run(self):
        """Wander: pick a spot far enough along the taskbar and face it. On a
        window it mostly stays on it (STAY_CHANCE); otherwise it may walk off."""
        lo, hi = self.bounds()
        if self.platform_rect is not None and random.random() < STAY_CHANCE:
            left, _, right, _ = self.platform_rect
            on_lo, on_hi = max(lo, left + self.body_half), min(hi, right - self.body_half)
            if on_lo < on_hi:
                lo, hi = on_lo, on_hi
        lo, hi = max(lo, self.x - MAX_WANDER), min(hi, self.x + MAX_WANDER)
        options = [x for x in (random.uniform(lo, hi) for _ in range(20))
                   if abs(x - self.x) >= MIN_RUN_DISTANCE]
        self.target = options[0] if options else (lo if self.x > (lo + hi) / 2 else hi)
        self.facing = 1 if self.target > self.x else -1

    def start_jump(self):
        # Jump just high enough for the middle of the slash to reach the cursor.
        seen = self.sees_mouse(LOSE_RANGE)
        wanted = seen[1] - SLASH_CENTER if seen else JUMP_MAX_HEIGHT
        rise = min(max(wanted, JUMP_MIN_HEIGHT), JUMP_MAX_HEIGHT)
        self.vy = (2 * GRAVITY * rise) ** 0.5
        self.air_swung = False           # one air swing per jump
        self.set_anim("jump", restart=True)

    def start_doze(self):
        """Slump where it stands; the first "Z" comes a moment later."""
        self.on_cursor = False
        self.wake_guard = False
        self.nudged = 0.0
        self.slept_at = time.perf_counter()
        self.next_emote = self.slept_at + 0.8
        self.set_anim("doze", restart=True)

    def start_shuffle(self):
        # Away from the cursor (the other way if it is against the edge).
        mx, _ = mouse_pos()
        away = -1 if mx > self.x else 1
        lo, hi = self.bounds()
        if abs(min(max(self.x + away * SHUFFLE_DISTANCE, lo), hi) - self.x) < SHUFFLE_DISTANCE / 2:
            away = -away
        self.turn(away)                      # turns where it stands...
        self.target = min(max(self.x + away * SHUFFLE_DISTANCE, lo), hi)   # ...and walks off
        self.set_anim("walk", restart=True, frame_ms=SHUFFLE_FRAME_MS)

    def train_target(self):
        """Spot at the lantern's distance from the dummy, on the side Capu is on
        (or the other one if there is no room there)."""
        lo, hi = self.bounds()
        cx = self.dummy.center_x()
        side = 1 if self.x >= cx else -1
        for s in (side, -side):
            target = cx + s * TRAIN_GAP
            if lo <= target <= hi:
                return target
        return min(max(cx + side * TRAIN_GAP, lo), hi)

    def set_anim(self, name, restart=False, frame_ms=None, start=0):
        """Switch animation; start from frame `start` if it changes or if asked to."""
        if restart or self.anim != name:
            self.anim = name
            self.frame_ms = frame_ms or ANIMATIONS[name][1]
            self.frame_index = start
            self.frame_elapsed = 0.0

    def tick(self):
        # Whatever goes wrong in one update, the next one still comes: it
        # mustn't freeze for good.
        try:
            self.update()
        finally:
            self.root.after(TICK_MS, self.tick)

    def update(self):
        now = time.perf_counter()
        dt, self.last = min(now - self.last, 0.1), now
        if self.hidden or self.gone or self.away:   # off the screen: nothing to do
            self.hearts.hide()
            return
        self.heal(now)
        self.track_mouse(now)
        self.ride()
        if (self.state == "idle" and not self.pausing and self.grounded()
                and now - max(self.last_mouse_move, self.last_hurt) >= SLEEP_AFTER):
            self.set_state("doze")               # nothing has happened for a while: nap
        if self.state in EVADE_STATES and self.y == 0:
            self.check_incoming_dummy()

        if self.state in ("run", "train", "climb", "to_edge") or (self.state == "idle" and not self.pausing):
            # While calm, keep watch: if it sees the cursor, go after it (or flee).
            if self.sees_mouse(VISION_RANGE) is not None:
                self.set_state(self.reaction())

        self.act(now, dt)
        if self.pressed and self.state != "held":
            self.check_drag_start()

        before = (self.anim, self.frame_index)
        finished = self.animate(dt)
        self.check_slash(*before)
        self.check_impacts(dt)
        if finished:
            self.animation_finished()
        self.place()
        self.update_hearts()

    def act(self, now, dt):
        """What it does this update, by the state it is in."""
        if self.state == "idle":
            self.idle_step(dt)
        elif self.state == "train":
            if not self.dummy_standing():
                self.training = False
                self.set_state("idle")
            else:
                self.target = self.train_target()   # follow it if it was moved
                self.move_towards(self.target, RUN_SPEED, dt)
                if self.x == self.target:    # in position: face it and start swinging
                    self.face_dummy()
                    self.swings_left = random.randint(*TRAIN_SWINGS)
                    self.set_state("attack", target="dummy")
        elif self.state == "run":
            self.move_towards(self.target, WALK_SPEED, dt)
            if self.x == self.target:
                self.set_state("idle")
        elif self.state == "to_edge":
            if self.platform_rect is None:
                self.set_state("idle")
                return
            self.target = self.sit_x(self.sit_facing)    # (the window may be moving)
            self.move_towards(self.target, WALK_SPEED, dt)
            if self.x == self.target:            # at the edge, facing out of the window
                self.set_state("sit")
        elif self.state == "sit":
            self.sit_step(dt)
        elif self.state == "chase":
            self.chase(dt)
        elif self.state == "dodge":
            self.move_towards(self.target, DASH_SPEED, dt)
            if self.x == self.target:        # has room now: turn around and re-evaluate
                self.set_state("chase")
        elif self.state == "flee":
            self.flee(dt)
        elif self.state == "celebrate":
            pass                             # its victory pose: see animation_finished
        elif self.state == "evade":
            self.evade_step(dt)
        elif self.state in ("doze", "sleep"):
            self.sleeping(now, dt)
        elif self.state == "groggy":
            self.groggy_step(dt)
        elif self.state == "shuffle":
            self.move_towards(self.target, SHUFFLE_SPEED, dt)
            if self.x == self.target:            # far enough from that cursor: back to sleep
                self.set_state("doze")
        elif self.state == "jump":
            self.jump(dt)
        elif self.state == "climb":
            self.climb(dt)
        elif self.state == "parkour":
            self.parkour(dt)
        elif self.state == "wall_jump":
            self.wall_jump(dt)
        elif self.state == "wall_slide":
            self.wall_slide(dt)
        elif self.state == "ledge_hang":
            self.ledge_hang(dt)
        elif self.state == "ledge_climb":
            pass                             # pulling itself up: see animation_finished
        elif self.state in ("leap", "falling"):
            self.drop_down(dt)
        elif self.state == "air_attack":
            self.air_attack(dt)
        elif self.state == "held":
            self.follow_cursor()
        elif self.state == "dropped":
            self.fly(dt)
        elif self.state in ("hurt", "dead"):
            self.knocked(dt)                 # pushed by a hit, or falling if hit in the air

    def idle_step(self, dt):
        """Standing still, until its rest (or its short pause) is over."""
        self.idle_left -= dt
        if self.idle_left <= 0:
            # After a short pause, go back to the cursor if it is still in
            # sight, carry on training, or stay idle for a normal while.
            # After a normal idle: sometimes train on the dummy, else wander.
            if not self.pausing:
                ledge = self.ledge_to_climb() if random.random() < CLIMB_CHANCE else None
                side = self.sit_spot() if random.random() < SIT_CHANCE else None
                if self.dummy_in_range() and random.random() < TRAIN_CHANCE:
                    self.set_state("train")
                elif ledge is not None:
                    self.climb_to = ledge
                    self.set_state("climb")
                elif side is not None:
                    self.sit_facing = side
                    self.set_state("to_edge")
                else:
                    self.set_state("run")
            elif self.sees_mouse(VISION_RANGE) is not None:
                self.set_state(self.reaction())
            elif self.training and self.dummy_standing():
                self.face_dummy()
                self.set_state("attack", target="dummy")
            else:
                self.training = False
                self.set_state("idle")

    def sit_x(self, facing):
        """Where it sits on the edge of its window that is on the `facing` side."""
        left, _, right, _ = self.platform_rect
        return (right if facing == 1 else left) - facing * self.sit_reach

    def sit_spot(self):
        """Which edge of the window it stands on it would go and sit on: the side
        (1: right, -1: left), or None.

        It sits facing out of the window, with its legs hanging past the window's
        side, so it only goes to an edge it walks towards (it gets there facing
        out). The edge has to be a real one, not covered by a window in front, and
        on the screen."""
        if self.platform is None or self.platform_rect is None or not self.grounded():
            return None
        left, _, right, _ = self.platform_rect
        lo, hi = self.bounds()
        spots = []
        for facing in (1, -1):
            x = self.sit_x(facing)
            ahead = (x - self.x) * facing
            if not lo <= x <= hi or ahead < self.sit_reach:
                continue
            if any(hwnd == self.platform and abs(height - self.y) <= 2 and l <= x <= r
                   and (r >= right - 1 if facing == 1 else l <= left + 1)
                   for height, l, r, hwnd in self.ledges):
                spots.append(facing)
        return random.choice(spots) if spots else None

    def sit_step(self, dt):
        """Sitting on the edge: legs dangling until its while there is over or it
        sees the cursor; then it gets up (see animation_finished)."""
        if self.anim != "sit":
            return                               # still sitting down, or getting up
        self.sit_left -= dt
        if self.sit_left <= 0 or self.sees_mouse(VISION_RANGE) is not None:
            self.set_anim("stand_up", restart=True)

    def groggy_step(self, dt):
        # Dazed: it looks one way, then the other...
        self.look_left -= dt
        if self.look_left <= 0:
            self.looks_left -= 1
            if self.looks_left > 0:
                self.turn(-self.facing)      # turning its head, not moving
                self.look_left = GROGGY_LOOK_SECONDS
            else:
                self.set_state("shuffle")    # ...and wanders off a little

    def check_slash(self, anim, index):
        """Any slash that reaches the dummy hurts it, whatever it was aimed at.

        `anim` and `index` are the animation and the frame on show before this
        update: the slash lands when a swing gets to (or past: a late update may
        skip frames) one of its SLASH_FRAMES.
        """
        if self.state not in ("attack", "air_attack") or self.anim != anim:
            return
        if not any(index < frame <= self.frame_index for frame in SLASH_FRAMES.get(anim, ())):
            return
        if not self.slash_hits_dummy():
            return
        if self.dummy.take_hit(self.point_on_dummy(SLASH_CENTER)):
            self.celebrate_pending = True    # it broke it: celebrate
        elif self.app.settings["dummy_hits_back"] and random.random() < COUNTER_CHANCE:
            self.root.after(COUNTER_DELAY_MS, self.dummy_hits_back)

    def animation_finished(self):
        """A one-off animation (a swing, a flinch, slumping, dying) has played out."""
        if self.state == "attack" and self.celebrate_pending:
            self.celebrate_pending = False
            self.training = False
            self.set_state("celebrate")
        elif self.state == "attack" and self.attack_target == "dummy":
            # Training swing finished: another one after a short pause, or done.
            self.swings_left -= 1
            if self.swings_left > 0 and self.dummy_standing():
                self.set_state("idle", idle_seconds=TRAIN_PAUSE)
            else:
                self.training = False
                self.set_state("idle")
        elif self.state in ("attack", "air_attack"):
            self.celebrate_pending = False
            if not self.grounded():
                # Air swing finished: keep falling.
                self.state = "jump"
                self.set_anim("fall")
            else:
                # Swing finished: short pause and keep watching.
                self.set_state("idle", idle_seconds=ATTACK_PAUSE)
        elif self.state == "hurt":
            if not self.grounded():
                self.state, self.vy = "dropped", min(self.vy, 0.0)   # keeps any push
                self.set_anim("fall")
            elif self.sees_mouse(VISION_RANGE) is not None:
                self.set_state(self.reaction())  # strike back (or flee) right away
            else:
                self.set_state("idle", idle_seconds=ATTACK_PAUSE)
        elif self.state == "doze":
            self.set_state("sleep")      # slumped: now it sleeps
        elif self.state == "ledge_climb":
            self.set_state("idle", idle_seconds=JUMP_PAUSE)   # up on the window
        elif self.state == "celebrate":
            self.set_state("idle")
        elif self.state == "sit" and self.anim == "sit_down":
            self.set_anim("sit")                     # sat down: legs dangling for a while
            self.sit_left = random.uniform(*SIT_SECONDS)
        elif self.state == "sit":
            self.set_state("idle")                   # got up: idle (it may go for the cursor right away)
        elif self.anim == "wall_jump" and self.state == "parkour":
            self.set_anim("jump" if self.vy > 0 else "fall")
        elif self.state == "dead" and not self.closing:
            self.closing = True
            self.root.after(int(DEATH_LINGER * 1000), self.vanish)

    def update_hearts(self):
        """Show its health above its head while the cursor is over its body."""
        l, r, b, t = self.body_box()
        _, _, _, bottom = work_area()
        mx, my = mouse_pos()
        head_y = bottom - t
        if self.alive and self.state != "held" and l <= mx <= r and head_y <= my <= bottom - b:
            self.hearts.show(self.head_top()[0], head_y, HITS_TO_DIE - self.hits, HITS_TO_DIE)
        else:
            self.hearts.hide()

    def move_towards(self, target, speed, dt):
        step = speed * dt
        if abs(target - self.x) <= step:
            self.x = target
        else:
            self.facing = 1 if target > self.x else -1
            self.x += step * self.facing

    # --- Health: healing and fleeing ---------------------------------------------
    def low_health(self):
        return HITS_TO_DIE - self.hits <= FLEE_AT

    def reaction(self):
        """What it does on seeing the cursor: attack it, or run away when badly hurt."""
        return "flee" if self.low_health() else "chase"

    def heal(self, now):
        """After a while without being hit, recover one hit at a time."""
        if (self.alive and self.hits > 0 and now - self.last_hurt >= HEAL_DELAY
                and now - self.last_heal >= HEAL_INTERVAL):
            self.hits -= 1
            self.last_heal = now

    # --- Sleeping ----------------------------------------------------------------------
    def track_mouse(self, now):
        """Note when the mouse was last used: moved, or a button pressed (anywhere)."""
        position = mouse_pos()
        self.mouse_trail.add(*position)
        if position != self.last_mouse or ui.any_mouse_button_down():
            self.last_mouse, self.last_mouse_move = position, now

    def asleep(self):
        return self.state in ("doze", "sleep")

    def turn(self, facing):
        """Face the other way without moving: flipping the sprite alone would make
        its body jump sideways (the sprite isn't centered on it), so it is moved
        back by as much."""
        if facing == self.facing:
            return
        lo, hi = self.bounds()
        self.x = min(max(self.x + (self.facing - facing) * self.turn_shift, lo), hi)
        self.facing = facing

    def cursor_over_body(self):
        l, r, b, t = self.body_box()
        _, _, _, bottom = work_area()
        mx, my = mouse_pos()
        return l <= mx <= r and bottom - t <= my <= bottom - b

    def cursor_sneaking(self):
        """True while the mouse moves slowly (or not at all): too quietly to wake it."""
        vx, vy = self.mouse_trail.speed()
        return (vx * vx + vy * vy) ** 0.5 < SNEAK_SPEED

    def sleep_now(self):
        """Put to sleep from the menu (on the ground; not while held or flying)."""
        if not self.alive or not self.grounded() or self.state in ("held", "dropped", "dead"):
            return
        self.set_state("doze")
        # The cursor is right next to it (the menu was opened on it): leaving
        # mustn't wake it. It has to go away first; coming back then wakes it.
        self.wake_guard = True

    def sleeping(self, now, dt):
        """Asleep: "Z"s float up until the cursor comes near again.

        Only a cursor that has moved since it fell asleep wakes it, and one
        that moves slowly (SNEAK_SPEED) sneaks up on it: that one wakes it only
        when it touches its body. Put to sleep
        from the menu, the cursor must first go away before coming near wakes it.
        In calm mode the cursor never wakes it (a hit, picking it up or "Wake
        Capu" in the menu still do), but rubbing it for a while bothers it:
        it gets up, looks around dazed, walks a little way off and naps again.
        """
        if self.app.settings["calm"]:
            if self.cursor_over_body() and now - self.last_mouse_move < 0.15:
                self.nudged += dt                # the cursor moving over it
            else:
                self.nudged = max(0.0, self.nudged - dt / 2)   # it settles down again
            if self.nudged >= NUDGE_SECONDS:
                self.woken()                     # "!"
                self.on_cursor = False
                self.set_state("groggy")
                return
        near = (not self.app.settings["calm"]
                and self.cursor_in_sight(VISION_RANGE, taskbar=True) is not None)
        if self.wake_guard and not near:
            self.wake_guard = False
        noticed = self.cursor_over_body() or not self.cursor_sneaking()
        if near and noticed and not self.wake_guard and self.last_mouse_move > self.slept_at:
            self.wake()
            return
        if now >= self.next_emote:
            self.next_emote = now + Z_EVERY
            self.zzz[self.next_z].show(self.head_top, drift=self.facing * Z_DRIFT)
            self.next_z = 1 - self.next_z

    def wake(self):
        """Woken up by the cursor (or the menu): "!", a moment to come round, and
        then it reacts."""
        self.woken()
        self.set_state("idle", idle_seconds=WAKE_PAUSE)

    def woken(self):
        """Whatever woke it up: a "!" over its head."""
        self.alert.show(self.head_top)
        self.on_cursor = True                # the chase that may follow already had its "!"

    def flee(self, dt):
        """Run away from the cursor (dash if it is very close) until it is out of sight,
        hopping now and then so it is harder to hit."""
        airborne = not self.grounded()
        if airborne:
            self.fall(dt, 1.0)               # finish the hop wherever it is going
        seen = self.sees_mouse(LOSE_RANGE)
        if not airborne and seen is None:    # safe: calm down
            self.set_state("idle")
            return
        if not airborne and not self.low_health():   # healed enough: fight back
            self.set_state("chase")
            return
        dx = seen[0] if seen else -self.facing
        away = -1 if dx > 0 else 1 if dx < 0 else random.choice((1, -1))
        lo, hi = self.bounds()
        target = min(max(self.x + away * LOSE_RANGE, lo), hi)
        close = abs(dx) < FLEE_DASH_DISTANCE
        before = self.x
        self.move_towards(target, DASH_SPEED if close else CHASE_SPEED, dt)
        if not self.grounded():
            self.set_anim("jump" if self.vy > 0 else "fall")
        elif self.x == before:               # cornered: nowhere to go, it just faces it
            self.facing = 1 if dx >= 0 else -1
            self.set_anim("idle")
        else:
            self.set_anim("dash" if close else "run")
        # Dodging hops: more often the closer the cursor is.
        far_rate, close_rate = FLEE_JUMPS_PER_SECOND
        rate = close_rate if close else far_rate
        if self.grounded() and random.random() < rate * dt:
            self.vy = (2 * GRAVITY * FLEE_JUMP_HEIGHT) ** 0.5
            self.y = self.floor + 0.1        # off the ground

    def chase(self, dt):
        if self.low_health():                # badly hurt: run away instead
            self.set_state("flee")
            return
        seen = self.sees_mouse(LOSE_RANGE)
        if seen is None:                     # lost it: calm down again
            self.set_state("idle")
            return
        dx, height = seen
        self.facing = 1 if dx >= 0 else -1
        if abs(dx) <= ATTACK_REACH:
            if height > ATTACK_HEIGHT:
                self.set_state("jump")       # too high for the lantern: jump at it
            elif abs(dx) < TOO_CLOSE:
                self.dodge(dx)               # cursor on top of it: back off to hit it
            else:
                self.set_state("attack")
            return
        # Run closer until the cursor is within the lantern's reach.
        lo, hi = self.bounds()
        mx = self.x + dx
        target = min(max(mx - self.facing * ATTACK_REACH * 0.8, lo), hi)
        before = self.x
        self.move_towards(target, CHASE_SPEED, dt)
        self.facing = 1 if dx >= 0 else -1
        # Against the screen edge and unable to get closer: wait and watch.
        self.set_anim("run" if self.x != before else "idle")

    def jump(self, dt):
        """Jump at the cursor: rise, swing if it gets in reach, fall and land."""
        seen = self.sees_mouse(LOSE_RANGE)
        if seen is not None:
            dx, height = seen
            if abs(dx) >= 1:
                self.facing = 1 if dx > 0 else -1
            # Drift so the cursor ends up at the lantern's distance, not right overhead.
            lo, hi = self.bounds()
            target = min(max(self.x + dx - self.facing * ATTACK_REACH * 0.8, lo), hi)
            self.move_towards(target, JUMP_DRIFT, dt)
            self.facing = 1 if dx >= 0 else -1
            # At the top of the jump, swing if the cursor is within the slash.
            above = height - (self.y - self.floor)   # the cursor, above its feet
            if (not self.air_swung and self.vy <= 0
                    and TOO_CLOSE <= abs(dx) <= ATTACK_REACH
                    and 0 <= above <= ATTACK_HEIGHT):
                self.set_state("air_attack")
                return
        self.fall(dt, 1.0)
        if self.state == "jump":
            self.set_anim("jump" if self.vy > 0 else "fall")

    def air_attack(self, dt):
        """Swinging in mid-air: it drifts down slowly while it slashes, then
        falls normally (or lands, if it reached the ground first)."""
        self.fall(dt, AIR_ATTACK_GRAVITY)
        if self.frame_index > AIR_ATTACK_LAST_FRAME or self.grounded():
            self.celebrate_pending = False
            if not self.grounded():
                self.state = "jump"
                self.set_anim("fall")
            else:
                self.set_state("idle", idle_seconds=ATTACK_PAUSE)

    def fall(self, dt, gravity_factor):
        """Apply gravity; on landing (on the taskbar or a window), rest briefly
        (or finish the swing on the ground)."""
        before = self.y
        self.vy -= GRAVITY * gravity_factor * dt
        self.y += self.vy * dt
        if self.land(before) and self.state in ("jump", "dropped", "evade", "leap", "falling"):
            self.vx = 0.0
            self.set_state("idle", idle_seconds=JUMP_PAUSE)

    # --- Clicking: hit, or drag and drop -------------------------------------------
    def press(self, event):
        """Left button down: it becomes a hit or a grab depending on what follows."""
        if self.state == "dead":
            return
        self.pressed = (time.perf_counter(), event.x_root, event.y_root)
        self.grab_offset = (event.x_root - self.root.winfo_x(),
                            event.y_root - self.root.winfo_y())

    def check_drag_start(self):
        """Moving the cursor or holding the button turns the click into a grab."""
        _, _, _, bottom = work_area()
        window_pos = (self.x - self.width / 2, bottom - self.ground - self.y)
        if is_drag(self.pressed, mouse_pos(), window_pos, self.grab_offset, not self.grounded()):
            self.grab()

    def release(self, _event):
        """Left button up: a quick click is a hit; after a grab, it's a drop."""
        if self.state == "held":
            self.drop()
        elif self.pressed and self.state != "dead":
            self.hit()
        self.pressed = None

    def hit(self):
        """Take a hit: flinch towards the cursor, or die on the last one.

        Hits taken while it is already flinching still count, but don't make the
        flinch longer: clicking fast can't keep it stunned.
        """
        startled = self.asleep()                 # woken up by it
        self.let_go()                            # hanging from a corner: it falls from there
        self.hits += 1
        self.last_hurt = time.perf_counter()
        if self.state == "hurt" and self.hits < HITS_TO_DIE:
            return
        mx, _ = mouse_pos()
        if abs(mx - self.x) >= 1:
            self.facing = 1 if mx > self.x else -1
        self.vx = 0.0
        self.vy = min(self.vy, 0.0)
        self.training = False
        self.state = "dead" if self.hits >= HITS_TO_DIE else "hurt"
        self.alive = self.state != "dead"
        if not self.alive:
            self.set_cursor(None)            # nothing left to hit
        self.closing = False
        self.set_anim("death" if self.state == "dead" else "hurt", restart=True)
        if startled and self.alive:
            # "!" and a hop aside, away from the cursor (still facing it).
            self.woken()
            self.knock(-self.facing * STARTLE_PUSH, STARTLE_LIFT)

    def grab(self):
        """Pick it up: it hangs from the cursor at the point where it was grabbed."""
        if self.asleep():
            self.woken()
        self.let_go()                        # hanging from a corner: picked up from where it is drawn
        # Hold it by wherever the cursor is on it now, so it doesn't jump.
        mx, my = mouse_pos()
        _, _, _, bottom = work_area()
        wx = self.x - self.width / 2
        wy = bottom - self.ground - self.y
        self.grab_offset = (min(max(mx - wx, 0), self.width), min(max(my - wy, 0), self.height))
        self.pressed = None
        self.training = False
        self.platform = self.platform_rect = None   # lifted off whatever it stood on
        self.state = "held"
        self.vx = self.vy = 0.0
        self.cursor_trail = CursorTrail()
        self.impact_done = False             # this throw may hit the dummy
        self.set_anim("fall")
        self.set_cursor("fist")

    def drop(self):
        """Let go: it flies off with the cursor's speed and direction, then falls."""
        self.state = "dropped"
        self.set_cursor("sword")
        self.vx, self.vy = throw_velocity(*self.cursor_trail.speed())
        if abs(self.vx) > 50:
            self.facing = 1 if self.vx > 0 else -1

    def follow_cursor(self):
        mx, my = mouse_pos()
        self.cursor_trail.add(mx, my)
        _, _, _, bottom = work_area()
        lo, hi = self.bounds()
        ox, oy = self.grab_offset
        self.x = min(max(mx - ox + self.width / 2, lo), hi)
        self.y = max(bottom - self.ground - (my - oy), 0.0)   # never below the taskbar

    def fly(self, dt):
        """Thrown: move with its own speed, slowed by the air, bouncing off the screen
        edges (or grabbing a wall it hits hard enough, see grab_wall)."""
        lo, hi = self.bounds()
        _, top, _, bottom = work_area()
        ceiling = bottom - top - self.ground  # its window can't go above the screen
        before = self.vx
        x_before = self.x
        falling = -self.vy
        height = self.y
        self.x, self.vx, self.y, self.vy = fly_step(self.x, self.vx, self.y, self.vy,
                                                    dt, lo, hi, ceiling)
        if self.grab_wall(x_before, before):  # thrown hard into a wall: it slides down it
            return
        if before * self.vx < 0 and abs(self.vx) > 50:   # bounced: face the new way
            self.facing = 1 if self.vx > 0 else -1
        if self.land(height):                # landed (on the taskbar or a window)
            self.vx = 0.0
            self.impact_done = True
            if falling >= FALL_DAMAGE_SPEED:
                self.hit()                   # a hard landing hurts
            else:
                self.set_state("idle", idle_seconds=JUMP_PAUSE)

    # --- Standing on windows -----------------------------------------------------------
    def grounded(self):
        """Standing on something: the taskbar or the top of a window."""
        return self.y == self.floor

    @property
    def ledges(self):
        """The window tops with room for it to stand on, the highest first."""
        return self.app.ledges_for(self.body_height)

    def check_footing(self):
        """After each look at the windows: if the stretch it stands on has gone
        (covered by a window in front, say), it falls."""
        if (not self.hidden and not self.gone and not self.away and self.platform is not None
                and self.grounded()
                and not platforms.stands_on(self.ledges, self.platform, self.x, self.y)):
            self.step_off()

    def ride(self):
        """Standing on a window: move along with it. If it has gone (closed,
        minimized, maximized) or it no longer is under its feet, it falls."""
        if self.platform is None or not self.grounded():
            return
        rect = platforms.window_rect(self.platform)
        _, _, _, bottom = work_area()
        if rect is None or bottom - platforms.top_row(rect) <= 0:
            self.step_off()
            return
        if self.platform_rect is not None:
            lo, hi = self.bounds()
            self.x = min(max(self.x + rect[0] - self.platform_rect[0], lo), hi)
        self.platform_rect = rect
        self.y = self.floor = bottom - platforms.top_row(rect)
        if not rect[0] <= self.x <= rect[2]:
            self.step_off()

    def land(self, before):
        """After moving from height `before`: if it came down onto something,
        stand on it. True if it did. Going up, it passes through window tops."""
        if self.vy > 0:
            return False
        spot = platforms.landing(self.ledges, self.x, before, self.y)
        if spot is None:
            return False
        self.y, self.vy = spot[0], 0.0
        self.floor, self.platform = spot
        self.platform_rect = platforms.window_rect(self.platform) if self.platform else None
        return True

    def step_off(self):
        """The window under its feet is gone: it falls (no harm in it), keeping
        a little of its stride if it was walking."""
        self.let_go()                        # it was hanging from that window's corner
        self.platform = self.platform_rect = None
        self.floor = 0.0
        if self.y <= 0:                      # (only a window down at the taskbar)
            self.y = 0.0
            return
        if self.state in ("hurt", "dead"):
            return                           # already being carried down (see knocked)
        walking = self.state in ("run", "chase", "flee", "dodge", "shuffle", "train", "climb", "to_edge")
        self.vx = self.facing * WALK_OFF_SPEED if walking else 0.0
        self.vy = 0.0
        self.set_state("falling")

    def ledge_to_climb(self):
        """A window top to climb, or None. How it goes up is picked too (see
        climb_plans): one jump straight onto it, a jump to one of its corners
        to hang from it and pull itself up, or wall to wall up a gap."""
        options = [(ledge, plans) for ledge in self.ledges for plans in [self.climb_plans(ledge)] if plans]
        if not options:
            return None
        ledge, plans = random.choice(options)
        kinds = {}
        for plan in plans:
            kinds.setdefault(plan[0], []).append(plan)
        if "parkour" in kinds and (len(kinds) == 1 or random.random() < PARKOUR_CHANCE):
            self.climb_plan = random.choice(kinds["parkour"])
        elif "corner" in kinds and ("leap" not in kinds or random.random() < CORNER_CHANCE):
            self.climb_plan = random.choice(kinds["corner"])
        else:
            self.climb_plan = kinds["leap"][0]
        return ledge

    def on_my_floor(self, x):
        """Whether it can walk to `x` without leaving what it stands on."""
        return self.platform_rect is None or self.platform_rect[0] <= x <= self.platform_rect[2]

    def climb_plans(self, ledge):
        """The ways up onto `ledge` from where it stands: ("leap", x), ("corner",
        x, corner) or ("parkour", x, route), each with the spot `x` it starts from."""
        height, left, right, hwnd = ledge
        if hwnd == self.platform or height - self.y < CLIMB_MIN:
            return []
        lo, hi = self.bounds()
        plans = []
        spot = self.takeoff_x(ledge)
        if height - self.y <= CLIMB_HEIGHT and abs(spot - self.x) <= CLIMB_RANGE and self.on_my_floor(spot):
            plans.append(("leap", spot))
        for corner in self.corners(ledge):
            hang_x, hang_y = corner[3], corner[4]
            if (CLIMB_MIN <= hang_y - self.y <= CLIMB_HEIGHT and lo <= hang_x <= hi
                    and abs(hang_x - self.x) <= CLIMB_RANGE and self.on_my_floor(hang_x)):
                plans.append(("corner", hang_x, corner))
            route = self.chimney(ledge, corner)
            if route:
                plans.append(("parkour",) + route)
        return plans

    def corners(self, ledge):
        """The corners of `ledge` it can hang from: [(side, facing, stand_x, hang_x,
        hang_y)]. `side` is the window's side (screen column), `facing` the way it
        faces hanging there (towards the window), `stand_x` where it stands once up
        and (hang_x, hang_y) where its body is while it hangs. Only real corners: not
        where a window in front cuts the top."""
        height, left, right, hwnd = ledge
        rect = platforms.window_rect(hwnd)
        if rect is None:
            return []
        out = []
        for side, facing in ((left, 1), (right, -1)):
            if side != (rect[0] if facing == 1 else rect[2]):
                continue
            stand_x = side + facing * LEDGE_REACH * SCALE
            out.append((side, facing, stand_x, stand_x + facing * self.hang_shift[0],
                        height - self.hang_shift[1]))
        return out

    def chimney(self, ledge, corner):
        """A way up wall to wall to `corner` of `ledge`: (start_x, route) or None.

        It goes up the gap between that side of the window and a wall facing it
        (the screen's edge or another window's side), jumping from one to the
        other and rising the same at each jump; the last one is to the corner
        (to hang from it) or straight onto the top. Every wall it touches must be
        there at that height.
        """
        height, left, right, hwnd = ledge
        side, facing, stand_x, hang_x, hang_y = corner
        bh = self.body_half
        _, top, _, bottom = work_area()
        walls = self.app.all_walls()
        own = [w for w in walls if w[4] == hwnd and w[0] == side and w[3] == -facing]
        if not own:
            return None
        lo, hi = self.bounds()
        hang = random.random() < CORNER_CHANCE
        end = ("hang", stand_x, height, hwnd, facing, hang_x, hang_y) if hang else \
              ("top", side + facing * (bh + 10), height + CLIMB_OVERSHOOT, hwnd)
        end_y = end[6] if hang else end[2]
        for other in walls:
            gap = (side - other[0]) * facing
            if other[3] != facing or not MIN_GAP <= gap <= MAX_GAP:
                continue
            x_other, x_own = other[0] + facing * bh, side - facing * bh   # body center touching each
            start = (x_other + x_own) / 2
            if not (lo <= start <= hi and abs(start - self.x) <= CLIMB_RANGE and self.on_my_floor(start)):
                continue
            jumps = max(2, math.ceil((end_y - self.y) / KICK_RISE))
            if jumps - 1 > MAX_KICKS:
                continue
            rise = (end_y - self.y) / jumps
            route = []
            for i in range(1, jumps):        # the last wall before the corner is the other one
                wall = other if (jumps - 1 - i) % 2 == 0 else own[0]
                y = self.y + rise * i
                middle = y + self.body_height / 2
                if not (wall[1] <= middle <= wall[2]) or y + self.body_height > bottom - top:
                    break
                route.append(("wall", x_other if wall is other else x_own, wall[3], y, wall[4]))
            else:
                return start, route + [end]
        return None

    def takeoff_x(self, ledge):
        """Where it jumps from to land on `ledge`: under it, as close as it can."""
        _, left, right, _ = ledge
        lo, hi = self.bounds()
        return min(max(self.x, left + self.body_half, lo), right - self.body_half, hi)

    def climb(self, dt):
        """Run to where it goes up from, and go up: one jump onto the top, a jump
        to a corner, or wall to wall up a gap (see ledge_to_climb)."""
        same = [l for l in self.ledges if l[3] == self.climb_to[3]]
        if not same:                         # the window is gone (or covered)
            self.set_state("idle")
            return
        kind = self.climb_plan[0]
        if kind == "leap":
            self.climb_to = min(same, key=lambda l: abs(self.takeoff_x(l) - self.x))
            self.target = self.takeoff_x(self.climb_to)
        else:                                # the window may have moved: plan it again
            plans = [(l, p) for l in same for p in self.climb_plans(l) if p[0] == kind]
            if not plans:
                self.set_state("idle")       # out of reach now
                return
            self.climb_to, self.climb_plan = min(plans, key=lambda lp: abs(lp[1][1] - self.x))
            self.target = self.climb_plan[1]
        self.move_towards(self.target, RUN_SPEED, dt)
        if self.x != self.target:
            return
        if kind == "leap":
            rise = self.climb_to[0] - self.y + CLIMB_OVERSHOOT
            if not 0 < rise <= CLIMB_HEIGHT + CLIMB_OVERSHOOT:
                self.set_state("idle")       # the window moved out of reach
                return
            self.vy = (2 * GRAVITY * rise) ** 0.5
            self.y += 0.1                    # off the ground
            self.set_state("leap")
        elif kind == "corner":
            side, facing, stand_x, hang_x, hang_y = self.climb_plan[2]
            self.facing = facing
            self.route = [("hang", stand_x, self.climb_to[0], self.climb_to[3], facing, hang_x, hang_y)]
            self.launch((hang_x, hang_y), (2 * (hang_y - self.y) / GRAVITY) ** 0.5)
        else:
            self.route = list(self.climb_plan[2])
            self.launch(self.step_target(self.route[0]), KICK_TIME)

    # --- Parkour: walls, corners and the jumps between them ---------------------------
    @staticmethod
    def step_target(step):
        """Where a step of a route takes it: (x, height) of its body (see chimney)."""
        if step[0] == "wall":
            return step[1], step[3]
        if step[0] == "hang":
            return step[5], step[6]
        return step[1], step[2]

    def launch(self, target, seconds, vx=0.0, vy=0.0):
        """Jump off: to reach `target` (x, height) in `seconds` (it gets there at
        the top of its jump, or on the way up), or, with no target, with speed (vx, vy)."""
        if target is not None:
            tx, ty = target
            vx = (tx - self.x) / seconds
            vy = (ty - self.y + GRAVITY * seconds * seconds / 2) / seconds
        self.vx, self.vy = vx, vy
        self.flight = {"target": target, "seconds": seconds, "t": 0.0}
        self.platform = self.platform_rect = None
        self.floor = 0.0
        self.y += 0.1                        # off the ground
        self.state = "parkour"
        if self.anim != "wall_jump":
            self.set_anim("jump", restart=True)

    def parkour(self, dt):
        """In the air, parkouring: on its way to the next step of its route, or
        free (after jumping off a wall, or onto a window's top) until it lands."""
        flight = self.flight
        before = self.y
        lo, hi = self.bounds()
        self.x = min(max(self.x + self.vx * dt, lo), hi)
        self.vy -= GRAVITY * dt
        self.y += self.vy * dt
        if flight["target"] is not None:
            flight["t"] += dt
            if flight["t"] >= flight["seconds"]:
                self.x, self.y = flight["target"]
                self.arrive()
                return
            if self.y < 0:                   # can't go through the taskbar
                self.y = 0.0
        elif self.land(before):
            self.vx = 0.0
            self.set_state("idle", idle_seconds=JUMP_PAUSE)
            return
        if self.anim != "wall_jump":
            self.set_anim("jump" if self.vy > 0 else "fall")

    def arrive(self):
        """Got to the next step of its route: a wall to jump off again, a corner to
        hang from, or above a window's top to drop onto it."""
        step = self.route.pop(0)
        if step[0] == "wall":
            _, x, face, y, hwnd = step
            if self.find_wall(hwnd, face) is None:
                self.route = []              # the window has gone: it just falls
                self.launch(None, 0.0)
                return
            self.vx = self.vy = 0.0
            self.cling_to(face, WALL_CLING)
        elif step[0] == "hang":
            _, stand_x, height, hwnd, facing, _, _ = step
            if not any(l[3] == hwnd and abs(l[0] - height) <= 2 for l in self.ledges):
                self.launch(None, 0.0)       # the window has gone (or moved)
                return
            self.hang_from(stand_x, height, hwnd, facing)
        else:
            self.vx = self.vy = 0.0
            self.launch(None, 0.0)           # drops onto the window's top

    def find_wall(self, hwnd, face):
        """The wall of window `hwnd` facing `face` next to its body, or None (it has
        gone); the screen's edges (hwnd None) are always there."""
        middle = self.y + self.body_height / 2
        for wall in self.app.all_walls():
            if wall[4] == hwnd and wall[3] == face and wall[1] <= middle <= wall[2]:
                return wall
        return None

    def cling_to(self, face, seconds):
        """On a wall, back to it (facing away) and crouched for `seconds`, then it
        jumps off it: to the next step of its route, or back into the screen."""
        self.facing = face
        self.cling = seconds
        self.state = "wall_jump"
        self.set_anim("wall_jump", restart=True)

    def wall_jump(self, dt):
        self.cling -= dt
        if self.cling > 0:
            return
        if self.route:
            self.launch(self.step_target(self.route[0]), KICK_TIME)
        else:
            self.launch(None, 0.0, self.facing * WALL_JUMP[0], WALL_JUMP[1])

    def grab_wall(self, x_before, vx):
        """Thrown into a wall: fast, it bounces off it; slower, it grabs it and slides
        down it (True). The screen's edges are walls (bouncing off them is fly_step's);
        so are the windows' sides."""
        middle = self.y + self.body_height / 2
        hits = []
        for wall in self.app.all_walls():
            x, low, high, face, hwnd = wall
            touch = x + face * self.body_half    # its body center, touching the wall
            if vx * face < 0 and (x_before - touch) * (self.x - touch) <= 0 and low <= middle <= high:
                hits.append((abs(x_before - touch), touch, wall))
        if not hits:
            return False
        _, touch, wall = min(hits)
        if abs(vx) >= WALL_BOUNCE_SPEED:
            if wall[4] is not None:          # off a window's side, as off the screen's edges
                self.x, self.vx = touch, -vx * WALL_BOUNCE
            return False
        self.x, self.vx, self.vy = touch, 0.0, 0.0
        self.facing = wall[3]
        self.wall = wall
        self.wall_left = WALL_HOLD
        self.route = []
        self.impact_done = True
        self.state = "wall_slide"
        self.set_anim("wall_slide", restart=True)
        return True

    def wall_slide(self, dt):
        """Sliding down a wall: it lands, falls off where the wall ends, or after a
        moment jumps off it, back into the screen."""
        x, low, high, face, hwnd = self.wall
        wall = self.find_wall(hwnd, face)
        if wall is None or self.y + self.body_height / 2 < low:
            self.vx = self.vy = 0.0
            self.set_state("falling")        # the wall has ended (or gone)
            return
        self.wall = wall
        self.x = wall[0] + face * self.body_half     # its window may have moved
        before = self.y
        self.vy = -WALL_SLIDE_SPEED
        self.y += self.vy * dt
        if self.land(before):
            self.set_state("idle", idle_seconds=JUMP_PAUSE)
            return
        self.wall_left -= dt
        if self.wall_left <= 0:
            self.cling_to(face, WALL_CLING)

    def hang_from(self, stand_x, height, hwnd, facing):
        """Grab a window's corner. It is already where it will stand once up (on the
        window, riding it if it moves); the sprite shows it hanging below that."""
        self.x, self.y = stand_x, height
        self.vx = self.vy = 0.0
        self.floor, self.platform = height, hwnd
        self.platform_rect = platforms.window_rect(hwnd)
        self.facing = facing
        self.hang_left = random.uniform(*HANG_SECONDS)
        self.state = "ledge_hang"
        self.set_anim("ledge_grab", restart=True)

    def ledge_hang(self, dt):
        self.hang_left -= dt
        if self.hang_left <= 0:
            self.state = "ledge_climb"
            self.set_anim("ledge_climb", restart=True)

    def drawn_shift(self):
        """(dx, dy) from where it stands to where it is drawn: only while it hangs
        from a corner or climbs (the sprite shows it below and beside the top)."""
        if self.state not in ("ledge_hang", "ledge_climb") or self.anim not in ("ledge_grab", "ledge_climb"):
            return 0.0, 0.0
        i = min(self.frame_index, len(self.head_offsets[self.anim]) - 1)
        dx = (self.head_offsets[self.anim][i] - self.head_offsets["idle"][0]) * self.facing
        return dx, self.head_heights[self.anim][i] - self.head_heights["idle"][0]

    def let_go(self):
        """Hanging from a corner or climbing, it lets go: from where it is drawn."""
        if self.state not in ("ledge_hang", "ledge_climb"):
            return
        dx, dy = self.drawn_shift()
        self.x += dx
        self.y = max(self.y + dy, 0.0)
        self.platform = self.platform_rect = None
        self.floor = 0.0

    def drop_down(self, dt):
        """Leaping up onto a window, or falling off one: on landing, a short rest."""
        lo, hi = self.bounds()
        self.x = min(max(self.x + self.vx * dt, lo), hi)
        self.fall(dt, 1.0)
        if self.state in ("leap", "falling"):
            self.set_anim("jump" if self.vy > 0 else "fall")

    # --- Interactions with the dummy ------------------------------------------------
    def body_box(self):
        """(left, right, bottom, top) of its body: x on the screen, heights above the taskbar."""
        dx, dy = self.drawn_shift()          # hanging from a corner it is drawn lower
        x, y = self.x + dx, self.y + dy
        return x - self.body_half, x + self.body_half, y, y + self.body_height

    def touches_dummy(self):
        if self.dummy is None or not self.dummy.can_be_hit():
            return False
        l, r, b, t = self.body_box()
        d0, d1 = self.dummy.body_span()
        low, high = self.dummy.body_heights()
        return r >= d0 and l <= d1 and t >= low and b <= high

    @staticmethod
    def impact_speed(vx, vy, mover_bottom, other_top, dt):
        """How hard a moving body hits another: from the side only its sideways speed
        counts; falling onto it from above, its whole speed does."""
        was_bottom = mover_bottom - vy * dt          # where its bottom was a moment ago
        if was_bottom >= other_top - 5:
            return (vx * vx + vy * vy) ** 0.5
        return abs(vx)

    def check_impacts(self, dt):
        """A thrown body crashing into the other one hurts it (once per throw)."""
        if not self.touches_dummy():
            return
        d = self.dummy
        d_low, d_top = d.body_heights()
        if (self.state == "dropped" and not self.impact_done
                and self.impact_speed(self.vx, self.vy, self.y, d_top, dt) >= IMPACT_SPEED):
            self.impact_done = True
            d.take_hit(self.point_on_dummy(self.body_height / 2))
            self.vx = -self.vx * IMPACT_BOUNCE       # bounce off it
        if (d.state == "flying" and not d.impact_done and self.alive and self.state != "held"
                and self.impact_speed(d.vx, d.vy, d_low, self.y + self.body_height,
                                      max(dt, 0.016)) >= IMPACT_SPEED):
            d.impact_done = True
            push = self.knockback_speed(d)
            d.vx = -d.vx * IMPACT_BOUNCE
            self.hit()                       # the dummy landed on Capu...
            self.knock(push, KNOCKBACK_LIFT)  # ...and pushes him away

    def knock(self, vx, lift):
        """Pushed by a hit: it flies off sideways with a little hop (see knocked),
        facing whatever hit it."""
        self.vx, self.vy = vx, lift
        self.y = max(self.y, self.floor + 0.1)   # off the ground
        if abs(vx) >= 1:
            self.facing = -1 if vx > 0 else 1

    def dummy_hits_back(self):
        """The dummy swings back after one of Capu's hits: if he is still right
        next to it, it hits him and knocks him away."""
        d = self.dummy
        if (d is None or not d.standing() or not self.alive or self.away
                or self.state in ("held", "dropped", "evade")):
            return
        l, r, b, _ = self.body_box()
        d0, d1 = d.body_span()
        _, d_top = d.body_heights()
        if max(d0 - r, l - d1) > COUNTER_REACH or b > d_top:
            return                           # he has moved away (or is above it)
        d.swing_back()
        self.hit()
        self.knock(COUNTER_PUSH if self.x >= d.center_x() else -COUNTER_PUSH, COUNTER_LIFT)
        self.question.show(self.head_top)    # "?": he didn't see that coming

    def head_top(self):
        """Screen (x, y) of the top of its head in the frame on show, where things pop over it."""
        _, _, _, bottom = work_area()
        i = min(self.frame_index, len(self.head_offsets[self.anim]) - 1)
        offset = self.head_offsets[self.anim][i]
        return self.x + self.facing * offset, bottom - self.y - self.head_heights[self.anim][i]

    def knockback_speed(self, d):
        """Sideways speed the dummy's hit gives Capu: in the direction the dummy
        was flying, or away from it if it fell on him from above."""
        speed = min(d.speed() * KNOCKBACK_FACTOR, KNOCKBACK_MAX)
        if abs(d.vx) >= 50:
            direction = 1 if d.vx > 0 else -1
        else:
            direction = 1 if self.x >= d.center_x() else -1
        return direction * speed

    def knocked(self, dt):
        """Hurt or dead: carried by a push (air drag, gravity, bounces off the
        screen edges) until it lands and stops; without a push it just falls."""
        if self.vx == 0 and self.grounded():
            return
        lo, hi = self.bounds()
        _, top, _, bottom = work_area()
        height = self.y
        self.x, self.vx, self.y, self.vy = fly_step(self.x, self.vx, self.y, self.vy, dt,
                                                    lo, hi, bottom - top - self.ground)
        if self.land(height):
            self.vx = 0.0                    # lands and stops

    def dummy_threat(self, move="stay", delay=0.0):
        """Whether the thrown dummy would hit it hard if it did `move` after `delay` seconds.

        Follows the dummy's flight ahead of time with the same physics as the
        real throw, together with its own motion: it stands still for `delay`
        seconds and then does `move`, "stay", "jump" or "dash" (see evade).
        Returns (seconds until the hit, "side" or "above"), or None if the
        dummy misses, falls short, lands on a window first or is too slow to hurt.
        """
        d = self.dummy
        lo, hi, ceiling = d.bounds()
        ledges = d.ledges
        middle = (d.body[0] + d.body[2]) / 2     # its body's middle, from its window's left edge
        x, vx, y, vy = d.x, d.vx, d.y, d.vy
        px, py, pvy = self.x, 0.0, 0.0
        target = self.dash_target() if move == "dash" else px
        started = False
        step = 1 / 60
        for i in range(1, round(EVADE_LOOKAHEAD / step) + 1):
            was_over = px + self.body_half >= x + d.body[0] and px - self.body_half <= x + d.body[2]
            feet = y + d.feet_offset()
            x, vx, y, vy = fly_step(x, vx, y, vy, step, lo, hi, ceiling, training_dummy.WEIGHT)
            if vy <= 0:
                spot = platforms.landing(ledges, x + middle, feet, y + d.feet_offset())
                if spot is not None and spot[1] is not None:
                    return None                  # a window catches it on the way
            if i * step <= delay:
                pass                             # still waiting
            elif move == "jump":
                if not started:
                    started, pvy = True, (2 * GRAVITY * EVADE_JUMP_HEIGHT) ** 0.5
                pvy -= GRAVITY * step
                py = max(py + pvy * step, 0.0)
            elif move == "dash":
                px += max(-DASH_SPEED * step, min(DASH_SPEED * step, target - px))
            low, high = y + d.height - d.body[3], y + d.height - d.body[1]
            top = py + self.body_height
            if (px + self.body_half >= x + d.body[0] and px - self.body_half <= x + d.body[2]
                    and high >= py and low <= top):
                if self.impact_speed(vx, vy, low, top, step) < IMPACT_SPEED:
                    return None                  # a gentle bump: nothing to fear
                return i * step, "above" if was_over else "side"
            if y == 0:
                return None                      # it lands without reaching it
        return None

    def dash_target(self):
        """Where to dash to get out of the dummy's way: away from it, or the other
        way if there is no room."""
        lo, hi = self.bounds()
        away = 1 if self.x >= self.dummy.center_x() else -1
        target = min(max(self.x + away * EVADE_DASH_DISTANCE, lo), hi)
        if abs(target - self.x) < EVADE_DASH_DISTANCE / 2:
            target = min(max(self.x - away * EVADE_DASH_DISTANCE, lo), hi)
        return target

    def check_incoming_dummy(self):
        """When the thrown dummy is going to hit it, maybe dodge, at the last moment.

        On each throw it decides once whether it will dodge (EVADE_CHANCE). If it
        will, it waits: it only moves when waiting a bit longer (EVADE_MARGIN)
        would no longer get it clear. It jumps or dashes, whichever still works;
        if neither does, it takes the hit.
        """
        d = self.dummy
        if d is None or d.state != "flying" or d.impact_done or not d.can_be_hit():
            return
        threat = self.dummy_threat()
        if threat is None:
            return
        if self.evade_roll != d.throws:          # a new throw: dodge this one or not?
            self.evade_roll = d.throws
            self.evade_planned = random.random() < EVADE_CHANCE
        if not self.evade_planned:
            return
        moves = ("dash", "jump") if threat[1] == "above" else ("jump", "dash")
        for move in moves:
            if self.dummy_threat(move) is None:  # this still gets it clear...
                if self.dummy_threat(move, delay=EVADE_MARGIN) is not None:
                    self.evade(move)             # ...but not if it waited: now
                return                           # otherwise keep waiting

    def evade(self, move):
        """Jump over the dummy, or dash out of its way."""
        self.set_state("evade")
        self.face_dummy()
        self.evade_jump = move == "jump"
        if self.evade_jump:
            self.vy = (2 * GRAVITY * EVADE_JUMP_HEIGHT) ** 0.5
            self.y = 0.1                         # off the ground
            self.set_anim("jump", restart=True)
        else:
            self.target = self.dash_target()
            self.set_anim("dash", restart=True)

    def evade_step(self, dt):
        if self.evade_jump:
            self.fall(dt, 1.0)                   # lands into a short rest
            if self.state == "evade":
                self.set_anim("jump" if self.vy > 0 else "fall")
        else:
            self.move_towards(self.target, DASH_SPEED, dt)
            if self.x == self.target:
                self.set_state("idle", idle_seconds=JUMP_PAUSE)

    def dodge(self, dx):
        """Dash back so the cursor ends up at the lantern's distance."""
        lo, hi = self.bounds()
        mx = self.x + dx
        away = -1 if dx > 0 else 1 if dx < 0 else random.choice((1, -1))
        gap = ATTACK_REACH * 0.8
        for side in (away, -away):           # no room on one side: use the other
            target = mx + side * gap
            if lo <= target <= hi:
                break
        else:
            target = min(max(mx + away * gap, lo), hi)
        if abs(target - self.x) < 1:         # no room to back off: attack anyway
            self.set_state("attack")
            return
        self.set_state("dodge")
        self.target = target
        self.facing = 1 if target > self.x else -1

    def animate(self, dt):
        """Advance the current animation. Returns True when a non-looping one has finished."""
        frames = self.frames[self.anim][self.facing]
        loops = ANIMATIONS[self.anim][2]
        ms = self.frame_ms
        finished = False
        self.frame_elapsed += dt
        while self.frame_elapsed >= ms / 1000:
            self.frame_elapsed -= ms / 1000
            if self.frame_index + 1 < len(frames):
                self.frame_index += 1
            elif loops:
                self.frame_index = 0
            else:
                finished = True
                break
        self.frame_index = min(self.frame_index, len(frames) - 1)
        frame = frames[self.frame_index]
        if frame is not self.shown:
            self.label.config(image=frame)
            self.shown = frame
        return finished

    # --- Window ----------------------------------------------------------------
    def place(self):
        _, _, _, bottom = work_area()
        x = round(self.x - self.width / 2)
        # Feet rest right on the taskbar (or above it while jumping); anything
        # below them is transparent.
        y = bottom - self.ground - round(self.y)
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.place_hitbox(x, y)
        self.place_light(x, y)

    def light_strength(self):
        """How strong its lantern shines now: by what it is doing, wavering like a flame."""
        now = time.perf_counter()
        if now >= self.next_flicker:
            self.flicker_to = self.flicker_rng.uniform(1 - LIGHT_FLICKER, 1 + LIGHT_FLICKER / 3)
            self.next_flicker = now + LIGHT_FLICKER_MS / 1000
        self.flicker += (self.flicker_to - self.flicker) * 0.35
        return min(1.0, LIGHT_STATES.get(self.state, LIGHT_STRENGTH) * self.flicker)

    def place_light(self, x, y):
        """Put its lantern's light where the lantern is in the frame on show (its
        window is at x, y), in front of it, or hide it: off in the settings, or no
        lantern shows."""
        if self.glow is None:
            return
        spot = None
        if self.app.settings["light"] and not self.hidden and not self.gone and not self.away:
            frames = self.lanterns[self.anim]
            at = frames[min(self.frame_index, len(frames) - 1)]
            if at is not None:
                ox, oy = at
                spot = (x + (ox if self.facing == 1 else self.width - ox), y + oy, self.light_strength())
        self.light_spot = spot
        if spot is None:
            self.glow.hide()
            return
        self.glow.show(*spot)
        now = time.perf_counter()
        if now >= self.next_raise:           # its window may have come to the front: back behind the light
            self.glow.raise_()
            self.next_raise = now + LIGHT_RAISE_SECONDS

    def place_hitbox(self, x, y):
        """Keep the hit zone under its body, facing its way; only while it is alive
        on the screen (its dead body can't be hit)."""
        self.show_hitbox(self.alive and not self.hidden and not self.gone and not self.away)
        if not self.hitbox_shown:
            return
        shape, (ox, oy) = self.hit_shape_now()
        kind = self.anim if self.anim in self.hit_shapes else None
        if (kind, self.facing) != (self.hitbox_kind, self.hitbox_facing):
            ui.shape_window(ui.top_hwnd(self.hitbox), shape)
            self.hitbox_kind, self.hitbox_facing = kind, self.facing
        self.hitbox.geometry(f"{shape.width}x{shape.height}+{x + ox}+{y + oy}")

    def hit_shape_now(self):
        """(shape, offset in its window) of its hit zone now: its idle pose, or its
        own one while it hangs from a corner or climbs (it is drawn elsewhere)."""
        return self.hit_shapes[self.anim if self.anim in self.hit_shapes else None][self.facing]

    def show_hitbox(self, show):
        if show == self.hitbox_shown:
            return
        self.hitbox_shown = show
        if show:
            self.hitbox.deiconify()
            ui.stack_below(self.hitbox, self.label)
        else:
            self.hitbox.withdraw()

    def set_cursor(self, name):
        """The cursor over it: "sword", "fist", or None for the normal arrow."""
        for widget in (self.label, self.hitbox):
            widget.config(cursor=ui.cursor(name) if name else "")

    def keep_on_top(self):
        self.root.attributes("-topmost", True)
        if self.glow is not None:
            self.glow.raise_()                    # its light stays in front of it
        if self.hitbox_shown:
            self.hitbox.attributes("-topmost", True)
            ui.stack_below(self.hitbox, self.label)
        self.root.after(5_000, self.keep_on_top)


if __name__ == "__main__":
    # Single instance: if Capu is already running, don't open another one.
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Capu_SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        raise SystemExit
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # physical coordinates on scaled displays
    except Exception:
        pass
    missing = missing_sprites()
    if missing:
        tk.Tk().withdraw()
        messagebox.showerror(
            "Capu",
            "Sprites not found in assets/capu/sprites:\n\n" + "\n".join(missing)
            + "\n\nSee README.md.")
        raise SystemExit(1)
    App().run()
