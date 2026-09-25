"""The two fast paths that make the UI usable.

Both exist because a measurement showed a command spending nearly all its time on
work it had already done:

* `scan_with_cache` re-detected the same nine redistributables on every invocation
  (~540 ms of a ~1050 ms `plan`), because a non-game result was `continue`d past
  before it could be written to the cache.
* `plan` made a synchronous GitHub API request per call (0.9-2.4 s behind a proxy),
  and an unauthenticated API allows 60 requests an hour — so ordinary use hit the
  limit and the route was left with no version at all.

These assert the *behaviour* that fixes those, not the timings, which belong to the
machine rather than to the code.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nvfku import providers, steam
from nvfku.paths import Paths


class NonGameCacheTest(unittest.TestCase):
    """A redistributable is cached as firmly as a game is."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.steam = self.root / "Steam"
        library = self.root / "library"
        (self.steam / "steamapps").mkdir(parents=True)
        (self.steam / "steamapps/libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n"0"\n{\n"path" "%s"\n}\n}\n' % library
        )
        apps = library / "steamapps"
        (apps / "common").mkdir(parents=True)
        # A redistributable: no executable, no DLSS payload, so `is_non_game`
        # returns True and the old code dropped it without recording anything.
        (apps / "common/Steamworks Shared").mkdir()
        (apps / "appmanifest_228980.acf").write_text(
            '"AppState"\n{\n\t"appid"\t\t"228980"\n\t"installdir"\t\t"Steamworks Shared"\n}\n'
        )
        self.paths = Paths(
            home=self.root, state_root=self.root / "state", steam_root=self.steam
        )

    def test_a_non_game_is_recorded_in_the_cache(self) -> None:
        games = steam.scan_with_cache(self.paths)
        self.assertEqual(games, [], "a redistributable is not a game")
        cache = steam._load_cache(self.paths)
        entry = next(iter(cache.values()), None)
        self.assertIsNotNone(entry, "the verdict was not cached")
        self.assertTrue(entry.get("non_game"), entry)
        self.assertNotIn("game", entry, "a non-game must not carry a game payload")

    def test_the_second_scan_does_not_re_detect_it(self) -> None:
        """The property that recovers ~540 ms.

        Detection is stubbed to fail loudly, so a second scan that re-detects the
        non-game fails this test rather than merely being slower.
        """
        steam.scan_with_cache(self.paths)
        with mock.patch.object(
            steam,
            "scan_steam_game",
            side_effect=AssertionError("re-detected a cached non-game"),
        ):
            games = steam.scan_with_cache(self.paths)
        self.assertEqual(games, [])


