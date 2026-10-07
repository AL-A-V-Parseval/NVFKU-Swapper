"""Journal and rollback tests.

These matter more than the rest of the suite: the entire reason this tool exists
instead of a shell script is that every change to a game directory can be undone
exactly.  A rollback bug corrupts someone's game install.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from nvfku.journal import FileJournal, list_journals, load_journal, rollback_journal
from nvfku.paths import Paths


def make_paths(root: Path) -> Paths:
    return Paths(home=root, state_root=root / "state")


class JournalTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.paths = make_paths(self.root)
        self.game = self.root / "game"
        self.game.mkdir(parents=True)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "new.dll").write_bytes(b"NEW-CONTENT")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_created_file_is_removed_on_rollback(self) -> None:
        journal = FileJournal(self.paths, self.game, "a1")
        journal.install_file(self.source / "new.dll", self.game / "added.dll")
        self.assertTrue((self.game / "added.dll").is_file())

        lines = journal.rollback()
        self.assertFalse((self.game / "added.dll").exists())
        self.assertTrue(any("deleted" in line for line in lines))

    def test_replaced_file_is_restored_byte_for_byte(self) -> None:
        original = b"ORIGINAL-BYTES"
        (self.game / "dxgi.dll").write_bytes(original)

        journal = FileJournal(self.paths, self.game, "a1")
        journal.install_file(self.source / "new.dll", self.game / "dxgi.dll")
        self.assertEqual((self.game / "dxgi.dll").read_bytes(), b"NEW-CONTENT")

        journal.rollback()
        self.assertEqual((self.game / "dxgi.dll").read_bytes(), original)

    def test_removed_file_is_restored(self) -> None:
        (self.game / "keep.ini").write_bytes(b"[section]\nkey=value\n")
        journal = FileJournal(self.paths, self.game, "a2")
        journal.remove(self.game / "keep.ini")
        self.assertFalse((self.game / "keep.ini").exists())
        journal.rollback()
        self.assertEqual((self.game / "keep.ini").read_bytes(), b"[section]\nkey=value\n")

    def test_symlink_is_restored_as_a_symlink(self) -> None:
        """Proton prefixes are full of symlinks into the Steam runtime.

        Replacing one by writing *through* it would edit the runtime instead of
        the prefix, so the pre-image has to remember that it was a link.
        """
        target = self.root / "runtime-lib.so"
        target.write_bytes(b"runtime")
        link = self.game / "linked.dll"
        os.symlink(target, link)

        journal = FileJournal(self.paths, self.game, "a1")
        journal.install_file(self.source / "new.dll", link)
        self.assertFalse(link.is_symlink())
        self.assertEqual(link.read_bytes(), b"NEW-CONTENT")

        journal.rollback()
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(target))
        self.assertEqual(target.read_bytes(), b"runtime")

    def test_write_text_roundtrip(self) -> None:
        (self.game / "dlss5-bridge.cfg").write_text("unwrap=1\n")
        journal = FileJournal(self.paths, self.game, "a1")
        journal.write_text(self.game / "dlss5-bridge.cfg", "unwrap=0\n")
        self.assertEqual((self.game / "dlss5-bridge.cfg").read_text(), "unwrap=0\n")
        journal.rollback()
        self.assertEqual((self.game / "dlss5-bridge.cfg").read_text(), "unwrap=1\n")

    def test_refuses_to_touch_paths_outside_the_game(self) -> None:
        journal = FileJournal(self.paths, self.game, "a1")
        outside = self.root / "outside.dll"
        with self.assertRaises(ValueError):
            journal.install_file(self.source / "new.dll", outside)
        self.assertFalse(outside.exists())

    def test_manifest_remains_visible_when_index_is_corrupt(self) -> None:
        journal = FileJournal(self.paths, self.game, "a1")
        journal.install_file(self.source / "new.dll", self.game / "new.dll")
        index = self.paths.backups_root() / "index.json"
        index.write_text("{broken index")
        entries = list_journals(self.paths, game_dir=self.game)
        self.assertEqual([entry["id"] for entry in entries], [journal.journal_id])
        self.assertFalse(entries[0]["finished"])

    def test_all_manifests_visible_beyond_bounded_index(self) -> None:
        journal = FileJournal(self.paths, self.game, "a1")
        journal.note("unfinished installation")
        manifest = json.loads((journal.dir / "manifest.json").read_text())
        for number in range(500):
            entry = dict(manifest, id=f"older-{number:04d}", created_at=number)
            directory = journal.dir.parent / entry["id"]
            directory.mkdir()
            (directory / "manifest.json").write_text(json.dumps(entry))
        entries = list_journals(self.paths, game_dir=self.game)
        self.assertEqual(len(entries), 501)
        self.assertIn(journal.journal_id, {entry["id"] for entry in entries})

    def test_rollback_survives_a_reloaded_journal(self) -> None:
        """Rollback must work from disk, not just from in-memory state."""
        journal = FileJournal(self.paths, self.game, "a1")
        (self.game / "dxgi.dll").write_bytes(b"ORIGINAL")
        journal.install_file(self.source / "new.dll", self.game / "dxgi.dll")
        journal.install_file(self.source / "new.dll", self.game / "extra.dll")
        journal.finish()

        entries = list_journals(self.paths, game_dir=self.game)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["finished"])

        lines = rollback_journal(self.paths, journal.journal_id)
        self.assertTrue(lines)
        self.assertEqual((self.game / "dxgi.dll").read_bytes(), b"ORIGINAL")
        self.assertFalse((self.game / "extra.dll").exists())

        reloaded = load_journal(self.paths, journal.journal_id)
        self.assertTrue(reloaded.rolled_back)

    def test_missing_preimage_is_retryable_and_never_claimed_complete(self) -> None:
        original = self.game / "dxgi.dll"
        original.write_bytes(b"ORIGINAL")
        journal = FileJournal(self.paths, self.game, "a1")
        journal.install_file(self.source / "new.dll", original)
        backup = journal.dir / journal._journal.operations[-1].backup
        backup.unlink()
        report = rollback_journal(self.paths, journal.journal_id)
        self.assertFalse(report.ok)
        self.assertEqual(original.read_bytes(), b"NEW-CONTENT")
        self.assertFalse(load_journal(self.paths, journal.journal_id).rolled_back)
        backup.write_bytes(b"ORIGINAL")
        retry = rollback_journal(self.paths, journal.journal_id)
        self.assertTrue(retry.ok)
        self.assertEqual(original.read_bytes(), b"ORIGINAL")

    def test_symlinked_game_parent_is_refused(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.game / "escape").symlink_to(outside, target_is_directory=True)
        journal = FileJournal(self.paths, self.game, "a1")
        with self.assertRaisesRegex(ValueError, "symlinked parent"):
            journal.install_file(self.source / "new.dll", self.game / "escape" / "new.dll")
        self.assertFalse((outside / "new.dll").exists())

    def test_external_state_rollback_preserves_independent_edits(self) -> None:
        state = self.paths.state_root / "profiles" / "sample" / "a1.json"
        state.parent.mkdir(parents=True)
        state.write_text("original")
        journal = FileJournal(self.paths, self.game, "a1", game_key="sample")
        operation = journal.snapshot_external(state, source_label="route state")
        state.write_text("installed")
        journal.seal_external(operation)
        state.write_text("user edit")
        report = rollback_journal(self.paths, journal.journal_id)
        self.assertFalse(report.ok)
        self.assertEqual(state.read_text(), "user edit")
        self.assertFalse(load_journal(self.paths, journal.journal_id).rolled_back)
        state.write_text("installed")
        self.assertTrue(rollback_journal(self.paths, journal.journal_id).ok)
        self.assertEqual(state.read_text(), "original")

    def test_mkdir_is_undone_only_when_empty(self) -> None:
        journal = FileJournal(self.paths, self.game, "a1")
        nested = self.game / "host64" / "sub"
        journal.mkdir(nested)
        self.assertTrue(nested.is_dir())
        journal.rollback()
        self.assertFalse((self.game / "host64").exists())


class PathsTest(unittest.TestCase):
    def test_discover_finds_steam_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".local/share/Steam/steamapps").mkdir(parents=True)
            paths = Paths.discover(home=home, state_root=home / "state")
            self.assertEqual(paths.steam_root, home / ".local/share/Steam")

    def test_state_dirs_are_created_on_demand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            self.assertFalse(paths.state_root.exists())
            self.assertTrue(paths.backups_root().is_dir())
            self.assertTrue(paths.download_cache().is_dir())


if __name__ == "__main__":
    unittest.main()
