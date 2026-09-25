"""Steam library discovery and per-game detection.

Two things are being answered here, and they are different questions:

1.  **Where is the game?**  Parsed from Steam's VDF files, including the
    Proton prefix, because every route installs *into the prefix-aware game
    directory* and the launch options differ per Proton build.
2.  **What can be installed into it?**  Rendering API, bitness, and whether the
    game ships its own DLSS.  The API answer matters more than it looks: a
    Vulkan verdict disqualifies every ReShade-as-Vulkan-layer route on Wine
    (``winevulkan`` does not enumerate third-party layers at all), while a
    D3D11/D3D12 verdict keeps the local ``dxgi.dll`` route alive.
"""

from __future__ import annotations

import json
import os
import time
import re
from dataclasses import dataclass, field
from pathlib import Path

from .paths import Paths, atomic_write_text, human_size, iter_files
from .pe import PEFile, read_pe

# --------------------------------------------------------------- VDF parsing


def tokenize_vdf(text: str) -> list[str]:
    """Tokenize Valve's KeyValues format.

    Handles ``//`` comments, quoted strings with backslash escapes, and the
    unquoted-name form older installs use.
    """
    tokens: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in " \t\r\n":
            index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "/":
            newline = text.find("\n", index)
            index = length if newline < 0 else newline + 1
            continue
        if char in "{}":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            buffer: list[str] = []
            while index < length:
                current = text[index]
                if current == "\\" and index + 1 < length:
                    buffer.append(text[index + 1])
                    index += 2
                    continue
                if current == '"':
                    index += 1
                    break
                buffer.append(current)
                index += 1
            tokens.append("".join(buffer))
            continue
        start = index
        while index < length and text[index] not in ' \t\r\n"{}':
            index += 1
        tokens.append(text[start:index])
    return tokens


def _parse_block(tokens: list[str], index: int = 0) -> tuple[dict, int]:
    result: dict = {}
    while index < len(tokens):
        token = tokens[index]
        if token == "}":
            return result, index + 1
        key = token
        index += 1
        if index >= len(tokens):
            break
        value = tokens[index]
        if value == "{":
            nested, index = _parse_block(tokens, index + 1)
            result[key] = nested
            continue
        result[key] = value
        index += 1
    return result, index


def parse_vdf(text: str) -> dict:
    tokens = tokenize_vdf(text)
    parsed, _ = _parse_block(tokens)
    return parsed


# ------------------------------------------------------------- file sniffing


def file_contains(path: Path, needle: bytes, *, limit: int = 64 * 1024 * 1024) -> bool:
    """Whether a file contains a byte string, scanning only its head.

    Used to tell "this proxy DLL is ReShade" from "this proxy DLL is some other
    tool that happens to be named dxgi.dll" -- OptiScaler installs under the same
    names.  The limit is generous on purpose: measured against a real 25 MiB
    ReShade 6.8 proxy DLL, the product string sits past the 8 MiB mark, so a
    smaller cap produced a false negative and hid a working installation.
    """
    try:
        with open(path, "rb") as handle:
            return needle in handle.read(limit)
    except OSError:
        return False


# Proxy filenames a renderer might occupy.  ReShade and OptiScaler both use them,
# which is exactly why the name alone is not evidence.
RESHADE_DLL_NAMES = ("dxgi.dll", "d3d11.dll", "d3d12.dll", "dinput8.dll", "opengl32.dll", "version.dll")


# ---------------------------------------------------------------- game model


