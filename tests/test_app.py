"""Capu and the dummy together: behavior, menu, settings, cursors and hearts.

These run the real program for a moment, with a simulated cursor (the real
mouse is never moved), so Capu and the dummy show up on the screen while
they run.
"""
import ctypes
import time
import unittest
from ctypes import wintypes
from unittest import mock

from tests.support import REAL_FULLSCREEN_CHECK, AppCase, Click, cursor_file, needs_sprites
import dummy
import capu
import platforms
import tray
import ui

STAND = platforms.BORDER          # things stand on a window's top border line, this far below its top

tray.user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
tray.user32.IsWindow.argtypes = [wintypes.HWND]


def _without_key(frame):
    """A frame as shown on screen, with the see-through color made transparent again."""
    rgba = frame.convert("RGBA")
    px = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            if px[x, y][:3] == (255, 0, 254):
                px[x, y] = (0, 0, 0, 0)
    return rgba


@needs_sprites
class Basics(AppCase):
    def test_both_start_alive_on_the_taskbar(self):
        self.assertTrue(self.p.alive and self.d.alive)
        self.assertEqual(self.p.y, 0)
        self.assertEqual(self.d.y, 0)

    def test_health_is_even_two_hits_per_heart(self):
        self.assertEqual(capu.HITS_TO_DIE % 2, 0)
        self.assertEqual(dummy.HITS_TO_DIE % 2, 0)

    def test_capu_dies_on_the_last_hit_and_revives(self):
        self.park_capu()
        self.p.hits = capu.HITS_TO_DIE - 1
        self.p.hit()
        self.assertFalse(self.p.alive)
        self.p.revive()
        self.assertTrue(self.p.alive)
        self.assertEqual(self.p.hits, 0)

    def test_the_dummy_breaks_on_the_last_hit(self):
        self.d.hits = dummy.HITS_TO_DIE - 1
        self.assertTrue(self.d.take_hit())
        self.assertFalse(self.d.alive)


