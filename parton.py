"""Parton: a desktop pet for Windows ("Little Axion" character by Jesshiyoo).

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
ATTACK_REACH = 35 * SCALE     # axe reach (the slash reaches 26-43 px ahead)
ATTACK_HEIGHT = 19 * SCALE    # top of the slash above its feet (sprite: 1-19 px)
SLASH_CENTER = 10 * SCALE     # middle of the slash above its feet: where it aims
ATTACK_PAUSE = 0.35           # pause between swings, in seconds
TOO_CLOSE = 20 * SCALE        # cursor on top of it: the axe would miss
DASH_SPEED = 550              # pixels per second when dashing back
JUMP_MAX_HEIGHT = 160         # highest jump, in pixels (it jumps just enough to aim)
JUMP_MIN_HEIGHT = 40          # lowest jump, in pixels
GRAVITY = 2600                # pixels per second squared
JUMP_DRIFT = 140              # sideways speed while in the air, towards the cursor
JUMP_PAUSE = 0.6              # pause after landing before jumping again, in seconds
AIR_ATTACK_FRAME_MS = 45      # the air swing plays faster than the ground one
AIR_SLASH_LAST_FRAME = 8      # it hangs in the air until this frame of the swing

# Throwing (when you drag it and let go)
THROW_SAMPLE_SECONDS = 0.08   # cursor speed is measured over this last stretch
THROW_FACTOR = 0.6            # share of the cursor speed it keeps when released
THROW_FLICK_SPEED = 1500      # above this cursor speed, flicks get stronger...
THROW_FLICK_FACTOR = 0.9      # ...up to this share at twice that speed
THROW_MAX_SPEED = 2400        # cap on the throw speed, in pixels per second
AIR_DRAG = 1.8                # how quickly the air slows its sideways speed
WALL_BOUNCE = 0.5             # share of speed it keeps when bouncing off a screen edge

SPRITES = Path(__file__).parent / "assets" / "sprites"

# name: (file, milliseconds per frame, loops)
ANIMATIONS = {
    "idle":    ("Idle.png",     130, True),
    "run":     ("Run.png",       80, True),
    "attack1": ("Attack 1.png",  70, False),
    "attack2": ("Attack 2.png",  70, False),
    "dash":    ("Dash.png",      60, True),
    "jump":    ("Jump.png",     100, True),
    "fall":    ("Fall.png",     100, True),
    # For later:
    "death":   ("Death.png",     90, False),
    "hurt":    ("Hurt.png",     100, False),
}
USED = ("idle", "run", "attack1", "attack2", "dash", "jump", "fall")


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
        self.label.bind("<ButtonPress-1>", self.grab)
        self.label.bind("<ButtonRelease-1>", self.drop)
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Exit", command=self.root.destroy)

        lo, hi = self.bounds()
        self.x = random.uniform(lo, hi)           # body center, in screen pixels
        self.y = 0.0                              # height above the taskbar (jumps)
        self.vy = 0.0                             # vertical speed, positive is up
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
        elif state == "chase":
            self.set_anim("run")
        elif state == "attack":
            self.set_anim(random.choice(("attack1", "attack2")), restart=True)
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
        elif state == "air_attack":
            self.air_swung = True
            self.vy = 0.0                    # hang at the top while swinging
            self.set_anim("attack1", restart=True, frame_ms=AIR_ATTACK_FRAME_MS)

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

        if self.state == "run" or (self.state == "idle" and not self.pausing):
            # While calm, keep watch: if it sees the cursor, go after it.
            if self.sees_mouse(VISION_RANGE) is not None:
                self.set_state("chase")

        if self.state == "idle":
            self.idle_left -= dt
            if self.idle_left <= 0:
                # After a short pause, go back to the cursor if it is still in
                # sight, or stay idle for a normal while. Otherwise, wander.
                if not self.pausing:
                    self.set_state("run")
                elif self.sees_mouse(VISION_RANGE) is not None:
                    self.set_state("chase")
                else:
                    self.set_state("idle")
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
        elif self.state == "jump":
            self.jump(dt)
        elif self.state == "air_attack":
            # Hang still until the slash is over, then start falling.
            self.fall(dt, 0.0 if self.frame_index <= AIR_SLASH_LAST_FRAME else 1.0)
        elif self.state == "held":
            self.follow_cursor()
        elif self.state == "dropped":
            self.fly(dt)

        if self.animate(dt) and self.state in ("attack", "air_attack"):
            if self.y > 0:
                # Air swing finished: keep falling.
                self.state = "jump"
                self.set_anim("fall")
            else:
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
            if self.state in ("jump", "dropped"):
                self.set_state("idle", idle_seconds=JUMP_PAUSE)

    # --- Drag and drop ---------------------------------------------------------
    def grab(self, event):
        """Pick it up: it hangs from the cursor at the point where it was grabbed."""
        self.grab_offset = (event.x_root - self.root.winfo_x(),
                            event.y_root - self.root.winfo_y())
        self.state = "held"
        self.vx = self.vy = 0.0
        self.cursor_trail = []               # recent (time, x, y) of the cursor
        self.set_anim("fall")

    def drop(self, _event):
        """Let go: it flies off with the cursor's speed and direction, then falls."""
        if self.state != "held":
            return
        self.state = "dropped"
        vx, vy = self.cursor_speed()
        speed = (vx * vx + vy * vy) ** 0.5
        scale = THROW_FACTOR
        if speed > THROW_FLICK_SPEED:        # sharp flicks keep more of their speed
            t = min(1.0, (speed - THROW_FLICK_SPEED) / THROW_FLICK_SPEED)
            scale = THROW_FACTOR + (THROW_FLICK_FACTOR - THROW_FACTOR) * t
        if speed * scale > THROW_MAX_SPEED:  # cap very fast flicks
            scale = THROW_MAX_SPEED / speed
        self.vx = vx * scale
        self.vy = -vy * scale                # screen y grows downwards; ours grows upwards
        if abs(self.vx) > 50:
            self.facing = 1 if self.vx > 0 else -1

    def cursor_speed(self):
        """Cursor speed (pixels per second) over the last THROW_SAMPLE_SECONDS."""
        now = time.perf_counter()
        trail = [s for s in self.cursor_trail if now - s[0] <= THROW_SAMPLE_SECONDS]
        if len(trail) < 2 or trail[-1][0] - trail[0][0] <= 0:
            return 0.0, 0.0
        (t0, x0, y0), (t1, x1, y1) = trail[0], trail[-1]
        return (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)

    def follow_cursor(self):
        mx, my = mouse_pos()
        now = time.perf_counter()
        self.cursor_trail = [s for s in self.cursor_trail if now - s[0] <= 0.5] + [(now, mx, my)]
        _, _, _, bottom = work_area()
        lo, hi = self.bounds()
        ox, oy = self.grab_offset
        self.x = min(max(mx - ox + self.width / 2, lo), hi)
        self.y = max(bottom - self.ground - (my - oy), 0.0)   # never below the taskbar

    def fly(self, dt):
        """Thrown: move with its own speed, slowed by the air, bouncing off the screen edges."""
        lo, hi = self.bounds()
        _, top, _, bottom = work_area()
        self.vx *= max(0.0, 1.0 - AIR_DRAG * dt)
        self.x += self.vx * dt
        if self.x < lo or self.x > hi:       # side edges: bounce back
            self.x = min(max(self.x, lo), hi)
            self.vx = -self.vx * WALL_BOUNCE
            if abs(self.vx) > 50:
                self.facing = 1 if self.vx > 0 else -1
        ceiling = bottom - top - self.ground  # its window can't go above the screen
        if self.y > ceiling:
            self.y = ceiling
            self.vy = -abs(self.vy) * WALL_BOUNCE
        self.fall(dt, 1.0)
        if self.state != "dropped":          # landed
            self.vx = 0.0

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
