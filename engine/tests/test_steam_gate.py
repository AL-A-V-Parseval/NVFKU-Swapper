"""The Steam gate on route A1.

A1 cannot work without its launch options: the override is what makes Wine prefer
the local proxy, and the bridge needs the NGX override. Those options live in
`localconfig.vdf`, and an experiment on this machine showed Steam keeps each app's
`LaunchOptions` in memory and writes its own copy back — so a write made while it
runs is silently reverted.

The gate is therefore not a nicety. It is the difference between a game directory
that is installed and working and one that looks installed and does nothing.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nvfku import steamconfig
from nvfku.paths import Paths
from nvfku.plan import InstallRefused
from nvfku.route import a1_bridge

from engine.tests.test_install import InstallTestBase


class SteamGateTest(InstallTestBase):
    """A1's install is refused while Steam runs, before anything is written."""

    def _snapshot(self) -> dict[str, int]:
        return {
            str(p.relative_to(self.sandbox.install_dir)): p.stat().st_size
            for p in self.sandbox.install_dir.rglob("*")
            if p.is_file()
        }

    def test_a_running_steam_refuses_the_install(self) -> None:
        game = self.sandbox.game()
        # A model must be resolvable, or the refusal would be about that instead and
        # the test would pass for the wrong reason.
        self.sandbox.stub_model()
        before = self._snapshot()
        with self.assertRaises(Exception) as ctx:
            a1_bridge.install(
                self.sandbox.paths,
                game,
                verify_against_upstream=False,
                skip_download=True,
                logger=lambda *_: None,
                proc_root=self.FAKE_PROC_WITH_STEAM,
            )
        message = str(ctx.exception)
        self.assertIn("Steam is running", message)
        # And it says what to do, because "refused" alone is not actionable.
        self.assertIn("Exit Steam", message)
        # Nothing was written.
        self.assertEqual(self._snapshot(), before)

    def test_the_plan_reports_that_steam_is_running(self) -> None:
        game = self.sandbox.game()
        self.sandbox.stub_model()
        # The plan reads the live process table; point it at the stand-in rather
        # than at the host, whose Steam state is not this test's subject.
        with mock.patch.object(
            steamconfig, "running_steam_processes", return_value=[(4242, "steam")]
        ):
            plan = a1_bridge.plan(self.sandbox.paths, game, language="en")
        self.assertTrue(plan.steam_running)
        names = [c.name for c in plan.checks.checks]
        self.assertIn("Steam launch options", names)
        check = next(c for c in plan.checks.checks if c.name == "Steam launch options")
        self.assertEqual(check.severity, "warning")
        self.assertIn("4242", check.detail)

    def test_the_plan_reports_steam_closed(self) -> None:
        game = self.sandbox.game()
        self.sandbox.stub_model()
        with mock.patch.object(steamconfig, "running_steam_processes", return_value=[]):
            plan = a1_bridge.plan(self.sandbox.paths, game, language="en")
        self.assertFalse(plan.steam_running)

    def test_the_launch_option_appears_as_an_install_action(self) -> None:
        """It is part of the install, not a separate panel to remember."""
        game = self.sandbox.game()
        self.sandbox.stub_model()
        plan = a1_bridge.plan(self.sandbox.paths, game, language="en")
        kinds = [a.kind for a in plan.actions]
        self.assertIn("launch-option", kinds)
        action = next(a for a in plan.actions if a.kind == "launch-option")
        self.assertEqual(action.destination, plan.launch_options)


class SteamStateTest(unittest.TestCase):
    """`steam_state` reports rather than raises, so a caller can explain itself."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.paths = Paths(home=self.root, state_root=self.root / "state", steam_root=None)

    def test_a_missing_config_is_an_error_not_a_crash(self) -> None:
        # `EMPTY_PROC` rather than the default: the host may have Steam running,
        # and this test is about the missing config, not about the process table.
        state = steamconfig.steam_state(self.paths, "123", proc_root="/nonexistent-proc")
        self.assertFalse(state.running)
        self.assertIsNotNone(state.error)
        self.assertIsNone(state.current)

    def test_it_reads_the_current_value(self) -> None:
        steam_root = self.root / "steam"
        config = steam_root / "userdata/1/config/localconfig.vdf"
        config.parent.mkdir(parents=True)
        config.write_text(
            '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n'
            '\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n\t\t\t\t\t"990080"\n'
            '\t\t\t\t\t{\n\t\t\t\t\t\t"LaunchOptions"\t\t"OLD=1 %command%"\n'
            "\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n"
        )
        paths = Paths(home=self.root, state_root=self.root / "state", steam_root=steam_root)
        state = steamconfig.steam_state(paths, "990080", proc_root="/nonexistent-proc")
        self.assertEqual(state.current, "OLD=1 %command%")
        self.assertIsNone(state.error)

    def test_describe_names_the_pids(self) -> None:
        state = steamconfig.SteamState(running_pids=[7, 9], config=None, current=None)
        self.assertIn("7, 9", state.describe())
        quiet = steamconfig.SteamState(running_pids=[], config=None, current=None)
        self.assertIn("not running", quiet.describe())


class MissingConfigTest(InstallTestBase):
    """A1 must not install a nonfunctional bridge without Steam launch options."""

    def test_missing_config_refuses_before_modifying_game(self) -> None:
        game = self.sandbox.game()
        self.sandbox.stub_model()
        # This case is about *no config at all*, which the sandbox otherwise has.
        for leftover in (self.sandbox.steam / "userdata").rglob("localconfig.vdf"):
            leftover.unlink()
        with self.assertRaisesRegex(InstallRefused, "launch options"):
            a1_bridge.install(
                self.sandbox.paths,
                game,
                verify_against_upstream=False,
                skip_download=True,
                logger=lambda *_: None,
                proc_root=self.EMPTY_PROC,
            )
        self.assertFalse((self.sandbox.exe_dir / a1_bridge.ADDON_DLL).exists())


if __name__ == "__main__":
    unittest.main()
