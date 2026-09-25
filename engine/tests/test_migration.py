"""State-directory migration.

The package was renamed, which moved the default state root. That root holds the
only copy of the files an install replaced, so a migration that fails silently
would strand every rollback a user had. These tests pin the behaviour that
matters: files come forward, nothing in the new root is overwritten, and the old
directory is never deleted.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nvfku.paths import Paths


class MigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.legacy = self.home / ".local/share/dlss5ctl"
        # `discover` is where the default state root is applied, so the test has to
        # go through it rather than construct Paths directly.
        import os
        from unittest import mock

        self._env = mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=False)
        self._env.start()
        self.addCleanup(self._env.stop)
        self.paths = Paths.discover()

    def _seed_legacy(self, name: str = "index.json", body: str = "{}") -> Path:
        target = self.legacy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        return target

    def test_nothing_happens_without_a_legacy_directory(self) -> None:
        self.paths.ensure_state_dir()
        self.assertFalse((self.paths.state_root / ".migrated-from-dlss5ctl").exists())

    def test_files_come_forward(self) -> None:
        (self.legacy / "backups/steam-1/20260101-000000-aaaaaa").mkdir(parents=True)
        (self.legacy / "backups/steam-1/20260101-000000-aaaaaa/manifest.json").write_text("{}")
        (self.legacy / "artwork").mkdir(parents=True)
        (self.legacy / "artwork/1-library.jpg").write_bytes(b"jpg")

        self.paths.ensure_state_dir()

        self.assertTrue(
            (self.paths.state_root / "backups/steam-1/20260101-000000-aaaaaa/manifest.json").is_file()
        )
        self.assertEqual(
            (self.paths.state_root / "artwork/1-library.jpg").read_bytes(), b"jpg"
        )

    def test_the_new_root_wins_a_conflict(self) -> None:
        """A file already present is never overwritten: the old tree is a fallback."""
        self._seed_legacy("scan-cache.json", '{"old": true}')
        self.paths.ensure_state_dir()
        (self.paths.state_root / "scan-cache.json").write_text('{"new": true}')

        # A second call must not clobber it either.
        self.paths.ensure_state_dir()
        self.assertEqual(
            (self.paths.state_root / "scan-cache.json").read_text(), '{"new": true}'
        )

    def test_the_legacy_directory_is_left_alone(self) -> None:
        self._seed_legacy()
        self.paths.ensure_state_dir()
        self.assertTrue(self.legacy.is_dir(), "the old backups must survive the rename")
        self.assertTrue((self.legacy / "index.json").is_file())

    def test_it_runs_once(self) -> None:
        self._seed_legacy("first.json")
        self.paths.ensure_state_dir()
        marker = self.paths.state_root / ".migrated-from-dlss5ctl"
        self.assertTrue(marker.is_file())
        self.assertIn("merged", marker.read_text())

        # A file added to the legacy tree afterwards is not picked up, so a stale
        # directory cannot keep re-injecting old state.
        self._seed_legacy("second.json")
        self.paths.ensure_state_dir()
        self.assertFalse((self.paths.state_root / "second.json").exists())

    def test_an_explicit_state_root_equal_to_the_legacy_one_is_a_no_op(self) -> None:
        paths = Paths(home=self.home, state_root=self.legacy)
        paths.ensure_state_dir()
        self.assertFalse((self.legacy / ".migrated-from-dlss5ctl").exists())


if __name__ == "__main__":
    unittest.main()