@needs_sprites
class Cursor(AppCase):
    """Capu chasing (or not) the cursor."""

    def cursor_near(self):
        self.cursor[:] = [int(self.p.x + 300), int(self.bottom - 60)]

    def test_it_chases_and_attacks_the_cursor_with_a_heads_up(self):
        self.park_capu(seconds=0.2)
        shown = mock.Mock(wraps=self.p.alert.show)
        self.p.alert.show = shown
        self.cursor_near()
        states = self.watch_states(2.5)
        self.assertIn("chase", states)
        self.assertIn("attack", states)
        self.assertEqual(shown.call_count, 1)           # one "!", not one per swing

    def test_the_heads_up_also_comes_after_a_short_pause(self):
        # It spots the cursor while resting after a landing: the chase still starts with a "!".
        shown = mock.Mock(wraps=self.p.alert.show)
        self.p.alert.show = shown
        self.park_capu(seconds=0.4)
        self.p.on_cursor = False
        self.cursor_near()
        self.watch_states(1.0)
        self.assertGreaterEqual(shown.call_count, 1)

    def test_the_heads_up_is_centered_on_its_head(self):
        """In every pose, facing either way, the "!" is right over the middle of the
        head in the frame on show (measured on the image itself)."""
        from PIL import Image, ImageTk
        self.park_capu()
        for name in ("idle", "run", "dash", "jump", "fall", "attack1", "hurt"):
            for facing in (1, -1):
                with self.subTest(animation=name, facing=facing):
                    self.p.facing = facing
                    self.p.set_anim(name, restart=True)
                    self.p.animate(0)
                    self.p.place()
                    self.p.alert.show(self.p.head_top)
                    self.pump(0.03)
                    shown = ImageTk.getimage(self.p.shown).convert("RGB")   # at screen size
                    frame = shown.resize((shown.width // capu.SCALE, shown.height // capu.SCALE),
                                         Image.NEAREST)
                    head = capu.head_offset(_without_key(frame))
                    if head is None:
                        continue                 # nose hidden (a white flash): it keeps the last spot
                    window_center = self.p.root.winfo_rootx() + self.p.width / 2
                    alert = self.p.alert.window
                    alert_center = alert.winfo_rootx() + alert.winfo_width() / 2
                    self.assertAlmostEqual(alert_center, window_center + head, delta=2)

    def test_calm_mode_ignores_it(self):
        self.app.settings["calm"] = True
        self.park_capu(seconds=0.2)
        self.cursor_near()
        states = self.watch_states(1.5)
        self.assertNotIn("chase", states)
        self.assertNotIn("attack", states)

    def test_it_jumps_and_swings_in_the_air_without_stopping(self):
        self.park_capu(seconds=0.2)
        self.cursor[:] = [int(self.p.x + capu.ATTACK_REACH * 0.6), int(self.bottom - 175)]
        samples = []                                    # the first swing in the air only
        end = time.perf_counter() + 2.0
        while time.perf_counter() < end:
            self.app.root.update()
            if self.p.state == "air_attack":
                samples.append((self.p.frame_index, self.p.y))
            elif samples:
                break
            time.sleep(0.005)
        self.assertTrue(samples, "it never swung in the air")
        self.assertGreaterEqual(samples[0][0], capu.AIR_ATTACK_FIRST_FRAME)
        heights = [y for _, y in samples]
        self.assertLess(heights[-1], heights[0])        # it keeps moving down: no hanging still


@needs_sprites
class Sleeping(AppCase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(capu, "SLEEP_AFTER", 0.4)
        patch.start()
        self.addCleanup(patch.stop)
        self.alert = mock.Mock(wraps=self.p.alert.show)
        self.p.alert.show = self.alert
        self.zzz = mock.Mock()                         # counts the "Z"s, whichever of the two
        for z in self.p.zzz:
            def show(head, drift=0, real=z.show):
                self.zzz(head)
                real(head, drift=drift)
            z.show = show

    def fall_asleep(self):
        lo, hi = self.p.bounds()
        self.p.x = (lo + hi) / 2
        self.p.set_state("idle")
        self.p.idle_left = 100                         # a long, normal rest
        self.cursor[:] = [int(self.p.x + 800), int(self.bottom - 600)]   # far, and still
        self.pump(0.1)
        self.p.last_mouse_move = time.perf_counter() - 1
        return self.pump(3.0, until=lambda: self.p.state == "sleep")

    def test_it_dozes_off_when_the_mouse_is_still(self):
        self.assertTrue(self.fall_asleep())
        self.pump(capu.Z_EVERY + 0.5)
        self.assertEqual(self.p.state, "sleep")
        self.assertGreaterEqual(self.zzz.call_count, 1)

    def test_the_zs_rise_from_its_head_diagonally_one_after_another(self):
        for facing in (1, -1):
            with self.subTest(facing=facing):
                self.fall_asleep()
                self.p.facing = facing
                begin = time.perf_counter()          # Zs from before it turned don't count
                both, starts, ends = False, [], []
                seen = {}
                end = time.perf_counter() + 4.0                 # a few Zs, with margin for a busy PC
                while time.perf_counter() < end:
                    self.app.root.update()
                    rising = [z for z in self.p.zzz if z.job is not None]
                    both = both or len(rising) == 2
                    hx, hy = self.p.head_top()
                    for z in (z for z in rising if z.start >= begin):
                        w = z.window
                        dx = w.winfo_rootx() + w.winfo_width() / 2 - hx
                        gap = hy - (w.winfo_rooty() + w.winfo_height())
                        if seen.get(id(z)) != z.start:       # a new Z: where it starts
                            seen[id(z)] = z.start
                            # On a busy PC it is first seen a little late: take off
                            # how far it has already risen and drifted by then.
                            t = (time.perf_counter() - z.start) / z.seconds
                            starts.append((dx - z.drift * t, gap - z.rise * t))
                        ends.append(dx)
                    time.sleep(0.01)
                self.assertTrue(both, "a new Z should start before the last one is gone")
                for dx, gap in starts:                       # from the middle of its head...
                    self.assertLessEqual(abs(dx), 2)
                    self.assertLessEqual(gap, ui.HEARTS_GAP + 2)
                self.assertGreater(max(facing * dx for dx in ends), capu.Z_DRIFT / 2)     # ...towards where it faces

    def test_the_cursor_coming_near_wakes_it_with_a_heads_up(self):
        self.fall_asleep()
        self.cursor[:] = [int(self.p.x + 300), int(self.bottom - 60)]
        self.assertTrue(self.pump(1.0, until=lambda: self.p.state not in ("doze", "sleep")))
        self.assertEqual(self.alert.call_count, 1)
        states = self.watch_states(1.5)
        self.assertIn("chase", states)
        self.assertEqual(self.alert.call_count, 1)     # no second "!" for the chase

    def creep(self, to_x, y, speed=120):
        """Move the cursor slowly across to `to_x`, at screen height `y`."""
        x, last = float(self.cursor[0]), time.perf_counter()
        direction = 1 if to_x > x else -1
        while (to_x - x) * direction > 0:
            now = time.perf_counter()
            x, last = x + direction * speed * (now - last), now
            self.cursor[:] = [int(x), int(y)]
            self.app.root.update()
            time.sleep(0.005)

    def test_a_cursor_creeping_up_wakes_it_only_when_it_touches_it(self):
        self.fall_asleep()
        y = self.bottom - self.p.body_height / 2
        self.cursor[:] = [int(self.p.x + 900), int(y)]   # out of sight, level with its body
        self.pump(0.2)
        self.creep(self.p.x + 700, y, speed=2000)        # (a quick start, far away, to save time)
        self.pump(0.2)
        self.assertTrue(self.p.asleep())
        self.cursor[0] = int(self.p.x + self.p.body_half + 150)   # in sight... (a jump the test
        self.p.mouse_trail.points.clear()                         # makes: not a fast move)
        self.creep(self.p.x + self.p.body_half + 20, y)  # ...and creeping closer: it sleeps on
        self.assertTrue(self.p.asleep())
        self.assertEqual(self.alert.call_count, 0)
        self.creep(self.p.x, y)                          # onto its body: it wakes up
        self.assertFalse(self.p.asleep())
        self.assertEqual(self.alert.call_count, 1)

    def test_the_mouse_moving_far_away_does_not_wake_it(self):
        self.fall_asleep()
        self.cursor[:] = [int(self.p.x + 900), int(self.bottom - 700)]
        self.pump(0.6)
        self.assertEqual(self.p.state, "sleep")

    def test_the_cursor_on_the_taskbar_next_to_it_wakes_it(self):
        self.fall_asleep()
        self.cursor[:] = [int(self.p.x + 180), int(self.bottom + 25)]   # down on the taskbar
        self.assertTrue(self.pump(1.0, until=lambda: self.p.state not in ("doze", "sleep")))
        self.assertEqual(self.alert.call_count, 1)

    def test_a_click_keeps_it_awake(self):
        lo, hi = self.p.bounds()
        self.p.x = (lo + hi) / 2
        self.p.set_state("idle")
        self.p.idle_left = 100
        self.cursor[:] = [int(self.p.x + 800), int(self.bottom - 600)]   # far, and still
        self.pump(0.1)
        self.p.last_mouse_move = time.perf_counter() - 1
        self.buttons = True                            # a click somewhere, without moving
        self.pump(0.05)
        self.buttons = False
        self.pump(capu.SLEEP_AFTER * 0.8)
        self.assertNotIn(self.p.state, ("doze", "sleep"))
        self.assertTrue(self.pump(2.0, until=lambda: self.p.state == "sleep"))   # later, yes

    def test_it_does_not_doze_off_right_after_being_hit(self):
        lo, hi = self.p.bounds()
        self.p.x = (lo + hi) / 2
        self.cursor[:] = [int(self.p.x + 800), int(self.bottom - 600)]
        self.pump(0.1)
        self.p.last_mouse_move = time.perf_counter() - 5   # the mouse has been still a while...
        self.p.hit()                                   # ...but it was just hit
        states = self.watch_states(capu.SLEEP_AFTER * 0.8)
        self.assertNotIn("doze", states)               # it waits the full time after the hit

    def test_a_hit_wakes_it_with_a_startled_hop_aside(self):
        self.fall_asleep()
        x0 = self.p.x
        self.cursor[:] = [int(self.p.x + 40), int(self.bottom - 40)]   # hit from its right
        hits = self.p.hits
        self.p.hit()
        self.assertEqual(self.p.hits, hits + 1)                      # the hit still counts
        self.assertEqual(self.alert.call_count, 1)                   # "!"
        peak, facings = 0.0, set()
        end = time.perf_counter() + 1.2
        while time.perf_counter() < end:
            self.app.root.update()
            peak = max(peak, self.p.y)
            facings.add(self.p.facing)
            time.sleep(0.005)
        self.assertGreater(peak, 70)                                 # a good hop...
        self.assertLess(peak, 130)                                   # ...but not a big jump
        self.assertLess(self.p.x, x0 - 80)                           # aside, away from the cursor
        self.assertEqual(self.p.y, 0)                                # back on its feet
        self.assertEqual(facings, {1})                               # eyes on the cursor all along

    def test_a_hit_while_awake_is_no_hop(self):
        self.park_capu()
        self.cursor[:] = [int(self.p.x + 40), int(self.bottom - 40)]
        self.p.hit()
        self.assertEqual(self.p.vx, 0)
        self.assertEqual(self.alert.call_count, 0)

    def test_picking_it_up_wakes_it_with_a_heads_up(self):
        self.fall_asleep()
        self.cursor_on_capu()
        self.p.grab()
        self.assertEqual(self.p.state, "held")
        self.assertEqual(self.alert.call_count, 1)

    def test_in_calm_mode_the_cursor_never_wakes_it(self):
        self.app.settings["calm"] = True
        self.fall_asleep()
        for x in range(-200, 200, 8):                  # all over it and around it
            self.cursor[:] = [int(self.p.x + x), int(self.bottom - 40)]
            self.pump(0.02)
        self.cursor[:] = [int(self.p.x + 60), int(self.bottom + 20)]    # the taskbar too
        self.pump(0.3)
        self.assertTrue(self.p.asleep())
        self.assertEqual(self.alert.call_count, 0)
        self.p.hit()                                   # a hit still does
        self.assertFalse(self.p.asleep())

    def rub(self, seconds):
        """Move the cursor back and forth over its body for `seconds`."""
        end = time.perf_counter() + seconds
        step = 0
        while time.perf_counter() < end:
            step += 1
            self.cursor[:] = [int(self.p.x + (step % 10 - 5) * 4), int(self.bottom - 30)]
            self.app.root.update()
            time.sleep(0.02)

    def test_in_calm_mode_rubbing_it_makes_it_look_around_walk_off_and_nap_again(self):
        self.app.settings["calm"] = True
        self.fall_asleep()
        x0 = self.p.x
        head0 = self.p.head_top()[0]                                 # where it is on the screen
        self.rub(capu.NUDGE_SECONDS + 0.3)
        self.assertEqual(self.p.state, "groggy")                     # up, dazed...
        self.cursor[:] = [int(x0 + 10), int(self.bottom - 30)]
        facings, states, heads = set(), [], []
        end = time.perf_counter() + 12.0                             # (looking around, walking off slowly)
        while time.perf_counter() < end and self.p.state != "doze":
            self.app.root.update()
            if self.p.state == "groggy":
                facings.add(self.p.facing)
                heads.append(self.p.head_top()[0])
            if not states or states[-1] != self.p.state:
                states.append(self.p.state)
            time.sleep(0.005)
        self.assertEqual(facings, {1, -1})                           # ...looking one way and the other...
        self.assertLessEqual(max(heads) - min(heads), 2)             # ...without its head jumping about
        self.assertEqual(states, ["groggy", "shuffle", "doze"])      # ...then walks off, and naps
        self.assertGreater(abs(self.p.head_top()[0] - head0), capu.SHUFFLE_DISTANCE * 0.8)
        self.assertEqual(self.alert.call_count, 1)                   # "!" as it wakes up
        self.assertTrue(self.pump(4.0, until=lambda: self.p.state == "sleep"))

    def test_in_calm_mode_a_quick_pass_over_it_does_not_bother_it(self):
        self.app.settings["calm"] = True
        self.fall_asleep()
        for _ in range(3):                                           # a few short passes
            self.rub(capu.NUDGE_SECONDS * 0.3)
            self.cursor[:] = [int(self.p.x + 400), int(self.bottom - 300)]
            self.pump(0.6)
        self.assertTrue(self.p.asleep())
        self.assertEqual(self.alert.call_count, 0)

    def test_a_cursor_left_next_to_it_in_calm_mode_lets_it_sleep(self):
        self.app.settings["calm"] = True
        lo, hi = self.p.bounds()
        self.p.x = (lo + hi) / 2
        self.p.set_state("idle")
        self.p.idle_left = 100
        self.cursor[:] = [int(self.p.x + 200), int(self.bottom - 60)]   # near, and still
        self.pump(0.1)
        self.p.last_mouse_move = time.perf_counter() - 1
        self.assertTrue(self.pump(3.0, until=lambda: self.p.state == "sleep"))
        states = self.watch_states(1.0)
        self.assertEqual(states, ["sleep"])            # it doesn't keep waking up

    def test_not_while_the_mouse_moves(self):
        lo, hi = self.p.bounds()
        self.p.x = (lo + hi) / 2
        self.p.set_state("idle")
        self.p.idle_left = 100
        end = time.perf_counter() + 1.2
        while time.perf_counter() < end:
            self.cursor[:] = [int(self.p.x + 800 + (time.perf_counter() * 50) % 40), int(self.bottom - 600)]
            self.app.root.update()
            time.sleep(0.01)
        self.assertNotIn(self.p.state, ("doze", "sleep"))


@needs_sprites
class Dodging(AppCase):
    def hits_from(self, chance, **throw):
        with mock.patch.object(capu, "EVADE_CHANCE", chance):
            self.park_capu()
            self.throw_dummy(**throw)
            states = self.watch_states(1.6)
        return self.p.hits, "evade" in states

    def test_a_hard_throw_hurts_if_it_does_not_dodge(self):
        self.assertEqual(self.hits_from(0.0, gap=600, vx=2400.0, y=20.0, vy=450.0), (1, False))

    def test_it_jumps_over_a_hard_throw(self):
        self.assertEqual(self.hits_from(1.0, gap=600, vx=2400.0, y=20.0, vy=450.0), (0, True))

    def test_it_dashes_away_from_a_dummy_falling_on_it(self):
        self.assertEqual(self.hits_from(1.0, y=450.0, vy=-600.0), (0, True))

    def test_it_ignores_a_throw_that_falls_short(self):
        self.assertEqual(self.hits_from(1.0, gap=350, vx=700.0, y=20.0, vy=450.0), (0, False))

    def test_it_stays_put_when_a_window_will_catch_the_dummy(self):
        self.park_capu()
        top = int(self.bottom - 250)                     # a window right above him
        self.windows.append((1, (int(self.p.x - 300), top, int(self.p.x + 300), top + 200)))
        self.pump(capu.PLATFORM_SCAN_MS / 1000 + 0.1)
        self.assertEqual(self.hits_from(1.0, y=450.0, vy=-600.0), (0, False))
        self.assertEqual(self.d.platform, 1)             # it stayed up there

    def test_it_waits_until_the_last_moment(self):
        with mock.patch.object(capu, "EVADE_CHANCE", 1.0):
            self.park_capu()
            self.throw_dummy(gap=600, vx=2400.0, y=20.0, vy=450.0)
            lead = None
            end = time.perf_counter() + 1.5
            while time.perf_counter() < end and lead is None:
                threat = self.p.dummy_threat()
                self.app.root.update()
                if self.p.state == "evade":
                    lead = threat[0] if threat else 0
                time.sleep(0.003)
        self.assertIsNotNone(lead)
        self.assertLess(lead, 0.4)                       # not long before the hit

    def test_a_hit_knocks_it_the_way_the_dummy_flew(self):
        self.park_capu()
        x0 = self.p.x
        self.throw_dummy(gap=600, vx=2400.0, y=20.0, vy=450.0)
        self.pump(1.6)
        self.assertEqual(self.p.hits, 1)
        self.assertGreater(self.p.x - x0, 100)


@needs_sprites
class HittingBack(AppCase):
    def swing_at_dummy(self):
        self.park_capu(x=self.d.center_x() + capu.TRAIN_GAP, facing=-1)
        self.p.swings_left = 1
        self.p.set_state("attack", target="dummy")
        self.x0 = self.p.x

    def test_the_dummy_hits_back(self):
        shown = mock.Mock(wraps=self.p.question.show)
        self.p.question.show = shown
        with mock.patch.object(capu, "COUNTER_CHANCE", 1.0):
            self.swing_at_dummy()
            self.pump(1.5)
        self.assertGreaterEqual(self.d.hits, 1)
        self.assertEqual(self.p.hits, 1)
        self.assertGreater(self.p.x, self.x0)            # knocked away from it
        self.assertEqual(shown.call_count, 1)            # the "?"

    def test_not_when_the_setting_is_off(self):
        self.app.settings["dummy_hits_back"] = False
        with mock.patch.object(capu, "COUNTER_CHANCE", 1.0):
            self.swing_at_dummy()
            self.pump(1.5)
        self.assertGreaterEqual(self.d.hits, 1)      # one of its swings lands twice
        self.assertEqual(self.p.hits, 0)

    def test_no_training_when_the_setting_is_off(self):
        self.park_capu(x=self.d.center_x() + 300)
        self.assertTrue(self.p.dummy_in_range())
        self.app.settings["training"] = False
        self.assertFalse(self.p.dummy_in_range())


@needs_sprites
class Impacts(AppCase):
    def test_sparks_go_where_it_is_hit(self):
        wx, wy = self.d.window_pos()
        bx0, by0, bx1, by1 = self.d.body
        left = self.d.hit_frames_at((wx + bx0 + 10, wy + (by0 + by1) / 2))
        right = self.d.hit_frames_at((wx + bx1 - 10, wy + (by0 + by1) / 2))
        self.assertIsNot(left, right)
        self.assertEqual(len(left), len(self.d.hit))
        mirrored = {key[2] for key in self.d.hit_cache}
        self.assertEqual(mirrored, {True, False})        # flipped on the left side

    def test_a_point_off_the_body_is_kept_on_it(self):
        self.d.hit_frames_at((-5000, -5000))
        (x, y, _), = self.d.hit_cache
        bx0, by0, _, _ = (v / dummy.SCALE for v in self.d.body)
        self.assertGreaterEqual(x, round(bx0))
        self.assertGreaterEqual(y, round(by0))

    def test_only_the_latest_hit_animations_are_kept(self):
        wx, wy = self.d.window_pos()
        bx0, by0, _, _ = self.d.body
        with mock.patch.object(dummy, "HIT_CACHE_SIZE", 3):
            for i in range(6):
                self.d.hit_frames_at((wx + bx0 + 8 + i * dummy.SCALE, wy + by0 + 40))
            first = next(iter(self.d.hit_cache))
            self.d.hit_frames_at((wx + bx0 + 8 + 3 * dummy.SCALE, wy + by0 + 40))   # used again: kept
            self.d.hit_frames_at((wx + bx0 + 8 + 9 * dummy.SCALE, wy + by0 + 40))
        self.assertEqual(len(self.d.hit_cache), 3)
        self.assertIn(first, self.d.hit_cache)

    def test_a_slash_still_lands_when_a_late_update_skips_its_frame(self):
        self.park_capu()
        self.p.x = self.p.train_target()
        self.p.face_dummy()
        self.p.set_state("attack", target="dummy")
        self.p.swings_left = 1
        self.p.set_anim("attack1", restart=True)
        slash = capu.SLASH_FRAMES["attack1"][0]
        self.p.frame_index = slash + 1                   # it went from before the slash to after it
        self.p.check_slash("attack1", slash - 1)
        self.assertEqual(self.d.hits, 1)
        self.p.check_slash("attack1", slash + 1)         # the same frame again: no second hit
        self.assertEqual(self.d.hits, 1)

    def test_nothing_is_left_floating_when_capu_is_hidden(self):
        self.park_capu()
        self.p.alert.show(self.p.head_top)
        self.pump(0.1)
        self.assertEqual(self.p.alert.window.state(), "normal")
        self.p.hide()
        self.pump(0.1)
        self.assertEqual(self.p.alert.window.state(), "withdrawn")

    def test_capu_strikes_the_side_facing_him(self):
        from_left = self.d.surface_point(self.bottom - 40, from_left=True)
        from_right = self.d.surface_point(self.bottom - 40, from_left=False)
        self.assertLess(from_left[0], from_right[0])


@needs_sprites
class Hearts(AppCase):
    def test_capu_shows_three_hearts_when_hovered(self):
        self.park_capu()
        self.cursor_on_capu()
        self.assertTrue(self.pump(0.5, until=lambda: self.p.hearts.visible))
        heart_w = len(ui.HEART[0]) + ui.HEART_GAP
        self.assertEqual(self.p.hearts.current.width(),
                         (3 * heart_w - ui.HEART_GAP) * ui.UI_SCALE)

    def test_the_dummy_shows_seven(self):
        self.cursor_on_dummy()
        self.assertTrue(self.pump(0.5, until=lambda: self.d.hearts.visible))
        heart_w = len(ui.HEART[0]) + ui.HEART_GAP
        self.assertEqual(self.d.hearts.current.width(),
                         (7 * heart_w - ui.HEART_GAP) * ui.UI_SCALE)

    def test_not_while_held(self):
        self.park_capu()
        self.cursor_on_capu()
        self.pump(0.3)
        self.p.grab()
        self.pump(0.3)
        self.assertFalse(self.p.hearts.visible)
        self.cursor_on_dummy()
        self.pump(0.3)
        self.d.grab()
        self.pump(0.3)
        self.assertFalse(self.d.hearts.visible)


@needs_sprites
class Cursors(AppCase):
    def test_sword_over_both_fist_while_holding(self):
        self.park_capu()
        for c in (self.p, self.d):
            self.assertEqual(cursor_file(c.label), "sword")
            self.assertEqual(cursor_file(c.hitbox), "sword")
        self.cursor_on_capu()
        self.p.grab()
        self.assertEqual(cursor_file(self.p.label), "fist")
        self.p.cursor_trail.add(*self.cursor)
        self.p.drop()
        self.assertEqual(cursor_file(self.p.label), "sword")
        self.d.grab()
        self.assertEqual(cursor_file(self.d.hitbox), "fist")
        self.d.release(None)
        self.assertEqual(cursor_file(self.d.hitbox), "sword")

    def test_the_arrow_when_there_is_nothing_to_hit(self):
        self.park_capu()
        self.p.hits = capu.HITS_TO_DIE - 1
        self.p.hit()
        self.d.hits = dummy.HITS_TO_DIE - 1
        self.d.take_hit()
        self.pump(0.2)
        self.assertEqual(cursor_file(self.p.label), "")
        self.assertEqual(cursor_file(self.d.label), "")
        self.assertFalse(self.p.hitbox_shown)
        self.p.revive()
        self.d.revive()
        self.pump(0.2)
        self.assertEqual(cursor_file(self.p.label), "sword")
        self.assertTrue(self.p.hitbox_shown)

    def test_capus_hit_zone_turns_with_him(self):
        self.park_capu(facing=1)
        self.pump(0.1)
        self.assertEqual(self.p.hitbox_facing, 1)
        self.p.facing = -1
        self.p.place()
        self.assertEqual(self.p.hitbox_facing, -1)

    def test_a_click_on_the_dummy_hits_it_where_clicked(self):
        wx, wy = self.d.window_pos()
        x, y = wx + self.d.body[0] + 20, wy + self.d.body[1] + 60
        self.d.press(Click(x, y))
        self.d.release(None)
        self.assertEqual(self.d.hits, 1)
        self.assertEqual(len(self.d.hit_cache), 1)


@needs_sprites
class MenuAndSettings(AppCase):
    def open_menu(self):
        e = Click(300, 200)
        self.app.show_menu(e)
        self.pump(0.05)
        return self.app.menu

    def pick(self, label_start):
        menu = self.app.menu
        labels = [label for label, _ in self.labels(menu)]
        row = next(i for i, label in enumerate(labels) if label.startswith(label_start))
        e = Click(0, 0)
        e.y = menu.rows[row][0] * ui.UI_SCALE + 2
        menu.press(e)
        menu.release(e)
        self.pump(0.05)

    def labels(self, menu):
        return self.items[id(menu)]

    def setUp(self):
        super().setUp()
        if not ui.available():
            self.skipTest("the Nanofon font is not in assets/ui")
        # Remember each menu's labels (the menu itself only keeps images).
        self.items = {}
        real = ui.PopupMenu.__init__
        test = self

        def init(menu, master, items, *args, **kwargs):
            real(menu, master, items, *args, **kwargs)
            test.items[id(menu)] = [i for i in items if i]
        patch = mock.patch.object(ui.PopupMenu, "__init__", init)
        patch.start()
        self.addCleanup(patch.stop)

    def test_main_menu(self):
        menu = self.open_menu()
        labels = [label for label, _ in self.labels(menu)]
        self.assertEqual(labels, ["Hide Capu", "Sleep Capu", "Hide dummy", "Settings", "Exit"])

    def test_settings_open_in_place_and_stay_open_after_a_switch(self):
        menu = self.open_menu()
        x, y = menu.x, menu.y
        self.pick("Settings")
        settings = self.app.menu
        self.assertEqual((settings.x, settings.y), (x, y))
        self.assertEqual([label for label, _ in self.labels(settings)][:1], ["Calm mode: off"])
        self.pick("Calm mode")
        self.assertTrue(self.app.settings["calm"])
        self.assertTrue(capu.load_settings()["calm"])              # saved
        self.assertFalse(self.app.menu.closed)                      # still open...
        self.assertEqual(self.labels(self.app.menu)[0][0], "Calm mode: on")   # ...showing the change
        self.pick("Back")
        self.assertEqual(self.labels(self.app.menu)[3][0], "Settings")

    def test_hide_and_show(self):
        self.open_menu()
        self.pick("Hide Capu")
        self.assertTrue(self.p.hidden)
        self.assertFalse(self.p.root.winfo_viewable())
        self.open_menu()
        self.pick("Show Capu")
        self.assertFalse(self.p.hidden)

    def test_sleep_and_wake_from_the_menu(self):
        self.park_capu(seconds=0.2)
        self.app.settings["calm"] = True
        self.cursor_on_capu()                          # the menu is opened on him
        self.open_menu()
        self.pick("Sleep Capu")
        self.assertTrue(self.p.asleep())
        # Moving the cursor away doesn't wake him...
        for step in range(20):
            self.cursor[0] += 6
            self.pump(0.02)
        self.assertTrue(self.p.asleep())
        self.open_menu()
        self.assertIn("Wake Capu", [label for label, _ in self.labels(self.app.menu)])
        self.pick("Wake Capu")
        self.assertFalse(self.p.asleep())

    def test_put_to_sleep_the_cursor_must_leave_before_it_can_wake_him(self):
        self.park_capu(seconds=0.2)
        self.cursor_on_capu()
        self.p.sleep_now()
        self.cursor[0] += 30                           # still near: he sleeps on
        self.pump(0.3)
        self.assertTrue(self.p.asleep())
        self.cursor[:] = [int(self.p.x + 900), int(self.bottom - 700)]   # gone...
        self.pump(0.2)
        self.cursor[:] = [int(self.p.x + 100), int(self.bottom - 40)]    # ...and back
        self.assertTrue(self.pump(1.0, until=lambda: not self.p.asleep()))

    def click_tray_icon(self, button=tray.WM_RBUTTONUP):
        """What Windows sends when the icon is clicked, with the cursor down on the taskbar."""
        self.cursor[:] = [600, self.bottom + 20]
        tray.user32.PostMessageW(self.app.tray.hwnd, tray.CALLBACK_MESSAGE, 1, button)
        return self.pump(1.0, until=lambda: self.app.menu is not None and not self.app.menu.closed)

    def test_the_tray_icon_opens_the_menu_above_the_taskbar(self):
        for button in (tray.WM_RBUTTONUP, tray.WM_LBUTTONUP):
            self.assertTrue(self.click_tray_icon(button))
            menu = self.app.menu
            self.assertEqual([label for label, _ in self.labels(menu)],
                             ["Hide Capu", "Sleep Capu", "Hide dummy", "Settings", "Exit"])
            self.assertLessEqual(menu.y + menu.height, self.bottom)
            menu.close()

    def test_with_the_tray_icon_it_stays_when_nobody_is_left(self):
        self.open_menu()
        self.pick("Hide Capu")
        self.open_menu()
        self.pick("Hide dummy")
        self.assertTrue(self.app.root.winfo_exists())
        self.assertTrue(self.click_tray_icon())              # ...and they can be brought back
        self.pick("Show Capu")
        self.assertTrue(self.p.on_screen())

    def test_without_it_it_closes_when_nobody_is_left(self):
        self.app.tray.remove()
        self.app.tray = None
        self.open_menu()
        self.pick("Hide Capu")
        self.open_menu()
        self.pick("Hide dummy")
        with self.assertRaises(Exception):
            self.app.root.winfo_exists()

    def test_the_tray_icon_goes_away_with_the_program(self):
        hwnd = self.app.tray.hwnd
        self.open_menu()
        self.pick("Exit")
        self.assertIsNone(self.app.tray)
        self.assertFalse(tray.user32.IsWindow(hwnd))

    def test_the_tray_icon_is_drawn_pixel_for_pixel(self):
        images = capu.tray_images(self.p.box)
        self.assertEqual(sorted(images), list(capu.TRAY_SIZES))
        for size, image in images.items():
            self.assertEqual(image.size, (size, size))
            self.assertIsNotNone(image.getbbox())
            alphas = set(image.getchannel("A").tobytes())
            self.assertLessEqual(alphas, {0, 255})            # crisp: nothing half see-through


@needs_sprites
class OnWindows(AppCase):
    """Simulated open windows to stand on (see AppCase), and helpers for them."""

    def setUp(self):
        super().setUp()
        self.cursor[:] = [0, 0]                        # out of its sight
        lo, hi = self.p.bounds()
        self.middle = (lo + hi) / 2

    def add_window(self, hwnd, left, height, right, depth=300, front=False, standable=True):
        """A window whose top is `height` px above the taskbar; it is seen at the next scan.
        Things stand on its top border line: STAND below `height`."""
        top = int(self.bottom - height)
        entry = (hwnd, (int(left), top, int(right), top + depth), standable)
        self.windows.insert(0, entry) if front else self.windows.append(entry)
        self.pump(capu.PLATFORM_SCAN_MS / 1000 + 0.1)

    def move_window(self, hwnd, dx, dy):
        i = next(i for i, w in enumerate(self.windows) if w[0] == hwnd)
        left, top, right, bottom = self.windows[i][1]
        self.windows[i] = (hwnd, (left + dx, top + dy, right + dx, bottom + dy), self.windows[i][2])

    def drop_onto(self, hwnd):
        """Let Capu go above the middle of the window, and wait until he stands on it."""
        left, top, right, _ = next(w[1] for w in self.windows if w[0] == hwnd)
        self.p.x = (left + right) / 2
        self.p.y, self.p.vx, self.p.vy = self.bottom - top + 60, 0.0, 0.0
        self.p.state = "dropped"
        self.assertTrue(self.pump(2.0, until=lambda: self.p.platform == hwnd and self.p.grounded()))
        self.p.set_state("idle", idle_seconds=100)     # and stays there


@needs_sprites
class Windows(OnWindows):
    """Standing on the open windows."""

    def test_dropped_over_a_window_it_lands_on_top(self):
        self.add_window(1, self.middle - 200, 300, self.middle + 200)
        self.drop_onto(1)
        self.assertEqual(self.p.y, 300 - STAND)        # its feet on the window's top border line
        self.assertEqual(self.p.hits, 0)

    def test_it_rides_along_when_the_window_moves(self):
        self.add_window(1, self.middle - 200, 300, self.middle + 200)
        self.drop_onto(1)
        x = self.p.x
        self.move_window(1, 80, -40)                   # dragged right and up
        self.pump(0.1)
        self.assertAlmostEqual(self.p.x, x + 80)
        self.assertEqual(self.p.y, 340 - STAND)
        self.assertEqual(self.p.platform, 1)

    def test_it_falls_unhurt_when_the_window_closes(self):
        self.add_window(1, self.middle - 200, 300, self.middle + 200)
        self.drop_onto(1)
        self.windows.clear()
        states = self.watch_states(1.0)
        self.assertIn("falling", states)
        self.assertEqual((self.p.y, self.p.platform, self.p.hits), (0, None, 0))

    def test_walking_off_the_edge_it_falls_unhurt(self):
        self.add_window(1, self.middle - 200, 300, self.middle + 200)
        self.drop_onto(1)
        self.p.set_state("run")
        self.p.target = self.middle + 400              # past the window's right edge
        states = self.watch_states(4.0)
        self.assertIn("falling", states)
        self.assertEqual((self.p.y, self.p.hits), (0, 0))
        self.assertGreater(self.p.x, self.middle + 200)   # it kept going a little as it fell

    def test_a_window_in_front_takes_the_ground_from_under_it(self):
        self.add_window(1, self.middle - 200, 300, self.middle + 200)
        self.drop_onto(1)
        self.add_window(2, self.middle - 100, 400, self.middle + 300, front=True)   # across its spot
        self.assertTrue(self.pump(1.5, until=lambda: self.p.y == 0))
        self.assertIsNone(self.p.platform)

    def test_a_maximized_window_in_front_takes_it_too(self):
        self.add_window(1, self.middle - 200, 300, self.middle + 200)
        self.drop_onto(1)
        self.add_window(2, 0, 2000, 4000, depth=4000, front=True, standable=False)
        self.assertTrue(self.pump(1.5, until=lambda: self.p.y == 0))
        self.assertEqual(self.p.ledges, [])

    def test_the_dummy_lands_on_a_window_rides_it_and_falls_when_it_goes(self):
        d = self.d
        cx = d.center_x()
        self.add_window(1, cx - 200, 300, cx + 200)
        d.y, d.vx, d.vy, d.state, d.impact_done = 360.0, 0.0, 0.0, "flying", True
        self.assertTrue(self.pump(2.0, until=lambda: d.state == "rest"))
        self.assertEqual((d.platform, d.feet()), (1, 300 - STAND))
        self.assertFalse(d.standing())                 # not down where Capu trains on it
        x = d.x
        self.move_window(1, 60, -30)
        self.pump(0.1)
        self.assertAlmostEqual(d.x, x + 60)
        self.assertEqual(d.feet(), 330 - STAND)
        self.windows.clear()
        self.assertTrue(self.pump(2.0, until=lambda: d.state == "rest" and d.y == 0))
        self.assertTrue(d.standing())
        self.assertEqual(d.hits, 0)

    def test_it_jumps_up_onto_a_window_nearby(self):
        self.add_window(1, self.middle + 100, 250, self.middle + 500)
        with mock.patch.object(capu, "CLIMB_CHANCE", 1.0):
            self.p.x = self.middle
            self.p.set_state("idle")
            self.p.idle_left = 0.05
            self.assertTrue(self.pump(6.0, until=lambda: self.p.platform == 1 and self.p.grounded()))
        self.assertEqual(self.p.y, 250 - STAND)

    def test_a_window_out_of_reach_is_not_climbed(self):
        self.add_window(1, self.middle - 200, capu.CLIMB_HEIGHT + 100, self.middle + 200)
        self.assertEqual(len(self.p.ledges), 1)
        self.assertIsNone(self.p.ledge_to_climb())

    def test_it_sees_the_cursor_from_where_it_stands(self):
        self.add_window(1, self.middle - 300, 300, self.middle + 300)
        self.drop_onto(1)
        self.cursor[:] = [int(self.p.x + 200), int(self.bottom - 300 - 40)]   # just above the window
        self.assertEqual(self.p.sees_mouse(capu.VISION_RANGE), (200, 40 + STAND))

    def test_not_when_the_setting_is_off(self):
        self.app.settings["windows"] = False
        self.add_window(1, self.middle - 200, 300, self.middle + 200)
        self.assertEqual(self.p.ledges, [])
        self.assertEqual(self.app.walls, [])           # nor their sides as walls
        self.p.x, self.p.y, self.p.state = self.middle, 360, "dropped"
        self.assertTrue(self.pump(2.0, until=lambda: self.p.grounded()))
        self.assertEqual((self.p.y, self.p.platform), (0, None))

    # --- Parkour: walls, corners and gaps -------------------------------------------
    def throw(self, x, y, vx):
        self.p.x, self.p.y, self.p.vx, self.p.vy = x, y, vx, 0.0
        self.p.state, self.p.impact_done = "dropped", True

    def climb_now(self, **chances):
        """Make it go up onto a window right away, the way the chances say."""
        self.p.set_state("idle")
        self.p.idle_left = 0.05
        patches = [mock.patch.object(capu, "CLIMB_CHANCE", 1.0)]
        patches += [mock.patch.object(capu, name, value) for name, value in chances.items()]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_thrown_softly_at_the_screen_edge_it_slides_down_and_jumps_off(self):
        lo, hi = self.p.bounds()
        self.throw(hi - 150, 400, 500)
        states = self.watch_states(2.5)
        self.assertIn("wall_slide", states)
        self.assertIn("wall_jump", states)
        self.assertTrue(self.p.grounded())
        self.assertLess(self.p.x, hi - 50)             # jumped back into the screen
        self.assertEqual(self.p.hits, 0)

    def test_thrown_hard_at_the_screen_edge_it_bounces_off(self):
        lo, hi = self.p.bounds()
        self.throw(hi - 30, 200, 1500)
        states = self.watch_states(1.5)
        self.assertNotIn("wall_slide", states)
        self.assertEqual(self.p.facing, -1)            # bounced back

    def test_thrown_softly_at_a_windows_side_it_slides_down_it(self):
        self.add_window(1, self.middle + 200, 500, self.middle + 600, depth=500)
        self.throw(self.middle, 450, 500)
        self.assertTrue(self.pump(3.0, until=lambda: self.p.state == "wall_slide"))
        self.assertAlmostEqual(self.p.x, self.middle + 200 - self.p.body_half)   # its back on the side
        self.assertEqual(self.p.facing, -1)            # back to the wall, facing away from it

    def test_thrown_hard_at_a_windows_side_it_bounces_off_it(self):
        self.add_window(1, self.middle + 200, 500, self.middle + 600, depth=500)
        self.throw(self.middle, 300, 1500)
        states = self.watch_states(1.5)
        self.assertNotIn("wall_slide", states)
        self.assertEqual(self.p.facing, -1)            # bounced back...
        self.assertLess(self.p.x, self.middle + 200)   # ...without going past the side

    def test_it_climbs_onto_a_window_by_its_corner(self):
        self.add_window(1, self.middle + 100, 250, self.middle + 500)
        self.p.x = self.middle
        self.climb_now(CORNER_CHANCE=1.0, PARKOUR_CHANCE=0.0)
        states = []
        def up():
            if not states or states[-1] != self.p.state:
                states.append(self.p.state)
            return self.p.platform == 1 and self.p.state == "idle"
        self.assertTrue(self.pump(8.0, until=up))
        self.assertIn("ledge_hang", states)
        self.assertIn("ledge_climb", states)
        self.assertEqual(self.p.y, 250 - STAND)
        self.assertGreater(self.p.x, self.middle + 100)   # up on the window, by its left corner

    def test_hanging_from_a_corner_a_hit_drops_it_from_where_it_hangs(self):
        self.add_window(1, self.middle + 100, 250, self.middle + 500)
        self.p.x = self.middle
        self.climb_now(CORNER_CHANCE=1.0, PARKOUR_CHANCE=0.0)
        self.assertTrue(self.pump(3.0, until=lambda: self.p.state == "ledge_hang"))
        hanging = self.p.body_box()
        self.cursor[:] = [int(self.p.x), int(self.bottom - 300)]
        self.p.hit()
        self.assertIsNone(self.p.platform)
        self.assertAlmostEqual(self.p.y, hanging[2])   # from its body, below the window's top
        self.assertTrue(self.pump(2.0, until=lambda: self.p.grounded()))
        self.assertEqual(self.p.y, 0)

    def test_it_goes_up_a_gap_wall_to_wall(self):
        # Two tall windows with a gap between them; their tops are out of reach of one jump.
        self.add_window(1, self.middle + 100, 650, self.middle + 500, depth=650)
        self.add_window(2, self.middle - 500, 680, self.middle - 100, depth=680)
        self.p.x = self.middle
        self.climb_now(PARKOUR_CHANCE=1.0)
        states = []
        def up():
            if not states or states[-1] != self.p.state:
                states.append(self.p.state)
            return self.p.platform in (1, 2) and self.p.state == "idle"
        self.assertTrue(self.pump(14.0, until=up), states)
        self.assertIn("wall_jump", states)
        self.assertGreater(self.p.y, capu.CLIMB_HEIGHT)
        self.assertEqual(self.p.hits, 0)

    def test_a_window_too_high_without_a_gap_is_not_climbed(self):
        self.add_window(1, self.middle - 200, capu.CLIMB_HEIGHT + 200, self.middle + 200,
                        depth=capu.CLIMB_HEIGHT + 200)
        self.assertIsNone(self.p.ledge_to_climb())

    def test_breaking_the_dummy_it_strikes_its_victory_pose(self):
        self.p.set_state("celebrate")
        self.assertEqual(self.p.anim, "celebrate")
        self.assertTrue(self.pump(6.0, until=lambda: self.p.state == "idle"))
        self.assertTrue(self.p.grounded())


@needs_sprites
class SittingAndWalking(OnWindows):
    """It wanders walking, and sits on the edges of the windows."""

    def sit_soon(self, **patches):
        """Make it go and sit on an edge of its window when its idle ends (now)."""
        patches = {"SIT_CHANCE": 1.0, "CLIMB_CHANCE": 0.0, "TRAIN_CHANCE": 0.0, **patches}
        for name, value in patches.items():
            p = mock.patch.object(capu, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.p.set_state("idle")
        self.p.idle_left = 0.05

    def hanging_part_on_screen(self):
        """(left, right) on the screen of what hangs below its seat (legs, hem), measured on the image."""
        from PIL import ImageTk
        shown = _without_key(ImageTk.getimage(self.p.shown).convert("RGB"))
        below = shown.crop((0, self.p.ground, shown.width, shown.height)).getbbox()
        x = self.p.root.winfo_rootx()
        return x + below[0], x + below[2]

    def test_on_a_window_it_goes_to_sit_on_an_edge_with_its_legs_dangling_outside(self):
        left, right = self.middle - 120, self.middle + 120
        self.add_window(1, left, 300, right)
        reach = self.p.sit_reach
        # Next to one edge it can only go and sit on the other one (it gets there facing out).
        for x, facing in ((left + reach + 10, 1), (right - reach - 10, -1)):
            with self.subTest(facing=facing):
                self.drop_onto(1)
                self.p.x, self.p.facing = x, -facing
                self.sit_soon()
                walked = []
                def sitting():
                    walked.append(self.p.anim)
                    return self.p.state == "sit" and self.p.anim == "sit"
                self.assertTrue(self.pump(12.0, until=sitting))
                self.assertIn("walk", walked)
                self.assertEqual(self.p.facing, facing)                    # facing out of the window
                self.assertEqual(self.p.platform, 1)
                self.pump(0.1)
                hang_left, hang_right = self.hanging_part_on_screen()
                if facing == 1:
                    self.assertAlmostEqual(hang_left, right, delta=capu.SCALE)   # right past its side
                else:
                    self.assertAlmostEqual(hang_right, left, delta=capu.SCALE)

    def test_sitting_it_gets_up_after_a_while(self):
        self.add_window(1, self.middle - 200, 300, self.middle + 200)
        self.drop_onto(1)
        self.sit_soon(SIT_SECONDS=(0.3, 0.3))
        anims = []
        def up_again():
            if not anims or anims[-1] != self.p.anim:
                anims.append(self.p.anim)
            return "sit" in anims and self.p.state == "idle"
        self.assertTrue(self.pump(16.0, until=up_again))
        self.assertEqual(anims[-3:], ["sit", "stand_up", "idle"])
        self.assertEqual(self.p.platform, 1)

    def test_sitting_it_gets_up_and_goes_for_the_cursor_it_sees(self):
        self.add_window(1, self.middle - 200, 300, self.middle + 200)
        self.drop_onto(1)
        self.sit_soon()
        self.assertTrue(self.pump(12.0, until=lambda: self.p.anim == "sit"))
        self.cursor[:] = [int(self.p.x - 150 * self.p.facing), int(self.bottom - self.p.y - 40)]
        self.assertTrue(self.pump(2.0, until=lambda: self.p.anim == "stand_up"))
        self.assertTrue(self.pump(2.0, until=lambda: self.p.state in ("chase", "attack", "jump")))

    def test_it_does_not_sit_where_a_window_in_front_covers_the_edge(self):
        left = self.middle - 200
        self.add_window(1, left, 300, self.middle + 200)
        self.drop_onto(1)
        self.add_window(2, self.middle + 100, 350, self.middle + 400, front=True)   # over its right end
        self.p.x = self.middle
        self.assertEqual(self.p.sit_spot(), -1)                           # only the left edge
        self.p.x = left + self.p.sit_reach + 10                           # ...and not once it is past it
        self.assertIsNone(self.p.sit_spot())

    def test_the_window_moving_as_it_goes_to_the_edge_it_still_sits_on_it(self):
        left, right = self.middle - 200, self.middle + 200
        self.add_window(1, left, 300, right)
        self.drop_onto(1)
        self.p.x = left + self.p.sit_reach + 10                           # it can only go right
        self.sit_soon()
        self.assertTrue(self.pump(2.0, until=lambda: self.p.state == "to_edge"))
        self.move_window(1, -150, 0)                                       # dragged left meanwhile
        self.assertTrue(self.pump(16.0, until=lambda: self.p.anim == "sit"))
        self.assertAlmostEqual(self.p.x, right - 150 - self.p.sit_reach, delta=1)

    def test_it_wanders_walking(self):
        self.add_window(1, self.middle - 300, 300, self.middle + 300)
        self.drop_onto(1)
        self.p.set_state("run")
        self.p.target = self.middle + 250
        start = self.p.x
        self.pump(1.0)
        self.assertEqual(self.p.anim, "walk")
        self.assertGreater(self.p.x, start)
        self.assertLess(self.p.x - start, capu.WALK_SPEED * 1.2)        # (running would take it twice as far)


@needs_sprites
class LanternLight(AppCase):
    """The glow of its lantern (see light.py)."""

    def lantern_on_screen(self):
        """Where the lantern's glass is in the frame on show, on the screen (measured on the image)."""
        from PIL import Image, ImageTk
        shown = ImageTk.getimage(self.p.shown).convert("RGB")
        frame = shown.resize((shown.width // capu.SCALE, shown.height // capu.SCALE), Image.NEAREST)
        at = capu.lantern_at(_without_key(frame))
        if at is None:
            return None
        return (self.p.root.winfo_rootx() + at[0] * capu.SCALE,
                self.p.root.winfo_rooty() + at[1] * capu.SCALE)

    def test_it_shines_on_its_lantern_facing_either_way(self):
        for facing in (1, -1):
            with self.subTest(facing=facing):
                self.park_capu(facing=facing)
                self.pump(0.15)
                self.assertTrue(self.p.glow.shown)
                x, y, _ = self.p.light_spot
                lx, ly = self.lantern_on_screen()
                self.assertAlmostEqual(x, lx, delta=2)
                self.assertAlmostEqual(y, ly, delta=2)

    def test_its_light_is_in_front_of_it_so_it_lights_it_up_too(self):
        self.park_capu()
        self.pump(0.15)
        user32 = ctypes.windll.user32
        user32.GetWindow.restype = wintypes.HWND
        user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
        capus = ui.top_hwnd(self.p.root)
        below, hwnd = [], self.p.glow.hwnd
        for _ in range(500):                             # the windows under the light, in order
            hwnd = user32.GetWindow(hwnd, 2)             # GW_HWNDNEXT
            if not hwnd:
                break
            below.append(hwnd)
        self.assertIn(capus, below)

    def test_it_shines_brighter_as_it_swings_and_dimmer_as_it_sleeps(self):
        self.park_capu()
        idle = self.p.light_strength()
        self.p.state = "attack"
        swinging = self.p.light_strength()
        self.p.state = "sleep"
        asleep = self.p.light_strength()
        self.assertGreater(swinging, idle)
        self.assertLess(asleep, idle)

    def test_no_light_when_switched_off_or_hidden(self):
        self.park_capu()
        self.pump(0.1)
        self.assertTrue(self.p.glow.shown)
        self.app.settings["light"] = False
        self.pump(0.1)
        self.assertFalse(self.p.glow.shown)
        self.app.settings["light"] = True
        self.pump(0.1)
        self.assertTrue(self.p.glow.shown)
        self.p.hide()
        self.pump(0.1)
        self.assertFalse(self.p.glow.shown)

    def test_no_light_where_no_lantern_shows(self):
        self.park_capu()
        self.p.set_anim("death", restart=True, start=12)    # fading away: no lantern left
        self.p.place()
        self.assertIsNone(self.p.light_spot)
        self.assertFalse(self.p.glow.shown)


@needs_sprites
class DoNotDisturb(AppCase):
    def test_both_hide_while_a_full_screen_app_is_open(self):
        self.fullscreen = True
        self.assertTrue(self.pump(capu.FULLSCREEN_CHECK_MS / 1000 * 3, until=lambda: self.app.away))
        self.pump(0.1)
        self.assertFalse(self.p.root.winfo_viewable())
        self.assertFalse(self.d.window.winfo_viewable())
        self.assertFalse(self.p.hitbox_shown)
        self.fullscreen = False
        self.assertTrue(self.pump(capu.FULLSCREEN_CHECK_MS / 1000 * 3, until=lambda: not self.app.away))
        self.pump(0.1)
        self.assertTrue(self.p.root.winfo_viewable())
        self.assertTrue(self.d.window.winfo_viewable())

    def test_not_when_the_setting_is_off(self):
        self.app.settings["do_not_disturb"] = False
        self.fullscreen = True
        self.pump(capu.FULLSCREEN_CHECK_MS / 1000 + 0.5)
        self.assertFalse(self.app.away)
        self.assertTrue(self.p.root.winfo_viewable())

    def test_switching_it_off_brings_them_back_at_once(self):
        self.fullscreen = True
        self.assertTrue(self.pump(capu.FULLSCREEN_CHECK_MS / 1000 * 3, until=lambda: self.app.away))
        self.app.toggle("do_not_disturb")                    # e.g. from the tray icon's menu
        self.assertFalse(self.app.away)
        self.assertFalse(self.p.away)



class FullScreenCheck(unittest.TestCase):
    def test_it_answers_yes_or_no(self):
        # Whatever is in front right now; the window of this test run doesn't count.
        self.assertIsInstance(REAL_FULLSCREEN_CHECK(), bool)


if __name__ == "__main__":
    unittest.main()
