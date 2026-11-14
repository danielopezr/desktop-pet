"""Parton: a desktop pet for Windows ("Little Axion" character by Jesshiyoo),
together with a training dummy (dummy.py), both in this one program.

- Lives at the bottom of the screen, standing on the taskbar.
- Idles for a while and then runs to a random spot.
- If it sees the cursor nearby (left or right, not too high), it runs to it
  and swings its axe with attack 1 or attack 2, at random. If the cursor is
  above the axe's vertical reach, it tries to jump at it.
- If the cursor is right on top of it, it dashes back to get the axe's
  distance and then attacks.
- If the cursor is within reach sideways but too high for the axe, it jumps
  to try to reach it, and swings in the air if it gets close enough.
- Left click and hold to pick it up; release it anywhere and it falls back
  down to the taskbar. Let go while moving the cursor and it is thrown in
  that direction, as fast as the cursor was moving.
- A quick left click hits it; on the sixth hit it dies and disappears.
- Now and then, when the dummy is close enough, Parton goes to it and hits it
  a few times.
- When the dummy is thrown at it, it usually dodges: it jumps over a dummy
  coming from the side and dashes away from one falling on it.
- Right click on either of them: menu to revive, hide or show each one, change
  the settings (calm mode, do not disturb, training) or exit. If neither is
  left on the screen, the program closes.
- Calm mode: it ignores the cursor (no chasing or attacking).
- Do not disturb: both hide while a full-screen app (a game, a video, a
  presentation) is in front, and come back when it closes.

Every animation in the pack is listed in ANIMATIONS; the ones not used yet
are ready for later. The sprites are not included in the repository (see
README.md): put the pack's PNG files in assets/parton/sprites.
"""
import ctypes
import json
import os
import random
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox

from PIL import Image, ImageTk

import dummy as training_dummy
import ui
from physics import (FALL_DAMAGE_SPEED, GRAVITY, IMPACT_BOUNCE, IMPACT_SPEED, CursorTrail,
                     fly_step, is_drag, throw_velocity)

# --- Settings ------------------------------------------------------------------
SCALE = 4                     # the character is ~27x22 px in the original sprite
FRAME = 144                   # each frame in the pack is 144x144
RUN_SPEED = 160               # pixels per second while wandering
CHASE_SPEED = 260             # pixels per second while chasing the cursor
IDLE_SECONDS = (2.0, 7.0)     # how long it stays idle (min, max)
MIN_RUN_DISTANCE = 150        # minimum length of each wander run, in pixels
TICK_MS = 16                  # update rate (~60 fps)
KEY_COLOR = "#ff00fe"         # color that becomes transparent

# Vision and attack (screen pixels, measured from the character's body)
VISION_RANGE = 450            # horizontal distance at which it sees the cursor
VISION_HEIGHT = 250           # how far above the taskbar it can see the cursor
LOSE_RANGE = 600              # beyond this distance it stops chasing
ATTACK_REACH = 35 * SCALE     # axe reach (the slash reaches 26-43 px ahead)
ATTACK_HEIGHT = 19 * SCALE    # top of the slash above its feet (sprite: 1-19 px)
SLASH_CENTER = 10 * SCALE     # middle of the slash above its feet: where it aims
SLASH_REACH = 43 * SCALE      # how far ahead of its body center the slash gets
ATTACK_PAUSE = 0.35           # pause between swings, in seconds
TOO_CLOSE = 20 * SCALE        # cursor on top of it: the axe would miss
DASH_SPEED = 550              # pixels per second when dashing back
JUMP_MAX_HEIGHT = 160         # highest jump, in pixels (it jumps just enough to aim)
JUMP_MIN_HEIGHT = 40          # lowest jump, in pixels
JUMP_DRIFT = 140              # sideways speed while in the air, towards the cursor
JUMP_PAUSE = 0.6              # pause after landing before jumping again, in seconds
AIR_ATTACK_FRAME_MS = 45      # the air swing plays faster than the ground one
AIR_SLASH_LAST_FRAME = 8      # it hangs in the air until this frame of the swing

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
CELEBRATE_HOPS = 3            # little hops when it breaks the dummy
CELEBRATE_HOP_HEIGHT = 75     # height of those hops, in pixels

