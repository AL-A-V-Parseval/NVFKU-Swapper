"""Scan-cache tests.

The cache exists because detection — walking a game directory on a mounted NTFS
volume — took ~9 s for a 20-game library, so every CLI invocation paid it and the
UI's detail view looked hung. Caching a *detection result*, though, is exactly the
kind of optimisation that can quietly start lying, so its invalidation is tested
rather than assumed.
"""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

from nvfku import steam
from nvfku.paths import Paths

# A minimal but valid D3D12 executable so detection has something to find.
from engine.tests.test_install import minimal_pe


class ScanCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        self.library = self.root / "library"
        self.install = self.library / "steamapps/common/Cache Game"
        (self.install / "bin/x64").mkdir(parents=True)
        (self.install / "bin/x64/CacheGame.exe").write_bytes(minimal_pe())
        (self.library / "steamapps").mkdir(parents=True, exist_ok=True)
        (self.library / "steamapps/appmanifest_424242.acf").write_text(
            '"AppState"\n{\n"appid" "424242"\n"name" "Cache Game"\n'
            '"installdir" "Cache Game"\n"SizeOnDisk" "10"\n}\n'
        )
        steam_root = self.root / "steam"
        (steam_root / "steamapps").mkdir(parents=True)
        (steam_root / "steamapps/libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n"0"\n{\n"path" "%s"\n}\n}\n' % self.library
        )
        self.paths = Paths(home=self.root, state_root=self.root / "state", steam_root=steam_root)

    def _scan(self):
        return steam.scan_with_cache(self.paths)

    def test_first_scan_populates_the_cache(self) -> None:
        games = self._scan()
        self.assertEqual([g.appid for g in games], ["424242"])
        cache = json.loads((self.root / "state/scan-cache.json").read_text())
        self.assertEqual(len(cache), 1)
        entry = next(iter(cache.values()))
        self.assertIn("stamp", entry)
        self.assertIn("at", entry)
        self.assertEqual(entry["game"]["rendering_api"], "DirectX 12")

    def test_second_scan_reuses_the_cache_and_agrees(self) -> None:
        first = self._scan()
        second = self._scan()
        self.assertEqual(len(first), len(second))
        self.assertEqual(first[0].appid, second[0].appid)
        self.assertEqual(first[0].rendering_api, second[0].rendering_api)
        self.assertEqual(first[0].launch_exe, second[0].launch_exe)
        self.assertEqual(first[0].bitness, second[0].bitness)

    def test_a_shallow_change_invalidates(self) -> None:
        self._scan()
        before = json.loads((self.root / "state/scan-cache.json").read_text())
        stamp = next(iter(before.values()))["stamp"]
        # A file at the game's top level moves its own mtime.
        time.sleep(0.01)
        (self.install / "readme.txt").write_text("x")
        self._scan()
        after = json.loads((self.root / "state/scan-cache.json").read_text())
        self.assertNotEqual(next(iter(after.values()))["stamp"], stamp)

    def test_a_change_at_the_executable_s_level_is_NOT_noticed_by_the_key(self) -> None:
        """Documents the real boundary, which testing revealed to be tighter than
        assumed.

        The key covers the game directory and its children. Writing into a
        *grandchild* — `bin/x64/`, which is exactly where this tool installs its
        components, beside the executable — moves the mtime of `x64` and leaves
        `bin` untouched. The key therefore does not change.

        That is acceptable only because the install path invalidates explicitly;
        the next test proves that mechanism, and `CACHE_TTL_SECONDS` bounds the
        damage if anything else ever writes there. Covering this depth with the
        key would mean either walking the tree (the cost the cache exists to
        avoid) or trusting a fixed depth to stay correct as layouts change.
        """
        self._scan()
        stamp = next(
            iter(json.loads((self.root / "state/scan-cache.json").read_text()).values())
        )["stamp"]
        time.sleep(0.01)
        (self.install / "bin/x64/dlss5-bridge.addon64").write_bytes(b"x")
        self._scan()
        new_stamp = next(
            iter(json.loads((self.root / "state/scan-cache.json").read_text()).values())
        )["stamp"]
        self.assertEqual(new_stamp, stamp, "the key is not expected to cover this depth")

    def test_the_install_path_invalidates_explicitly(self) -> None:
        """The mechanism that actually keeps the cache honest for our own writes.

        This is what a completed install triggers, and it is why the tighter
        boundary above does not turn into a stale "not installed" verdict in the
        UI after a successful install.
        """
        self._scan()
        cache_path = self.root / "state/scan-cache.json"
        self.assertNotEqual(json.loads(cache_path.read_text()), {})
        steam.invalidate_scan_cache(self.paths, self.install)
        self.assertEqual(json.loads(cache_path.read_text()), {})
        # And the next scan rebuilds it correctly.
        games = self._scan()
        self.assertEqual([g.appid for g in games], ["424242"])

    def test_explicit_invalidation_removes_only_that_game(self) -> None:
        self._scan()
        steam.invalidate_scan_cache(self.paths, self.install)
        cache = json.loads((self.root / "state/scan-cache.json").read_text())
        self.assertEqual(cache, {})

    def test_a_stale_timestamp_forces_a_rescan(self) -> None:
        self._scan()
        path = self.root / "state/scan-cache.json"
        cache = json.loads(path.read_text())
        for entry in cache.values():
            entry["at"] = time.time() - (steam.CACHE_TTL_SECONDS + 60)
        path.write_text(json.dumps(cache))
        # The stamp still matches, so only the ttl can cause a rescan; the result
        # must still be correct.
        games = self._scan()
        self.assertEqual([g.appid for g in games], ["424242"])

    def test_a_removed_game_disappears_from_the_cache(self) -> None:
        self._scan()
        (self.library / "steamapps/appmanifest_424242.acf").unlink()
        import shutil

        shutil.rmtree(self.install)
        games = self._scan()
        self.assertEqual(games, [])
        cache = json.loads((self.root / "state/scan-cache.json").read_text())
        self.assertEqual(cache, {})

    def test_gaining_a_proton_prefix_invalidates(self) -> None:
        """A first launch creates the prefix, and detection must notice.

        The key originally covered only the game directory and its manifest. A
        game that gained a Proton prefix after a scan therefore kept reporting that
        it had none, until the cache ttl expired — hours — which made every Proton
        dependent feature refuse to run.
        """
        self._scan()
        before = json.loads((self.root / "state/scan-cache.json").read_text())
        stamp = next(iter(before.values()))["stamp"]
        self.assertIsNone(
            next(iter(before.values()))["game"]["proton_prefix"],
            "the fixture should start with no prefix",
        )

        time.sleep(0.01)
        prefix = self.paths.steam_root / "steamapps/compatdata/424242/pfx"
        prefix.mkdir(parents=True)
        (prefix.parent / "config_info").write_text("proton-cachyos-slr\n")

        games = self._scan()
        self.assertIsNotNone(games[0].proton_prefix)
        after = json.loads((self.root / "state/scan-cache.json").read_text())
        self.assertNotEqual(next(iter(after.values()))["stamp"], stamp)

    def test_corrupt_cache_is_ignored_not_fatal(self) -> None:
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        (self.root / "state/scan-cache.json").write_text("{ not json")
        games = self._scan()
        self.assertEqual([g.appid for g in games], ["424242"])


if __name__ == "__main__":
    unittest.main()
