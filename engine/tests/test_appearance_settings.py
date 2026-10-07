"""Theme and language preferences: stored, bounded, and rejected when wrong.

The language picker was documented as storing its choice for a while and did not —
it wrote to an in-memory notifier, so every launch started at "system". These tests
exist so that claim cannot quietly become false again.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from nvfku import settings as settings_module  # noqa: E402


class SettingsShapeTest(unittest.TestCase):
    def test_the_defaults_follow_the_desktop(self) -> None:
        s = settings_module.Settings()
        self.assertEqual(s.theme, "system")
        self.assertEqual(s.language, "system")

    def test_the_accepted_values_are_declared_next_to_the_fields(self) -> None:
        """A CLI `choices` list and a validator can drift; one tuple cannot."""
        self.assertEqual(settings_module.Settings.THEMES, ("system", "dark", "light"))
        self.assertEqual(settings_module.Settings.LANGUAGES, ("system", "en", "zh"))

    def test_validate_accepts_every_declared_value(self) -> None:
        for theme in settings_module.Settings.THEMES:
            for language in settings_module.Settings.LANGUAGES:
                with self.subTest(theme=theme, language=language):
                    settings_module.Settings(theme=theme, language=language).validate()

    def test_validate_rejects_an_unknown_theme(self) -> None:
        """Not silent coercion: `--theme ligth` must fail, not become `system`.

        A quietly-corrected value is reported by users as "the setting does not
        stay", which is far harder to diagnose than a refusal.
        """
        with self.assertRaises(ValueError) as caught:
            settings_module.Settings(theme="ligth").validate()
        self.assertIn("ligth", str(caught.exception))
        self.assertIn("system", str(caught.exception), "it names the valid values")

    def test_validate_rejects_an_unknown_language(self) -> None:
        with self.assertRaises(ValueError):
            settings_module.Settings(language="fr").validate()

    def test_both_fields_round_trip_through_json(self) -> None:
        original = settings_module.Settings(theme="dark", language="zh")
        restored = settings_module.Settings.from_json(original.to_json())
        self.assertEqual(restored.theme, "dark")
        self.assertEqual(restored.language, "zh")

    def test_a_settings_file_without_the_new_fields_still_loads(self) -> None:
        """An older file predates both fields, and must not break a launch."""
        restored = settings_module.Settings.from_json(
            json.dumps({"python_path": "", "steam_root": "", "verify_upstream": True})
        )
        self.assertEqual(restored.theme, "system")
        self.assertEqual(restored.language, "system")

    def test_a_corrupt_file_falls_back_to_defaults(self) -> None:
        restored = settings_module.Settings.from_json("{not json at all")
        self.assertEqual(restored.theme, "system")


class SettingsPersistenceTest(unittest.TestCase):
    """Round trip through the real file, not just the dataclass."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # `state_root` is the constructor argument, and `home` is separate: the
        # state directory is where settings live, not the user's home.
        self.paths = settings_module.Paths(
            home=Path(self._tmp.name),
            state_root=Path(self._tmp.name) / "state",
        )

    def test_saved_values_come_back(self) -> None:
        s = settings_module.load_settings(self.paths)
        s.theme = "light"
        s.language = "en"
        settings_module.save_settings(self.paths, s)

        again = settings_module.load_settings(self.paths)
        self.assertEqual(again.theme, "light")
        self.assertEqual(again.language, "en")

    def test_the_file_is_readable_json(self) -> None:
        """Deliberate: the settings file is documented as editable by hand."""
        s = settings_module.load_settings(self.paths)
        s.theme = "dark"
        path = settings_module.save_settings(self.paths, s)
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(document["theme"], "dark")


if __name__ == "__main__":
    unittest.main()