# Training on the dummy
TRAIN_CHANCE = 0.4            # chance of training instead of wandering, after idling
TRAIN_RANGE = 600             # only if the dummy is at most this far, in pixels
TRAIN_SWINGS = (1, 3)         # how many swings per training session (min, max)
TRAIN_PAUSE = 0.5             # pause between swings, in seconds
TRAIN_GAP = ATTACK_REACH * 0.8  # distance from the dummy it swings from
SLASH_FRAMES = {"attack1": (3,), "attack2": (3, 9)}  # frames where the slash lands

# Dodging the dummy when it is thrown at Parton
EVADE_CHANCE = 0.75           # chance of dodging each throw of the dummy at it
EVADE_MARGIN = 0.06           # it dodges at the last moment: when waiting this much longer would be too late
EVADE_LOOKAHEAD = 1.2         # how far ahead it follows the dummy's flight, in seconds
EVADE_JUMP_HEIGHT = 260       # how high it jumps over the dummy, in pixels
EVADE_DASH_DISTANCE = 260     # how far it dashes out of the way, in pixels
KNOCKBACK_FACTOR = 0.6        # share of the dummy's speed that pushes Parton when it hits him
KNOCKBACK_MAX = 900           # cap on that push, in pixels per second
KNOCKBACK_LIFT = 450          # the push also pops him up a little (upward speed)
EVADE_STATES = ("idle", "run", "train", "chase", "flee", "attack", "dodge")  # it can dodge from these

# Menu settings, saved between runs
SETTINGS_FILE = Path(os.environ.get("APPDATA", Path.home())) / "Parton" / "settings.json"
DEFAULT_SETTINGS = {
    "calm": False,            # ignore the cursor: no chasing or attacking it
    "do_not_disturb": True,   # hide while a full-screen app is in front
    "training": True,         # go and hit the dummy now and then
}
SETTING_LABELS = {"calm": "Calm mode", "do_not_disturb": "Do not disturb", "training": "Training"}
FULLSCREEN_CHECK_MS = 1000    # how often "do not disturb" looks for a full-screen app

SPRITES = Path(__file__).parent / "assets" / "parton" / "sprites"

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
}
USED = tuple(ANIMATIONS)


def work_area():
    """Windows work area (screen minus the taskbar), in physical pixels."""
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def mouse_pos():
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


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
    on_main_screen = info.dwFlags & 1                 # MONITORINFOF_PRIMARY: where they live
    return bool(on_main_screen and rect.left <= m.left and rect.top <= m.top
                and rect.right >= m.right and rect.bottom >= m.bottom)


def missing_sprites():
    return [file for file, _, _ in ANIMATIONS.values() if not (SPRITES / file).exists()]


def solid_mask(frame):
    return frame.getchannel("A").point(lambda a: 255 if a >= 128 else 0)


