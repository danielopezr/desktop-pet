"""The tops of the windows, where Capu and the dummy stand: which stretches can be seen."""
import unittest

from tests.support import ROOT  # noqa: F401  (puts the program's folder on the path)
import platforms

AREA = (0, 100, 1920, 1000)       # left, highest top, right, lowest top
B = platforms.BORDER              # feet go on the window's top border line


class Ledges(unittest.TestCase):
    def test_a_window_alone_gives_its_whole_top(self):
        self.assertEqual(platforms.ledges([(1, (200, 400, 800, 900), True)], AREA, 100),
                         [(1, 200, 800, 400 + B)])

    def test_a_window_in_front_covers_the_edge_behind_it(self):
        front = (2, (400, 300, 600, 700), True)  # across the back one's top (row 400)
        back = (1, (200, 400, 800, 900), True)
        self.assertEqual(platforms.ledges([front, back], AREA, 100),
                         [(2, 400, 600, 300 + B), (1, 200, 400, 400 + B), (1, 600, 800, 400 + B)])

    def test_a_maximized_window_in_front_covers_everything_behind_it(self):
        front = (2, (0, 0, 1920, 1000), False)   # can't be stood on, but it covers
        back = (1, (200, 400, 800, 900), True)
        self.assertEqual(platforms.ledges([front, back], AREA, 100), [])

    def test_a_window_behind_does_not_cover_one_in_front(self):
        front = (1, (200, 400, 800, 900), True)
        back = (2, (400, 300, 600, 700), True)
        self.assertEqual(platforms.ledges([front, back], AREA, 100),
                         [(1, 200, 800, 400 + B), (2, 400, 600, 300 + B)])

    def test_a_window_just_below_an_edge_does_not_cover_it(self):
        front = (2, (0, 100, 1920, 400), True)   # ends right where the other one starts
        back = (1, (200, 400, 800, 900), True)
        self.assertIn((1, 200, 800, 400 + B), platforms.ledges([front, back], AREA, 100))

    def test_stretches_are_cut_to_the_screen_and_short_ones_dropped(self):
        windows = [(1, (1800, 400, 2600, 900), True),  # mostly on another monitor
                   (2, (-500, 500, 50, 900), True)]    # only 50 px on this one
        self.assertEqual(platforms.ledges(windows, AREA, 100), [(1, 1800, 1920, 400 + B)])

    def test_only_tops_inside_the_area(self):
        windows = [(1, (200, 50, 800, 900), True),     # above the top of the screen's work area
                   (2, (200, 1000, 800, 1200), True)]  # down at the taskbar
        self.assertEqual(platforms.ledges(windows, AREA, 100), [])


class Walls(unittest.TestCase):
    def test_a_window_alone_gives_both_its_sides(self):
        self.assertEqual(platforms.walls([(1, (200, 400, 800, 900), True)], AREA),
                         [(1, 200, 400, 900, -1), (1, 800, 400, 900, 1)])

    def test_a_window_in_front_covers_the_side_behind_it(self):
        front = (2, (100, 500, 300, 700), True)  # across the back one's left side (column 200)
        back = (1, (200, 400, 800, 900), True)
        self.assertEqual([w for w in platforms.walls([front, back], AREA) if w[0] == 1],
                         [(1, 200, 400, 500, -1), (1, 200, 700, 900, -1), (1, 800, 400, 900, 1)])

    def test_windows_that_cant_be_stood_on_are_no_walls_but_cover(self):
        front = (2, (0, 0, 1920, 1000), False)   # maximized: it covers everything behind it
        back = (1, (200, 400, 800, 900), True)
        self.assertEqual(platforms.walls([front, back], AREA), [])

    def test_sides_are_cut_to_the_area(self):
        windows = [(1, (200, 50, 800, 1200), True),     # taller than the work area
                   (2, (1800, 400, 2600, 900), True)]   # its right side on another monitor
        self.assertEqual(platforms.walls(windows, AREA),
                         [(1, 200, 100, 1000, -1), (1, 800, 100, 1000, 1), (2, 1800, 400, 900, -1)])


class Landing(unittest.TestCase):
    LEDGES = [(500, 100, 300, 2), (300, 200, 600, 1)]   # (height, left, right, window), highest first

    def test_it_lands_on_the_first_top_it_comes_down_onto(self):
        self.assertEqual(platforms.landing(self.LEDGES, 250, 520, 480), (500, 2))
        self.assertEqual(platforms.landing(self.LEDGES, 250, 480, 290), (300, 1))

    def test_not_beside_it_and_not_before_reaching_it(self):
        self.assertIsNone(platforms.landing(self.LEDGES, 700, 480, 290))
        self.assertIsNone(platforms.landing(self.LEDGES, 250, 480, 320))

    def test_the_taskbar_is_always_there(self):
        self.assertEqual(platforms.landing(self.LEDGES, 700, 100, -5), (0.0, None))

    def test_standing_on_a_window_needs_its_top_under_it(self):
        self.assertTrue(platforms.stands_on(self.LEDGES, 1, 400, 300))
        self.assertFalse(platforms.stands_on(self.LEDGES, 1, 650, 300))   # off its edge
        self.assertFalse(platforms.stands_on(self.LEDGES, 1, 400, 340))   # it has moved


if __name__ == "__main__":
    unittest.main()
