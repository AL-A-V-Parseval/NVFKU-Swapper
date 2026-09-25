"""ReShade installer tests.

This module writes into a game directory, so its pieces are tested individually
rather than trusted: the digest check, the Proton discovery order, the path
mapping, the prefix-creation branch, and the plan's verdict for games where the
DXGI proxy cannot work.
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nvfku import reshade
from nvfku.paths import Paths
from nvfku.plan import Checks
from nvfku.steam import Game


def _game(tmp: Path, *, exe_name="Game.exe", api="DirectX 12", appid="424242") -> Game:
    install = tmp / "library/steamapps/common/Test Game"
    exe_dir = install / "bin"
    exe_dir.mkdir(parents=True, exist_ok=True)
    exe = exe_dir / exe_name
    exe.write_bytes(b"MZ" + b"\0" * 100)
    prefix = tmp / "compatdata" / appid / "pfx"
    prefix.mkdir(parents=True, exist_ok=True)
    return Game(
        appid=appid,
        name="Test Game",
        install_dir=install,
        library=tmp / "library",
        steam_root=tmp / "steam",
        proton_prefix=prefix,
        launch_exe=exe,
        bitness=64,
        rendering_api=api,
    )


class WindowsPathTest(unittest.TestCase):
    def test_maps_root_relative_paths_to_the_z_drive(self) -> None:
        self.assertEqual(
            reshade.windows_path(Path("/run/media/x/Game.exe")),
            "Z:\\run\\media\\x\\Game.exe",
        )

    def test_a_path_with_spaces_survives_unchanged(self) -> None:
        # The installer takes this as one positional argument, so no quoting is
        # needed and adding any would end up inside the path.
        self.assertEqual(
            reshade.windows_path(Path("/games/Some Game/Bin/Game.exe")),
            "Z:\\games\\Some Game\\Bin\\Game.exe",
        )


class VerifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_accepts_the_reviewed_bytes(self) -> None:
        payload = b"MZ" + b"x" * (reshade.SETUP_SIZE - 2)
        with mock.patch.object(reshade, "SETUP_SHA256", hashlib.sha256(payload).hexdigest()):
            path = self.root / "setup.exe"
            path.write_bytes(payload)
            reshade._verify_setup(path)

    def test_rejects_a_wrong_size(self) -> None:
        # An HTML error page is the realistic failure, and it is usually small.
        path = self.root / "setup.exe"
        path.write_bytes(b"<html>404</html>")
        with self.assertRaises(reshade.ReshadeError) as ctx:
            reshade._verify_setup(path)
        self.assertIn("expected", str(ctx.exception))

    def test_rejects_a_digest_mismatch(self) -> None:
        payload = b"MZ" + b"y" * (reshade.SETUP_SIZE - 2)
        path = self.root / "setup.exe"
        path.write_bytes(payload)
        with self.assertRaises(reshade.ReshadeError) as ctx:
            reshade._verify_setup(path)
        self.assertIn("digest", str(ctx.exception))

    def test_the_addon_build_is_the_one_requested(self) -> None:
        """The standard installer produces a ReShade that cannot load add-ons.

        The tool fetched it at first and the result injected fine, then skipped
        `dlss5-bridge.addon64` with "this build of ReShade has only limited add-on
        functionality". Upstream ships both installers; only the `_Addon` one can
        load the bridge.
        """
        self.assertIn("_Addon", reshade.SETUP_ASSET)
        self.assertIn("_Addon", reshade.DOWNLOAD_URL)
        # The marker is what the post-install check looks for.
        self.assertEqual(reshade.LIMITED_ADDON_MARKER, b"limited add-on functionality")

    def test_the_recorded_installer_identity_matches_the_url(self) -> None:
        self.assertTrue(reshade.DOWNLOAD_URL.endswith(reshade.SETUP_ASSET))
        self.assertGreater(reshade.SETUP_SIZE, 4_000_000)

    def test_rejects_a_non_executable_of_the_right_size(self) -> None:
        # Right size, wrong bytes: caught by the digest, and the MZ check is the
        # second line of defence for a future release whose digest is updated.
        payload = b"XX" + b"y" * (reshade.SETUP_SIZE - 2)
        with mock.patch.object(reshade, "SETUP_SHA256", hashlib.sha256(payload).hexdigest()):
            path = self.root / "setup.exe"
            path.write_bytes(payload)
            with self.assertRaises(reshade.ReshadeError) as ctx:
                reshade._verify_setup(path)
            self.assertIn("Windows executable", str(ctx.exception))


class ProtonDiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.paths = Paths(
            home=self.root, state_root=self.root / "state", steam_root=self.root / "steam"
        )

    def _tool(self, name: str) -> Path:
        root = self.root / "compatibilitytools.d" / name
        (root / "files").mkdir(parents=True, exist_ok=True)
        (root / "proton").write_text("#!/bin/sh\n")
        (root / "files/bin").mkdir(parents=True, exist_ok=True)
        return root

    def test_the_recorded_tool_wins(self) -> None:
        a = self._tool("proton-alpha")
        # Not unused: `_tool` creates the compatibility-tool directory on disk, and
        # this test is about a prefix whose config_info names the *second* tool. The
        # binding is never read, but the side effect is the point — pyflakes flagged
        # it, and deleting it made this test pass for the wrong reason (it fell back
        # to proton-alpha). Keep it.
        _ = self._tool("proton-beta")
        game = _game(self.root)
        (game.proton_prefix.parent / "config_info").write_text("proton-beta\n/fonts\n")
        with mock.patch.object(reshade, "_compat_tool_roots", return_value=[a.parent]), \
             mock.patch.object(reshade, "_steam_common_roots", return_value=[]):
            runtime = reshade.find_proton(game, self.paths)
        self.assertIsNotNone(runtime)
        self.assertEqual(runtime.name, "proton-beta")
        self.assertFalse(runtime.needs_prefix_init)
        self.assertEqual(runtime.data_dir, game.proton_prefix.parent)

    def test_a_prefix_without_config_info_is_flagged_for_creation(self) -> None:
        self._tool("proton-alpha")
        game = _game(self.root)
        with mock.patch.object(
            reshade, "_compat_tool_roots", return_value=[self.root / "compatibilitytools.d"]
        ):
            runtime = reshade.find_proton(game, self.paths)
        self.assertIsNotNone(runtime)
        self.assertTrue(runtime.needs_prefix_init)

    def test_a_recorded_tool_that_is_missing_falls_back(self) -> None:
        self._tool("proton-alpha")
        game = _game(self.root)
        (game.proton_prefix.parent / "config_info").write_text("proton-gone\n")
        with mock.patch.object(
            reshade, "_compat_tool_roots", return_value=[self.root / "compatibilitytools.d"]
        ), mock.patch.object(reshade, "_steam_common_roots", return_value=[]):
            runtime = reshade.find_proton(game, self.paths)
        self.assertIsNotNone(runtime)
        self.assertEqual(runtime.name, "proton-alpha")
        # The prefix was never created by the missing tool either.
        self.assertTrue(runtime.needs_prefix_init)

    def test_no_proton_anywhere_returns_none(self) -> None:
        game = _game(self.root)
        with mock.patch.object(reshade, "_compat_tool_roots", return_value=[]), \
             mock.patch.object(reshade, "_steam_common_roots", return_value=[]):
            self.assertIsNone(reshade.find_proton(game, self.paths))

    def test_a_symlinked_tool_is_found(self) -> None:
        """Symlinking is how a Proton is installed across filesystems.

        The first version filtered candidates with `entry.is_dir()`, which is
        False for a symlink that `Path.is_dir()` would otherwise follow — except
        the filter ran before the follow, so a symlinked build was invisible.
        """
        real = self._tool("proton-real")
        link_dir = self.root / "compatibilitytools.d"
        link = link_dir / "proton-linked"
        if link.exists():
            link.unlink()
        link.symlink_to(real, target_is_directory=True)

        game = _game(self.root)
        with mock.patch.object(
            reshade, "_compat_tool_roots", return_value=[link_dir]
        ), mock.patch.object(reshade, "_steam_common_roots", return_value=[]):
            runtime = reshade.find_proton(game, self.paths)
        self.assertIsNotNone(runtime, "a symlinked Proton must be discoverable")
        self.assertTrue(runtime.usable)

    def test_a_tool_without_a_proton_script_is_unusable(self) -> None:
        root = self.root / "compatibilitytools.d" / "broken"
        root.mkdir(parents=True)
        game = _game(self.root)
        with mock.patch.object(reshade, "_compat_tool_roots", return_value=[root.parent]), \
             mock.patch.object(reshade, "_steam_common_roots", return_value=[]):
            self.assertIsNone(reshade.find_proton(game, self.paths))


class PlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.paths = Paths(
            home=self.root, state_root=self.root / "state", steam_root=self.root / "steam"
        )
        self.tool = self.root / "compatibilitytools.d" / "proton-test"
        (self.tool / "files").mkdir(parents=True)
        (self.tool / "proton").write_text("#!/bin/sh\n")
        self._patch = mock.patch.object(
            reshade, "_compat_tool_roots", return_value=[self.tool.parent]
        )
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self._steam = mock.patch.object(
            reshade, "_steam_common_roots", return_value=[]
        )
        self._steam.start()
        self.addCleanup(self._steam.stop)

    def test_a_dxgi_game_is_viable(self) -> None:
        plan = reshade.check(self.paths, _game(self.root))
        self.assertTrue(plan.viable)
        self.assertEqual(plan.route, "reshade")
        # The two files it would create are named, not summarised.
        destinations = [a.destination for a in plan.actions]
        self.assertTrue(any(d.endswith("dxgi.dll") for d in destinations))
        self.assertTrue(any(d.endswith("ReShade.ini") for d in destinations))

    def test_a_vulkan_game_is_blocked_with_the_reason(self) -> None:
        plan = reshade.check(self.paths, _game(self.root, api="Vulkan"))
        self.assertFalse(plan.viable)
        names = [c.name for c in plan.checks.blockers]
        self.assertIn("rendering API", names)
        # The explanation has to be the real one, since it is the whole point.
        detail = next(c for c in plan.checks.blockers if c.name == "rendering API")
        self.assertIn("layer", (detail.detail + (detail.fix or "")).lower())

    def test_a_game_without_an_executable_is_blocked(self) -> None:
        game = _game(self.root)
        game.launch_exe = None
        plan = reshade.check(self.paths, game)
        self.assertFalse(plan.viable)
        self.assertIn("launch executable", [c.name for c in plan.checks.blockers])

    def test_an_uninitialised_prefix_is_a_warning_not_a_blocker(self) -> None:
        plan = reshade.check(self.paths, _game(self.root))
        prefix_check = next(c for c in plan.checks if c.name == "Proton prefix")
        self.assertEqual(prefix_check.severity, "warning")
        self.assertTrue(plan.viable)
        # And the plan says it will create the prefix rather than implying it
        # already works.
        notes = " ".join(a.destination for a in plan.actions if a.kind == "note")
        self.assertIn("create the Proton prefix", notes)

    def test_an_initialised_prefix_is_not_flagged(self) -> None:
        game = _game(self.root)
        (game.proton_prefix.parent / "config_info").write_text("proton-test\n")
        plan = reshade.check(self.paths, game)
        prefix_check = next(c for c in plan.checks if c.name == "Proton prefix")
        self.assertEqual(prefix_check.severity, "ok")
        notes = " ".join(a.destination for a in plan.actions if a.kind == "note")
        self.assertNotIn("create the Proton prefix", notes)

    def test_the_install_invocation_is_shown_verbatim(self) -> None:
        plan = reshade.check(self.paths, _game(self.root))
        notes = " ".join(a.destination for a in plan.actions if a.kind == "note")
        self.assertIn("--headless", notes)
        self.assertIn("--api dxgi", notes)
        self.assertIn("Z:\\", notes)


class InstallGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.paths = Paths(
            home=self.root, state_root=self.root / "state", steam_root=self.root / "steam"
        )
        self.tool = self.root / "compatibilitytools.d" / "proton-test"
        (self.tool / "files").mkdir(parents=True)
        (self.tool / "proton").write_text("#!/bin/sh\n")
        self._patch = mock.patch.object(
            reshade, "_compat_tool_roots", return_value=[self.tool.parent]
        )
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self._steam = mock.patch.object(
            reshade, "_steam_common_roots", return_value=[]
        )
        self._steam.start()
        self.addCleanup(self._steam.stop)

    def test_install_refuses_without_confirmation(self) -> None:
        game = _game(self.root)
        with self.assertRaises(Exception) as ctx:
            reshade.install(self.paths, game, logger=lambda m: None, yes=False)
        self.assertIn("yes", str(ctx.exception))

    def test_install_refuses_a_blocked_plan_before_touching_anything(self) -> None:
        blocked = _game(self.root, api="Vulkan")
        exe_dir = blocked.launch_exe.parent
        with self.assertRaises(Exception) as ctx:
            reshade.install(self.paths, blocked, logger=lambda m: None, yes=True)
        self.assertIn("rendering API", str(ctx.exception))
        # Nothing was created in the game directory.
        self.assertFalse((exe_dir / "dxgi.dll").exists())

    def test_the_installer_is_never_run_when_the_download_fails(self) -> None:
        game = _game(self.root)
        with mock.patch.object(reshade, "fetch_setup", side_effect=reshade.ReshadeError("no network")):
            with self.assertRaises(reshade.ReshadeError):
                reshade.install(self.paths, game, logger=lambda m: None, yes=True)
        self.assertFalse((game.launch_exe.parent / "dxgi.dll").exists())


class ChecksSequenceTest(unittest.TestCase):
    def test_checks_is_iterable_indexable_and_sized(self) -> None:
        """The container is used as a sequence everywhere, so it should be one."""
        checks = Checks()
        checks.ok("a", "1")
        checks.warn("b", "2")
        self.assertEqual([c.name for c in checks], ["a", "b"])
        self.assertEqual(len(checks), 2)
        self.assertEqual(checks[0].name, "a")
        self.assertEqual([c.name for c in checks.blockers], [])


if __name__ == "__main__":
    unittest.main()


class RollbackTest(unittest.TestCase):
    """The journal must restore what ReShade replaced and delete only what it made.

    This is the part that can destroy a user's files, so it is tested against a
    directory that contains both kinds: files ReShade overwrites and files it has
    no business touching.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        from engine.tests.test_install import minimal_pe

        self.exe_dir = self.root / "library/steamapps/common/Test Game/bin"
        self.exe_dir.mkdir(parents=True)
        (self.exe_dir / "TestGame.exe").write_bytes(minimal_pe(machine=0x8664))
        self.paths = Paths(
            home=self.root, state_root=self.root / "state", steam_root=self.root / "steam"
        )
        self.game = _game(self.root)

    def _journal(self):
        from nvfku.journal import FileJournal

        return FileJournal(self.paths, self.game.install_dir, "reshade", game_key="test")

    def test_a_replaced_file_is_restored_and_a_created_file_is_deleted(self) -> None:
        journal = self._journal()

        # What the installer would find.
        (self.exe_dir / "dxgi.dll").write_bytes(b"OLD-DXGI" * 100)
        (self.exe_dir / "ReShade.ini").write_bytes(b"OLD-INI")

        for name in reshade._written_names():
            candidate = self.exe_dir / name
            if candidate.is_file():
                journal.adopt(candidate)

        # What it would then produce.
        (self.exe_dir / "dxgi.dll").write_bytes(b"NEW" * 5000)
        (self.exe_dir / "ReShade.ini").write_bytes(b"NEW-INI")
        for name in ("ReShade.log", "ReShadePreset.ini"):
            (self.exe_dir / name).write_bytes(b"")
        for name in ("ReShade.log", "ReShadePreset.ini"):
            journal.record_absent(self.exe_dir / name)
        journal.finish()

        journal.rollback()

        self.assertEqual((self.exe_dir / "dxgi.dll").read_bytes(), b"OLD-DXGI" * 100)
        self.assertEqual((self.exe_dir / "ReShade.ini").read_bytes(), b"OLD-INI")
        self.assertFalse((self.exe_dir / "ReShade.log").exists())
        self.assertFalse((self.exe_dir / "ReShadePreset.ini").exists())

    def test_files_the_installer_did_not_touch_are_never_recorded(self) -> None:
        """The bug this guards against deleted the game's own executable.

        `record_absent` was called for every file in the directory rather than only
        the ones the installer created, so rollback removed the game executable and
        any unrelated DLL beside it.
        """
        journal = self._journal()
        (self.exe_dir / "unrelated.dll").write_bytes(b"KEEP-ME")

        # Only newly-created names are recorded, which is what the installer code
        # now does: it iterates the diff, not the directory.
        before = {p.name for p in self.exe_dir.iterdir()}
        (self.exe_dir / "ReShade.log").write_bytes(b"")
        created = [p.name for p in self.exe_dir.iterdir() if p.name not in before]
        for name in created:
            journal.record_absent(self.exe_dir / name)
        journal.finish()

        journal.rollback()

        self.assertTrue(
            (self.exe_dir / "TestGame.exe").is_file(), "the game executable must survive"
        )
        self.assertEqual((self.exe_dir / "unrelated.dll").read_bytes(), b"KEEP-ME")

    def test_record_absent_refuses_a_path_with_a_pre_image(self) -> None:
        journal = self._journal()
        target = self.exe_dir / "dxgi.dll"
        target.write_bytes(b"ORIGINAL")
        journal.adopt(target)
        with self.assertRaises(ValueError):
            journal.record_absent(target)

    def test_each_written_name_appears_once(self) -> None:
        names = reshade._written_names()
        self.assertEqual(len(names), len(set(names)), "a duplicated name is adopted twice")
        self.assertIn(reshade.INSTALLED_DLL, names)
        self.assertIn(reshade.INSTALLED_INI, names)