@dataclass
class Game:
    appid: str
    name: str
    install_dir: Path
    library: Path
    steam_root: Path
    proton_prefix: Path | None = None
    proton_tool: str | None = None
    launch_exe: Path | None = None
    bitness: int | None = None
    rendering_api: str | None = None
    api_evidence: list[str] = field(default_factory=list)
    native_dlss: list[Path] = field(default_factory=list)
    nvngx_dlssnr: list[Path] = field(default_factory=list)
    reshade_files: list[Path] = field(default_factory=list)
    size_on_disk: int | None = None
    source: str = "steam"

    @property
    def reshade_installed(self) -> bool:
        """Whether ReShade is genuinely active here: proxy DLL plus its ini.

        Both must sit in one directory.  A lone ``ReShade.ini`` is residue and
        must not be reported as an installed ReShade.
        """
        directories = {p.parent for p in self.reshade_files if p.name == "ReShade.ini"}
        if self.launch_exe is not None:
            directories.add(self.launch_exe.parent)
        for directory in directories:
            if not (directory / "ReShade.ini").is_file():
                continue
            for name in RESHADE_DLL_NAMES:
                candidate = directory / name
                if not candidate.is_file():
                    continue
                if file_contains(candidate, b"ReShade"):
                    return True
                # A proxy of the right name without the product string is a
                # different tool; it must not be counted as ReShade.
        return False

    @property
    def is_steam(self) -> bool:
        """Whether Steam manages this game.

        Hand-added folders have a synthetic key rather than an appid, so anything
        that talks to Steam — launch options, artwork — does not apply to them.
        """
        return self.source == "steam" and self.appid.isdigit()

    @property
    def key(self) -> str:
        return f"steam-{self.appid}"

    def to_dict(self) -> dict:
        return {
            "appid": self.appid,
            "name": self.name,
            "install_dir": str(self.install_dir),
            "library": str(self.library),
            "steam_root": str(self.steam_root),
            "proton_prefix": str(self.proton_prefix) if self.proton_prefix else None,
            "proton_tool": self.proton_tool,
            "launch_exe": str(self.launch_exe) if self.launch_exe else None,
            "bitness": self.bitness,
            "rendering_api": self.rendering_api,
            "api_evidence": self.api_evidence,
            "native_dlss": [str(p) for p in self.native_dlss],
            "nvngx_dlssnr": [str(p) for p in self.nvngx_dlssnr],
            "reshade_files": [str(p) for p in self.reshade_files],
            "source": self.source,
        }


DEFAULT_EXE_EXCLUDES = re.compile(
    r"(unins|setup|installer|crashpad|crashreport|launcher_update|vcredist|dxsetup|"
    r"dotnet|redist|helper|touchhelper|updater|eac|battleye|be_service|easyanticheat|"
    r"anticheat|activation|editor|dedicated|unrealcefsubprocess|epicwebhelper|"
    r"prerequisites|dxwebsetup|ue4prereq)",
    re.IGNORECASE,
)

# An import table can lie (RUSE links d3d11 and draws with d3d9), and a game can
# reach a backend the table never names -- Cyberpunk 2077 imports neither
# d3d12.dll nor d3d11.dll, only sl.interposer.dll, because Streamline loads the
# backend at runtime.  These markers are the fallback.
API_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("DirectX 9", ("d3d9.dll", "d3d9", "Direct3DCreate9", "D3DPERF_BeginEvent")),
    ("DirectX 10", ("d3d10.dll", "d3d10_1.dll", "d3d10core.dll")),
    ("DirectX 11", ("d3d11.dll", "D3D11CreateDevice")),
    ("DirectX 12", ("d3d12.dll", "d3d12core.dll", "D3D12CreateDevice")),
    ("Vulkan", ("vulkan-1.dll", "vulkan-1", "vkCreateInstance", "VK_ICD_FILENAMES")),
    ("OpenGL", ("opengl32.dll", "wglCreateContext")),
]