class ScanOneTest(unittest.TestCase):
    """`scan_one` finds one game without scanning the library."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.steam = self.root / "Steam"
        library = self.root / "library"
        (self.steam / "steamapps").mkdir(parents=True)
        (self.steam / "steamapps/libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n"0"\n{\n"path" "%s"\n}\n}\n' % library
        )
        apps = library / "steamapps"
        self.exe_dir = apps / "common/Test Game/bin"
        self.exe_dir.mkdir(parents=True)
        (self.exe_dir / "TestGame.exe").write_bytes(b"MZ" + b"\0" * 200)
        (apps / "appmanifest_123456.acf").write_text(
            '"AppState"\n{\n\t"appid"\t\t"123456"\n\t"installdir"\t\t"Test Game"\n}\n'
        )
        self.paths = Paths(
            home=self.root, state_root=self.root / "state", steam_root=self.steam
        )

    def test_it_finds_a_game_by_appid(self) -> None:
        game = steam.scan_one(self.paths, "123456")
        self.assertIsNotNone(game)
        self.assertEqual(game.appid, "123456")
        self.assertEqual(game.name, "Test Game")

    def test_it_does_not_scan_other_games(self) -> None:
        """The whole point: one manifest is examined, not all of them."""
        with mock.patch.object(
            steam,
            "scan_steam_game",
            wraps=steam.scan_steam_game,
        ) as spy:
            steam.scan_one(self.paths, "123456")
        self.assertEqual(spy.call_count, 1, "scan_one walked more than one manifest")

    def test_a_name_is_not_guessed_at(self) -> None:
        """A name only exists inside a manifest, so the caller falls back.

        Returning None rather than something wrong is what makes the fallback in
        `_resolve_one` correct instead of merely convenient.
        """
        self.assertIsNone(steam.scan_one(self.paths, "Test Game"))

    def test_an_unknown_appid_returns_none(self) -> None:
        self.assertIsNone(steam.scan_one(self.paths, "999999"))


class RollingCacheTest(unittest.TestCase):
    """The version lookup is cached, and survives a rate limit."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        # The process-wide rate-limit flag is deliberately global, so it has to be
        # reset between tests or whichever test runs first decides the rest.
        self.addCleanup(setattr, providers, "_PROCESS_RATE_LIMITED", False)
        providers._PROCESS_RATE_LIMITED = False
        self.paths = Paths(
            home=self.root, state_root=self.root / "state", steam_root=None
        )
        self.component = providers.Component(
            id="optiscaler",
            name="OptiScaler.7z",
            version="v9.9.9",
            url="https://example.invalid/x.7z",
            size=123,
            filename="OptiScaler.7z",
        )

    def test_a_fresh_answer_is_reused_without_asking_the_api(self) -> None:
        with mock.patch.object(
            providers, "resolve_rolling", return_value=self.component
        ) as api:
            first = providers.resolve_rolling_cached(self.paths, "optiscaler")
            second = providers.resolve_rolling_cached(self.paths, "optiscaler")
        self.assertEqual(first.version, "v9.9.9")
        self.assertEqual(second.version, "v9.9.9")
        self.assertEqual(api.call_count, 1, "the API was asked twice for one answer")

    def test_a_rate_limit_falls_back_to_the_known_release(self) -> None:
        """The failure that actually happened on this machine.

        An unauthenticated API allows 60 requests an hour and `plan` spent one per
        game-detail open, so the limit was reached in ordinary use. Raising instead
        of falling back left the route with no version to name.
        """
        error = RuntimeError("HTTP Error 403: rate limit exceeded")
        with mock.patch.object(providers, "resolve_rolling", side_effect=error):
            component = providers.resolve_rolling_cached(self.paths, "optiscaler")
        seed = providers.ROLLING_SEED["optiscaler"]
        self.assertEqual(component.version, seed["version"])
        self.assertEqual(component.url, seed["url"])

    def test_a_rate_limit_stops_the_next_call_from_trying(self) -> None:
        """Retrying a shut door on every plan is the cost this removes."""
        error = RuntimeError("HTTP Error 403: rate limit exceeded")
        with mock.patch.object(
            providers, "resolve_rolling", side_effect=error
        ) as first_api:
            providers.resolve_rolling_cached(self.paths, "optiscaler")
        self.assertEqual(first_api.call_count, 1)
        with mock.patch.object(
            providers, "resolve_rolling", side_effect=AssertionError("tried again")
        ):
            component = providers.resolve_rolling_cached(self.paths, "optiscaler")
        self.assertEqual(component.version, providers.ROLLING_SEED["optiscaler"]["version"])

    def test_the_backoff_survives_an_early_return(self) -> None:
        """The bug that made every invocation pay a failed round trip again.

        `_note_rate_limit` used to re-read the cache, write the flag, and return;
        the caller then wrote its own *stale* snapshot at the end and overwrote it.
        Worse, one call site still passed the old `(paths, exc)` signature, so the
        whole thing raised TypeError *instead of* recording anything — and the
        caller's `except Exception` turned that into an "error" in the table, which
        is how it stayed hidden.

        So: after a rate limit, the flag must be on disk, and a call for a component
        with a cached answer must not lose it.
        """
        error = RuntimeError("HTTP Error 403: rate limit exceeded")
        with mock.patch.object(providers, "resolve_rolling", side_effect=error):
            providers.resolve_rolling_cached(self.paths, "optiscaler")
        cache = providers._read_rolling_cache(self.paths)
        self.assertIn("_rate_limited_until", cache, "the backoff was not recorded")
        self.assertGreater(cache["_rate_limited_until"], 0)

    def test_a_second_process_skips_the_network_entirely(self) -> None:
        """Cross-process, which is what the on-disk flag is for.

        Simulated by forgetting the in-process flag, which is exactly the state a
        fresh CLI invocation starts in.
        """
        error = RuntimeError("HTTP Error 403: rate limit exceeded")
        with mock.patch.object(providers, "resolve_rolling", side_effect=error):
            providers.resolve_rolling_cached(self.paths, "optiscaler")

        providers._PROCESS_RATE_LIMITED = False  # a new process
        with mock.patch.object(
            providers,
            "resolve_rolling",
            side_effect=AssertionError("a new process asked the API again"),
        ):
            for key in ("optiscaler", "dlss5-bridge", "addon-dlssnr-linux"):
                component = providers.resolve_rolling_cached(self.paths, key)
                self.assertTrue(component.version)

    def test_each_component_is_recorded_so_the_next_run_is_free(self) -> None:
        """Every producing path caches, including the two fallbacks."""
        error = RuntimeError("HTTP Error 403: rate limit exceeded")
        with mock.patch.object(providers, "resolve_rolling", side_effect=error):
            for key in ("optiscaler", "dlss5-bridge", "addon-dlssnr-linux"):
                providers.resolve_rolling_cached(self.paths, key)
        cache = providers._read_rolling_cache(self.paths)
        for key in ("optiscaler", "dlss5-bridge", "addon-dlssnr-linux"):
            self.assertIn(f"{key}:None", cache, f"{key} was not cached")
            self.assertTrue(cache[f"{key}:None"]["component"]["version"])

    def test_an_unknown_component_still_raises(self) -> None:
        """No seed means no honest answer, and a wrong version is worse than none."""
        with mock.patch.object(
            providers, "resolve_rolling", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                providers.resolve_rolling_cached(self.paths, "not-a-component")

    def test_a_stale_cache_beats_the_seed(self) -> None:
        """A real version seen earlier outranks a hard-coded baseline."""
        cache = {
            "optiscaler:None": {
                "at": 0,
                "component": {
                    "id": "optiscaler",
                    "name": "older.7z",
                    "version": "v0.0.1",
                    "url": "https://example.invalid/older.7z",
                },
            }
        }
        path = providers._rolling_cache_path(self.paths)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache), encoding="utf-8")
        with mock.patch.object(
            providers, "resolve_rolling", side_effect=RuntimeError("offline")
        ):
            component = providers.resolve_rolling_cached(
                self.paths, "optiscaler", max_age=0
            )
        self.assertEqual(component.version, "v0.0.1")


if __name__ == "__main__":
    unittest.main()
