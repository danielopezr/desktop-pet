"""The menu, hearts, emotes, cursors and other pieces drawn by ui.py."""
import ctypes
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from tests.support import Click, TkCase
import ui


class HeartStates(unittest.TestCase):
    def test_each_heart_is_two_hits(self):
        self.assertEqual(ui.heart_states(6, 6), ["full", "full", "full"])
        self.assertEqual(ui.heart_states(5, 6), ["full", "full", "half"])
        self.assertEqual(ui.heart_states(4, 6), ["full", "full", "empty"])
        self.assertEqual(ui.heart_states(1, 6), ["half", "empty", "empty"])
        self.assertEqual(ui.heart_states(0, 6), ["empty", "empty", "empty"])

    def test_one_heart_per_two_hits_of_health(self):
        self.assertEqual(len(ui.heart_states(14, 14)), 7)


class HeadCenter(unittest.TestCase):
    def test_it_uses_the_top_rows_only(self):
        mask = Image.new("L", (20, 10))
        for y in range(3):                   # the head: columns 4..7
            for x in range(4, 8):
                mask.putpixel((x, y), 255)
        for y in range(3, 10):               # a long arm lower down, off to the right
            for x in range(4, 20):
                mask.putpixel((x, y), 255)
        self.assertEqual(ui.head_center(mask), 6.0)