# Backends reached *through* a runtime shim.  These cannot be told apart by
# asking "did the exe import d3d12.dll", so they are matched against import
# *names* and against strings, and they are ranked below a direct import
# because a game that imports both is drawing with the direct one.
INDIRECT_API_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    (
        "DirectX 12",
        (
            "d3d12.dll", "d3d12core.dll", "d3d12on7.dll",
            "sl.dlss_dx12.dll", "sl.reflex_dx12.dll", "sl.pcl_dx12.dll",
            "sl.dlss_g_dx12.dll", "sl.nis_dx12.dll",
            "ffx_backend_dx12", "ffx_fsr3", "libxess.dll", "libxess_fg.dll",
            "amd_fidelityfx_dx12", "dxil.dll",
        ),
    ),
    (
        "DirectX 11",
        (
            "sl.dlss_dx11.dll", "sl.reflex_dx11.dll", "sl.pcl_dx11.dll",
            "ffx_backend_dx11", "ffx_fsr2_api", "libxess_dx11.dll",
        ),
    ),
    ("Vulkan", ("sl.dlss_vk.dll", "sl.reflex_vk.dll", "vk_layer_", "amdvlk")),
]

# Preference order when an executable names several backends.  Direct3D wins
# over Vulkan/OpenGL because engines that support several name them all and on
# Windows draw with Direct3D.
API_RANK = {
    "DirectX 12": 0,
    "DirectX 11": 1,
    "DirectX 10": 2,
    "DirectX 9": 3,
    "Vulkan": 4,
    "OpenGL": 5,
    "DirectDraw": 6,
}


def classify_api(pe: PEFile) -> tuple[str | None, list[str]]:
    evidence: list[str] = []
    direct: set[str] = set()
    indirect: set[str] = set()

    dlls = pe.all_dlls
    for api, markers in API_MARKERS:
        for marker in markers:
            marker_l = marker.lower()
            if any(marker_l == dll or marker_l in dll for dll in dlls):
                direct.add(api)
                evidence.append(f"import:{marker}")
            elif pe.has_string(marker):
                direct.add(api)
                evidence.append(f"string:{marker}")

    for api, markers in INDIRECT_API_MARKERS:
        for marker in markers:
            marker_l = marker.lower()
            if api in direct:
                continue
            if any(marker_l in dll for dll in dlls):
                indirect.add(api)
                evidence.append(f"indirect-import:{marker}")
            elif pe.has_string(marker):
                indirect.add(api)
                evidence.append(f"indirect-string:{marker}")

    hits = direct or indirect
    if not hits:
        return None, evidence
    best = sorted(hits, key=lambda api: API_RANK.get(api, 99))[0]
    return best, sorted(set(evidence))


# Unreal's layout is '<ProjectName>/Binaries/Win64/<Game>.exe' and the project
# name does NOT match the store's install directory: Hogwarts Legacy's renderer
# lives under Phoenix/, Assetto Corsa Competizione's under AC2/.  Directory
# names therefore cannot be assumed -- measured on this machine, a directory
# allowlist found only the 0.3 MB launcher stubs.  Search to a bounded depth
# and rank by what each executable actually imports.
_MAX_EXE_DEPTH = 4

# Subdirectories that never contain a renderer.  Pruned so the walk stays cheap
# on games with hundreds of thousands of asset files.
_PRUNE_DIRS = {
    "content", "paks", "movies", "audio", "sound", "textures", "shaders",
    "cache", "saved", "config", "localization", "assetregistry",
    "derivedatacache", "__pycache__", ".git", "mods", "plugins",
}


def _candidate_executables(game_dir: Path, max_candidates: int = 60) -> list[Path]:
    """Every plausible launch executable, best candidate first."""
    exes: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            exes.append(path)

    base_depth = len(game_dir.parts)
    try:
        for dirpath, dirnames, filenames in os.walk(game_dir, followlinks=False):
            current = Path(dirpath)
            if len(current.parts) - base_depth >= _MAX_EXE_DEPTH:
                dirnames[:] = []
            else:
                dirnames[:] = [d for d in dirnames if d.lower() not in _PRUNE_DIRS]
            for name in filenames:
                if name.lower().endswith(".exe"):
                    add(current / name)
    except OSError:
        pass

    filtered = [p for p in exes if not DEFAULT_EXE_EXCLUDES.search(p.name)]
    ordered = sorted(filtered, key=lambda p: (-_maybe_main_score(p), len(str(p))))
    return ordered[:max_candidates]


