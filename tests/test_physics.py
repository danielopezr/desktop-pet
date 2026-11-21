"""Throwing, falling and click-or-drag rules shared by Capu and the dummy."""
import unittest
from unittest import mock

from tests import support  # noqa: F401  (puts the project on the path)
import physics
from physics import (AIR_DRAG_THRESHOLD, DRAG_THRESHOLD, GRAVITY, HOLD_SECONDS, THROW_FACTOR,
                     THROW_MAX_SPEED, WALL_BOUNCE, CursorTrail, fly_step, is_drag, throw_velocity)


class FlyStep(unittest.TestCase):
    def step(self, x=500.0, vx=0.0, y=100.0, vy=0.0, dt=0.016, weight=1.0):
        return fly_step(x, vx, y, vy, dt, 0.0, 1000.0, 800.0, weight)

    def test_gravity_pulls_it_down(self):
        _, _, y, vy = self.step(vy=0.0)
        self.assertLess(vy, 0)
        self.assertLess(y, 100)
        self.assertAlmostEqual(vy, -GRAVITY * 0.016)

    def test_it_lands_and_stops_falling(self):
        _, _, y, vy = self.step(y=1.0, vy=-500.0)
        self.assertEqual((y, vy), (0.0, 0.0))

    def test_air_drag_slows_it_sideways(self):
        _, vx, _, _ = self.step(vx=1000.0)
        self.assertLess(vx, 1000.0)
        self.assertGreater(vx, 0)

    def test_it_bounces_off_the_side_edges(self):
        x, vx, _, _ = self.step(x=995.0, vx=1000.0)
        self.assertEqual(x, 1000.0)
        self.assertLess(vx, 0)
        self.assertLess(abs(vx), 1000.0 * WALL_BOUNCE + 1)

    def test_a_heavier_body_bounces_less(self):
        _, light, _, _ = self.step(x=995.0, vx=1000.0)
        _, heavy, _, _ = self.step(x=995.0, vx=1000.0, weight=2.0)
        self.assertLess(abs(heavy), abs(light))

    def test_it_bounces_off_the_top_of_the_screen(self):
        _, _, y, vy = self.step(y=900.0, vy=800.0)
        self.assertLessEqual(y, 900.0)
        self.assertLess(vy, 0)


class ThrowVelocity(unittest.TestCase):
    def test_a_slow_throw_keeps_the_base_share(self):
        vx, vy = throw_velocity(100.0, 0.0)
        self.assertAlmostEqual(vx, 100.0 * THROW_FACTOR)
        self.assertEqual(vy, 0)

    def test_screen_y_is_flipped(self):
        _, vy = throw_velocity(0.0, -100.0)      # cursor moving up the screen
        self.assertGreater(vy, 0)                # thrown upwards

    def test_flicks_keep_more_of_their_speed(self):
        slow, _ = throw_velocity(1000.0, 0.0)
        fast, _ = throw_velocity(2900.0, 0.0)
        self.assertGreater(fast / 2900.0, slow / 1000.0)

    def test_it_is_capped(self):
        vx, vy = throw_velocity(20000.0, 0.0)
        self.assertAlmostEqual((vx * vx + vy * vy) ** 0.5, THROW_MAX_SPEED)

    def test_a_heavier_body_flies_slower(self):
        light, _ = throw_velocity(1000.0, 0.0)
        heavy, _ = throw_velocity(1000.0, 0.0, weight=2.0)
        self.assertAlmostEqual(heavy, light / 2)


class ClickOrDrag(unittest.TestCase):
    def drag(self, cursor, window=(100, 100), held=0.0, airborne=False):
        now = 1000.0
        with mock.patch.object(physics.time, "perf_counter", return_value=now + held):
            return is_drag((now, 110, 110), cursor, window, (10, 10), airborne)

    def test_a_still_click_is_a_hit(self):
        self.assertFalse(self.drag((110, 110)))

    def test_moving_the_mouse_is_a_drag(self):
        self.assertTrue(self.drag((110 + DRAG_THRESHOLD + 1, 110)))

    def test_following_it_while_it_moves_is_still_a_click(self):
        # The cursor moved on the screen, but so did the character under it.
        self.assertFalse(self.drag((140, 110), window=(130, 100)))

    def test_holding_the_button_is_a_drag(self):
        self.assertTrue(self.drag((110, 110), held=HOLD_SECONDS))

    def test_in_the_air_it_takes_a_bigger_move(self):
        move = (110 + DRAG_THRESHOLD + 1, 110)
        self.assertFalse(self.drag(move, airborne=True))
        self.assertTrue(self.drag((110 + AIR_DRAG_THRESHOLD + 1, 110), airborne=True))


class Trail(unittest.TestCase):
    def test_speed_over_the_last_moments(self):
        trail = CursorTrail()
        clock = iter([1.00, 1.05, 1.05])
        with mock.patch.object(physics.time, "perf_counter", side_effect=lambda: next(clock)):
            trail.add(0, 0)
            trail.add(50, -25)
            vx, vy = trail.speed()
        self.assertAlmostEqual(vx, 1000.0)
        self.assertAlmostEqual(vy, -500.0)

    def test_no_speed_without_movement(self):
        self.assertEqual(CursorTrail().speed(), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
