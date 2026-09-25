"""Minimal PE (Portable Executable) reader.

Written by hand rather than shelling out to ``objdump``/``pestr`` so the engine
has no external tool dependency and can run the same way on a machine with no
mingw installed.  We only need four things:

*   bitness (32 vs 64) - decides whether a 32-bit Feeder helper is required,
*   the import table - the authoritative answer for "which graphics API",
*   delay-load imports - engines keep a stale ``d3d9.dll`` import long after
    they stopped drawing with it, and DLSS5-Autopilot's scanner only accepts a
    D3D9 verdict after checking the delay-load table too,
*   a bounded string scan of ``.rdata`` for renderer names that never appear in
    an import table (Vulkan via a loader, D3D12 through an Agility SDK).

Parsing is defensive: a malformed header returns ``None`` instead of raising,
because this runs over every executable in every Steam library.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_FILE_MACHINE_I386 = 0x014C
IMAGE_FILE_MACHINE_AMD64 = 0x8664
IMAGE_FILE_MACHINE_ARM64 = 0xAA64

_PE_OFFSET = 0x3C


@dataclass
class PEFile:
    path: Path
    machine: int
    bitness: int
    imports: list[str] = field(default_factory=list)
    delay_imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    strings: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    is_dll: bool = False

    @property
    def import_dlls(self) -> list[str]:
        return sorted({name.lower() for name in self.imports})

    @property
    def all_dlls(self) -> list[str]:
        return sorted({name.lower() for name in self.imports + self.delay_imports})

    def has_string(self, needle: str) -> bool:
        needle = needle.lower()
        return any(needle in s.lower() for s in self.strings)

    def has_import(self, needle: str) -> bool:
        needle = needle.lower()
        return any(needle in name for name in self.imports + self.delay_imports)

    def summary(self) -> dict:
        return {
            "path": str(self.path),
            "bitness": self.bitness,
            "is_dll": self.is_dll,
            "import_dlls": self.import_dlls,
            "delay_import_dlls": sorted({n.lower() for n in self.delay_imports}),
        }


def _cstring(blob: bytes, offset: int, limit: int = 512) -> str:
    if offset < 0 or offset >= len(blob):
        return ""
    end = blob.find(b"\x00", offset, min(len(blob), offset + limit))
    if end < 0:
        end = min(len(blob), offset + limit)
    return blob[offset:end].decode("latin-1", "replace")


def _rva_to_offset(rva: int, sections: list[tuple[int, int, int, int]]) -> int | None:
    """sections: (virtual_address, virtual_size, raw_pointer, raw_size)"""
    for va, vsize, raw, raw_size in sections:
        span = max(vsize, raw_size)
        if va <= rva < va + span:
            return raw + (rva - va)
    return None


def read_pe(path: str | Path) -> PEFile | None:
    path = Path(path)
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    if len(blob) < 0x40 or blob[:2] != b"MZ":
        return None
    try:
        pe_off = struct.unpack_from("<I", blob, _PE_OFFSET)[0]
        if pe_off + 24 > len(blob) or blob[pe_off : pe_off + 4] != b"PE\x00\x00":
            return None
        machine, n_sections, _, _, _, opt_size, characteristics = struct.unpack_from(
            "<HHIIIHH", blob, pe_off + 4
        )
    except struct.error:
        return None

    bitness = {IMAGE_FILE_MACHINE_I386: 32, IMAGE_FILE_MACHINE_AMD64: 64, IMAGE_FILE_MACHINE_ARM64: 64}.get(
        machine, 0
    )
    if bitness == 0:
        return None

    opt_off = pe_off + 24
    if opt_off + 2 > len(blob):
        return None
    magic = struct.unpack_from("<H", blob, opt_off)[0]
    is_pe32_plus = magic == 0x20B

    # Data directories: export (0), import (1), delay import (13).
    dd_off = opt_off + (112 if is_pe32_plus else 96)
    directories: list[tuple[int, int]] = []
    for index in range(16):
        try:
            rva, size = struct.unpack_from("<II", blob, dd_off + index * 8)
        except struct.error:
            rva, size = 0, 0
        directories.append((rva, size))

    section_off = opt_off + opt_size
    sections: list[tuple[int, int, int, int]] = []
    section_names: list[str] = []
    for index in range(n_sections):
        base = section_off + index * 40
        if base + 40 > len(blob):
            break
        name = _cstring(blob, base, 8)
        vsize, va, raw_size, raw = struct.unpack_from("<IIII", blob, base + 8)
        sections.append((va, vsize, raw, raw_size))
        section_names.append(name)

    pe = PEFile(
        path=path,
        machine=machine,
        bitness=bitness,
        is_dll=bool(characteristics & 0x2000),
        sections=section_names,
    )

    pe.imports = _read_import_names(blob, directories[1][0], sections)
    pe.delay_imports = _read_delay_import_names(blob, directories[13][0], sections)
    pe.exports = _read_export_names(blob, directories[0][0], sections, bitness)
    pe.strings = _scan_strings(blob, sections)
    return pe


def _read_import_names(blob: bytes, rva: int, sections: list[tuple[int, int, int, int]]) -> list[str]:
    if not rva:
        return []
    base = _rva_to_offset(rva, sections)
    if base is None:
        return []
    names: list[str] = []
    cursor = base
    while True:
        try:
            entry = blob[cursor : cursor + 20]
        except IndexError:
            break
        if len(entry) < 20:
            break
        name_rva = struct.unpack_from("<I", entry, 12)[0]
        if name_rva == 0:
            break
        offset = _rva_to_offset(name_rva, sections)
        if offset is not None:
            names.append(_cstring(blob, offset))
        cursor += 20
    return names


def _read_delay_import_names(
    blob: bytes, rva: int, sections: list[tuple[int, int, int, int]]
) -> list[str]:
    if not rva:
        return []
    base = _rva_to_offset(rva, sections)
    if base is None:
        return []
    names: list[str] = []
    cursor = base
    while True:
        entry = blob[cursor : cursor + 32]
        if len(entry) < 32:
            break
        attrs, name_rva = struct.unpack_from("<II", entry, 0)
        if not (attrs & 1) and name_rva == 0:  # not RVA-based and no name -> end
            break
        if attrs & 1 and name_rva:
            offset = _rva_to_offset(name_rva, sections)
            if offset is not None:
                names.append(_cstring(blob, offset))
        cursor += 32
    return names


def _read_export_names(
    blob: bytes, rva: int, sections: list[tuple[int, int, int, int]], bitness: int
) -> list[str]:
    """Exported *symbol* names.

    We do not resolve addresses; we only want to know whether an executable
    exports NGX entry points itself, which happens for games that statically
    link the NGX SDK.
    """
    if not rva:
        return []
    base = _rva_to_offset(rva, sections)
    if base is None or base + 40 > len(blob):
        return []
    try:
        _, _, _, name_count, _, names_rva = struct.unpack_from("<IIIIII", blob, base + 16)
    except struct.error:
        return []
    names_off = _rva_to_offset(names_rva, sections)
    if names_off is None:
        return []
    out: list[str] = []
    for index in range(min(name_count, 4096)):
        try:
            sym_rva = struct.unpack_from("<I", blob, names_off + index * 4)[0]
        except struct.error:
            break
        offset = _rva_to_offset(sym_rva, sections)
        if offset is not None:
            out.append(_cstring(blob, offset))
    return out


# Strings an import table cannot express.  A game using the D3D12 Agility SDK
# loads d3d12core.dll at runtime; a Vulkan game points at the loader by name.
_INTERESTING_STRINGS = (
    b"d3d12core.dll",
    b"d3d12.dll",
    b"d3d11.dll",
    b"d3d10",
    b"d3d9.dll",
    b"dxgi.dll",
    b"vulkan-1.dll",
    b"vulkan-1",
    b"VK_ICD_FILENAMES",
    b"vkCreateInstance",
    b"opengl32.dll",
    b"wglCreateContext",
    b"nvngx_dlss",
    b"NVSDK_NGX",
    b"sl.interposer",
    b"sl.dlss",
    b"DLSS",
    b"libEGL.dll",
    b"VK_LAYER_",
    b"VK_INSTANCE_LAYERS",
)


def _scan_strings(blob: bytes, sections: list[tuple[int, int, int, int]], budget: int = 64 * 1024 * 1024) -> list[str]:
    """Scan readable sections for the markers above, upper-bounded.

    Game executables can be hundreds of MiB.  We cap total scanned bytes and
    only look in sections whose name suggests data or code.
    """
    found: list[str] = []
    scanned = 0
    for va, vsize, raw, raw_size in sections:
        if raw == 0 or raw_size == 0:
            continue
        chunk = blob[raw : raw + min(raw_size, vsize or raw_size)]
        if not chunk:
            continue
        scanned += len(chunk)
        lowered = chunk.lower()
        for needle in _INTERESTING_STRINGS:
            if needle.lower() in lowered:
                found.append(needle.decode("latin-1"))
        if scanned >= budget:
            break
    return sorted(set(found))