def _maybe_main_score(path: Path) -> int:
    """Heuristic preference for the *main* executable.

    Size dominates on purpose.  A launcher stub and the real renderer sit next
    to each other, and the renderer is one to two orders of magnitude larger.
    Hogwarts Legacy's root ``HogwartsLegacy.exe`` is a few hundred KiB while
    the renderer under ``Phoenix/Binaries/Win64`` is tens of MiB.
    """
    score = 0
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
    except OSError:
        size_mb = 0.0
    score += int(min(size_mb, 400))  # 1 point per MiB, capped
    if size_mb < 1:
        score -= 50  # almost certainly a stub
    if path.parent.name.lower() in {"win64", "x64", "bin64", "binaries"}:
        score += 1
    if path.stem.lower() in {"game", "main"}:
        score += 1
    return score


def choose_launch_exe(game_dir: Path) -> tuple[Path | None, PEFile | None]:
    """Pick the executable ReShade should attach to.

    Ranking is by *evidence*, not by size: a game's root executable is often a
    launcher stub while the renderer sits in a subdirectory, and a store
    directory name cannot be used to find it (Unreal project names differ).
    We therefore parse candidates in size order and take the first one that
    carries a recognisable graphics API import, then fall back to the largest
    remaining candidate.
    """
    fallback: tuple[Path, PEFile | None] | None = None

    for candidate in _candidate_executables(game_dir):
        pe = read_pe(candidate)
        if pe is None or pe.is_dll:
            continue
        if fallback is None:
            fallback = (candidate, pe)
        api, _ = classify_api(pe)
        if api is not None:
            return candidate, pe
    if fallback is not None:
        return fallback
    candidates = _candidate_executables(game_dir, max_candidates=1)
    return (candidates[0], read_pe(candidates[0])) if candidates else (None, None)


# ------------------------------------------------------------------ scanning


