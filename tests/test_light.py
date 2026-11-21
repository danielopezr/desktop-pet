"""The glow of Capu's lantern: its picture, how it blends, and its window (see light.py)."""
import ctypes
import unittest

from PIL import Image

from tests.support import ROOT  # noqa: F401  (puts the program's folder on the path)
import light

NAVY = (44, 56, 92)               # Capu's cloak


class Picture(unittest.TestCase):
    def test_it_is_brightest_in_the_middle_and_fades_out(self):
        image = light.glow_image(16, 4)
        self.assertEqual(image.size, (128, 128))
        along = [sum(image.getpixel((x, 64))[:3]) for x in range(64, 128)]   # light, from the middle out
        self.assertEqual(along, sorted(along, reverse=True))
        self.assertGreater(along[0], 0)
        self.assertEqual(along[-1], 0)
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))              # nothing in the corners

    def test_it_is_drawn_in_squares_as_big_as_the_sprites_pixels(self):
        image = light.glow_image(16, 4)
        for x0, y0 in ((60, 60), (80, 64), (100, 72)):
            block = {image.getpixel((x0 + dx, y0 + dy)) for dx in range(4) for dy in range(4)}
            self.assertEqual(len(block), 1)

    def test_it_adds_more_light_than_it_covers(self):
        r, g, b, a = light.glow_image(16, 4).getpixel((64, 64))
        self.assertGreater(r, a)          # premultiplied color above its alpha: light added

    def test_windows_gets_it_as_blue_green_red_alpha(self):
        image = light.glow_image(2, 1)
        data = light.premultiplied_bgra(image)
        r, g, b, a = image.getpixel((1, 1))
        i = (1 * image.width + 1) * 4
        self.assertEqual(tuple(data[i:i + 4]), (b, g, r, a))


class Blending(unittest.TestCase):
    def test_it_brightens_and_warms_what_is_under_it_near_the_lantern(self):
        glow = light.glow_image(16, 4)
        screen = Image.new("RGB", (128, 128), NAVY)
        light.light_up(screen, glow, 0, 0, 1.0)
        middle, edge = screen.getpixel((64, 64)), screen.getpixel((126, 64))
        self.assertGreater(sum(middle), sum(NAVY) + 100)
        self.assertGreater(middle[0] - NAVY[0], middle[2] - NAVY[2])          # warmer: more red than blue
        self.assertEqual(edge, NAVY)                                        # nothing out of its reach

    def test_weaker_it_brightens_less(self):
        glow = light.glow_image(16, 4)
        full, half = Image.new("RGB", (128, 128), NAVY), Image.new("RGB", (128, 128), NAVY)
        light.light_up(full, glow, 0, 0, 1.0)
        light.light_up(half, glow, 0, 0, 0.5)
        self.assertGreater(sum(full.getpixel((64, 64))), sum(half.getpixel((64, 64))))
        self.assertGreater(sum(half.getpixel((64, 64))), sum(NAVY))


class Window(unittest.TestCase):
    def test_it_shows_moves_and_hides_without_taking_the_mouse(self):
        glow = light.Glow(16, 4)
        self.addCleanup(glow.destroy)
        glow.show(400, 300, 0.8)
        self.assertTrue(ctypes.windll.user32.IsWindowVisible(glow.hwnd))
        self.assertEqual(glow.spot, (400 - 64, 300 - 64, round(255 * 0.8)))
        style = ctypes.windll.user32.GetWindowLongW(glow.hwnd, -20)   # GWL_EXSTYLE
        self.assertTrue(style & light.WS_EX_TRANSPARENT)
        glow.show(450, 320, 0.5)
        self.assertEqual(glow.spot, (450 - 64, 320 - 64, round(255 * 0.5)))
        glow.hide()
        self.assertFalse(ctypes.windll.user32.IsWindowVisible(glow.hwnd))


if __name__ == "__main__":
    unittest.main()