class EffectsTest(unittest.TestCase):
    MANIFEST = """
[00]
Enabled=1
Required=1
PackageName=Standard effects
DownloadUrl=https://example.invalid/standard.zip
EffectFiles=Deband.fx

[01]
Enabled=1
PackageName=SweetFX by CeeJay.dk
DownloadUrl=https://example.invalid/sweetfx.zip

[02]
Required=1
PackageName=Legacy effects
DownloadUrl=https://example.invalid/legacy.zip
"""

    def test_parses_the_manifest_shape(self) -> None:
        packages = reshade._parse_effect_packages(self.MANIFEST)
        self.assertEqual(len(packages), 3)
        self.assertEqual(packages[0]["PackageName"], "Standard effects")
        self.assertEqual(packages[1]["DownloadUrl"], "https://example.invalid/sweetfx.zip")

    def test_only_required_packages_are_selected(self) -> None:
        """A contributor's shader pack must not be installed by default."""
        with mock.patch("nvfku.providers.http_get", return_value=self.MANIFEST.encode()):
            urls = reshade.required_effects_urls()
        self.assertEqual(
            urls, ["https://example.invalid/standard.zip", "https://example.invalid/legacy.zip"]
        )
        self.assertNotIn("https://example.invalid/sweetfx.zip", urls)

    def test_the_standard_package_is_the_fallback(self) -> None:
        with mock.patch("nvfku.providers.http_get", side_effect=OSError("no network")):
            urls = reshade.required_effects_urls()
        self.assertEqual(urls, [reshade.STANDARD_EFFECTS_URL])

    def test_an_empty_manifest_falls_back(self) -> None:
        with mock.patch("nvfku.providers.http_get", return_value=b"[00]\nEnabled=1\n"):
            self.assertEqual(reshade.required_effects_urls(), [reshade.STANDARD_EFFECTS_URL])

    def test_unpacks_only_the_shader_and_texture_trees(self) -> None:
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("reshade-shaders-slim/README.md", "ignore me")
            zf.writestr("reshade-shaders-slim/Shaders/Deband.fx", "// fx")
            zf.writestr("reshade-shaders-slim/Textures/lut.png", b"png")
        blob = buffer.getvalue()

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            paths = Paths(home=target, state_root=target / "state", steam_root=target / "steam")
            with mock.patch("nvfku.providers.http_get", return_value=blob), \
                 mock.patch.object(reshade, "required_effects_urls",
                                   return_value=["https://example.invalid/x.zip"]):
                result = reshade.install_effects(paths, target, logger=lambda m: None)

        names = result["files"]
        self.assertIn("Shaders/Deband.fx", names)
        self.assertIn("Textures/lut.png", names)
        self.assertNotIn("README.md", names)
