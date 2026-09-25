"""Detection tests: VDF parsing, PE reading, API classification, INI merging."""

from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from nvfku import steam
from nvfku.pe import read_pe
from nvfku.route.a2_optiscaler import render_ini


# --------------------------------------------------------------- VDF parsing


class VdfTest(unittest.TestCase):
    def test_tokenize_strips_comments_and_handles_escapes(self) -> None:
        text = '''
        // a comment
        "libraryfolders"
        {
            "0"
            {
                "path"      "/home/user/.local/share/Steam"
                "label"     ""
            }
            "1"
            {
                // another comment
                "path"      "D:\\\\Games\\\\SteamLibrary"
            }
        }
        '''
        data = steam.parse_vdf(text)
        folders = data["libraryfolders"]
        self.assertEqual(folders["0"]["path"], "/home/user/.local/share/Steam")
        self.assertEqual(folders["1"]["path"], r"D:\Games\SteamLibrary")

    def test_tokenize_handles_unquoted_names(self) -> None:
        data = steam.parse_vdf('AppState { appid 123 name "Some Game" }')
        self.assertEqual(data["AppState"]["appid"], "123")
        self.assertEqual(data["AppState"]["name"], "Some Game")


# ------------------------------------------------------------------ PE parse


def make_minimal_pe(*, machine: int = 0x8664, imports: tuple[str, ...] = ()) -> bytes:
    """A syntactically valid PE with one import descriptor per requested name.

    Enough for :func:`read_pe` to walk the import table: DOS header, PE header,
    one section covering everything, an import directory and NUL-terminated
    DLL-name strings.
    """
    opt_size = 0xF0  # PE32+ optional header size
    headers_size = 0x200
    section_rva = 0x1000
    section_raw = headers_size

    # Lay the import table and names out inside the single section.
    blob = bytearray(headers_size)
    data_off = (len(imports) + 1) * 20  # descriptors then names
    names_blob = bytearray()
    descriptors = b""
    for name in imports:
        name_rva = section_rva + data_off + len(names_blob)
        # Import descriptor: OriginalFirstThunk, TimeDateStamp, ForwarderChain,
        # Name, FirstThunk
        descriptors += struct.pack("<IIIII", 0, 0, 0, name_rva, 0)
        names_blob += name.encode("ascii") + b"\x00"
    descriptors += b"\x00" * 20  # terminating descriptor
    import_rva = section_rva
    section = bytes(descriptors) + bytes(0) * 0 + bytes(names_blob)

    blob = bytearray(headers_size + len(section))
    blob[0:2] = b"MZ"
    struct.pack_into("<I", blob, 0x3C, 0x40)

    pe_off = 0x40
    blob[pe_off : pe_off + 4] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", blob, pe_off + 4, machine, 1, 0, 0, 0, opt_size, 0x0022)
    opt_off = pe_off + 24
    struct.pack_into("<H", blob, opt_off, 0x20B)  # PE32+
    dd_off = opt_off + 112
    # Data directory 1 = import table
    struct.pack_into("<II", blob, dd_off + 1 * 8, import_rva, len(descriptors))

    section_off = opt_off + opt_size
    blob[section_off : section_off + 8] = b".rdata\x00\x00"
    struct.pack_into("<IIII", blob, section_off + 8, len(section), section_rva, len(section), section_raw)
    blob[section_raw : section_raw + len(section)] = section
    return bytes(blob)


class PETest(unittest.TestCase):
    def test_bitness_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x64.exe"
            path.write_bytes(make_minimal_pe(machine=0x8664))
            pe = read_pe(path)
            self.assertIsNotNone(pe)
            self.assertEqual(pe.bitness, 64)

            path32 = Path(tmp) / "x86.exe"
            path32.write_bytes(make_minimal_pe(machine=0x014C))
            self.assertEqual(read_pe(path32).bitness, 32)

    def test_import_dlls_are_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.exe"
            path.write_bytes(make_minimal_pe(imports=("d3d12.dll", "sl.interposer.dll")))
            pe = read_pe(path)
            self.assertIn("d3d12.dll", pe.import_dlls)
            self.assertIn("sl.interposer.dll", pe.import_dlls)

    def test_non_pe_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "text.txt"
            path.write_text("not a pe file")
            self.assertIsNone(read_pe(path))

    def test_truncated_pe_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.exe"
            path.write_bytes(b"MZ" + b"\x00" * 10)
            self.assertIsNone(read_pe(path))


# ------------------------------------------------------------- classification


