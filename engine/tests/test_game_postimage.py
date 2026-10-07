"""Game-file rollback safety via the public journal/CLI rollback seam."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nvfku.journal import FileJournal, load_journal, rollback_journal
from nvfku.paths import Paths


class GamePostImageTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.paths = Paths(home=self.root, state_root=self.root / "state")
        self.game = self.root / "fake-game"
        self.game.mkdir()
        self.source = self.root / "source.dll"
        self.source.write_bytes(b"INSTALLED")
        self.journal = FileJournal(self.paths, self.game, "a1")

    def test_replaced_game_file_edit_is_preserved_until_retry(self) -> None:
        target = self.game / "dxgi.dll"
        target.write_bytes(b"ORIGINAL")
        self.journal.install_file(self.source, target)
        self.journal.finish()
        target.write_bytes(b"USER EDIT")

        report = rollback_journal(self.paths, self.journal.journal_id)
        self.assertFalse(report.ok)
        self.assertEqual(target.read_bytes(), b"USER EDIT")
        self.assertFalse(load_journal(self.paths, self.journal.journal_id).rolled_back)

        target.write_bytes(b"INSTALLED")
        retry = rollback_journal(self.paths, self.journal.journal_id)
        self.assertTrue(retry.ok, retry.failed)
        self.assertEqual(target.read_bytes(), b"ORIGINAL")
        self.assertTrue(load_journal(self.paths, self.journal.journal_id).rolled_back)

    def test_generated_game_file_edit_is_preserved_until_retry(self) -> None:
        target = self.game / "bridge.cfg"
        target.write_text("original\n")
        self.journal.write_text(target, "installed\n")
        self.journal.finish()
        target.write_text("user edit\n")

        report = rollback_journal(self.paths, self.journal.journal_id)
        self.assertFalse(report.ok)
        self.assertEqual(target.read_text(), "user edit\n")
        self.assertFalse(load_journal(self.paths, self.journal.journal_id).rolled_back)

        target.write_text("installed\n")
        retry = rollback_journal(self.paths, self.journal.journal_id)
        self.assertTrue(retry.ok, retry.failed)
        self.assertEqual(target.read_text(), "original\n")

    def test_deleted_game_file_recreated_by_user_is_preserved_until_retry(self) -> None:
        target = self.game / "old.dll"
        target.write_bytes(b"ORIGINAL")
        self.journal.remove(target)
        self.journal.finish()
        target.write_bytes(b"USER RECREATED")

        report = rollback_journal(self.paths, self.journal.journal_id)
        self.assertFalse(report.ok)
        self.assertEqual(target.read_bytes(), b"USER RECREATED")
        self.assertFalse(load_journal(self.paths, self.journal.journal_id).rolled_back)

        target.unlink()
        retry = rollback_journal(self.paths, self.journal.journal_id)
        self.assertTrue(retry.ok, retry.failed)
        self.assertEqual(target.read_bytes(), b"ORIGINAL")

    def test_created_game_file_edit_is_not_deleted_and_retry_can_finish(self) -> None:
        target = self.game / "new.dll"
        self.journal.install_file(self.source, target)
        self.journal.finish()
        target.write_bytes(b"USER EDIT")

        report = rollback_journal(self.paths, self.journal.journal_id)
        self.assertFalse(report.ok)
        self.assertEqual(target.read_bytes(), b"USER EDIT")
        self.assertFalse(load_journal(self.paths, self.journal.journal_id).rolled_back)

        target.write_bytes(b"INSTALLED")
        retry = rollback_journal(self.paths, self.journal.journal_id)
        self.assertTrue(retry.ok, retry.failed)
        self.assertFalse(target.exists())

    def test_retry_resumes_after_a_later_operation_on_same_file(self) -> None:
        target = self.game / "dxgi.dll"
        target.write_bytes(b"ORIGINAL")
        self.journal.install_file(self.source, target)
        self.journal.write_text(target, "SECOND")
        self.journal.finish()
        target.write_bytes(b"USER EDIT")

        report = rollback_journal(self.paths, self.journal.journal_id)
        self.assertFalse(report.ok)
        self.assertEqual(target.read_bytes(), b"USER EDIT")

        target.write_bytes(b"SECOND")
        retry = rollback_journal(self.paths, self.journal.journal_id)
        self.assertTrue(retry.ok, retry.failed)
        self.assertEqual(target.read_bytes(), b"ORIGINAL")

    def test_unsealed_game_operation_refuses_later_edits_after_write_fails(self) -> None:
        target = self.game / "dxgi.dll"
        target.write_bytes(b"ORIGINAL")
        temporary = self.game / "dxgi.dll.nvfku-new"
        temporary.write_bytes(b"OTHER WORK")
        with self.assertRaises(FileExistsError):
            self.journal.install_file(self.source, target)
        target.write_bytes(b"USER EDIT")

        report = rollback_journal(self.paths, self.journal.journal_id)
        self.assertFalse(report.ok)
        self.assertEqual(target.read_bytes(), b"USER EDIT")
        self.assertEqual(temporary.read_bytes(), b"OTHER WORK")
        self.assertFalse(load_journal(self.paths, self.journal.journal_id).rolled_back)

        target.write_bytes(b"ORIGINAL")
        self.assertTrue(rollback_journal(self.paths, self.journal.journal_id).ok)
        self.assertEqual(target.read_bytes(), b"ORIGINAL")


if __name__ == "__main__":
    unittest.main()