def library_folders(steam_root: Path) -> list[Path]:
    """Every Steam library, primary first."""
    libraries: list[Path] = []
    primary = steam_root / "steamapps"
    if primary.is_dir():
        libraries.append(steam_root)
    vdf = primary / "libraryfolders.vdf"
    if vdf.is_file():
        try:
            data = parse_vdf(vdf.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            data = {}
        for value in (data.get("libraryfolders") or {}).values():
            if isinstance(value, dict):
                path = value.get("path")
                if path:
                    candidate = Path(path)
                    if candidate not in libraries and (candidate / "steamapps").is_dir():
                        libraries.append(candidate)
    return libraries


def proton_tool_for(steam_root: Path, prefix: Path) -> str | None:
    """The Proton build Steam last used for this prefix.

    ``config_info`` next to the prefix holds the display name, e.g.
    ``proton-cachyos-slr`` or ``Proton 9.0``.  This is what decides whether the
    launch options need ``PROTON_FORCE_NVAPI`` (GE-Proton / proton-cachyos) or
    ``PROTON_ENABLE_NVAPI`` (Valve Proton) - ``PROTON_ENABLE_NVAPI`` simply does
    not exist on the former.
    """
    config = prefix.parent / "config_info"
    if not config.is_file():
        return None
    try:
        text = config.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def scan_steam_game(library: Path, appmanifest: Path, steam_root: Path) -> Game | None:
    try:
        manifest = parse_vdf(appmanifest.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    state = manifest.get("AppState") or {}
    appid = str(state.get("appid") or "").strip()
    installdir = str(state.get("installdir") or "").strip()
    if not appid or not installdir:
        return None
    game_dir = library / "steamapps" / "common" / installdir
    if not game_dir.is_dir():
        return None

    prefix = steam_root / "steamapps" / "compatdata" / appid / "pfx"
    game = Game(
        appid=appid,
        name=str(state.get("name") or installdir),
        install_dir=game_dir,
        library=library,
        steam_root=steam_root,
        proton_prefix=prefix if prefix.is_dir() else None,
        proton_tool=proton_tool_for(steam_root, prefix) if prefix.is_dir() else None,
        size_on_disk=_dir_size_bounded(game_dir, int(state.get("SizeOnDisk") or 0)),
    )
    _detect_into(game)
    return game


def _dir_size_bounded(path: Path, declared: int = 0, *, limit_files: int = 4000) -> int | None:
    """Sum file sizes but stop early: some games have 100k+ files and a full
    stat walk over an NTFS mount is slow enough to look like a hang."""
    if declared:
        return declared
    total = 0
    seen = 0
    for entry in iter_files(path, max_depth=4):
        try:
            total += entry.stat().st_size
        except OSError:
            continue
        seen += 1
        if seen >= limit_files:
            return None
    return total


# Backup and restore trees left behind by other tools.  DLSS5-Swapper writes
# `_DLSS5_Backup/originals/<id>/...` inside the game directory, and treating its
# contents as live game files made the scanner report a game as shipping DLSS
# when the only copy was Swapper's backup of what it replaced.
_BACKUP_DIR_MARKERS = (
    "_dlss5_backup",
    "originals",
    ".nvfku",
    "reshade-shaders",
)



def _is_backup_path(path: Path, game_dir: Path) -> bool:
    try:
        relative = path.relative_to(game_dir)
    except ValueError:
        return False
    return any(part.lower() in _BACKUP_DIR_MARKERS for part in relative.parts[:-1])


def _detect_into(game: Game) -> None:
    exe, pe = choose_launch_exe(game.install_dir)
    game.launch_exe = exe
    if pe is not None:
        game.bitness = pe.bitness
        api, evidence = classify_api(pe)
        game.rendering_api = api
        game.api_evidence = evidence

    for name in ("nvngx_dlss.dll", "nvngx_dlssg.dll", "nvngx_dlssd.dll", "nvngx_dlssnr.dll"):
        for found in game.install_dir.rglob(name):
            if _is_backup_path(found, game.install_dir):
                continue
            if "nvngx_dlssnr" in name:
                game.nvngx_dlssnr.append(found)
            else:
                game.native_dlss.append(found)

    # ReShade counts as installed only where it actually takes effect: a proxy
    # DLL *and* its ReShade.ini in the same directory, next to the executable.
    # A stray ReShade.ini without the DLL is residue from another tool's install
    # and reporting it as "installed" would tell the user to skip a step they
    # still owe.
    for candidate_dir in {exe.parent if exe else game.install_dir, game.install_dir}:
        has_ini = (candidate_dir / "ReShade.ini").is_file()
        present_dlls = [candidate_dir / name for name in RESHADE_DLL_NAMES if (candidate_dir / name).is_file()]
        if has_ini and present_dlls:
            game.reshade_files.extend([candidate_dir / "ReShade.ini", *present_dlls])
    for name in ("ReShade.ini",):
        for found in game.install_dir.rglob(name):
            if _is_backup_path(found, game.install_dir):
                continue
            if found not in game.reshade_files:
                game.reshade_files.append(found)

    if game.rendering_api is None and any(
        (game.install_dir / marker).exists() for marker in ("UnityPlayer.dll", "UE4Game", "UE5")
    ):
        game.rendering_api = "DirectX 11"
        game.api_evidence.append("engine-marker")


def scan(paths: Paths) -> list[Game]:
    if paths.steam_root is None:
        return []
    games: list[Game] = []
    for library in library_folders(paths.steam_root):
        apps = library / "steamapps"
        try:
            manifests = sorted(apps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            game = scan_steam_game(library, manifest, paths.steam_root)
            if game is not None and not is_non_game(game):
                games.append(game)
    games.sort(key=lambda g: g.name.lower())
    return games


# Tooling that lives in a Steam library with an appmanifest but is not a game.
# Without this filter the scanner reports Proton itself, three Steam Linux
# Runtimes, the Steamworks redistributable and the EasyAntiCheat runtime as
# installable titles.
_NON_GAME_APPIDS = {
    "228980",   # Steamworks Common Redistributables
    "1070560",  # Steam Linux Runtime 1.0 (scout)
    "1391110",  # Steam Linux Runtime 2.0 (soldier)
    "1628350",  # Steam Linux Runtime 3.0 (sniper)
    "4183110",  # Steam Linux Runtime 4.0
    "1826330",  # Proton EasyAntiCheat Runtime
    "1493710",  # Proton Experimental
    "4628710",  # Proton 11.0
    "2805730",  # Proton 9.0
    "961940",   # Proton 7.0
    "2348590",  # Proton 8.0
}

_NON_GAME_NAME = re.compile(
    r"^(proton\b|steam linux runtime|steamworks common redistributables|"
    r"steamvr\b|steam audio|easyanticheat|battleye|steam play)",
    re.IGNORECASE,
)

# Directories never worth presenting as a title even if they slip through.
_NON_GAME_INSTALL_DIRS = {"steamworks shared", "steamlinuxruntime", "proton"}


def is_non_game(game: Game) -> bool:
    if game.appid in _NON_GAME_APPIDS:
        return True
    if _NON_GAME_NAME.search(game.name):
        return True
    if game.install_dir.name.lower() in _NON_GAME_INSTALL_DIRS:
        return True
    # A "game" whose directory holds no executable at all is a runtime payload.
    return game.launch_exe is None and not game.native_dlss and not game.nvngx_dlssnr


# --------------------------------------------------------------- scan cache


# How long a cached detection is trusted even when nothing appears to have
# changed. This is the backstop for the depth limit documented on `_cache_key`.
CACHE_TTL_SECONDS = 6 * 60 * 60


def _cache_path(paths: Paths) -> Path:
    return paths.ensure_state_dir() / "scan-cache.json"


def _cache_key(
    game_dir: Path,
    manifest: Path,
    steam_root: Path | None = None,
    appid: str | None = None,
) -> str:
    """Identity of a game's *detection inputs*.

    Two levels matter, and only one of them was obvious. The game directory's own
    mtime changes when something is added at its top level, but this tool installs
    add-ons into subdirectories like ``bin/x64`` — where the *parent's* mtime does
    not move, so a top-level-only key would keep serving a stale "not installed"
    verdict after a successful install.

    So the key digests the mtimes of the directory and its immediate children,
    which the filesystem updates whenever a file appears in, or disappears from,
    any of them. That is a handful of stats, not a walk.

    **The boundary, stated plainly:** a change three or more levels deep that
    leaves every parent's mtime untouched is *not* detected by this key. For this
    tool's own installs that cannot happen — `FileJournal.finish` invalidates the
    affected game explicitly — but an external tool writing that deep would leave
    a stale verdict until the ttl below expires. Covering every depth would mean
    walking the tree, which is the cost this cache exists to avoid.
    """
    parts: list[str] = []
    for directory in [game_dir, *sorted(p for p in _safe_iterdir(game_dir) if p.is_dir())]:
        try:
            parts.append(f"{directory.name}:{int(directory.stat().st_mtime_ns)}")
        except OSError:
            continue
    try:
        parts.append(f"manifest:{int(manifest.stat().st_mtime_ns)}")
    except OSError:
        parts.append("manifest:0")

    # The Proton prefix is part of the detection result, so it has to be part of
    # the key. Creating it moves the mtime of `<compatdata>/<appid>`, and without
    # this a game that gained a prefix after a scan kept reporting that it had
    # none — for up to the cache ttl, which is hours.
    if steam_root is not None and appid:
        compat = steam_root / "steamapps" / "compatdata" / appid
        try:
            parts.append(f"compat:{int(compat.stat().st_mtime_ns)}")
        except OSError:
            parts.append("compat:absent")
    return "|".join(parts)


def _safe_iterdir(directory: Path) -> list[Path]:
    try:
        return list(directory.iterdir())
    except OSError:
        return []


def invalidate_scan_cache(paths: Paths, install_dir: Path | None = None) -> None:
    """Drop cached detection, all of it or one game's.

    A tool-initiated install already changes the directory mtimes the key reads,
    so this is belt and braces — but it makes the intent explicit and covers a
    filesystem that does not update a directory mtime as expected.
    """
    cache = _load_cache(paths)
    if install_dir is None:
        _save_cache(paths, {})
        return
    target = str(install_dir)
    kept = {
        key: value
        for key, value in cache.items()
        if not (isinstance(value, dict)
                and str((value.get("game") or {}).get("install_dir", "")) == target)
    }
    _save_cache(paths, kept)


def _load_cache(paths: Paths) -> dict:
    try:
        data = json.loads(_cache_path(paths).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(paths: Paths, cache: dict) -> None:
    try:
        atomic_write_text(_cache_path(paths), json.dumps(cache))
    except OSError:
        pass



def _installdir_of(manifest: Path, library: Path) -> Path:
    """The game's directory, read cheaply from its manifest."""
    try:
        data = parse_vdf(manifest.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return library
    installdir = str((data.get("AppState") or {}).get("installdir") or "").strip()
    if not installdir:
        return library
    return library / "steamapps" / "common" / installdir


def scan_with_cache(paths: Paths, *, logger=None) -> list[Game]:
    """``scan`` with a detection cache.

    Detection is the expensive half of every command: walking a game directory on
    a mounted NTFS volume to find the renderer took ~9 s for a 20-game library, so
    the CLI paid it on every invocation and the UI's detail view looked hung. The
    walk's *result* is stable until the game's own directory changes, so it is
    cached on that basis and reused.
    """
    cache = _load_cache(paths)
    games: list[Game] = []
    fresh: dict = {}
    hits = 0

    if paths.steam_root is not None:
        for library in library_folders(paths.steam_root):
            apps = library / "steamapps"
            try:
                manifests = sorted(apps.glob("appmanifest_*.acf"))
            except OSError:
                continue
            for manifest in manifests:
                key = str(manifest)
                appid = manifest.stem.removeprefix("appmanifest_")
                stamp = _cache_key(
                    _installdir_of(manifest, library),
                    manifest,
                    steam_root=paths.steam_root,
                    appid=appid,
                )
                entry = cache.get(key)
                fresh_enough = (
                    isinstance(entry, dict)
                    and time.time() - float(entry.get("at", 0)) < CACHE_TTL_SECONDS
                    and entry.get("stamp") == stamp
                )
                if fresh_enough and entry.get("non_game"):
                    # A redistributable or a Proton payload. Cached as firmly as a
                    # game is: "this is not a game" is just as stable as "this is",
                    # and without this the same nine entries were re-detected on
                    # every invocation — ~540 ms of a ~1050 ms command, every time,
                    # because the old code `continue`d before ever writing them out.
                    fresh[key] = entry
                    hits += 1
                    continue
                if fresh_enough and entry.get("game"):
                    game = _game_from_cache(entry["game"])
                    if game is not None and not is_non_game(game):
                        games.append(game)
                        fresh[key] = entry
                        hits += 1
                        continue
                game = scan_steam_game(library, manifest, paths.steam_root)
                if game is None:
                    # Nothing to describe, and nothing that a change in the
                    # directory would make describable. Not cached: a manifest
                    # whose install dir has not appeared yet is a different case
                    # from one that resolved to a payload.
                    continue
                if is_non_game(game):
                    # Recorded, not dropped. See above.
                    fresh[key] = {"stamp": stamp, "at": time.time(), "non_game": True}
                    continue
                games.append(game)
                fresh[key] = {"stamp": stamp, "at": time.time(), "game": game.to_dict()}

    # Anything not rebuilt this run is dropped, so a removed game disappears.
    _save_cache(paths, fresh)
    if logger is not None:
        logger(f"scan: {len(games)} games, {hits} from cache")
    return games


def scan_one(paths: Paths, needle: str) -> Game | None:
    """Detect a single game by appid, without scanning the library.

    The library scan costs ~10 s cold on this machine, and every command that acts
    on one game (`plan`, `show`, `launch-options`, `reshade`) was paying it to find
    a manifest whose name it already knew. The appid is the manifest's filename, so
    the lookup is a `glob` per library rather than a walk of every game.

    `needle` is matched as an appid first and then by name, and a name falls back to
    the full scan because names only exist inside the manifests. That keeps the fast
    path fast and the slow path correct.
    """
    if not needle.isdigit():
        return None
    if paths.steam_root is None:
        return None

    cache = _load_cache(paths)
    fresh = dict(cache)

    for library in library_folders(paths.steam_root):
        manifest = library / "steamapps" / f"appmanifest_{needle}.acf"
        if not manifest.is_file():
            continue
        key = str(manifest)
        stamp = _cache_key(
            _installdir_of(manifest, library),
            manifest,
            steam_root=paths.steam_root,
            appid=needle,
        )
        entry = cache.get(key)
        fresh_enough = (
            isinstance(entry, dict)
            and time.time() - float(entry.get("at", 0)) < CACHE_TTL_SECONDS
            and entry.get("stamp") == stamp
        )
        if fresh_enough and entry.get("non_game"):
            return None
        if fresh_enough and entry.get("game"):
            game = _game_from_cache(entry["game"])
            if game is not None and not is_non_game(game):
                return game
        game = scan_steam_game(library, manifest, paths.steam_root)
        if game is None:
            return None
        if is_non_game(game):
            fresh[key] = {"stamp": stamp, "at": time.time(), "non_game": True}
            _save_cache(paths, fresh)
            return None
        fresh[key] = {"stamp": stamp, "at": time.time(), "game": game.to_dict()}
        _save_cache(paths, fresh)
        return game
    return None


def _game_from_cache(data: dict) -> Game | None:
    """Rebuild a :class:`Game` from its cached dictionary."""
    try:
        prefix = data.get("proton_prefix")
        return Game(
            appid=str(data["appid"]),
            name=str(data["name"]),
            install_dir=Path(data["install_dir"]),
            library=Path(data["library"]),
            steam_root=Path(data["steam_root"]),
            proton_prefix=Path(prefix) if prefix else None,
            proton_tool=data.get("proton_tool"),
            launch_exe=Path(data["launch_exe"]) if data.get("launch_exe") else None,
            bitness=data.get("bitness"),
            rendering_api=data.get("rendering_api"),
            api_evidence=list(data.get("api_evidence") or []),
            native_dlss=[Path(p) for p in data.get("native_dlss") or []],
            nvngx_dlssnr=[Path(p) for p in data.get("nvngx_dlssnr") or []],
            reshade_files=[Path(p) for p in data.get("reshade_files") or []],
            source=str(data.get("source") or "steam"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def format_game_line(game: Game) -> str:
    api = game.rendering_api or "unknown API"
    bits = f"{game.bitness}-bit" if game.bitness else "?-bit"
    dlss = "DLSS" if game.native_dlss else "no DLSS"
    nr = " + NR model" if game.nvngx_dlssnr else ""
    proton = game.proton_tool or "no prefix"
    size = human_size(game.size_on_disk) if game.size_on_disk else "-"
    return f"{game.appid:>8}  {game.name[:42]:<42} {api:<11} {bits:<8} {dlss}{nr:<12} {proton:<20} {size}"