def raw_frames(file):
    sheet = Image.open(SPRITES / file).convert("RGBA")
    return [sheet.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME))
            for i in range(sheet.width // FRAME)]


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
    all_frames = [f for file, _, _ in ANIMATIONS.values() for f in raw_frames(file)]
    x0, y0, x1, y1 = union_bbox(all_frames)
    bx0, _, bx1, _ = union_bbox(raw_frames(ANIMATIONS["idle"][0]))
    center = (bx0 + bx1) / 2
    half = max(center - x0, x1 - center)
    body_half = (bx1 - bx0) / 2
    bottoms = [solid_mask(f).getbbox()[3] for name in ("idle", "run")
               for f in raw_frames(ANIMATIONS[name][0])]
    ground = max(set(bottoms), key=bottoms.count)
    return (round(center - half), y0, round(center + half), y1), body_half, ground


def to_photo(frame):
    frame = frame.resize((frame.width * SCALE, frame.height * SCALE), Image.NEAREST)
    # tkinter only supports full transparency: the background is painted with the key color.
    bg = Image.new("RGBA", frame.size, KEY_COLOR)
    bg.paste(frame, mask=solid_mask(frame))
    return ImageTk.PhotoImage(bg.convert("RGB"))


class App:
    """Owns both characters and the right-click menu they share."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()                      # only the characters' windows show
        self.menu = None                          # the styled menu, while it is open
        self.settings = load_settings()
        self.away = False                         # hidden by "do not disturb"
        self.dummy = training_dummy.TrainingDummy(self.root, self) if training_dummy.available() else None
        self.parton = Parton(self.root, self)
        self.watch_fullscreen()

    def characters(self):
        return [(name, c) for name, c in (("Parton", self.parton), ("dummy", self.dummy)) if c]

    def menu_items(self):
        """(label, action) for each character: revive the dead, hide or show the living."""
        items = []
        for name, c in self.characters():
            if not c.alive:
                items.append((f"Revive {name}", c.revive))
            elif c.hidden:
                items.append((f"Show {name}", c.unhide))
            else:
                items.append((f"Hide {name}", c.hide))
        return items

    def setting_items(self):
        """(label, action) that switches each setting on or off."""
        return [(f"{label}: {'on' if self.settings[key] else 'off'}",
                 lambda k=key: self.toggle(k))
                for key, label in SETTING_LABELS.items()]

    def toggle(self, key):
        self.settings[key] = not self.settings[key]
        save_settings(self.settings)

    def watch_fullscreen(self):
        """Do not disturb: hide both while a full-screen app is in front."""
        away = self.settings["do_not_disturb"] and fullscreen_app_open()
        if away != self.away:
            self.away = away
            if away and self.menu:
                self.menu.close()
            for _, c in self.characters():
                c.set_away(away)
        self.root.after(FULLSCREEN_CHECK_MS, self.watch_fullscreen)

    def show_menu(self, event):
        """Menu built on the spot, so it always matches what is on the screen.

        Pixel-art if the font is in assets/ui; otherwise the plain Windows menu.
        """
        if self.menu:
            self.menu.close()
        if ui.available():
            items = (self.menu_items() + [None] + self.setting_items()
                     + [None, ("Exit", self.root.destroy)])
            self.menu = ui.PopupMenu(self.root, items, event.x_root, event.y_root, self.do)
            return
        menu = tk.Menu(self.root, tearoff=0)
        for section in (self.menu_items(), self.setting_items()):
            for label, action in section:
                menu.add_command(label=label, command=lambda a=action: self.do(a))
            menu.add_separator()
        menu.add_command(label="Exit", command=self.root.destroy)
        menu.tk_popup(event.x_root, event.y_root)

    def do(self, action):
        action()
        self.check_empty()

    def check_empty(self):
        """With nobody left on the screen there is nothing to right-click: close.

        Unless the dummy is about to come back on its own.
        """
        if not any(c.on_screen() or c.respawning() for _, c in self.characters()):
            self.root.destroy()

    def run(self):
        self.root.mainloop()


class Parton:
    def __init__(self, master, app):
        self.app = app
        self.root = tk.Toplevel(master)
        self.root.title("Parton")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", KEY_COLOR)
        self.root.config(bg=KEY_COLOR)

        box, body_half, ground = crop_box()
        self.width = (box[2] - box[0]) * SCALE
        self.height = (box[3] - box[1]) * SCALE
        self.ground = (ground - box[1]) * SCALE   # height of the feet inside the window
        self.body_half = body_half * SCALE
        idle_top = union_bbox(raw_frames(ANIMATIONS["idle"][0]))[1]
        self.body_height = (ground - idle_top) * SCALE   # from its feet to the top of its head
        # Where its head is, from its body center, facing right (the hearts go over it).
        idle = raw_frames(ANIMATIONS["idle"][0])[0].crop(box)
        self.head_offset = (ui.head_center(solid_mask(idle)) - idle.width / 2) * SCALE
        self.impact_done = True                   # only a fresh throw can hit the dummy
        self.celebrate_pending = False

        # Frames facing right (original) and left (flipped).
        self.frames = {}
        for name in USED:
            raw = [f.crop(box) for f in raw_frames(ANIMATIONS[name][0])]
            self.frames[name] = {
                1: [to_photo(f) for f in raw],
                -1: [to_photo(f.transpose(Image.FLIP_LEFT_RIGHT)) for f in raw],
            }

        self.label = tk.Label(self.root, bg=KEY_COLOR, bd=0)
        self.label.pack()
        self.label.bind("<Button-3>", app.show_menu)
        self.label.bind("<ButtonPress-1>", self.press)
        self.label.bind("<ButtonRelease-1>", self.release)
        self.pressed = None                       # (time, x, y) of a left click in progress
        self.dummy = app.dummy                    # None if the dummy's sprites are missing
        self.away = False                         # hidden by "do not disturb"
        self.evade_roll = 0                       # the last dummy throw it decided to dodge or not
        self.evade_planned = False                # ...and whether it will dodge that one
        self.hearts = ui.Hearts(master)         # shown while the cursor is over it
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
        self.y = 0.0                              # height above the taskbar (jumps)
        self.vx = self.vy = 0.0                   # speed, positive is right / up
        self.facing = random.choice((1, -1))
        self.hits = 0
        self.alive = True
        self.gone = False                         # dead and already gone from the screen
        self.hidden = False                       # hidden from the menu
        self.closing = False
        self.last_hurt = self.last_heal = 0.0     # when it was last hit / last healed
        self.training = False                     # in the middle of a session on the dummy
        self.attack_target = "cursor"
        self.set_state("idle")

    # --- Menu actions ------------------------------------------------------------
    def on_screen(self):
        return not self.gone and not self.hidden

    def respawning(self):
        return False                              # Parton only comes back from the menu

    def hide(self):
        self.hidden = True
        self.pressed = None
        self.root.withdraw()

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
            self.pressed = None
            self.root.withdraw()
            self.hearts.hide()
        elif not self.hidden and not self.gone:
            self.root.deiconify()

    def vanish(self):
        """After dying and lying there a moment, it disappears until revived."""
        if self.alive:                            # revived in the meantime
            return
        self.gone = True
        self.root.withdraw()
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
        mx, my = mouse_pos()
        _, _, _, bottom = work_area()
        dx, height = mx - self.x, bottom - my
        if abs(dx) <= max_range and -5 <= height <= VISION_HEIGHT:
            return dx, height
        return None

    def dummy_in_range(self):
        """True if training is on and the dummy is standing close enough to go and hit it."""
        return (self.app.settings["training"] and self.dummy_standing()
                and abs(self.dummy.center_x() - self.x) <= TRAIN_RANGE)

    def dummy_standing(self):
        return self.dummy is not None and self.dummy.standing()

    def slash_hits_dummy(self):
        """True if a slash right now reaches the dummy, whatever it was aimed at."""
        if self.dummy is None or not self.dummy.can_be_hit():
            return False
        d0, d1 = self.dummy.body_span()
        a, b = sorted((self.x, self.x + self.facing * SLASH_REACH))
        if b < d0 or a > d1:                 # not in front of it, or too far
            return False
        low, high = self.dummy.body_heights()  # the dummy may be held or flying
        return self.y <= high and self.y + ATTACK_HEIGHT >= low

    def face_dummy(self):
        self.facing = 1 if self.dummy.center_x() > self.x else -1

    # --- States ----------------------------------------------------------------
    def set_state(self, state, idle_seconds=None, target="cursor"):
        self.state = state
        if state in ("chase", "flee", "run", "jump", "dodge", "evade"):
            self.training = False            # the cursor or a wander interrupts training
        if state in ("idle", "run"):
            self.set_anim(state, restart=True)
        # A short pause (after a swing or a jump): it keeps still and doesn't react.
        self.pausing = state == "idle" and idle_seconds is not None
        if state == "idle":
            self.idle_left = idle_seconds if idle_seconds is not None else random.uniform(*IDLE_SECONDS)
        elif state == "run":
            lo, hi = self.bounds()
            options = [x for x in (random.uniform(lo, hi) for _ in range(20))
                       if abs(x - self.x) >= MIN_RUN_DISTANCE]
            self.target = options[0] if options else (lo if self.x > (lo + hi) / 2 else hi)
            self.facing = 1 if self.target > self.x else -1
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
            # Jump just high enough for the middle of the slash to reach the cursor.
            seen = self.sees_mouse(LOSE_RANGE)
            wanted = seen[1] - SLASH_CENTER if seen else JUMP_MAX_HEIGHT
            rise = min(max(wanted, JUMP_MIN_HEIGHT), JUMP_MAX_HEIGHT)
            self.vy = (2 * GRAVITY * rise) ** 0.5
            self.air_swung = False           # one air swing per jump
            self.set_anim("jump", restart=True)
        elif state == "celebrate":
            self.hops_left = CELEBRATE_HOPS
            self.vy = 0.0
        elif state == "air_attack":
            self.air_swung = True
            self.vy = 0.0                    # hang at the top while swinging
            self.set_anim("attack1", restart=True, frame_ms=AIR_ATTACK_FRAME_MS)

    def train_target(self):
        """Spot at the axe's distance from the dummy, on the side Parton is on
        (or the other one if there is no room there)."""
        lo, hi = self.bounds()
        cx = self.dummy.center_x()
        side = 1 if self.x >= cx else -1
        for s in (side, -side):
            target = cx + s * TRAIN_GAP
            if lo <= target <= hi:
                return target
        return min(max(cx + side * TRAIN_GAP, lo), hi)

    def set_anim(self, name, restart=False, frame_ms=None):
        """Switch animation; start from the first frame if it changes or if asked to."""
        if restart or self.anim != name:
            self.anim = name
            self.frame_ms = frame_ms or ANIMATIONS[name][1]
            self.frame_index = 0
            self.frame_elapsed = 0.0

    def tick(self):
        now = time.perf_counter()
        dt, self.last = min(now - self.last, 0.1), now
        if self.hidden or self.gone or self.away:   # off the screen: nothing to do
            self.hearts.hide()
            self.root.after(TICK_MS, self.tick)
            return
        self.heal(now)
        if self.state in EVADE_STATES and self.y == 0:
            self.check_incoming_dummy()

        if self.state in ("run", "train") or (self.state == "idle" and not self.pausing):
            # While calm, keep watch: if it sees the cursor, go after it (or flee).
            if self.sees_mouse(VISION_RANGE) is not None:
                self.set_state(self.reaction())

        if self.state == "idle":
            self.idle_left -= dt
            if self.idle_left <= 0:
                # After a short pause, go back to the cursor if it is still in
                # sight, carry on training, or stay idle for a normal while.
                # After a normal idle: sometimes train on the dummy, else wander.
                if not self.pausing:
                    if self.dummy_in_range() and random.random() < TRAIN_CHANCE:
                        self.set_state("train")
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
            self.move_towards(self.target, RUN_SPEED, dt)
            if self.x == self.target:
                self.set_state("idle")
        elif self.state == "chase":
            self.chase(dt)
        elif self.state == "dodge":
            self.move_towards(self.target, DASH_SPEED, dt)
            if self.x == self.target:        # has room now: turn around and re-evaluate
                self.set_state("chase")
        elif self.state == "flee":
            self.flee(dt)
        elif self.state == "celebrate":
            self.celebrate(dt)
        elif self.state == "evade":
            self.evade_step(dt)
        elif self.state == "jump":
            self.jump(dt)
        elif self.state == "air_attack":
            # Hang still until the slash is over, then start falling.
            self.fall(dt, 0.0 if self.frame_index <= AIR_SLASH_LAST_FRAME else 1.0)
        elif self.state == "held":
            self.follow_cursor()
        elif self.state == "dropped":
            self.fly(dt)
        elif self.state in ("hurt", "dead"):
            self.knocked(dt)                 # pushed by a hit, or falling if hit in the air

        if self.pressed and self.state != "held":
            self.check_drag_start()

        before = (self.anim, self.frame_index)
        finished = self.animate(dt)
        if (self.state in ("attack", "air_attack")
                and self.anim == before[0] and self.frame_index != before[1]
                and self.frame_index in SLASH_FRAMES.get(self.anim, ())
                and self.slash_hits_dummy()):
            if self.dummy.take_hit():        # any slash that reaches the dummy hurts it
                self.celebrate_pending = True    # ...and if that broke it: celebrate

        self.check_impacts(dt)

        if finished:
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
                if self.y > 0:
                    # Air swing finished: keep falling.
                    self.state = "jump"
                    self.set_anim("fall")
                else:
                    # Swing finished: short pause and keep watching.
                    self.set_state("idle", idle_seconds=ATTACK_PAUSE)
            elif self.state == "hurt":
                if self.y > 0:
                    self.state, self.vy = "dropped", min(self.vy, 0.0)   # keeps any push
                    self.set_anim("fall")
                elif self.sees_mouse(VISION_RANGE) is not None:
                    self.set_state(self.reaction())  # strike back (or flee) right away
                else:
                    self.set_state("idle", idle_seconds=ATTACK_PAUSE)
            elif self.state == "dead" and not self.closing:
                self.closing = True
                self.root.after(int(DEATH_LINGER * 1000), self.vanish)

        self.place()
        self.update_hearts()
        self.root.after(TICK_MS, self.tick)

    def update_hearts(self):
        """Show its health above its head while the cursor is over its body."""
        l, r, b, t = self.body_box()
        _, _, _, bottom = work_area()
        mx, my = mouse_pos()
        head_y = bottom - t
        if self.alive and self.state != "held" and l <= mx <= r and head_y <= my <= bottom - b:
            head_x = self.x + self.facing * self.head_offset
            self.hearts.show(head_x, head_y, HITS_TO_DIE - self.hits, HITS_TO_DIE)
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

    def flee(self, dt):
        """Run away from the cursor (dash if it is very close) until it is out of sight,
        hopping now and then so it is harder to hit."""
        airborne = self.y > 0
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
        if self.y > 0:
            self.set_anim("jump" if self.vy > 0 else "fall")
        elif self.x == before:               # cornered: nowhere to go, it just faces it
            self.facing = 1 if dx >= 0 else -1
            self.set_anim("idle")
        else:
            self.set_anim("dash" if close else "run")
        # Dodging hops: more often the closer the cursor is.
        far_rate, close_rate = FLEE_JUMPS_PER_SECOND
        rate = close_rate if close else far_rate
        if self.y == 0 and random.random() < rate * dt:
            self.vy = (2 * GRAVITY * FLEE_JUMP_HEIGHT) ** 0.5
            self.y = 0.1                     # off the ground

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
                self.set_state("jump")       # too high for the axe: jump at it
            elif abs(dx) < TOO_CLOSE:
                self.dodge(dx)               # cursor on top of it: back off to hit it
            else:
                self.set_state("attack")
            return
        # Run closer until the cursor is within the axe's reach.
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
            # Drift so the cursor ends up at the axe's distance, not right overhead.
            lo, hi = self.bounds()
            target = min(max(self.x + dx - self.facing * ATTACK_REACH * 0.8, lo), hi)
            self.move_towards(target, JUMP_DRIFT, dt)
            self.facing = 1 if dx >= 0 else -1
            # At the top of the jump, swing if the cursor is within the slash.
            above = height - self.y
            if (not self.air_swung and self.vy <= 0
                    and TOO_CLOSE <= abs(dx) <= ATTACK_REACH
                    and 0 <= above <= ATTACK_HEIGHT):
                self.set_state("air_attack")
                return
        self.fall(dt, 1.0)
        if self.state == "jump":
            self.set_anim("jump" if self.vy > 0 else "fall")

    def fall(self, dt, gravity_factor):
        """Apply gravity; on landing, rest briefly (or finish the swing on the ground)."""
        self.vy -= GRAVITY * gravity_factor * dt
        self.y += self.vy * dt
        if self.y <= 0:
            self.y = self.vy = 0.0
            if self.state in ("jump", "dropped", "evade"):
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
        if is_drag(self.pressed, mouse_pos(), window_pos, self.grab_offset, self.y > 0):
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
        self.closing = False
        self.set_anim("death" if self.state == "dead" else "hurt", restart=True)

    def grab(self):
        """Pick it up: it hangs from the cursor at the point where it was grabbed."""
        # Hold it by wherever the cursor is on it now, so it doesn't jump.
        mx, my = mouse_pos()
        _, _, _, bottom = work_area()
        wx = self.x - self.width / 2
        wy = bottom - self.ground - self.y
        self.grab_offset = (min(max(mx - wx, 0), self.width), min(max(my - wy, 0), self.height))
        self.pressed = None
        self.training = False
        self.state = "held"
        self.vx = self.vy = 0.0
        self.cursor_trail = CursorTrail()
        self.impact_done = False             # this throw may hit the dummy
        self.set_anim("fall")

    def drop(self):
        """Let go: it flies off with the cursor's speed and direction, then falls."""
        self.state = "dropped"
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
        """Thrown: move with its own speed, slowed by the air, bouncing off the screen edges."""
        lo, hi = self.bounds()
        _, top, _, bottom = work_area()
        ceiling = bottom - top - self.ground  # its window can't go above the screen
        before = self.vx
        falling = -self.vy
        self.x, self.vx, self.y, self.vy = fly_step(self.x, self.vx, self.y, self.vy,
                                                    dt, lo, hi, ceiling)
        if before * self.vx < 0 and abs(self.vx) > 50:   # bounced: face the new way
            self.facing = 1 if self.vx > 0 else -1
        if self.y == 0:                      # landed
            self.vx = 0.0
            self.impact_done = True
            if falling >= FALL_DAMAGE_SPEED:
                self.hit()                   # a hard landing hurts
            else:
                self.set_state("idle", idle_seconds=JUMP_PAUSE)

    # --- Interactions with the dummy ------------------------------------------------
    def body_box(self):
        """(left, right, bottom, top) of its body: x on the screen, heights above the taskbar."""
        return self.x - self.body_half, self.x + self.body_half, self.y, self.y + self.body_height

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
            d.take_hit()
            self.vx = -self.vx * IMPACT_BOUNCE       # bounce off it
        if (d.state == "flying" and not d.impact_done and self.alive and self.state != "held"
                and self.impact_speed(d.vx, d.vy, d_low, self.y + self.body_height,
                                      max(dt, 0.016)) >= IMPACT_SPEED):
            d.impact_done = True
            push = self.knockback_speed(d)
            d.vx = -d.vx * IMPACT_BOUNCE
            self.hit()                       # the dummy landed on Parton...
            self.vx, self.vy = push, KNOCKBACK_LIFT   # ...and pushes him away
            self.y = max(self.y, 0.1)        # off the ground
            if abs(push) >= 1:
                self.facing = -1 if push > 0 else 1   # facing the dummy that hit him

    def knockback_speed(self, d):
        """Sideways speed the dummy's hit gives Parton: in the direction the dummy
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
        if self.vx == 0 and self.y == 0:
            return
        lo, hi = self.bounds()
        _, top, _, bottom = work_area()
        self.x, self.vx, self.y, self.vy = fly_step(self.x, self.vx, self.y, self.vy, dt,
                                                    lo, hi, bottom - top - self.ground)
        if self.y == 0:
            self.vx = 0.0                    # lands and stops

    def dummy_threat(self, move="stay", delay=0.0):
        """Whether the thrown dummy would hit it hard if it did `move` after `delay` seconds.

        Follows the dummy's flight ahead of time with the same physics as the
        real throw, together with its own motion: it stands still for `delay`
        seconds and then does `move`, "stay", "jump" or "dash" (see evade).
        Returns (seconds until the hit, "side" or "above"), or None if the
        dummy misses, falls short or is too slow to hurt.
        """
        d = self.dummy
        lo, hi, ceiling = d.bounds()
        x, vx, y, vy = d.x, d.vx, d.y, d.vy
        px, py, pvy = self.x, 0.0, 0.0
        target = self.dash_target() if move == "dash" else px
        started = False
        step = 1 / 60
        for i in range(1, round(EVADE_LOOKAHEAD / step) + 1):
            was_over = px + self.body_half >= x + d.body[0] and px - self.body_half <= x + d.body[2]
            x, vx, y, vy = fly_step(x, vx, y, vy, step, lo, hi, ceiling, training_dummy.WEIGHT)
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

    def celebrate(self, dt):
        """Little hops of joy after breaking the dummy."""
        if self.y == 0 and self.vy <= 0:
            if self.hops_left == 0:
                self.set_state("idle")
                return
            self.hops_left -= 1
            self.vy = (2 * GRAVITY * CELEBRATE_HOP_HEIGHT) ** 0.5
            self.y = 0.1
        self.vy -= GRAVITY * dt
        self.y = max(self.y + self.vy * dt, 0.0)
        if self.y == 0:
            self.vy = 0.0
        self.set_anim("jump" if self.vy > 0 else "fall" if self.y > 0 else "idle")

    def dodge(self, dx):
        """Dash back so the cursor ends up at the axe's distance."""
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

    def keep_on_top(self):
        self.root.attributes("-topmost", True)
        self.root.after(5_000, self.keep_on_top)


if __name__ == "__main__":
    # Single instance: if Parton is already running, don't open another one.
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Parton_SingleInstance")
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
            "Parton",
            "Sprites not found in assets/parton/sprites:\n\n" + "\n".join(missing)
            + "\n\nDownload the free \"Little Axion\" pack by Jesshiyoo "
              "(https://jesshiyoo.itch.io/) and copy its PNG files there. See README.md.")
        raise SystemExit(1)
    App().run()
