"""Install/rollback integration tests against a fabricated Steam library.

The point of these tests is the *whole* path: scan a library, plan a route,
apply it through the journal, then roll it back and confirm the game directory
is byte-for-byte what it was.  A rollback bug here corrupts a real game install,
which is the one failure mode this tool exists to prevent.

Component fetching is stubbed: the tests exercise the filesystem contract, not
the network.  ``model.set_discovery_override`` supplies a stand-in for the
proprietary DLSS NR model, because a real one is 158 MiB and cannot be
fabricated.
"""

from __future__ import annotations

import json
import struct
import tempfile
import os
import unittest
from unittest import mock
from pathlib import Path

from nvfku import model, providers, steam
from nvfku.journal import rollback_journal
from nvfku.paths import Paths
from nvfku.plan import InstallRefused
from nvfku.route import a1_bridge, a2_optiscaler


# ------------------------------------------------------------------ fixtures


def minimal_pe(*, machine: int = 0x8664, imports: tuple[str, ...] = ("d3d12.dll",)) -> bytes:
    """A PE that :func:`read_pe` can parse and classify."""
    opt_size = 0xF0
    headers_size = 0x200
    section_rva = 0x1000
    section_raw = headers_size

    descriptors = b""
    names_blob = bytearray()
    data_off = (len(imports) + 1) * 20
    for name in imports:
        name_rva = section_rva + data_off + len(names_blob)
        descriptors += struct.pack("<IIIII", 0, 0, 0, name_rva, 0)
        names_blob += name.encode("ascii") + b"\x00"
    descriptors += b"\x00" * 20
    section = descriptors + bytes(names_blob)

    blob = bytearray(headers_size + len(section))
    blob[0:2] = b"MZ"
    struct.pack_into("<I", blob, 0x3C, 0x40)
    pe_off = 0x40
    blob[pe_off : pe_off + 4] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", blob, pe_off + 4, machine, 1, 0, 0, 0, opt_size, 0x0022)
    opt_off = pe_off + 24
    struct.pack_into("<H", blob, opt_off, 0x20B)
    struct.pack_into("<II", blob, opt_off + 112 + 8, section_rva, len(descriptors))
    section_off = opt_off + opt_size
    blob[section_off : section_off + 8] = b".rdata\x00\x00"
    struct.pack_into("<IIII", blob, section_off + 8, len(section), section_rva, len(section), section_raw)
    blob[section_raw : section_raw + len(section)] = section
    return bytes(blob)


