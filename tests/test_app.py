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
        self.assertEqual(labels, ["Hide Parton", "Hide dummy", "Settings", "Exit"])

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
        self.assertEqual(self.labels(self.app.menu)[2][0], "Settings")

    def test_hide_and_show(self):
        self.open_menu()
        self.pick("Hide Parton")
        self.assertTrue(self.p.hidden)
        self.assertFalse(self.p.root.winfo_viewable())
        self.open_menu()
        self.pick("Show Parton")
        self.assertFalse(self.p.hidden)

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
