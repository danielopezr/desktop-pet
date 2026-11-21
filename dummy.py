"""Training dummy that lives next to Capu, in the same program.

- Starts in the bottom-left corner of the screen, standing on the taskbar.
- A quick left click hits it (the cursor turns into a sword over it); Capu
  hits it too. The yellow impact of the hit shows up where it was hit.
- Hold or drag to pick it up and throw it, like Capu, but it is twice as
  heavy: it flies half as fast and bounces less. Thrown at Capu, it hurts
  him. Like him, it lands on the tops of the open windows, rides along when a
  window moves, and falls when it goes.
- On the 14th hit it breaks and disappears; it comes back on its own after
  RESPAWN_SECONDS, or right away with "Revive dummy" in the menu.
- Right click: the shared menu (see App in capu.py).
"""
import time
import tkinter as tk
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

import platforms
import ui
from physics import CursorTrail, fly_step, is_drag, throw_velocity
from screen import KEY_COLOR, mouse_pos, solid_mask, to_photo, work_area

# --- Settings ------------------------------------------------------------------
SCALE = 4                 # 80x48 px frames; same pixel size as Capu
FRAME_W, FRAME_H = 80, 48
HITS_TO_DIE = 14          # even: two hits per heart
HIT_FRAME_MS = 60
BREAK_FRAME_MS = 90
RUBBLE_VISIBLE_MS = 1_500  # how long the remains stay before it disappears
RESPAWN_SECONDS = 15      # after breaking, it comes back on its own after this long
MARGIN = 8                # distance from the screen edge where it starts
WEIGHT = 2.0              # twice as heavy as Capu: thrown half as fast
TICK_MS = 16              # update rate while held or flying (~60 fps)
HIT_CACHE_SIZE = 30       # hit animations kept ready (one per spot hit): the oldest are dropped
IMPACT_COLOR = (255, 200, 37)  # the yellow sparks in HIT.png: moved to where each hit lands

SPRITES = Path(__file__).parent / "assets" / "dummy" / "sprites"
SHEETS = ("IDLE", "HIT", "BREAKING")


def available():
    """True if the dummy's sprites are in place (otherwise Capu runs alone)."""
    return all((SPRITES / f"{name}.png").exists() for name in SHEETS)