class Sandbox:
    """A fake Steam install with one game, one prefix, and a component cache."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.steam = self.home / ".local/share/Steam"
        self.library = self.root / "library"
        self.appid = "999999"
        self.game_name = "Test Game"
        self.install_dir = self.library / "steamapps/common" / self.game_name
        self.exe_dir = self.install_dir / "bin/x64"
        self.exe_dir.mkdir(parents=True)
        (self.exe_dir / "TestGame.exe").write_bytes(minimal_pe())

        (self.steam / "steamapps").mkdir(parents=True)
        # One account with a valid config, so `steam_state` has something to read.
        # Without it the plan reports a missing config and every launch-option
        # assertion would be about the wrong thing.
        config = self.steam / "userdata/1/config/localconfig.vdf"
        config.parent.mkdir(parents=True)
        config.write_text(
            '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n'
            '\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n'
            '\t\t\t\t\t"%s"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LaunchOptions"\t\t"OLD=1 %%command%%"\n'
            '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n' % self.appid
        )
        (self.steam / "steamapps/libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n"0"\n{\n"path" "%s"\n}\n}\n' % self.library
        )
        (self.library / "steamapps").mkdir(parents=True, exist_ok=True)
        (self.library / "steamapps" / f"appmanifest_{self.appid}.acf").write_text(
            f'"AppState"\n{{\n"appid" "{self.appid}"\n"name" "{self.game_name}"\n'
            f'"installdir" "{self.game_name}"\n"SizeOnDisk" "1000"\n}}\n'
        )
        prefix = self.steam / "steamapps/compatdata" / self.appid / "pfx"
        (prefix / "drive_c/windows/system32").mkdir(parents=True)
        (prefix / "drive_c/windows/system32/nvngx.dll").write_bytes(b"x" * 4096)
        (prefix.parent / "config_info").write_text("proton-cachyos 11.0\n")

        # Native DLSS so A1 takes the native-mirror path.
        (self.exe_dir / "nvngx_dlss.dll").write_bytes(b"dlss-runtime")

        self.state = self.root / "state"
        self.paths = Paths(home=self.home, state_root=self.state, steam_root=self.steam)

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def game(self) -> steam.Game:
        games = steam.scan(self.paths)
        self.assert_one = games
        if len(games) != 1:
            raise AssertionError(f"expected 1 game, scanner found {len(games)}: "
                                 f"{[g.name for g in games]}")
        return games[0]

    def stub_model(self, *, verdict: str = "tested", inside_game: bool = False) -> Path:
        """Point model discovery at a small stand-in file."""
        blob = self.root / "model-source"
        blob.mkdir(exist_ok=True)
        path = (self.exe_dir if inside_game else blob) / model.MODEL_NAME
        path.write_bytes(b"stand-in-nr-model")
        digest = model.sha256_file(path)

        def discovery(_paths, _game):
            return [
                model.ModelCandidate(
                    path=path,
                    size=path.stat().st_size,
                    sha256=digest,
                    verdict=verdict,
                    inside_game=inside_game,
                )
            ]

        model.set_discovery_override(discovery)
        return path

    def stub_components(self) -> dict[str, Path]:
        """Fake the pinned component downloads inside the real cache layout."""
        sources = {}
        for key, component in providers.PINNED.items():
            target = component.local_path(self.paths)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = f"component:{key}".encode()
            if component.size is not None:
                payload = payload.ljust(component.size, b"\x00")
            with mock.patch.object(providers, "http_get", return_value=payload):
                sources[key] = providers.fetch(component, self.paths, logger=lambda *_: None)
        return sources


class InstallTestBase(unittest.TestCase):
    #: A path with no Steam processes in it, for tests that must not depend on the
    #: host's real process table.
    EMPTY_PROC = "/nonexistent-proc"

    #: Filled in by `setUp`: a `/proc` stand-in holding one Steam process.
    FAKE_PROC_WITH_STEAM = "/nonexistent-proc"

    def setUp(self) -> None:
        self.sandbox = Sandbox()
        self.addCleanup(self.sandbox.cleanup)
        self.addCleanup(model.set_discovery_override, None)
        self.sandbox.stub_components()

        # A `/proc` stand-in holding one Steam client process. The install reads it
        # to decide whether writing the launch options would be reverted, so a test
        # using the host's real `/proc` would depend on whether the developer has
        # Steam open — which is exactly how this was noticed.
        import shutil
        import tempfile

        proc = Path(tempfile.mkdtemp(prefix="nvfku-fake-proc-"))
        self.addCleanup(shutil.rmtree, proc, True)
        (proc / "4242").mkdir()
        (proc / "4242" / "cmdline").write_bytes(
            b"/home/user/.local/share/Steam/ubuntu12_32/steam\x00-srt-logger-opened\x00"
        )
        # A non-numeric entry and a process that is not Steam, so the scanner's own
        # filtering is exercised rather than assumed.
        (proc / "self").mkdir()
        (proc / "999").mkdir()
        (proc / "999" / "cmdline").write_bytes(b"/usr/bin/bash\x00-c\x00echo hi\x00")
        InstallTestBase.FAKE_PROC_WITH_STEAM = str(proc)

    def snapshot(self, root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }


# ------------------------------------------------------------------- A1 tests


class A1InstallTest(InstallTestBase):
    def test_plan_is_viable_for_a_d3d12_game(self) -> None:
        game = self.sandbox.game()
        self.sandbox.stub_model()
        plan = a1_bridge.plan(self.sandbox.paths, game, language='en')
        self.assertTrue(plan.viable, [c.detail for c in plan.checks.blockers])
        self.assertEqual(game.rendering_api, "DirectX 12")
        self.assertEqual(game.bitness, 64)

    def test_launch_options_follow_the_proton_build(self) -> None:
        game = self.sandbox.game()
        options, note = a1_bridge.launch_options(game)
        self.assertIn("PROTON_FORCE_NVAPI=1", options)
        self.assertIn('WINEDLLOVERRIDES="dxgi=n,b"', options)
        self.assertIn("custom Proton", note)

        game.proton_tool = "Proton 9.0"
        options, note = a1_bridge.launch_options(game)
        self.assertIn("PROTON_ENABLE_NVAPI=1", options)
        self.assertNotIn("PROTON_FORCE_NVAPI", options)

    def test_install_then_rollback_restores_the_directory(self) -> None:
        game = self.sandbox.game()
        self.sandbox.stub_model()
        before = self.snapshot(self.sandbox.install_dir)

        result = a1_bridge.install(
            self.sandbox.paths, game, verify_against_upstream=False, skip_download=True, proc_root=self.EMPTY_PROC, logger=lambda *_: None
        )

        self.assertIsNotNone(result.journal_id)
        for name in (a1_bridge.BRIDGE_ADDON, a1_bridge.ADDON_DLL, a1_bridge.ADDON_FORWARDER):
            self.assertTrue((self.sandbox.exe_dir / name).is_file(), name)
        self.assertTrue((self.sandbox.exe_dir / a1_bridge.BRIDGE_CFG).is_file())
        self.assertTrue((self.sandbox.exe_dir / model.MODEL_NAME).is_file())

        cfg = (self.sandbox.exe_dir / a1_bridge.BRIDGE_CFG).read_text()
        self.assertIn("unwrap=0", cfg)
        self.assertIn("synth=0", cfg)  # the game has its own DLSS

        lines = rollback_journal(self.sandbox.paths, result.journal_id)
        self.assertTrue(lines)
        self.assertEqual(self.snapshot(self.sandbox.install_dir), before)

    def test_mid_install_failure_restores_game_steam_and_route_state(self) -> None:
        game = self.sandbox.game()
        self.sandbox.stub_model()
        config = self.sandbox.steam / "userdata/1/config/localconfig.vdf"
        route_state = providers.route_state_path(self.sandbox.paths, game.key, "a1")
        route_state.write_text('{"version": 1, "custom": "keep"}')
        before_game = self.snapshot(self.sandbox.install_dir)
        before_config = config.read_bytes()
        before_state = route_state.read_bytes()
        original = a1_bridge.FileJournal.install_file
        calls = 0

        def fail_second(journal, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second file failure")
            return original(journal, *args, **kwargs)

        # Automatic rollback checks Steam independently of install's proc_root.
        # This fabricated Steam library must not depend on the host Steam client.
        with mock.patch.object(a1_bridge.FileJournal, "install_file", fail_second), \
                mock.patch("nvfku.steamconfig.running_steam_processes", return_value=[]):
            with self.assertRaisesRegex(OSError, "simulated second file failure"):
                a1_bridge.install(
                    self.sandbox.paths, game, verify_against_upstream=False,
                    skip_download=True, proc_root=self.EMPTY_PROC, logger=lambda *_: None,
                )
        self.assertEqual(self.snapshot(self.sandbox.install_dir), before_game)
        self.assertEqual(config.read_bytes(), before_config)
        self.assertEqual(route_state.read_bytes(), before_state)

    def test_install_is_refused_without_a_model(self) -> None:
        game = self.sandbox.game()
        model.set_discovery_override(lambda *_: [])
        with self.assertRaises(InstallRefused) as ctx:
            a1_bridge.install(
                self.sandbox.paths, game, verify_against_upstream=False, skip_download=True, proc_root=self.EMPTY_PROC, logger=lambda *_: None
            )
        self.assertIn("nvngx_dlssnr.dll", str(ctx.exception))

    def test_nothing_is_written_when_refused(self) -> None:
        game = self.sandbox.game()
        model.set_discovery_override(lambda *_: [])
        before = self.snapshot(self.sandbox.install_dir)
        with self.assertRaises(InstallRefused):
            a1_bridge.install(
                self.sandbox.paths, game, verify_against_upstream=False, skip_download=True, proc_root=self.EMPTY_PROC, logger=lambda *_: None
            )
        self.assertEqual(self.snapshot(self.sandbox.install_dir), before)

    def test_vulkan_game_is_refused(self) -> None:
        (self.sandbox.exe_dir / "TestGame.exe").write_bytes(
            minimal_pe(imports=("vulkan-1.dll",))
        )
        game = self.sandbox.game()
        self.sandbox.stub_model()
        self.assertEqual(game.rendering_api, "Vulkan")
        plan = a1_bridge.plan(self.sandbox.paths, game, language='en')
        self.assertFalse(plan.viable)
        with self.assertRaises(InstallRefused):
            a1_bridge.install(
                self.sandbox.paths, game, verify_against_upstream=False, skip_download=True, proc_root=self.EMPTY_PROC, logger=lambda *_: None
            )

    def test_untested_model_raises_a_warning_but_still_installs(self) -> None:
        game = self.sandbox.game()
        self.sandbox.stub_model(verdict="untested")
        result = a1_bridge.install(
            self.sandbox.paths, game, verify_against_upstream=False, skip_download=True, proc_root=self.EMPTY_PROC, logger=lambda *_: None
        )
        self.assertTrue(any("not the measured-stable build" in w for w in result.warnings))

    def test_model_already_beside_the_executable_is_not_copied(self) -> None:
        """An existing model is left byte-identical and gets no journal entry.

        Listing a copy onto itself as an action would be misleading, and a
        journal entry for a file the install never touched would let a rollback
        remove a model that was already there.
        """
        game = self.sandbox.game()
        self.sandbox.stub_model(inside_game=True)
        original = (self.sandbox.exe_dir / model.MODEL_NAME).read_bytes()

        route_plan = a1_bridge.plan(self.sandbox.paths, game, language='en')
        model_actions = [
            a for a in route_plan.actions
            if a.kind == "copy" and a.destination.endswith(model.MODEL_NAME)
        ]
        self.assertTrue(model_actions, "the plan should still mention the model")
        self.assertTrue(model_actions[0].optional, "a copy onto itself is not required")

        result = a1_bridge.install(
            self.sandbox.paths, game, verify_against_upstream=False, skip_download=True, proc_root=self.EMPTY_PROC, logger=lambda *_: None
        )
        self.assertEqual((self.sandbox.exe_dir / model.MODEL_NAME).read_bytes(), original)
        self.assertTrue(
            any("left unchanged" in n for n in result.notes),
            f"the result should say the model was left alone: {result.notes}",
        )

        journals = list(self.sandbox.paths.backups_root().glob("*/*/manifest.json"))
        self.assertEqual(len(journals), 1)
        manifest = json.loads(journals[0].read_text())
        model_ops = [op for op in manifest["operations"] if op["path"].endswith(model.MODEL_NAME)]
        self.assertEqual(model_ops, [], model_ops)

    def test_route_state_is_written_and_reused(self) -> None:
        game = self.sandbox.game()
        self.sandbox.stub_model()
        result = a1_bridge.install(
            self.sandbox.paths, game, verify_against_upstream=False, skip_download=True, proc_root=self.EMPTY_PROC, logger=lambda *_: None
        )
        state_file = providers.route_state_path(self.sandbox.paths, game.key, "a1")
        self.assertTrue(state_file.is_file())
        state = json.loads(state_file.read_text())
        self.assertEqual(state["journal_id"], result.journal_id)
        self.assertEqual(state["model_verdict"], "tested")

    def test_substitute_path_sets_synth_when_the_game_has_no_dlss(self) -> None:
        (self.sandbox.exe_dir / "nvngx_dlss.dll").unlink()
        game = self.sandbox.game()
        self.sandbox.stub_model()
        a1_bridge.install(
            self.sandbox.paths, game, verify_against_upstream=False, skip_download=True, proc_root=self.EMPTY_PROC, logger=lambda *_: None
        )
        cfg = (self.sandbox.exe_dir / a1_bridge.BRIDGE_CFG).read_text()
        self.assertIn("synth=1", cfg)


# ------------------------------------------------------------------- A2 tests


class A2InstallTest(InstallTestBase):
    def _stub_archive(self) -> None:
        """Replace download+extract with a prepared extraction directory."""
        version = "v-test"
        extract_dir = self.sandbox.paths.download_cache() / "optiscaler" / f"extract-{version}"
        (extract_dir / "OptiScaler").mkdir(parents=True, exist_ok=True)
        (extract_dir / "OptiScaler" / "OptiScaler.dll").write_bytes(b"proxy-dll")
        (extract_dir / "OptiScaler" / "dxgi.dll").write_bytes(b"dxgi-proxy")
        (extract_dir / "OptiScaler" / "OptiScaler.ini").write_text("[Upscalers]\nDx12Upscaler=dlss\n")

        component = providers.Component(
            id="optiscaler",
            name="OptiScaler.7z",
            version=version,
            url="https://example.invalid/OptiScaler.7z",
            filename="OptiScaler.7z",
        )
        archive = component.local_path(self.sandbox.paths)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"7z-archive-placeholder")

        original = providers.resolve_rolling

        def resolver(key: str, **kwargs):
            if key == "optiscaler":
                return component
            return original(key, **kwargs)

        providers.resolve_rolling = resolver
        self.addCleanup(setattr, providers, "resolve_rolling", original)

        # The extraction is stubbed too: a placeholder file is not a valid 7z
        # archive, and this test is about the filesystem contract, not about
        # whether p7zip works.
        original_extract = providers.extract_7z

        def extractor(_archive, dest, **kwargs):
            dest.mkdir(parents=True, exist_ok=True)
            return [p for p in dest.rglob("*") if p.is_file()]

        providers.extract_7z = extractor
        self.addCleanup(setattr, providers, "extract_7z", original_extract)

    def test_install_then_rollback_restores_the_directory(self) -> None:
        self._stub_archive()
        game = self.sandbox.game()
        self.sandbox.stub_model()
        before = self.snapshot(self.sandbox.install_dir)

        result = a2_optiscaler.install(
            self.sandbox.paths, game, working_scale=75, skip_download=True, logger=lambda *_: None
        )

        proxy = self.sandbox.exe_dir / "dxgi.dll"
        self.assertTrue(proxy.is_file())
        # The canonical payload is installed under the name we chose, not a
        # pre-renamed copy from the archive.
        self.assertEqual(proxy.read_bytes(), b"proxy-dll")
        ini = (self.sandbox.exe_dir / "OptiScaler.ini").read_text()
        self.assertIn("[DlssNr]", ini)
        self.assertIn("WorkingScale=75", ini)
        self.assertIn("Dx12Upscaler=dlss", ini)  # the user's own keys survive

        state = json.loads(providers.route_state_path(self.sandbox.paths, game.key, "a2").read_text())
        self.assertEqual(state["proxy_name"], "dxgi.dll")
        self.assertEqual(state["working_scale"], 75)

        rollback_journal(self.sandbox.paths, result.journal_id)
        self.assertEqual(self.snapshot(self.sandbox.install_dir), before)

    def test_mid_install_failure_restores_game_and_route_state(self) -> None:
        self._stub_archive()
        game = self.sandbox.game()
        self.sandbox.stub_model()
        route_state = providers.route_state_path(self.sandbox.paths, game.key, "a2")
        route_state.write_text('{"version": 1, "custom": "keep"}')
        before_game = self.snapshot(self.sandbox.install_dir)
        before_state = route_state.read_bytes()
        original = a2_optiscaler.FileJournal.install_file
        calls = 0

        def fail_second(journal, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated A2 model failure")
            return original(journal, *args, **kwargs)

        with mock.patch.object(a2_optiscaler.FileJournal, "install_file", fail_second):
            with self.assertRaisesRegex(OSError, "simulated A2 model failure"):
                a2_optiscaler.install(
                    self.sandbox.paths, game, skip_download=True, logger=lambda *_: None,
                )
        self.assertEqual(self.snapshot(self.sandbox.install_dir), before_game)
        self.assertEqual(route_state.read_bytes(), before_state)

    def test_reinstall_reuses_the_recorded_proxy_name(self) -> None:
        self._stub_archive()
        game = self.sandbox.game()
        self.sandbox.stub_model()
        a2_optiscaler.install(self.sandbox.paths, game, skip_download=True, logger=lambda *_: None)
        # A second install must not pick a different name and shadow the first.
        result = a2_optiscaler.install(self.sandbox.paths, game, skip_download=True, logger=lambda *_: None)
        self.assertTrue((self.sandbox.exe_dir / "dxgi.dll").is_file())
        state = json.loads(providers.route_state_path(self.sandbox.paths, game.key, "a2").read_text())
        self.assertEqual(state["proxy_name"], "dxgi.dll")
        self.assertEqual(state["journal_id"], result.journal_id)

    def test_working_scale_is_validated(self) -> None:
        self._stub_archive()
        game = self.sandbox.game()
        self.sandbox.stub_model()
        for bad in (10, 101, 0):
            with self.assertRaises(InstallRefused):
                a2_optiscaler.install(
                    self.sandbox.paths, game, working_scale=bad, skip_download=True, logger=lambda *_: None
                )

    def test_all_proxy_names_taken_is_refused(self) -> None:
        self._stub_archive()
        game = self.sandbox.game()
        self.sandbox.stub_model()
        for name in a2_optiscaler.PROXY_CHOICES:
            (self.sandbox.exe_dir / name).write_bytes(b"other-tool")
        with self.assertRaises(InstallRefused) as ctx:
            a2_optiscaler.install(self.sandbox.paths, game, skip_download=True, logger=lambda *_: None)
        self.assertIn("already taken", str(ctx.exception))




class InstallJsonContractTest(InstallTestBase):
    """`install --json` must emit one JSON object on stdout, always.

    The Flutter UI decodes this document instead of scraping the human-readable
    rendering, so a stray print on stdout breaks the UI silently. These tests
    pin the shape of every exit path.
    """

    def _run_json(self, *args: str) -> tuple[int, dict]:
        import io
        import json
        from contextlib import redirect_stdout

        from nvfku.__main__ import main

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--json", *args])
        text = buffer.getvalue().strip()
        self.assertTrue(text, f"install --json printed nothing (exit {code})")
        return code, json.loads(text)

    def _args(self, *extra: str) -> list[str]:
        return [
            "--steam-root", str(self.sandbox.steam),
            "--state-dir", str(self.sandbox.state),
            "install", "999999", "a1", *extra,
        ]

    def test_blocked_route_is_a_json_document(self) -> None:
        (self.sandbox.exe_dir / "TestGame.exe").write_bytes(
            minimal_pe(imports=("vulkan-1.dll",))
        )
        self.sandbox.stub_model()
        code, document = self._run_json(*self._args())
        self.assertEqual(code, 2)
        self.assertFalse(document["ok"])
        self.assertIn("blockers", document)
        self.assertTrue(document["blockers"])
        # The one-field reader still gets the specific reason.
        self.assertIn("rendering API", document["refused"])

    def test_missing_confirmation_is_a_json_document(self) -> None:
        self.sandbox.stub_model()
        code, document = self._run_json(*self._args("--skip-download"))
        self.assertEqual(code, 3)
        self.assertTrue(document["needs_confirmation"])
        self.assertIn("plan", document)

    def test_successful_install_is_a_json_document(self) -> None:
        # The install reads /proc to decide whether Steam would revert a launch
        # option write. Pointing it at an empty directory keeps the test from
        # depending on whether the machine under test has Steam open.
        self._env = mock.patch.dict(
            os.environ, {"NVFKU_PROC_ROOT": "/nonexistent-proc"}
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        self.sandbox.stub_model()
        code, document = self._run_json(
            *self._args("--yes", "--skip-download", "--no-upstream-verify")
        )
        self.assertEqual(code, 0, document)
        self.assertTrue(document["ok"])
        self.assertIn("plan", document)
        self.assertIn("result", document)
        self.assertTrue(document["result"]["journal_id"])

    def test_runtime_refusal_is_a_json_document(self) -> None:
        # No model at all: the plan is viable-but-warned, install refuses.
        model.set_discovery_override(lambda *_: [])
        code, document = self._run_json(
            *self._args("--yes", "--skip-download", "--no-upstream-verify")
        )
        self.assertEqual(code, 2)
        self.assertFalse(document["ok"])
        self.assertIn("refused", document)
        self.assertIn("nvngx_dlssnr.dll", document["refused"])

    def test_partial_rollback_blocks_reinstall_until_recovery_finishes(self) -> None:
        from nvfku.journal import FileJournal

        self.sandbox.stub_model()
        game = self.sandbox.game()
        target = self.sandbox.exe_dir / "rollback-conflict.dll"
        completed = self.sandbox.exe_dir / "rollback-first.dll"
        journal = FileJournal(self.sandbox.paths, game.install_dir, "a1", game_key=game.key)
        journal.write_text(target, "INSTALLED")
        journal.write_text(completed, "INSTALLED")
        journal.finish()
        target.write_text("USER EDIT")
        with mock.patch.dict(os.environ, {"HOME": str(self.sandbox.home),
                                          "NVFKU_PROC_ROOT": self.EMPTY_PROC}):
            code, report = self._run_json(
                "--state-dir", str(self.sandbox.state), "rollback", journal.journal_id,
            )
            self.assertEqual(code, 1)
            self.assertFalse(report["ok"])
            self.assertFalse(completed.exists())
            self.assertEqual(target.read_text(), "USER EDIT")
            before = self.snapshot(game.install_dir)
            code, refused = self._run_json(
                *self._args("--yes", "--skip-download", "--no-upstream-verify")
            )
            self.assertEqual(code, 2, refused)
            self.assertIn("Incomplete transaction", refused["refused"])
            self.assertEqual(self.snapshot(game.install_dir), before)
            code, backups = self._run_json("--state-dir", str(self.sandbox.state), "backups")
            self.assertEqual(code, 0)
            self.assertTrue(backups[0]["rollback_started"])
            self.assertTrue(backups[0]["finished"])
            self.assertFalse(backups[0]["rolled_back"])
            # The user resolves the conflict; retry finishes the same journal.
            target.write_text("INSTALLED")
            code, recovered = self._run_json(
                "--state-dir", str(self.sandbox.state), "rollback", journal.journal_id,
            )
            self.assertEqual(code, 0, recovered)
            self.assertTrue(recovered["ok"])
            code, installed = self._run_json(
                *self._args("--yes", "--skip-download", "--no-upstream-verify")
            )
            self.assertEqual(code, 0, installed)
            self.assertTrue(installed["ok"])

    def test_legacy_partial_rollback_is_still_detected_by_backups_and_install(self) -> None:
        from nvfku.journal import FileJournal

        self.sandbox.stub_model()
        game = self.sandbox.game()
        target = self.sandbox.exe_dir / "legacy-remaining.dll"
        journal = FileJournal(self.sandbox.paths, game.install_dir, "a1", game_key=game.key)
        journal.write_text(target, "INSTALLED")
        journal.note("legacy rollback already passed this note")
        journal.finish()
        # Seed the persisted format from before rollback_started was introduced.
        manifest_path = journal.dir / "manifest.json"
        legacy = json.loads(manifest_path.read_text())
        legacy.pop("rollback_started")
        legacy["operations"][-1]["rollback_done"] = True
        manifest_path.write_text(json.dumps(legacy))
        with mock.patch.dict(os.environ, {"HOME": str(self.sandbox.home),
                                          "NVFKU_PROC_ROOT": self.EMPTY_PROC}):
            code, backups = self._run_json("--state-dir", str(self.sandbox.state), "backups")
            self.assertEqual(code, 0)
            self.assertTrue(backups[0]["rollback_started"])
            code, refused = self._run_json(
                *self._args("--yes", "--skip-download", "--no-upstream-verify")
            )
            self.assertEqual(code, 2, refused)
            self.assertIn("Incomplete transaction", refused["refused"])
            self.assertEqual(target.read_text(), "INSTALLED")

    def test_rollback_and_retry_do_not_depend_on_writable_display_index(self) -> None:
        from nvfku.journal import FileJournal

        game = self.sandbox.game()
        target = self.sandbox.exe_dir / "index-fault.dll"
        target.write_text("ORIGINAL")
        journal = FileJournal(self.sandbox.paths, game.install_dir, "a1", game_key=game.key)
        journal.write_text(target, "INSTALLED")
        journal.finish()
        # Fault injection at the filesystem boundary: an optional display cache
        # cannot be replaced when its filename is occupied by a directory.
        index = self.sandbox.paths.backups_root() / "index.json"
        self.assertEqual(index.resolve().parent, self.sandbox.paths.backups_root().resolve())
        index.unlink()
        index.mkdir()
        with mock.patch.dict(os.environ, {"HOME": str(self.sandbox.home)}):
            code, report = self._run_json(
                "--state-dir", str(self.sandbox.state), "rollback", journal.journal_id,
            )
            self.assertEqual(code, 0, report)
            self.assertTrue(report["ok"])
            self.assertEqual(target.read_text(), "ORIGINAL")
            code, backups = self._run_json("--state-dir", str(self.sandbox.state), "backups")
            self.assertEqual(code, 0)
            self.assertTrue(backups[0]["rolled_back"])
            code, retried = self._run_json(
                "--state-dir", str(self.sandbox.state), "rollback", journal.journal_id,
            )
            self.assertEqual(code, 0, retried)
            self.assertTrue(retried["ok"])
            self.assertEqual(target.read_text(), "ORIGINAL")

    def test_retry_retains_successful_undo_after_transient_manifest_write_failure(self) -> None:
        from nvfku.journal import FileJournal

        game = self.sandbox.game()
        target = self.sandbox.exe_dir / "checkpoint-fault.dll"
        target.write_text("ORIGINAL")
        journal = FileJournal(self.sandbox.paths, game.install_dir, "a1", game_key=game.key)
        journal.write_text(target, "INSTALLED")
        journal.finish()
        real_replace = os.replace
        manifest_writes = 0
        def fail_one_checkpoint(source, destination, *args, **kwargs):
            nonlocal manifest_writes
            if Path(destination).name == "manifest.json":
                manifest_writes += 1
                # Intent is the first write; the successful undo's checkpoint is second.
                if manifest_writes == 2:
                    raise OSError("transient acceptance checkpoint fault")
            return real_replace(source, destination, *args, **kwargs)
        with mock.patch.dict(os.environ, {"HOME": str(self.sandbox.home)}):
            # Inject at the filesystem replace boundary, not into journal internals.
            with mock.patch("nvfku.paths.os.replace", side_effect=fail_one_checkpoint):
                code, report = self._run_json(
                    "--state-dir", str(self.sandbox.state), "rollback", journal.journal_id,
                )
            self.assertEqual(code, 1, report)
            self.assertFalse(report["ok"])
            self.assertEqual(target.read_text(), "ORIGINAL")
            code, retried = self._run_json(
                "--state-dir", str(self.sandbox.state), "rollback", journal.journal_id,
            )
            self.assertEqual(code, 0, retried)
            self.assertTrue(retried["ok"])
            self.assertEqual(target.read_text(), "ORIGINAL")

    def test_rollback_failure_is_nonzero_json_and_can_be_retried(self) -> None:
        from nvfku.journal import FileJournal, load_journal

        game = self.sandbox.game()
        destination = self.sandbox.exe_dir / "rollback-test.dll"
        destination.write_bytes(b"original")
        source = self.sandbox.root / "replacement.dll"
        source.write_bytes(b"replacement")
        journal = FileJournal(self.sandbox.paths, game.install_dir, "a1", game_key=game.key)
        journal.install_file(source, destination)
        backup = journal.dir / load_journal(self.sandbox.paths, journal.journal_id).operations[0].backup
        backup.unlink()
        code, document = self._run_json(
            "--state-dir", str(self.sandbox.state), "rollback", journal.journal_id,
        )
        self.assertEqual(code, 1)
        self.assertFalse(document["ok"])
        self.assertTrue(document["failed"])
        self.assertEqual(destination.read_bytes(), b"replacement")
        backup.write_bytes(b"original")
        code, document = self._run_json(
            "--state-dir", str(self.sandbox.state), "rollback", journal.journal_id,
        )
        self.assertEqual(code, 0)
        self.assertTrue(document["ok"])
        self.assertEqual(destination.read_bytes(), b"original")

    def test_unknown_game_is_a_json_document(self) -> None:
        code, document = self._run_json(
            "--steam-root", str(self.sandbox.steam),
            "--state-dir", str(self.sandbox.state),
            "install", "no-such-game", "a1",
        )
        self.assertEqual(code, 1)
        self.assertFalse(document["ok"])
        self.assertIn("error", document)


if __name__ == "__main__":
    unittest.main()
