"""Tests for the guarded Steam launch-option writer.

The behaviour under test is not invented: it encodes what an experiment measured
about `localconfig.vdf` (see `docs/experiment-localconfig.md`). The two facts that
matter most, and that these tests pin, are

*   a Steam client running makes the write unsafe, because Steam keeps the value
    in memory and writes its copy back — so the writer must refuse; and
*   the file must be edited by single-line surgery, never regenerated, because it
    also holds friends, avatars, cloud-sync state and packed fields.

The fixture is a synthetic file whose layout matches the real one exactly: tabs
only, 5 tabs for an app key, 6 for its children, two tabs between key and value.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nvfku import steamconfig
from nvfku.paths import Paths

# A minimal but structurally faithful localconfig.vdf.
FIXTURE = (
    '"UserLocalConfigStore"\n'
    '{\n'
    '\t"Software"\n'
    '\t{\n'
    '\t\t"Valve"\n'
    '\t\t{\n'
    '\t\t\t"Steam"\n'
    '\t\t\t{\n'
    '\t\t\t\t"apps"\n'
    '\t\t\t\t{\n'
    '\t\t\t\t\t"1091500"\n'
    '\t\t\t\t\t{\n'
    '\t\t\t\t\t\t"LastPlayed"\t\t"1776669426"\n'
    '\t\t\t\t\t\t"LaunchOptions"\t\t"OLD_VALUE %command%"\n'
    '\t\t\t\t\t\t"BadgeData"\t\t"02000000"\n'
    '\t\t\t\t\t}\n'
    '\t\t\t\t\t"805550"\n'
    '\t\t\t\t\t{\n'
    '\t\t\t\t\t\t"Playtime"\t\t"119"\n'
    '\t\t\t\t\t\t"cloud"\n'
    '\t\t\t\t\t\t{\n'
    '\t\t\t\t\t\t\t"last_sync_state"\t\t"synchronized"\n'
    '\t\t\t\t\t\t}\n'
    '\t\t\t\t\t}\n'
    '\t\t\t\t}\n'
    '\t\t\t}\n'
    '\t\t}\n'
    '\t}\n'
    '\t"friends"\n'
    '\t{\n'
    '\t\t"1110180960"\n'
    '\t\t{\n'
    '\t\t\t"name"\t\t"someone"\n'
    '\t\t}\n'
    '\t}\n'
    '}\n'
)


class MergeTest(unittest.TestCase):
    """The surgery itself: pure, no filesystem, no Steam."""

    def test_replaces_an_existing_value(self) -> None:
        text, created = steamconfig.merge_launch_options(
            FIXTURE, "1091500", "NEW_VALUE %command%"
        )
        self.assertFalse(created)
        self.assertEqual(steamconfig.read_launch_options(text, "1091500"), "NEW_VALUE %command%")
        # Only that one line changed.
        before = FIXTURE.splitlines()
        after = text.splitlines()
        self.assertEqual(len(before), len(after))
        differing = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(len(differing), 1)

    def test_creates_the_key_when_absent(self) -> None:
        text, created = steamconfig.merge_launch_options(
            FIXTURE, "805550", "ADDED %command%"
        )
        self.assertTrue(created)
        self.assertEqual(steamconfig.read_launch_options(text, "805550"), "ADDED %command%")
        self.assertEqual(len(text.splitlines()), len(FIXTURE.splitlines()) + 1)

    def test_inserted_key_uses_the_file_s_own_indentation(self) -> None:
        text, _ = steamconfig.merge_launch_options(FIXTURE, "805550", "X %command%")
        line = next(l for l in text.splitlines() if "LaunchOptions" in l and "X %command%" in l)
        self.assertTrue(line.startswith("\t" * 6), repr(line))
        self.assertIn('"\t\t"', line, "key and value must be separated by two tabs")

    def test_never_touches_other_keys(self) -> None:
        text, _ = steamconfig.merge_launch_options(FIXTURE, "805550", "X %command%")
        for marker in ('"friends"', '"name"', '"cloud"', '"last_sync_state"', '"BadgeData"'):
            self.assertIn(marker, text)

    def test_braces_stay_balanced(self) -> None:
        for appid in ("1091500", "805550"):
            text, _ = steamconfig.merge_launch_options(FIXTURE, appid, "X %command%")
            self.assertEqual(steamconfig._brace_balance(text), 0, appid)

    def test_quotes_and_backslashes_are_escaped(self) -> None:
        value = 'VAR="a b" PATH=C:\\games %command%'
        text, _ = steamconfig.merge_launch_options(FIXTURE, "805550", value)
        self.assertIn("\\\"a b\\\"", text)
        self.assertIn("C:\\\\games", text)
        self.assertEqual(steamconfig.read_launch_options(text, "805550"), value)

    def test_dollar_and_percent_are_left_alone(self) -> None:
        # `%command%` must survive verbatim; Steam does its own substitution.
        text, _ = steamconfig.merge_launch_options(FIXTURE, "805550", "A=1 %command% --flag")
        self.assertIn("A=1 %command% --flag", text)

    def test_empty_value_is_refused(self) -> None:
        with self.assertRaises(steamconfig.SteamConfigError):
            steamconfig.merge_launch_options(FIXTURE, "805550", "   ")

    def test_newline_in_value_is_refused(self) -> None:
        with self.assertRaises(steamconfig.SteamConfigError):
            steamconfig.merge_launch_options(FIXTURE, "805550", "a\nb")

    def test_unknown_appid_is_refused_not_invented(self) -> None:
        # Steam creates the app block when the game is first configured. Creating
        # one ourselves would be guessing at Steam's schema.
        with self.assertRaises(steamconfig.SteamConfigError) as ctx:
            steamconfig.merge_launch_options(FIXTURE, "9999999", "X")
        self.assertIn("no block", str(ctx.exception))

    def test_a_damaged_file_is_detected_before_editing(self) -> None:
        broken = FIXTURE.replace('\t\t\t\t\t"805550"\n\t\t\t\t\t{\n', '\t\t\t\t\t"805550"\n\t\t\t\t\t{\n', 1)
        broken = broken[: broken.index('"805550"')] + broken[broken.index('"805550"'):]
        with self.assertRaises(steamconfig.SteamConfigError):
            steamconfig.merge_launch_options(broken + "}\n", "1091500", "X")

    def test_identical_value_reports_no_change(self) -> None:
        text, created = steamconfig.merge_launch_options(FIXTURE, "1091500", "OLD_VALUE %command%")
        self.assertFalse(created)
        self.assertEqual(text, FIXTURE)

    def test_removal(self) -> None:
        text, removed = steamconfig.remove_launch_options(FIXTURE, "1091500")
        self.assertTrue(removed)
        self.assertIsNone(steamconfig.read_launch_options(text, "1091500"))
        self.assertIn('"BadgeData"', text)
        self.assertEqual(steamconfig._brace_balance(text), 0)

    def test_removal_of_absent_key_is_a_no_op(self) -> None:
        text, removed = steamconfig.remove_launch_options(FIXTURE, "805550")
        self.assertFalse(removed)
        self.assertEqual(text, FIXTURE)


class StearnRunningGuardTest(unittest.TestCase):
    """A running client must block the write — this is the measured revert case."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.proc = self.root / "proc"
        (self.proc / "1234").mkdir(parents=True)
        self.paths = Paths(home=self.root, state_root=self.root / "state")
        self.addCleanup(self._tmp.cleanup)

    def _fake_process(self, argv0: str, pid: str = "1234") -> None:
        directory = self.proc / pid
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "cmdline").write_bytes(argv0.encode() + b"\x00-silent\x00")

    def test_detects_the_client_binary(self) -> None:
        self._fake_process("/home/u/.local/share/Steam/ubuntu12_32/steam")
        found = steamconfig.running_steam_processes(proc_root=str(self.proc))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], 1234)

    def test_ignores_unrelated_processes(self) -> None:
        self._fake_process("/usr/bin/firefox")
        self._fake_process("/home/u/.local/share/Steam/steamrt64/pv-runtime/bin/python3", pid="2222")
        self.assertEqual(steamconfig.running_steam_processes(proc_root=str(self.proc)), [])

    def test_write_is_refused_while_steam_runs(self) -> None:
        self._fake_process("/home/u/.local/share/Steam/ubuntu12_32/steam")
        config = self.root / "localconfig.vdf"
        config.write_text(FIXTURE)
        with self.assertRaises(steamconfig.SteamConfigError) as ctx:
            steamconfig.set_launch_options(
                self.paths, "1091500", "X %command%", config_path=config, proc_root=str(self.proc)
            )
        self.assertIn("Steam", str(ctx.exception))
        # And crucially: the file is untouched.
        self.assertEqual(config.read_text(), FIXTURE)

    def test_write_proceeds_when_no_client_runs(self) -> None:
        self._fake_process("/usr/bin/firefox")
        config = self.root / "localconfig.vdf"
        config.write_text(FIXTURE)
        result = steamconfig.set_launch_options(
            self.paths, "1091500", "X %command%", config_path=config, proc_root=str(self.proc)
        )
        self.assertTrue(result.verified)
        self.assertEqual(steamconfig.read_launch_options(config.read_text(), "1091500"), "X %command%")


class WriteFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.paths = Paths(home=self.root, state_root=self.root / "state")
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.config = self.root / "localconfig.vdf"
        self.config.write_text(FIXTURE)
        self.addCleanup(self._tmp.cleanup)

    def _set(self, appid: str, value: str):
        return steamconfig.set_launch_options(
            self.paths, appid, value, config_path=self.config, proc_root=str(self.proc)
        )

    def test_backup_is_written_and_matches_the_original(self) -> None:
        result = self._set("1091500", "NEW %command%")
        self.assertTrue(result.backup.is_file())
        self.assertEqual(result.backup.read_text(), FIXTURE)
        self.assertEqual(steamconfig.sha256_file(result.backup), result.backup_sha256)

    def test_result_reports_the_previous_value(self) -> None:
        result = self._set("1091500", "NEW %command%")
        self.assertEqual(result.previous, "OLD_VALUE %command%")
        self.assertFalse(result.created_key)

    def test_result_says_steam_must_restart(self) -> None:
        result = self._set("1091500", "NEW %command%")
        joined = " ".join(result.notes)
        self.assertIn("Start Steam again", joined)

    def test_last_line_ending_is_preserved(self) -> None:
        self.assertTrue(self.config.read_text().endswith("\n"))
        self._set("1091500", "NEW %command%")
        self.assertTrue(self.config.read_text().endswith("\n"))

    def test_no_crlf_is_introduced(self) -> None:
        self._set("1091500", "NEW %command%")
        self.assertNotIn("\r\n", self.config.read_text())

    def test_repeated_writes_are_stable(self) -> None:
        for value in ("A %command%", "B %command%", "C %command%"):
            result = self._set("1091500", value)
            self.assertTrue(result.verified, value)
        self.assertEqual(steamconfig.read_launch_options(self.config.read_text(), "1091500"), "C %command%")
        self.assertEqual(steamconfig._brace_balance(self.config.read_text()), 0)

    def test_writing_the_same_value_is_a_no_op_not_a_failure(self) -> None:
        """Being already correct is success.

        This used to refuse, on the reasoning that a write that changes nothing is
        suspicious. It is not: a reinstall, or an install whose earlier attempt got
        this far, is asking for the state it is already in. Refusing also made a
        caller unable to tell "nothing to do" from "could not write", which is how a
        reinstall was refused *after* its files were already in place.
        """
        result = self._set("1091500", "OLD_VALUE %command%")
        self.assertTrue(result.verified)
        self.assertIsNone(result.backup, "nothing was written, so there is no backup")
        self.assertFalse(result.created_key)
        self.assertIn("already set", " ".join(result.notes))
        # And the file is untouched.
        self.assertEqual(self.config.read_text(), FIXTURE)

    def test_an_unchanged_write_is_reported_as_unchanged(self) -> None:
        result = self._set("1091500", "OLD_VALUE %command%")
        self.assertIn("unchanged", result.render())

    def test_dry_run_writes_nothing(self) -> None:
        result = steamconfig.set_launch_options(
            self.paths, "1091500", "NEW %command%", config_path=self.config, proc_root=str(self.proc), dry_run=True
        )
        self.assertFalse(result.verified)
        self.assertEqual(self.config.read_text(), FIXTURE)

    def test_clear_dry_run_leaves_config_and_state_root_absent(self) -> None:
        result = steamconfig.clear_launch_options(
            self.paths, "1091500", config_path=self.config,
            proc_root=str(self.proc), dry_run=True,
        )
        self.assertFalse(result.verified)
        self.assertIsNone(result.backup)
        self.assertEqual(self.config.read_text(), FIXTURE)
        self.assertFalse(self.paths.state_root.exists())

    def test_a_damaged_file_is_refused_before_any_backup(self) -> None:
        self.config.write_text(FIXTURE + "\n}\n")  # unbalanced
        with self.assertRaises(steamconfig.SteamConfigError):
            self._set("1091500", "NEW %command%")
        backups = list((self.paths.ensure_state_dir() / "steam-config-backups").glob("*"))
        self.assertEqual(backups, [], "no backup should be made for a file we refuse to touch")

    def test_clear_removes_the_key_and_backs_up(self) -> None:
        result = steamconfig.clear_launch_options(
            self.paths, "1091500", config_path=self.config, proc_root=str(self.proc)
        )
        self.assertTrue(result.verified)
        self.assertIsNone(steamconfig.read_launch_options(self.config.read_text(), "1091500"))
        self.assertEqual(result.previous, "OLD_VALUE %command%")

    def test_clear_is_refused_while_steam_runs(self) -> None:
        directory = self.proc / "42"
        directory.mkdir()
        (directory / "cmdline").write_bytes(b"/x/ubuntu12_32/steam\x00")
        with self.assertRaises(steamconfig.SteamConfigError):
            steamconfig.clear_launch_options(
                self.paths, "1091500", config_path=self.config, proc_root=str(self.proc)
            )
        self.assertEqual(self.config.read_text(), FIXTURE)


class ConfigDiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _account(self, steam_id: str, content: str = FIXTURE) -> Path:
        path = self.root / "userdata" / steam_id / "config"
        path.mkdir(parents=True, exist_ok=True)
        (path / "localconfig.vdf").write_text(content)
        return path / "localconfig.vdf"

    def test_single_account_is_found(self) -> None:
        self._account("1110180960")
        paths = Paths(home=self.root, state_root=self.root / "state", steam_root=self.root)
        self.assertEqual(steamconfig.config_file_for(paths).parts[-3], "1110180960")

    def test_several_accounts_are_refused_rather_than_guessed(self) -> None:
        self._account("1110180960")
        self._account("2222222222")
        paths = Paths(home=self.root, state_root=self.root / "state", steam_root=self.root)
        with self.assertRaises(steamconfig.SteamConfigError) as ctx:
            steamconfig.config_file_for(paths)
        self.assertIn("several Steam accounts", str(ctx.exception))

    def test_no_steam_at_all_is_reported_clearly(self) -> None:
        paths = Paths(home=self.root, state_root=self.root / "state", steam_root=self.root)
        with self.assertRaises(steamconfig.SteamConfigError):
            steamconfig.config_file_for(paths)


class RealFileShapeTest(unittest.TestCase):
    """If the machine has a real config, the writer must read it without damage."""

    def test_reads_the_real_file_if_present(self) -> None:
        paths = Paths.discover()
        candidates = steamconfig.find_config_files(paths)
        if not candidates:
            self.skipTest("no Steam config on this machine")
        for path in candidates:
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertEqual(
                steamconfig._brace_balance(text), 0, f"{path} is not brace-balanced"
            )
            # Reading every appid must not raise, and must not alter anything.
            self.assertIsInstance(steamconfig.read_launch_options(text, "1091500"), (str, type(None)))


if __name__ == "__main__":
    unittest.main()