def raw_frames(name):
    sheet = Image.open(SPRITES / f"{name}.png").convert("RGBA")
    return [sheet.crop((i * FRAME_W, 0, (i + 1) * FRAME_W, FRAME_H))
            for i in range(sheet.width // FRAME_W)]


def content_box(names):
    """Box around the visible content of every animation.

    Cropping the frames to it removes the transparent space on the sides and
    under the feet, so the dummy stands right on the taskbar.
    """
    boxes = [solid_mask(f).getbbox() for n in names for f in raw_frames(n)]
    boxes = [b for b in boxes if b]
    return (min(b[0] for b in boxes), 0,
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def body_box(names, box):
    """Box around the dummy's body (without the flying pieces), relative to `box`."""
    boxes = [solid_mask(f.crop(box)).getbbox() for n in names for f in raw_frames(n)]
    boxes = [b for b in boxes if b]
    return tuple(v * SCALE for v in (min(b[0] for b in boxes), min(b[1] for b in boxes),
                                      max(b[2] for b in boxes), max(b[3] for b in boxes)))


def body_mask(names, box, body):
    """The dummy's silhouette on screen: the union of every pose in `names`.

    One-pixel gaps (the jagged edges of the pixel art) are closed so the cursor
    doesn't flicker along the outline, without making the silhouette bigger.
    """
    mask = None
    for frame in (f.crop(box) for n in names for f in raw_frames(n)):
        m = solid_mask(frame)
        mask = m if mask is None else ImageChops.lighter(mask, m)
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    mask = mask.resize((mask.width * SCALE, mask.height * SCALE), Image.NEAREST)
    return mask.crop(body)


def load_frames(name, box):
    return [to_photo(frame.crop(box), SCALE) for frame in raw_frames(name)]


def split_impact(frames):
    """Split each frame into the dummy alone and the yellow impact sparks alone."""
    bodies, sparks = [], []
    for frame in frames:
        body, spark = frame.copy(), Image.new("RGBA", frame.size)
        body_px, spark_px = body.load(), spark.load()
        for y in range(frame.height):
            for x in range(frame.width):
                if body_px[x, y][:3] == IMPACT_COLOR and body_px[x, y][3]:
                    spark_px[x, y] = body_px[x, y]
                    body_px[x, y] = (0, 0, 0, 0)
        bodies.append(body)
        sparks.append(spark)
    return bodies, sparks


class TrainingDummy:
    def __init__(self, master, app):
        self.master = master
        self.app = app
        self.window = tk.Toplevel(master)
        self.window.title("Dummy")
        self.window.overrideredirect(True)          # no border or title bar
        self.window.attributes("-topmost", True)    # always on top
        self.window.attributes("-transparentcolor", KEY_COLOR)
        self.window.config(bg=KEY_COLOR)

        box = content_box(SHEETS)
        self.width = (box[2] - box[0]) * SCALE
        self.height = (box[3] - box[1]) * SCALE
        self.body = body_box(["IDLE", "HIT"], box)
        self.body_shape = body_mask(["IDLE", "HIT"], box, self.body)
        # Where its head is in its window (the hearts go over it).
        self.head_x = ui.head_center(solid_mask(raw_frames("IDLE")[0].crop(box))) * SCALE
        self.idle = load_frames("IDLE", box)
        self.hit = load_frames("HIT", box)
        # The hit without its sparks, and the sparks alone, to put them where it is hit.
        self.hit_bodies, self.hit_sparks = split_impact([f.crop(box) for f in raw_frames("HIT")])
        self.hit_plain = [to_photo(f, SCALE) for f in self.hit_bodies]
        first = next(s for s in self.hit_sparks if s.getbbox())
        x0, y0, x1, y1 = first.getbbox()
        self.spark_origin = ((x0 + x1) / 2, (y0 + y1) / 2)   # where the sparks burst from
        self.hit_cache = OrderedDict()          # (x, y, mirrored) -> frames, the latest used last
        self.breaking = load_frames("BREAKING", box)

        self.hitbox = ui.hit_zone(master)       # behind its body, shaped like it

        self.label = tk.Label(self.window, bg=KEY_COLOR, bd=0)
        self.label.pack()

        # Sword cursor over it; a closed hand while holding it.
        for widget in (self.label, self.hitbox):
            widget.config(cursor=ui.cursor("sword"))
            widget.bind("<ButtonPress-1>", self.press)
            widget.bind("<ButtonRelease-1>", self.release)
            widget.bind("<Button-3>", app.show_menu)

        self.hits = 0
        self.alive = True       # standing (not broken)
        self.gone = False       # broken and already gone from the screen
        self.hidden = False     # hidden from the menu
        self.away = False       # hidden for a while by "do not disturb"
        self.throws = 0         # how many times it has been thrown (Capu dodges per throw)
        self.anim_job = None
        self.respawn_job = None # pending automatic comeback after breaking
        self.pressed = None     # (time, x, y) of a left click in progress
        self.hearts = ui.Hearts(master)  # shown while the cursor is over it
        self.reset_position()

        ui.shape_window(ui.top_hwnd(self.hitbox), self.body_shape)  # hits only on the silhouette
        self.show_frame(self.idle[0])
        self.keep_on_top()
        self.last = time.perf_counter()
        self.tick()

    def reset_position(self):
        """Back to its starting spot: bottom-left corner, on the taskbar."""
        left, _, _, _ = work_area()
        self.x = float(left + MARGIN)           # left edge of its window, on the screen
        self.y = 0.0                            # height above the taskbar
        self.vx = self.vy = 0.0
        self.state = "rest"                     # "rest", "held" or "flying"
        self.platform = None                    # the window it stands on (None: the taskbar)
        self.platform_rect = None               # ...and where that window was last seen
        self.impact_done = True                 # only a fresh throw can hit Capu
        self.place()

    # --- State seen by Capu and the menu ----------------------------------------
    def resting(self):
        """Standing still somewhere (the taskbar or a window), and visible."""
        return self.alive and not self.hidden and not self.away and self.state == "rest"

    def standing(self):
        """Standing still on the taskbar and visible: Capu can train on it."""
        return self.resting() and self.platform is None

    def can_be_hit(self):
        return self.alive and not self.hidden and not self.away

    def on_screen(self):
        """Something of it is on the screen (standing, or breaking)."""
        return not self.gone and not self.hidden

    def respawning(self):
        """Broken, and coming back on its own soon."""
        return self.respawn_job is not None

    def center_x(self):
        """Screen x of the middle of its body."""
        return self.x + (self.body[0] + self.body[2]) / 2

    def body_span(self):
        """Screen x where its body starts and ends."""
        return self.x + self.body[0], self.x + self.body[2]

    def body_heights(self):
        """Height of the bottom and the top of its body above the taskbar, in pixels."""
        return self.y + self.height - self.body[3], self.y + self.height - self.body[1]

    # --- Menu actions ------------------------------------------------------------
    def hide(self):
        self.hidden = True
        self.cancel_respawn()   # hidden on purpose: it stays away
        self.let_go()
        self.window.withdraw()
        self.hitbox.withdraw()

    def unhide(self):
        self.hidden = False
        self.show_windows()

    def show_windows(self):
        """Put it back on the screen, unless "do not disturb" is keeping it away."""
        if self.away:
            return
        self.window.deiconify()
        if self.alive:
            self.hitbox.deiconify()
        self.place()

    def set_away(self, away):
        """Hide it while a full-screen app is open ("do not disturb"), and bring it back."""
        if away == self.away:
            return
        self.away = away
        if away:
            self.let_go()
            self.window.withdraw()
            self.hitbox.withdraw()
            self.hearts.hide()
        elif not self.hidden and not self.gone:
            self.show_windows()

    def revive(self):
        self.cancel_respawn()
        self.cancel_anim()
        self.hits = 0
        self.alive, self.gone, self.hidden = True, False, False
        self.pressed = None
        self.set_cursor("sword")
        self.show_frame(self.idle[0])
        self.reset_position()
        self.show_windows()

    # --- Clicking: hit, or drag and throw (same as Capu) ---------------------------
    def window_pos(self):
        _, _, _, bottom = work_area()
        return self.x, bottom - self.height - self.y

    def press(self, event):
        if not self.can_be_hit():
            return
        self.pressed = (time.perf_counter(), event.x_root, event.y_root)
        wx, wy = self.window_pos()
        self.grab_offset = (event.x_root - wx, event.y_root - wy)

    def release(self, _event):
        """Quick click: a hit. After a grab: a throw."""
        if self.state == "held":
            self.state = "flying"
            self.set_cursor("sword")
            self.throws += 1
            vx, vy = self.trail.speed()
            self.vx, self.vy = throw_velocity(vx, vy, WEIGHT)
        elif self.pressed:
            self.take_hit(self.pressed[1:])     # where the click was
        self.pressed = None

    def grab(self):
        # Hold it by wherever the cursor is on it now, so it doesn't jump.
        mx, my = mouse_pos()
        wx, wy = self.window_pos()
        self.grab_offset = (min(max(mx - wx, 0), self.width), min(max(my - wy, 0), self.height))
        self.pressed = None
        self.state = "held"
        self.platform = self.platform_rect = None   # lifted off whatever it stood on
        self.set_cursor("fist")
        self.vx = self.vy = 0.0
        self.trail = CursorTrail()
        self.impact_done = False  # one hit on Capu per throw, at most

    def let_go(self):
        """Stop holding it (hidden or broken while held): it just falls."""
        self.pressed = None
        if self.state == "held":
            self.state, self.vx, self.vy = "flying", 0.0, 0.0
            self.set_cursor("sword")

    def set_cursor(self, name):
        """The cursor over it: "sword", "fist", or None for the normal arrow."""
        for widget in (self.label, self.hitbox):
            widget.config(cursor=ui.cursor(name) if name else "")

    def bounds(self):
        """Where its window's left edge can go, keeping the body on the screen."""
        left, top, right, bottom = work_area()
        return left - self.body[0], right - self.body[2], bottom - top - self.height

    def tick(self):
        # Whatever goes wrong in one update, the next one still comes: it
        # mustn't freeze for good.
        try:
            self.update()
        finally:
            self.master.after(TICK_MS, self.tick)

    def update(self):
        # Real time between updates (like Capu, who foresees its flight to
        # dodge it): a late update mustn't slow its flight down.
        now = time.perf_counter()
        dt, self.last = min(now - self.last, 0.1), now
        if not self.hidden and not self.gone and not self.away:
            if self.pressed and self.state != "held":
                if is_drag(self.pressed, mouse_pos(), self.window_pos(),
                           self.grab_offset, self.y > 0):
                    self.grab()
            if self.state == "held":
                mx, my = mouse_pos()
                self.trail.add(mx, my)
                lo, hi, ceiling = self.bounds()
                _, _, _, bottom = work_area()
                ox, oy = self.grab_offset
                self.x = min(max(mx - ox, lo), hi)
                self.y = min(max(bottom - self.height - (my - oy), 0.0), ceiling)
                self.place()
            elif self.state == "flying":
                lo, hi, ceiling = self.bounds()
                before = self.feet()
                self.x, self.vx, self.y, self.vy = fly_step(
                    self.x, self.vx, self.y, self.vy, dt, lo, hi, ceiling, WEIGHT)
                spot = None if self.vy > 0 else platforms.landing(
                    self.ledges, self.center_x(), before, self.feet())
                if spot is not None:                # landed (on the taskbar or a window)
                    self.state, self.vx, self.vy = "rest", 0.0, 0.0
                    self.platform = spot[1]
                    self.platform_rect = platforms.window_rect(spot[1]) if spot[1] else None
                    self.y = spot[0] - self.feet_offset()
                self.place()
            elif self.state == "rest":
                self.ride()
        self.update_hearts()

    # --- Standing on windows -----------------------------------------------------------
    def feet_offset(self):
        """How far above its window's bottom edge its body ends (what it stands on)."""
        return self.height - self.body[3]

    def feet(self):
        return self.y + self.feet_offset()

    @property
    def ledges(self):
        """The window tops with room for it to stand on, the highest first."""
        return self.app.ledges_for(self.body[3] - self.body[1])

    def ride(self):
        """Standing on a window: move along with it; if it has gone, or is no
        longer under it, fall."""
        if self.platform is None:
            return
        rect = platforms.window_rect(self.platform)
        _, _, _, bottom = work_area()
        if rect is None or bottom - platforms.top_row(rect) <= 0:
            self.fall()
            return
        if self.platform_rect is not None:
            lo, hi, _ = self.bounds()
            self.x = min(max(self.x + rect[0] - self.platform_rect[0], lo), hi)
        self.platform_rect = rect
        self.y = bottom - platforms.top_row(rect) - self.feet_offset()
        self.place()
        if not rect[0] <= self.center_x() <= rect[2]:
            self.fall()

    def check_footing(self):
        """After each look at the windows: if the stretch it stands on has gone
        (covered by a window in front, say), it falls."""
        if (not self.hidden and not self.gone and not self.away and self.platform is not None
                and self.state == "rest"
                and not platforms.stands_on(self.ledges, self.platform, self.center_x(), self.feet())):
            self.fall()

    def fall(self):
        """Off the window it stood on: it drops down."""
        self.platform = self.platform_rect = None
        if self.state == "rest":
            self.state, self.vx, self.vy = "flying", 0.0, 0.0
            self.impact_done = True             # a fall on its own doesn't hurt anyone

    def update_hearts(self):
        """Show its health above its head while the cursor is over its body."""
        if not self.can_be_hit() or self.state == "held":   # broken, hidden or picked up
            self.hearts.hide()
            return
        left, right = self.body_span()
        low, high = self.body_heights()
        _, _, _, bottom = work_area()
        mx, my = mouse_pos()
        if left <= mx <= right and bottom - high <= my <= bottom - low:
            self.hearts.show(self.x + self.head_x, bottom - high, HITS_TO_DIE - self.hits, HITS_TO_DIE)
        else:
            self.hearts.hide()

    # --- Window ----------------------------------------------------------------
    def place(self):
        _, _, _, bottom = work_area()
        x, y = round(self.x), round(bottom - self.height - self.y)
        self.window.geometry(f"{self.width}x{self.height}+{x}+{y}")
        bx0, by0, bx1, by1 = self.body
        self.hitbox.geometry(f"{bx1 - bx0}x{by1 - by0}+{x + bx0}+{y + by0}")

    def stack_hitbox_below(self):
        """Put the hit zone right below the dummy in the window order."""
        ui.stack_below(self.hitbox, self.label)

    def keep_on_top(self):
        # Re-assert "always on top" and the position (in case the taskbar changes).
        if self.resting():
            self.hitbox.attributes("-topmost", True)
            self.window.attributes("-topmost", True)
            lo, hi, _ = self.bounds()
            self.x = min(max(self.x, lo), hi)
            self.place()
            self.stack_hitbox_below()
        self.master.after(5_000, self.keep_on_top)

    def show_frame(self, frame):
        self.label.config(image=frame)

    # --- Animations ------------------------------------------------------------
    def play(self, frames, delay, on_done=None, index=0):
        if index < len(frames):
            self.show_frame(frames[index])
            self.anim_job = self.master.after(
                delay, self.play, frames, delay, on_done, index + 1)
        else:
            self.anim_job = None
            if on_done:
                on_done()

    def cancel_respawn(self):
        if self.respawn_job:
            self.master.after_cancel(self.respawn_job)
            self.respawn_job = None

    def cancel_anim(self):
        if self.anim_job:
            self.master.after_cancel(self.anim_job)
            self.anim_job = None

    def take_hit(self, point=None):
        """A hit from the cursor or from Capu (also while held or flying), at the
        screen `point` (x, y) it landed on, if known. Returns True if this hit broke it."""
        if not self.can_be_hit():
            return False
        self.hits += 1
        self.cancel_anim()
        if self.hits >= HITS_TO_DIE:
            self.die()
            return True
        frames = self.hit if point is None else self.hit_frames_at(point)
        self.play(frames, HIT_FRAME_MS, on_done=lambda: self.show_frame(self.idle[0]))
        return False

    def surface_point(self, screen_y, from_left):
        """Screen point on the edge of its silhouette, at height `screen_y`, seen
        from the left or from the right: where something coming from that side
        strikes it (a row with nothing solid uses the nearest one that has)."""
        wx, wy = self.window_pos()
        mask = self.body_shape
        left, top = wx + self.body[0], wy + self.body[1]
        row = min(max(round(screen_y - top), 0), mask.height - 1)
        for distance in range(mask.height):
            for r in (row - distance, row + distance):
                if 0 <= r < mask.height:
                    solid = [x for x in range(mask.width) if mask.getpixel((x, r))]
                    if solid:
                        inset = 2 * SCALE        # a little into the body, not on its very edge
                        x = solid[0] + inset if from_left else solid[-1] - inset
                        return left + x, top + r
        return left + mask.width / 2, top + row

    def hit_frames_at(self, point):
        """The hit animation with its sparks bursting from the screen `point`.

        The point is kept on its body. Hit on its left half, the sparks are
        mirrored so they fly out to the left.
        """
        wx, wy = self.window_pos()
        bx0, by0, bx1, by1 = (v / SCALE for v in self.body)
        x = min(max((point[0] - wx) / SCALE, bx0), bx1 - 1)
        y = min(max((point[1] - wy) / SCALE, by0), by1 - 1)
        mirrored = x < (bx0 + bx1) / 2
        key = (round(x), round(y), mirrored)
        if key not in self.hit_cache:
            ox, oy = self.spark_origin
            if mirrored:
                ox = self.hit_sparks[0].width - ox
            frames = []
            for body, sparks in zip(self.hit_bodies, self.hit_sparks):
                if mirrored:
                    sparks = sparks.transpose(Image.FLIP_LEFT_RIGHT)
                moved = Image.new("RGBA", body.size)
                moved.paste(sparks, (round(x - ox), round(y - oy)), sparks)
                frame = body.copy()
                frame.alpha_composite(moved)
                frames.append(to_photo(frame, SCALE))
            self.hit_cache[key] = frames
            while len(self.hit_cache) > HIT_CACHE_SIZE:   # each one is close to a megabyte
                self.hit_cache.popitem(last=False)
        self.hit_cache.move_to_end(key)
        return self.hit_cache[key]

    def swing_back(self):
        """Hit back at Capu: it swings on its post (the hit wobble)."""
        self.cancel_anim()
        self.play(self.hit_plain, HIT_FRAME_MS, on_done=lambda: self.show_frame(self.idle[0]))

    def speed(self):
        return (self.vx * self.vx + self.vy * self.vy) ** 0.5

    def die(self):
        # It breaks and, after a moment, disappears until it is revived.
        self.alive = False
        self.let_go()           # if it was held, the remains just fall
        self.hitbox.withdraw()  # the remains can't be hit...
        self.set_cursor(None)   # ...so no sword over them
        self.play(self.breaking, BREAK_FRAME_MS,
                  on_done=lambda: self.master.after(RUBBLE_VISIBLE_MS, self.vanish))

    def vanish(self):
        if self.alive:          # revived in the meantime
            return
        self.gone = True
        self.window.withdraw()
        self.respawn_job = self.master.after(int(RESPAWN_SECONDS * 1000), self.revive)
        self.app.check_empty()
