"""Shared helpers for the tests.

The tests never touch the real mouse, the real settings or the real cursor
files: the cursor position is simulated, and settings and cursors go to a
temporary folder. The open windows Capu can stand on are simulated too. Tests that run the whole program open its windows for a
moment (Capu and the dummy show up on the screen while they run).
"""
import ctypes
import random
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # physical pixels, like the program
except (AttributeError, OSError):
    pass

import dummy  # noqa: E402
import capu    # noqa: E402
import platforms  # noqa: E402
import ui  # noqa: E402

REAL_FULLSCREEN_CHECK = capu.fullscreen_app_open     # before any test swaps it


def cancel_timers(root):
    """Cancel a Tk root's pending timers: closed, they would still fire during later tests."""
    try:
        jobs = root.tk.splitlist(root.tk.call("after", "info"))
    except tk.TclError:
        return                                    # already closed
    for job in jobs:
        try:
            root.tk.call("after", "cancel", job)
        except tk.TclError:
            pass


def close_root(root):
    cancel_timers(root)
    try:
        root.destroy()
    except tk.TclError:
        pass                                      # already closed


def sprites_available():
    return not capu.missing_sprites() and dummy.available()


def needs_sprites(cls):
    """Skip a test class when the sprites (not in the repository) are missing."""
    return unittest.skipUnless(sprites_available(), "sprites not in assets/ (see README.md)")(cls)


class TkCase(unittest.TestCase):
    """A hidden Tk root for tests that make images or windows."""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        close_root(cls.root)

    def pump(self, seconds, until=None):
        """Let Tk run for `seconds` (or until `until()` is true). Returns whether it stopped early."""
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            self.root.update()
            if until and until():
                return True
            time.sleep(0.005)
        return False


class AppCase(unittest.TestCase):
    """The whole program, with a simulated cursor and full-screen app."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cursor = [0, 0]
        self.buttons = False                      # a simulated mouse button held down
        self.fullscreen = False
        # [(hwnd, (left, top, right, bottom))], front first; a third item False
        # makes one that only covers (a maximized window, say).
        self.windows = []
        patches = [
            mock.patch.object(platforms, "window_rects", self.simulated_windows),
            mock.patch.object(platforms, "window_rect",
                              lambda hwnd: next((r for h, r, ok in self.simulated_windows()
                                                 if h == hwnd and ok), None)),
            mock.patch.object(capu, "CLIMB_CHANCE", 0.0),         # it climbs only when a test says so
            mock.patch.object(capu, "FIDGET_CHANCE", 0.0),        # ...and fidgets only when one says so
            mock.patch.object(capu, "SETTINGS_FILE", Path(self.tmp.name) / "settings.json"),
            mock.patch.object(ui, "CURSOR_DIR", Path(self.tmp.name) / "cursors"),
            mock.patch.object(ui, "_cursors", None),
            mock.patch.object(capu, "fullscreen_app_open", lambda: self.fullscreen),
            mock.patch.object(ui, "any_mouse_button_down", lambda: self.buttons),
            mock.patch.object(capu, "TRAIN_CHANCE", 0.0),         # it trains only when a test says so
            mock.patch.object(capu, "COUNTER_CHANCE", 0.0),
            mock.patch.object(capu, "EVADE_CHANCE", 0.0),
        ]
        for module in (capu, dummy, ui):
            patches.append(mock.patch.object(module, "mouse_pos", lambda: tuple(self.cursor)))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        random.seed(1)
        self.app = capu.App()
        self.addCleanup(self.close_app)
        # When the program closes itself (nobody left on the screen), it must not
        # leave its timers behind for the next tests either.
        real_destroy = self.app.root.destroy
        def destroy():
            cancel_timers(self.app.root)
            real_destroy()
        self.app.root.destroy = destroy
        self.p, self.d = self.app.capu, self.app.dummy
        _, _, _, self.bottom = ui.work_area()
        self.pump(0.2)

    def simulated_windows(self):
        return [(w[0], w[1], w[2] if len(w) > 2 else True) for w in self.windows]

    def close_app(self):
        close_root(self.app.root)

    def pump(self, seconds, until=None):
        """Let the program run for `seconds` (or until `until()` is true; or until it
        closes itself). Returns whether it stopped early."""
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            try:
                self.app.root.update()
            except tk.TclError:
                return True                      # the program closed
            if until and until():
                return True
            time.sleep(0.005)
        return False

    # --- Setting the scene ---------------------------------------------------------
    def park_capu(self, x=None, facing=1, seconds=100):
        """Capu standing still (not reacting to anything) at `x`, middle of the screen by default."""
        lo, hi = self.p.bounds()
        self.p.x = (lo + hi) / 2 if x is None else x
        self.p.y = self.p.vx = self.p.vy = 0.0
        self.p.facing = facing
        self.p.hits = 0
        self.p.set_state("idle", idle_seconds=seconds)

    def cursor_on_capu(self):
        self.cursor[:] = [int(self.p.x), int(self.bottom - self.p.y - self.p.body_height / 2)]

    def cursor_on_dummy(self):
        low, high = self.d.body_heights()
        self.cursor[:] = [int(self.d.center_x()), int(self.bottom - (low + high) / 2)]

    def throw_dummy(self, gap=None, vx=0.0, y=0.0, vy=0.0):
        """Send the dummy flying at Capu: from `gap` px to his left, or from right above him."""
        d, p = self.d, self.p
        d.state, d.y, d.vx, d.vy = "rest", 0.0, 0.0, 0.0
        if gap is None:
            d.x = p.x - (d.body[0] + d.body[2]) / 2
        else:
            d.x = p.x - p.body_half - gap - d.body[2]
        d.y, d.vx, d.vy = y, vx, vy
        d.state, d.impact_done = "flying", False
        d.throws += 1

    def watch_states(self, seconds):
        """States Capu goes through over `seconds`."""
        seen = []
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            self.app.root.update()
            if not seen or seen[-1] != self.p.state:
                seen.append(self.p.state)
            time.sleep(0.005)
        return seen


class Click:
    """Stand-in for a Tk mouse event."""

    def __init__(self, x, y):
        self.x_root, self.y_root = x, y
        self.x, self.y = x, y


def cursor_file(widget):
    """Which of our cursors a widget shows: "sword", "fist", or "" for the arrow."""
    spec = str(widget.cget("cursor"))
    for name in ("sword", "fist"):
        if f"/{name}.cur" in spec:
            return name
    return spec
