"""Shared drag-and-throw physics for Capu and the training dummy.

Both are picked up and thrown the same way; a heavier body (weight > 1) is
thrown slower and bounces less off the screen edges. A thrown body that hits
the other one fast enough hurts it, and landing too fast hurts Capu.
"""
import time

GRAVITY = 2600                # pixels per second squared

# Throwing (when you drag something and let go)
THROW_SAMPLE_SECONDS = 0.08   # cursor speed is measured over this last stretch
THROW_FACTOR = 0.6            # share of the cursor speed it keeps when released
THROW_FLICK_SPEED = 1500      # above this cursor speed, flicks get stronger...
THROW_FLICK_FACTOR = 0.9      # ...up to this share at twice that speed
THROW_MAX_SPEED = 2400        # cap on the throw speed, in pixels per second
AIR_DRAG = 1.8                # how quickly the air slows its sideways speed
WALL_BOUNCE = 0.5             # share of speed it keeps when bouncing off a screen edge

# Impacts
IMPACT_SPEED = 400            # a thrown body hitting the other one this fast hurts it
IMPACT_BOUNCE = 0.3           # share of sideways speed it keeps when bouncing off the other
FALL_DAMAGE_SPEED = 1400      # Capu landing this fast gets hurt (about a drop from 380 px)

# Clicking: a quick click hits; holding or dragging picks it up
DRAG_THRESHOLD = 6            # pixels the cursor must move (relative to it) to start dragging
AIR_DRAG_THRESHOLD = 30       # same, while it is in the air (it's hard to track it exactly)
HOLD_SECONDS = 0.25           # holding the button this long also picks it up


class CursorTrail:
    """Recent cursor positions while dragging, to know how fast it was moving."""

    def __init__(self):
        self.points = []                     # (time, x, y)

    def add(self, x, y):
        now = time.perf_counter()
        self.points = [p for p in self.points if now - p[0] <= 0.5] + [(now, x, y)]

    def speed(self):
        """Cursor speed (pixels per second) over the last THROW_SAMPLE_SECONDS."""
        now = time.perf_counter()
        trail = [p for p in self.points if now - p[0] <= THROW_SAMPLE_SECONDS]
        if len(trail) < 2 or trail[-1][0] - trail[0][0] <= 0:
            return 0.0, 0.0
        (t0, x0, y0), (t1, x1, y1) = trail[0], trail[-1]
        return (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)


def throw_velocity(cursor_vx, cursor_vy, weight=1.0):
    """Velocity (vx, vy; vy positive is up) of something let go at this cursor speed."""
    speed = (cursor_vx * cursor_vx + cursor_vy * cursor_vy) ** 0.5
    scale = THROW_FACTOR
    if speed > THROW_FLICK_SPEED:            # sharp flicks keep more of their speed
        t = min(1.0, (speed - THROW_FLICK_SPEED) / THROW_FLICK_SPEED)
        scale = THROW_FACTOR + (THROW_FLICK_FACTOR - THROW_FACTOR) * t
    if speed * scale > THROW_MAX_SPEED:      # cap very fast flicks
        scale = THROW_MAX_SPEED / speed
    scale /= weight                          # heavier things fly slower
    # Screen y grows downwards; ours grows upwards.
    return cursor_vx * scale, -cursor_vy * scale


def is_drag(pressed, cursor, window_pos, grab_offset, airborne):
    """Whether a click in progress has become a drag (else it is still a hit).

    The cursor must move both on the screen and relative to the thing clicked:
    keeping the mouse still while it moves, or following it with the mouse
    while it runs or flies, both still count as a click.
    """
    t, px, py = pressed
    mx, my = cursor
    wx, wy = window_pos
    ox, oy = grab_offset
    on_screen = max(abs(mx - px), abs(my - py))
    on_body = max(abs(mx - wx - ox), abs(my - wy - oy))
    limit = AIR_DRAG_THRESHOLD if airborne else DRAG_THRESHOLD
    return min(on_screen, on_body) > limit or time.perf_counter() - t >= HOLD_SECONDS


def fly_step(x, vx, y, vy, dt, lo, hi, ceiling, weight=1.0):
    """One step of a thrown body: air drag, gravity and bounces off the screen edges.

    x is its position across (kept within lo..hi), y its height above the
    taskbar (kept below ceiling). Returns the new (x, vx, y, vy); once it has
    landed, y and vy are 0.
    """
    bounce = WALL_BOUNCE / weight
    vx *= max(0.0, 1.0 - AIR_DRAG * dt)
    x += vx * dt
    if x < lo or x > hi:                     # side edges: bounce back
        x = min(max(x, lo), hi)
        vx = -vx * bounce
    if y > ceiling:                          # top of the screen
        y = ceiling
        vy = -abs(vy) * bounce
    vy -= GRAVITY * dt
    y += vy * dt
    if y <= 0:
        y = vy = 0.0
    return x, vx, y, vy
