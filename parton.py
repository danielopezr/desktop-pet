"""Parton: a desktop pet for Windows ("Little Axion" character by Jesshiyoo).

- Lives at the bottom of the screen, standing on the taskbar.
- Idles for a while and then runs to a random spot.
- If it sees the cursor nearby (left or right, not too high), it runs to it
  and swings its axe with attack 1 or attack 2, at random. If the cursor is
  above the axe's vertical reach, it just watches it.
- If the cursor is right on top of it, it dashes back to get the axe's
  distance and then attacks.
- Right click: menu to exit.

Every animation in the pack is listed in ANIMATIONS; the ones not used yet
are ready for later. The sprites are not included in the repository (see
README.md): put the pack's PNG files in assets/sprites.
"""
import ctypes
import random
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox

from PIL import Image, ImageTk

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
ATTACK_REACH = 35 * SCALE     # axe reach (the sprite reaches 30-47 px)
ATTACK_HEIGHT = 23 * SCALE + 8  # max axe height above the taskbar (sprite: 17-23 px)
ATTACK_PAUSE = 0.35           # pause between swings, in seconds
TOO_CLOSE = 20 * SCALE        # cursor on top of it: the axe would miss
DASH_SPEED = 550              # pixels per second when dashing back

SPRITES = Path(__file__).parent / "assets" / "sprites"

# name: (file, milliseconds per frame, loops)
ANIMATIONS = {
    "idle":    ("Idle.png",     130, True),
    "run":     ("Run.png",       80, True),
    "attack1": ("Attack 1.png",  70, False),
    "attack2": ("Attack 2.png",  70, False),
    "dash":    ("Dash.png",      60, True),
    # For later:
    "death":   ("Death.png",     90, False),
    "fall":    ("Fall.png",     100, True),
    "hurt":    ("Hurt.png",     100, False),
    "jump":    ("Jump.png",     100, False),
}
USED = ("idle", "run", "attack1", "attack2", "dash")


def work_area():
    """Windows work area (screen minus the taskbar), in physical pixels."""
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def mouse_pos():
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


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


class Parton:
    def __init__(self):
        self.root = tk.Tk()
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
        self.label.bind("<Button-3>", self.show_menu)
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Exit", command=self.root.destroy)

        lo, hi = self.bounds()
        self.x = random.uniform(lo, hi)           # body center, in screen pixels
        self.facing = random.choice((1, -1))
        self.shown = None
        self.anim = None
        self.set_state("idle")
        self.last = time.perf_counter()
        self.tick()
        self.keep_on_top()

    # --- Helpers ---------------------------------------------------------------
    def bounds(self):
        """How far the body center can go without leaving the screen."""
        left, _, right, _ = work_area()
        return left + self.body_half, right - self.body_half

    def sees_mouse(self, max_range):
        """(horizontal distance, height above the taskbar) of the cursor if seen, else None."""
        mx, my = mouse_pos()
        _, _, _, bottom = work_area()
        dx, height = mx - self.x, bottom - my
        if abs(dx) <= max_range and -5 <= height <= VISION_HEIGHT:
            return dx, height
        return None

    # --- States ----------------------------------------------------------------
    def set_state(self, state, idle_seconds=None):
        self.state = state
        if state in ("idle", "run"):
            self.set_anim(state, restart=True)
        self.after_attack = idle_seconds == ATTACK_PAUSE
        if state == "idle":
            self.idle_left = idle_seconds if idle_seconds is not None else random.uniform(*IDLE_SECONDS)
        elif state == "run":
            lo, hi = self.bounds()
            options = [x for x in (random.uniform(lo, hi) for _ in range(20))
                       if abs(x - self.x) >= MIN_RUN_DISTANCE]
            self.target = options[0] if options else (lo if self.x > (lo + hi) / 2 else hi)
            self.facing = 1 if self.target > self.x else -1
        elif state == "chase":
            self.set_anim("run")
        elif state == "attack":
            self.set_anim(random.choice(("attack1", "attack2")), restart=True)
        elif state == "dodge":
            self.set_anim("dash", restart=True)

    def set_anim(self, name, restart=False):
        """Switch animation; start from the first frame if it changes or if asked to."""
        if restart or self.anim != name:
            self.anim = name
            self.frame_index = 0
            self.frame_elapsed = 0.0

    def tick(self):
        now = time.perf_counter()
        dt, self.last = min(now - self.last, 0.1), now

        if self.state in ("idle", "run"):
            # While calm, keep watch: if it sees the cursor, go after it.
            if self.sees_mouse(VISION_RANGE) is not None:
                self.set_state("chase")

        if self.state == "idle":
            self.idle_left -= dt
            if self.idle_left <= 0:
                # After the pause between swings, stay idle for a normal while;
                # otherwise, go for a wander.
                self.set_state("idle" if self.after_attack else "run")
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

        if self.animate(dt) and self.state == "attack":
            # Swing finished: short pause and keep watching.
            self.set_state("idle", idle_seconds=ATTACK_PAUSE)

        self.place()
        self.root.after(TICK_MS, self.tick)

    def move_towards(self, target, speed, dt):
        step = speed * dt
        if abs(target - self.x) <= step:
            self.x = target
        else:
            self.facing = 1 if target > self.x else -1
            self.x += step * self.facing

    def chase(self, dt):
        seen = self.sees_mouse(LOSE_RANGE)
        if seen is None:                     # lost it: calm down again
            self.set_state("idle")
            return
        dx, height = seen
        self.facing = 1 if dx >= 0 else -1
        if abs(dx) <= ATTACK_REACH:
            if height > ATTACK_HEIGHT:
                self.set_anim("idle")        # too high for the axe: just watch it
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
        _, ms, loops = ANIMATIONS[self.anim]
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
        # Feet rest right on the taskbar; anything below them is transparent.
        self.root.geometry(f"{self.width}x{self.height}+{x}+{bottom - self.ground}")

    def keep_on_top(self):
        self.root.attributes("-topmost", True)
        self.root.after(5_000, self.keep_on_top)

    def show_menu(self, event):
        self.menu.tk_popup(event.x_root, event.y_root)

    def run(self):
        self.root.mainloop()


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
            "Sprites not found in assets/sprites:\n\n" + "\n".join(missing)
            + "\n\nDownload the free \"Little Axion\" pack by Jesshiyoo "
              "(https://jesshiyoo.itch.io/) and copy its PNG files there. See README.md.")
        raise SystemExit(1)
    Parton().run()