class ApiClassificationTest(unittest.TestCase):
    def _pe_with(self, imports: tuple[str, ...], strings: tuple[bytes, ...] = ()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "game.exe"
        path.write_bytes(make_minimal_pe(imports=imports))
        pe = read_pe(path)
        pe.strings = [s.decode() for s in strings]
        return pe

    def test_direct_d3d12_import(self) -> None:
        pe = self._pe_with(("d3d12.dll",))
        api, evidence = steam.classify_api(pe)
        self.assertEqual(api, "DirectX 12")
        self.assertTrue(any("d3d12" in item for item in evidence))

    def test_streamline_only_game_is_still_d3d12(self) -> None:
        """Cyberpunk 2077 imports sl.interposer.dll and no d3d12.dll.

        Measured on this machine: a direct-import-only classifier returns None
        for it, which would wrongly disqualify the game from every route.
        """
        pe = self._pe_with(("sl.interposer.dll", "libxess.dll", "ffx_backend_dx12_x64.dll"))
        api, _ = steam.classify_api(pe)
        self.assertEqual(api, "DirectX 12")

    def test_vulkan_by_string(self) -> None:
        pe = self._pe_with((), strings=(b"vulkan-1.dll",))
        api, _ = steam.classify_api(pe)
        self.assertEqual(api, "Vulkan")

    def test_direct_import_outranks_indirect(self) -> None:
        pe = self._pe_with(("d3d11.dll", "sl.dlss_dx12.dll"))
        api, _ = steam.classify_api(pe)
        self.assertEqual(api, "DirectX 11")

    def test_unknown_when_nothing_matches(self) -> None:
        pe = self._pe_with(("kernel32.dll", "user32.dll"))
        api, evidence = steam.classify_api(pe)
        self.assertIsNone(api)
        self.assertEqual(evidence, [])


class NonGameFilterTest(unittest.TestCase):
    def test_runtimes_are_not_games(self) -> None:
        for appid, name, install in (
            ("4628710", "Proton 11.0", "Proton 11.0"),
            ("1628350", "Steam Linux Runtime 3.0 (sniper)", "SteamLinuxRuntime_sniper"),
            ("228980", "Steamworks Common Redistributables", "Steamworks Shared"),
            ("1826330", "Proton EasyAntiCheat Runtime", "Proton EasyAntiCheat Runtime"),
        ):
            game = steam.Game(
                appid=appid,
                name=name,
                install_dir=Path("/tmp") / install,
                library=Path("/tmp"),
                steam_root=Path("/tmp"),
            )
            self.assertTrue(steam.is_non_game(game), f"{name} should not be a game")

    def test_a_real_game_passes(self) -> None:
        game = steam.Game(
            appid="1091500",
            name="Cyberpunk 2077",
            install_dir=Path("/tmp/cyberpunk"),
            library=Path("/tmp"),
            steam_root=Path("/tmp"),
            launch_exe=Path("/tmp/cyberpunk/bin/x64/Cyberpunk2077.exe"),
        )
        self.assertFalse(steam.is_non_game(game))


# ----------------------------------------------------------------- INI merge


class OptiScalerIniTest(unittest.TestCase):
    def test_generated_when_absent(self) -> None:
        text = render_ini(None, working_scale=75)
        self.assertIn("[DlssNr]", text)
        self.assertIn("WorkingScale=75", text)

    def test_existing_keys_are_updated_and_others_preserved(self) -> None:
        existing = (
            "[Upscalers]\n"
            "Dx12Upscaler=dlss\n"
            "\n"
            "[DlssNr]\n"
            "Enabled=false\n"
            "WorkingScale=100\n"
            "Custom=keepme\n"
            "\n"
            "[Other]\n"
            "Whatever=1\n"
        )
        text = render_ini(existing, working_scale=50)
        self.assertIn("Dx12Upscaler=dlss", text)
        self.assertIn("Whatever=1", text)
        self.assertIn("Custom=keepme", text)
        self.assertIn("Enabled=true", text)
        self.assertIn("WorkingScale=50", text)
        # Exactly one section header, and the values were replaced not appended.
        self.assertEqual(text.count("[DlssNr]"), 1)
        self.assertEqual(text.count("WorkingScale="), 1)

    def test_section_is_appended_when_missing(self) -> None:
        text = render_ini("[Upscalers]\nDx12Upscaler=dlss\n", working_scale=100)
        self.assertIn("[Upscalers]", text)
        self.assertIn("[DlssNr]", text)
        self.assertIn("WorkingScale=100", text)

    def test_missing_keys_are_added_to_an_existing_section(self) -> None:
        text = render_ini("[DlssNr]\nWorkingScale=100\n", working_scale=100)
        self.assertIn("Enabled=true", text)
        self.assertEqual(text.count("[DlssNr]"), 1)


if __name__ == "__main__":
    unittest.main()
