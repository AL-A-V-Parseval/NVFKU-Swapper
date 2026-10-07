"""CLI discovery regression tests; all games, Steam roots, and state are temporary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from nvfku.journal import FileJournal
from nvfku.paths import Paths


ENGINE = Path(__file__).resolve().parents[1]


class CliGameDiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.state = self.root / "state"
        self.steam = self.root / "custom-steam"
        self.steam_apps = self.steam / "steamapps"
        self.steam_apps.mkdir(parents=True)
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.root / "xdg-data"),
            "XDG_CONFIG_HOME": str(self.root / "xdg-config"),
            "XDG_CACHE_HOME": str(self.root / "xdg-cache"),
            "PYTHONPATH": str(ENGINE),
        }
        self.paths = Paths(home=self.home, state_root=self.state, steam_root=self.steam)

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "nvfku", "--state-dir", str(self.state), "--json", *args],
            cwd=self.root, env=self.env, text=True, capture_output=True, check=False,
            timeout=30,
        )

    def assert_ok(self, result: subprocess.CompletedProcess[str]) -> object:
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def steam_game(self) -> Path:
        game = self.steam_apps / "common" / "Configured Steam Game"
        game.mkdir(parents=True)
        (game / "Game.exe").write_bytes(b"MZ")
        (self.steam_apps / "appmanifest_987654.acf").write_text(
            '"AppState"\n{\n"appid" "987654"\n"name" "Configured Steam Game"\n'
            '"installdir" "Configured Steam Game"\n}\n', encoding="utf-8",
        )
        return game

    def test_backups_resolves_persisted_steam_root_game_and_rollback(self) -> None:
        game = self.steam_game()
        self.assert_ok(self.cli("settings", "--steam-root", str(self.steam)))
        scanned = self.assert_ok(self.cli("scan"))
        self.assertIn("987654", [row["appid"] for row in scanned])
        journal = FileJournal(self.paths, game, "a2", game_key="steam-987654")
        journal.note("only temporary game files")
        journal.finish()

        backups = self.assert_ok(self.cli("backups", "987654"))
        self.assertEqual([entry["id"] for entry in backups], [journal.journal_id])
        report = self.assert_ok(self.cli("rollback", journal.journal_id))
        self.assertTrue(report["ok"])
        self.assertEqual(
            self.assert_ok(self.cli("backups", "987654"))[0]["rolled_back"], True
        )

    def test_rollback_invalidates_scan_of_deep_game_files(self) -> None:
        game = self.steam_game()
        self.assert_ok(self.cli("settings", "--steam-root", str(self.steam)))
        target = game / "bin" / "x64" / "plugins" / "nvngx_dlss.dll"
        target.parent.mkdir(parents=True)
        source = self.root / "source.dll"
        source.write_bytes(b"MZ")
        journal = FileJournal(self.paths, game, "a1", game_key="steam-987654")
        journal.install_file(source, target)
        journal.finish()
        game_before = next(row for row in self.assert_ok(self.cli("scan"))
                           if row["appid"] == "987654")
        self.assertIn(str(target), game_before["native_dlss"])
        self.assertTrue(self.assert_ok(self.cli("rollback", journal.journal_id))["ok"])
        game_after = next(row for row in self.assert_ok(self.cli("scan"))
                          if row["appid"] == "987654")
        self.assertEqual(game_after["native_dlss"], [])

    def test_backups_resolves_registered_folder_key_and_rollback(self) -> None:
        game = self.root / "manual" / "Standalone Game"
        game.mkdir(parents=True)
        (game / "Game.exe").write_bytes(b"MZ")
        added = self.assert_ok(self.cli("games", str(game)))
        key = added["key"]
        self.assertTrue(key.startswith("folder-"), key)
        scanned = self.assert_ok(self.cli("scan"))
        self.assertIn(key, [row["appid"] for row in scanned])
        journal = FileJournal(self.paths, game, "a2", game_key=key)
        journal.note("only temporary game files")
        journal.finish()

        backups = self.assert_ok(self.cli("backups", key))
        self.assertEqual([entry["id"] for entry in backups], [journal.journal_id])
        report = self.assert_ok(self.cli("rollback", journal.journal_id))
        self.assertTrue(report["ok"])
        self.assertTrue(self.assert_ok(self.cli("backups", key))[0]["rolled_back"])
