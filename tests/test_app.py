"""Parton and the dummy together: behavior, menu, settings, cursors and hearts.

These run the real program for a moment, with a simulated cursor (the real
mouse is never moved), so Parton and the dummy show up on the screen while
they run.
"""
import time
import unittest
from unittest import mock

from tests.support import REAL_FULLSCREEN_CHECK, AppCase, Click, cursor_file, needs_sprites
import dummy
import parton
import ui


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
        self.assertEqual(parton.HITS_TO_DIE % 2, 0)
        self.assertEqual(dummy.HITS_TO_DIE % 2, 0)

    def test_parton_dies_on_the_last_hit_and_revives(self):
        self.park_parton()
        self.p.hits = parton.HITS_TO_DIE - 1
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
    """Parton chasing (or not) the cursor."""

    def cursor_near(self):
        self.cursor[:] = [int(self.p.x + 300), int(self.bottom - 60)]

    def test_it_chases_and_attacks_the_cursor_with_a_heads_up(self):
        self.park_parton(seconds=0.2)
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
        self.park_parton(seconds=0.4)
        self.p.on_cursor = False
        self.cursor_near()
        self.watch_states(1.0)
        self.assertGreaterEqual(shown.call_count, 1)

    def test_the_heads_up_is_centered_on_its_head(self):
        """In every pose, facing either way, the "!" is right over the middle of the
        head in the frame on show (measured on the image itself, axe left out)."""
        from PIL import Image, ImageTk
        self.park_parton()
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
                    frame = shown.resize((shown.width // parton.SCALE, shown.height // parton.SCALE),
                                         Image.NEAREST)
                    head = parton.head_offset(_without_key(frame))
                    if head is None:
                        continue                 # horns hidden (a white flash): it keeps the last spot
                    window_center = self.p.root.winfo_rootx() + self.p.width / 2
                    alert = self.p.alert.window
                    alert_center = alert.winfo_rootx() + alert.winfo_width() / 2
                    self.assertAlmostEqual(alert_center, window_center + head, delta=2)

    def test_calm_mode_ignores_it(self):
        self.app.settings["calm"] = True
        self.park_parton(seconds=0.2)
        self.cursor_near()
        states = self.watch_states(1.5)
        self.assertNotIn("chase", states)
        self.assertNotIn("attack", states)

    def test_it_jumps_and_swings_in_the_air_without_stopping(self):
        self.park_parton(seconds=0.2)
        self.cursor[:] = [int(self.p.x + parton.ATTACK_REACH * 0.6), int(self.bottom - 175)]
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
        self.assertGreaterEqual(samples[0][0], parton.AIR_ATTACK_FIRST_FRAME)
        heights = [y for _, y in samples]
        self.assertLess(heights[-1], heights[0])        # it keeps moving down: no hanging still


@needs_sprites
class Sleeping(AppCase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(parton, "SLEEP_AFTER", 0.4)
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
        self.pump(parton.Z_EVERY + 0.5)
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
                            starts.append((dx, gap))
                        ends.append(dx)
                    time.sleep(0.01)
                self.assertTrue(both, "a new Z should start before the last one is gone")
                for dx, gap in starts:                       # from the middle of its head...
                    self.assertLessEqual(abs(dx), 2)
                    self.assertLessEqual(gap, ui.HEARTS_GAP + 2)
                self.assertGreater(max(facing * dx for dx in ends), parton.Z_DRIFT / 2)   # ...towards where it faces

    def test_the_cursor_coming_near_wakes_it_with_a_heads_up(self):
        self.fall_asleep()
        self.cursor[:] = [int(self.p.x + 300), int(self.bottom - 60)]
        self.assertTrue(self.pump(1.0, until=lambda: self.p.state not in ("doze", "sleep")))
        self.assertEqual(self.alert.call_count, 1)
        states = self.watch_states(1.5)
        self.assertIn("chase", states)
        self.assertEqual(self.alert.call_count, 1)     # no second "!" for the chase

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
        self.pump(parton.SLEEP_AFTER * 0.8)
        self.assertNotIn(self.p.state, ("doze", "sleep"))
        self.assertTrue(self.pump(2.0, until=lambda: self.p.state == "sleep"))   # later, yes

    def test_it_does_not_doze_off_right_after_being_hit(self):
        lo, hi = self.p.bounds()
        self.p.x = (lo + hi) / 2
        self.cursor[:] = [int(self.p.x + 800), int(self.bottom - 600)]
        self.pump(0.1)
        self.p.last_mouse_move = time.perf_counter() - 5   # the mouse has been still a while...
        self.p.hit()                                   # ...but it was just hit
        states = self.watch_states(parton.SLEEP_AFTER * 0.8)
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
        self.park_parton()
        self.cursor[:] = [int(self.p.x + 40), int(self.bottom - 40)]
        self.p.hit()
        self.assertEqual(self.p.vx, 0)
        self.assertEqual(self.alert.call_count, 0)

    def test_picking_it_up_wakes_it_with_a_heads_up(self):
        self.fall_asleep()
        self.cursor_on_parton()
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
        self.rub(parton.NUDGE_SECONDS + 0.3)
        self.assertEqual(self.p.state, "groggy")                     # up, dazed...
        self.cursor[:] = [int(x0 + 10), int(self.bottom - 30)]
        facings, states, heads = set(), [], []
        end = time.perf_counter() + 5.0
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
        self.assertGreater(abs(self.p.head_top()[0] - head0), parton.SHUFFLE_DISTANCE * 0.8)
        self.assertEqual(self.alert.call_count, 1)                   # "!" as it wakes up
        self.assertTrue(self.pump(1.5, until=lambda: self.p.state == "sleep"))

    def test_in_calm_mode_a_quick_pass_over_it_does_not_bother_it(self):
        self.app.settings["calm"] = True
        self.fall_asleep()
        for _ in range(3):                                           # a few short passes
            self.rub(parton.NUDGE_SECONDS * 0.3)
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
        with mock.patch.object(parton, "EVADE_CHANCE", chance):
            self.park_parton()
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

    def test_it_waits_until_the_last_moment(self):
        with mock.patch.object(parton, "EVADE_CHANCE", 1.0):
            self.park_parton()
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
        self.park_parton()
        x0 = self.p.x
        self.throw_dummy(gap=600, vx=2400.0, y=20.0, vy=450.0)
        self.pump(1.6)
        self.assertEqual(self.p.hits, 1)
        self.assertGreater(self.p.x - x0, 100)


@needs_sprites
class HittingBack(AppCase):
    def swing_at_dummy(self):
        self.park_parton(x=self.d.center_x() + parton.TRAIN_GAP, facing=-1)
        self.p.swings_left = 1
        self.p.set_state("attack", target="dummy")
        self.x0 = self.p.x

    def test_the_dummy_hits_back(self):
        shown = mock.Mock(wraps=self.p.question.show)
        self.p.question.show = shown
        with mock.patch.object(parton, "COUNTER_CHANCE", 1.0):
            self.swing_at_dummy()
            self.pump(1.5)
        self.assertGreaterEqual(self.d.hits, 1)
        self.assertEqual(self.p.hits, 1)
        self.assertGreater(self.p.x, self.x0)            # knocked away from it
        self.assertEqual(shown.call_count, 1)            # the "?"

    def test_not_when_the_setting_is_off(self):
        self.app.settings["dummy_hits_back"] = False
        with mock.patch.object(parton, "COUNTER_CHANCE", 1.0):
            self.swing_at_dummy()
            self.pump(1.5)
        self.assertGreaterEqual(self.d.hits, 1)      # one of its swings lands twice
        self.assertEqual(self.p.hits, 0)

    def test_no_training_when_the_setting_is_off(self):
        self.park_parton(x=self.d.center_x() + 300)
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

    def test_parton_strikes_the_side_facing_him(self):
        from_left = self.d.surface_point(self.bottom - 40, from_left=True)
        from_right = self.d.surface_point(self.bottom - 40, from_left=False)
        self.assertLess(from_left[0], from_right[0])


@needs_sprites
class Hearts(AppCase):
    def test_parton_shows_three_hearts_when_hovered(self):
        self.park_parton()
        self.cursor_on_parton()
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
        self.park_parton()
        self.cursor_on_parton()
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
        self.park_parton()
        for c in (self.p, self.d):
            self.assertEqual(cursor_file(c.label), "sword")
            self.assertEqual(cursor_file(c.hitbox), "sword")
        self.cursor_on_parton()
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
        self.park_parton()
        self.p.hits = parton.HITS_TO_DIE - 1
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

    def test_partons_hit_zone_turns_with_him(self):
        self.park_parton(facing=1)
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
        self.assertEqual(labels, ["Hide Parton", "Sleep Parton", "Hide dummy", "Settings", "Exit"])

    def test_settings_open_in_place_and_stay_open_after_a_switch(self):
        menu = self.open_menu()
        x, y = menu.x, menu.y
        self.pick("Settings")
        settings = self.app.menu
        self.assertEqual((settings.x, settings.y), (x, y))
        self.assertEqual([label for label, _ in self.labels(settings)][:1], ["Calm mode: off"])
        self.pick("Calm mode")
        self.assertTrue(self.app.settings["calm"])
        self.assertTrue(parton.load_settings()["calm"])            # saved
        self.assertFalse(self.app.menu.closed)                      # still open...
        self.assertEqual(self.labels(self.app.menu)[0][0], "Calm mode: on")   # ...showing the change
        self.pick("Back")
        self.assertEqual(self.labels(self.app.menu)[3][0], "Settings")

    def test_hide_and_show(self):
        self.open_menu()
        self.pick("Hide Parton")
        self.assertTrue(self.p.hidden)
        self.assertFalse(self.p.root.winfo_viewable())
        self.open_menu()
        self.pick("Show Parton")
        self.assertFalse(self.p.hidden)

    def test_sleep_and_wake_from_the_menu(self):
        self.park_parton(seconds=0.2)
        self.app.settings["calm"] = True
        self.cursor_on_parton()                        # the menu is opened on him
        self.open_menu()
        self.pick("Sleep Parton")
        self.assertTrue(self.p.asleep())
        # Moving the cursor away doesn't wake him...
        for step in range(20):
            self.cursor[0] += 6
            self.pump(0.02)
        self.assertTrue(self.p.asleep())
        self.open_menu()
        self.assertIn("Wake Parton", [label for label, _ in self.labels(self.app.menu)])
        self.pick("Wake Parton")
        self.assertFalse(self.p.asleep())

    def test_put_to_sleep_the_cursor_must_leave_before_it_can_wake_him(self):
        self.park_parton(seconds=0.2)
        self.cursor_on_parton()
        self.p.sleep_now()
        self.cursor[0] += 30                           # still near: he sleeps on
        self.pump(0.3)
        self.assertTrue(self.p.asleep())
        self.cursor[:] = [int(self.p.x + 900), int(self.bottom - 700)]   # gone...
        self.pump(0.2)
        self.cursor[:] = [int(self.p.x + 100), int(self.bottom - 40)]    # ...and back
        self.assertTrue(self.pump(1.0, until=lambda: not self.p.asleep()))

    def test_it_closes_when_nobody_is_left(self):
        self.open_menu()
        self.pick("Hide Parton")
        self.open_menu()
        self.pick("Hide dummy")
        with self.assertRaises(Exception):
            self.app.root.winfo_exists()


@needs_sprites
class DoNotDisturb(AppCase):
    def test_both_hide_while_a_full_screen_app_is_open(self):
        self.fullscreen = True
        self.pump(parton.FULLSCREEN_CHECK_MS / 1000 + 0.5, until=lambda: self.app.away)
        self.pump(0.1)
        self.assertFalse(self.p.root.winfo_viewable())
        self.assertFalse(self.d.window.winfo_viewable())
        self.assertFalse(self.p.hitbox_shown)
        self.fullscreen = False
        self.pump(parton.FULLSCREEN_CHECK_MS / 1000 + 0.5, until=lambda: not self.app.away)
        self.pump(0.1)
        self.assertTrue(self.p.root.winfo_viewable())
        self.assertTrue(self.d.window.winfo_viewable())

    def test_not_when_the_setting_is_off(self):
        self.app.settings["do_not_disturb"] = False
        self.fullscreen = True
        self.pump(parton.FULLSCREEN_CHECK_MS / 1000 + 0.5)
        self.assertFalse(self.app.away)
        self.assertTrue(self.p.root.winfo_viewable())



class FullScreenCheck(unittest.TestCase):
    def test_it_answers_yes_or_no(self):
        # Whatever is in front right now; the window of this test run doesn't count.
        self.assertIsInstance(REAL_FULLSCREEN_CHECK(), bool)


if __name__ == "__main__":
    unittest.main()