class Cursors(TkCase):
    def test_the_drawing_gets_an_outline_and_no_black(self):
        drawing = ui.cursor_drawing(ui.SWORD)
        self.assertEqual(drawing.size, (10, 10))
        colors = {drawing.getpixel((x, y)) for x in range(10) for y in range(10)}
        self.assertIn(ui.CURSOR_OUTLINE, colors)
        self.assertNotIn((0, 0, 0, 255), colors)
        self.assertEqual(drawing.getpixel((1, 1)), ui.CURSOR_PALETTE["b"])   # the tip

    def test_the_cur_file_is_a_cursor_clicking_at_the_tip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sword.cur"
            ui.write_cursor(ui.cursor_drawing(ui.SWORD), path, ui.CURSOR_HOTSPOTS["sword"])
            data = path.read_bytes()
            self.assertEqual(struct.unpack_from("<H", data, 2)[0], 2)                  # a cursor
            self.assertEqual(struct.unpack_from("<HH", data, 10), (4, 4))             # the tip
            if sys.platform == "win32":
                user32 = ctypes.windll.user32
                user32.LoadImageW.restype = ctypes.c_void_p
                self.assertTrue(user32.LoadImageW(None, str(path), 2, 0, 0, 0x10))    # Windows takes it

    def test_cursors_work_from_a_folder_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(ui, "CURSOR_DIR", Path(tmp) / "a folder with spaces"), \
                mock.patch.object(ui, "_cursors", None):
            for name in ("sword", "fist"):
                self.root.config(cursor=ui.cursor(name))       # Tk accepts it
                self.assertIn(f"{name}.cur", str(self.root.cget("cursor")))
            self.root.config(cursor="")

    def test_windows_cursors_stand_in_if_the_files_cannot_be_made(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "not a folder"
            blocker.write_text("")
            with mock.patch.object(ui, "CURSOR_DIR", blocker / "cursors"), \
                    mock.patch.object(ui, "_cursors", None):
                self.assertEqual(ui.cursor("sword"), "hand2")
                self.assertEqual(ui.cursor("fist"), "fleur")


class Hearts(TkCase):
    def test_a_row_of_hearts(self):
        image = ui.Hearts.draw(5, 6)
        w = len(ui.HEART[0])
        self.assertEqual(image.size, (3 * (w + ui.HEART_GAP) - ui.HEART_GAP, len(ui.HEART)))

    def test_a_half_heart_is_half_red(self):
        image = ui.Hearts.draw(1, 2)
        reds = sum(1 for x in range(5) for y in range(5) if image.getpixel((x, y)) == ui.RED)
        grays = sum(1 for x in range(5) for y in range(5) if image.getpixel((x, y)) == ui.GRAY)
        self.assertGreater(reds, 0)
        self.assertGreater(grays, 0)

    def test_show_and_hide(self):
        hearts = ui.Hearts(self.root)
        hearts.show(400, 400, 3, 6)
        self.pump(0.05)
        self.assertTrue(hearts.visible)
        self.assertEqual(hearts.window.winfo_rooty() + hearts.window.winfo_height(), 400 - ui.HEARTS_GAP)
        hearts.hide()
        self.assertFalse(hearts.visible)


class Emotes(TkCase):
    def test_it_floats_up_fades_and_goes(self):
        emote = ui.Emote(self.root, ui.EXCLAMATION, ui.GOLD)
        emote.show(lambda: (400, 400))
        self.pump(0.05)
        y0 = emote.window.winfo_rooty()
        self.pump(ui.EMOTE_SECONDS * 0.8)
        self.assertLess(emote.window.winfo_rooty(), y0)                  # higher up
        self.assertLess(float(emote.window.attributes("-alpha")), 1.0)   # fading
        self.pump(ui.EMOTE_SECONDS, until=lambda: emote.job is None)
        self.assertIsNone(emote.job)
        self.assertFalse(emote.window.winfo_viewable())

    def test_it_can_fade_in(self):
        emote = ui.Emote(self.root, ui.SLEEP_Z, ui.SKY, rise=50, seconds=1.0, fade_in=0.3)
        emote.show(lambda: (400, 400))
        self.pump(0.05)
        early = float(emote.window.attributes("-alpha"))
        self.pump(0.3)
        self.assertLess(early, 0.6)                                       # still appearing
        self.assertAlmostEqual(float(emote.window.attributes("-alpha")), 1.0, delta=0.05)

    def test_it_can_drift_sideways(self):
        emote = ui.Emote(self.root, ui.SLEEP_Z, ui.SKY, rise=50, seconds=0.6)
        emote.show(lambda: (400, 400), drift=40)
        self.pump(0.05)
        x0 = emote.window.winfo_rootx()
        self.pump(0.4)
        self.assertGreater(emote.window.winfo_rootx(), x0 + 15)

    def test_the_drawings(self):
        for drawing in (ui.QUESTION, ui.EXCLAMATION, ui.SLEEP_Z, ui.HEART):
            self.assertEqual(len({len(row) for row in drawing}), 1)   # all rows the same width


@unittest.skipUnless(ui.available(), "the Nanofon font is not in assets/ui")
class Menu(TkCase):
    def open(self, items, x=300, y=200, flip=True):
        chosen = []
        menu = ui.PopupMenu(self.root, items, x, y, chosen.append, flip)
        self.addCleanup(menu.close)
        self.pump(0.05)
        return menu, chosen

    def click(self, menu, row):
        e = Click(0, 0)
        e.y = menu.rows[row][0] * ui.UI_SCALE + 2
        menu.press(e)
        menu.release(e)

    def test_one_row_per_option_and_separators_leave_a_gap(self):
        a, b, c = object(), object(), object()
        menu, _ = self.open([("One", a), ("Two", b), None, ("Three", c)])
        self.assertEqual(len(menu.rows), 3)
        gap_12 = menu.rows[1][0] - menu.rows[0][0]
        gap_23 = menu.rows[2][0] - menu.rows[1][0]
        self.assertGreater(gap_23, gap_12)

    def test_clicking_a_row_picks_it_and_closes(self):
        a, b = object(), object()
        menu, chosen = self.open([("One", a), ("Two", b)])
        self.click(menu, 1)
        self.assertEqual(chosen, [b])
        self.assertTrue(menu.closed)

    def test_pressing_one_row_and_releasing_on_another_picks_nothing(self):
        menu, chosen = self.open([("One", 1), ("Two", 2)])
        press, release = Click(0, 0), Click(0, 0)
        press.y = menu.rows[0][0] * ui.UI_SCALE + 2
        release.y = menu.rows[1][0] * ui.UI_SCALE + 2
        menu.press(press)
        menu.release(release)
        self.assertEqual(chosen, [])
        self.assertFalse(menu.closed)

    def test_near_the_bottom_it_opens_upwards(self):
        _, _, _, bottom = ui.work_area()
        menu, _ = self.open([("One", 1), ("Two", 2)], y=bottom - 5)
        self.assertEqual(menu.y + menu.height, bottom - 5)

    def test_reopening_in_place_does_not_flip(self):
        _, _, _, bottom = ui.work_area()
        menu, _ = self.open([("One", 1), ("Two", 2)], y=bottom - 5, flip=False)
        self.assertEqual(menu.y + menu.height, bottom)              # just moved up to fit

    def test_text_rows_line_up(self):
        self.assertEqual(ui.text_image("Hide").height, ui.text_image("Revive dummy").height)


if __name__ == "__main__":
    unittest.main()
