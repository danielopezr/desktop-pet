"""Saving and loading the menu settings."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import support  # noqa: F401
import parton


class Settings(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.file = Path(tmp.name) / "Parton" / "settings.json"
        patch = mock.patch.object(parton, "SETTINGS_FILE", self.file)
        patch.start()
        self.addCleanup(patch.stop)

    def test_defaults_when_there_is_no_file(self):
        self.assertEqual(parton.load_settings(), parton.DEFAULT_SETTINGS)

    def test_save_and_load_back(self):
        settings = dict(parton.DEFAULT_SETTINGS, calm=True, training=False)
        parton.save_settings(settings)
        self.assertTrue(self.file.exists())
        self.assertEqual(parton.load_settings(), settings)

    def test_missing_keys_get_their_defaults(self):
        self.file.parent.mkdir(parents=True)
        self.file.write_text(json.dumps({"calm": True}), encoding="utf-8")
        loaded = parton.load_settings()
        self.assertTrue(loaded["calm"])
        self.assertEqual(loaded["do_not_disturb"], parton.DEFAULT_SETTINGS["do_not_disturb"])

    def test_unknown_keys_are_ignored(self):
        self.file.parent.mkdir(parents=True)
        self.file.write_text(json.dumps({"calm": True, "volume": 11}), encoding="utf-8")
        self.assertNotIn("volume", parton.load_settings())

    def test_a_broken_file_gives_the_defaults(self):
        self.file.parent.mkdir(parents=True)
        self.file.write_text("{not json", encoding="utf-8")
        self.assertEqual(parton.load_settings(), parton.DEFAULT_SETTINGS)

    def test_every_setting_has_a_menu_label(self):
        self.assertEqual(set(parton.SETTING_LABELS), set(parton.DEFAULT_SETTINGS))


if __name__ == "__main__":
    unittest.main()
