"""One-click ReShade installation, driven from Linux through Proton.

Why this is possible at all
---------------------------
ReShade's own setup tool is a .NET GUI application, which would normally rule out
unattended installation on a Linux host. It is not, because the tool accepts the
flags its own UI uses when it relaunches itself elevated::

    ReShade_Setup.exe --headless --api dxgi <target.exe>

`--headless` hides the window, `--api` preselects the proxy, and the positional
argument names the executable to install beside. Everything the GUI would do then
happens without it.

Every claim below was measured on the development machine, not assumed:

*   **The licence permits this.** ReShade is BSD 3-Clause, so downloading and
    running the official installer is fine. It is still downloaded from the
    publisher at install time rather than bundled: the project should not become
    a mirror of someone else's binary.
*   **A Proton prefix can drive a Windows program from the Linux side.** A probe
    executable run through `proton run` printed its marker, so the host can start
    the installer without Steam.
*   **The prefix has a usable .NET.** The setup tool is a .NET assembly; Proton's
    bundled `wine-mono` runs it. The `expect_no_runtimes Process exited with a
    Mono runtime loaded` line on stderr is Wine noticing that the process used
    Mono, not a failure — the install reports success and the files appear.
*   **A target outside the prefix is reachable** through the `Z:` drive, which
    Proton maps to `/`. The real game directories live on other mounts, so this
    is the case that matters.
*   **The tool picks the DLL by the target's bitness.** Installing for the same
    directory as a 32-bit and a 64-bit executable produced a 3.7 MB and a 4.7 MB
    `dxgi.dll` respectively.

What this deliberately does not do
----------------------------------
`--api vulkan` is never used. Wine's Vulkan loader does not enumerate
third-party layers — it reads only the ICD registry key — so a Vulkan layer
cannot load under Proton at all. The DXGI proxy is the only mechanism that works,
which is the same reason route A1 exists.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .journal import FileJournal
from .messages import text
from .paths import Paths, human_size
from .plan import Action, Checks, InstallRefused, InstallResult, Missing, RoutePlan
from .steam import Game

ROUTE = "reshade"

#: The release this tool installs. Pinned rather than "latest": a self-updating
#: download would mean an unreviewed binary appearing in a game directory, and the
#: digest below would be meaningless the moment upstream shipped a new build.
VERSION = "6.8.0"

#: Upstream's download page offers **two** installers per release, and only one of
#: them can load add-ons:
#:
#:     ReShade_Setup_6.8.0.exe        the standard build
#:     ReShade_Setup_6.8.0_Addon.exe  the full add-on build
#:
#: The standard build is compiled with limited add-on functionality and skips
#: every `*.addon64` beside the game, logging
#: "Skipped loading add-on ... because this build of ReShade has only limited
#: add-on functionality." That is what route A1 needs, so the first version of
#: this module — which fetched the standard installer — produced a ReShade that
#: injected correctly and then refused to load `dlss5-bridge.addon64`. The source
#: makes the distinction concrete: the skip sits behind `#if RESHADE_ADDON == 1`,
#: and the two builds' `ReShade64.dll` differ in size (5,255,448 vs 5,592,064
#: bytes) with the warning string present only in the standard one.
SETUP_ASSET = f"ReShade_Setup_{VERSION}_Addon.exe"

#: sha256 of that installer, recorded from the official download and verified by a
#: real run. Upstream publishes no checksum, so this is trust-on-first-download
#: made explicit and auditable: if the bytes change, the install stops and says so.
SETUP_SHA256 = "afe4c8f13048306307983b8b3d41d5bf00a86820440b0e57dea10950e1176445"
SETUP_SIZE = 4_318_424

#: Marker of the add-on-crippled build. Checked against the DLL that actually
#: lands in the game directory, because shipping a ReShade that cannot load the
#: bridge would look like a successful install and then silently do nothing.
LIMITED_ADDON_MARKER = b"limited add-on functionality"

DOWNLOAD_URL = f"https://reshade.me/downloads/{SETUP_ASSET}"

#: The proxies ReShade can install as, and the `--api` value for each. DXGI is the
#: only one this module offers; the others are listed so a future caller does not
#: have to rediscover the mapping.
API_FOR_DLL = {
    "dxgi.dll": "dxgi",
    "d3d9.dll": "d3d9",
    "d3d10.dll": "d3d10",
    "d3d11.dll": "d3d11",
    "d3d12.dll": "d3d12",
    "opengl32.dll": "opengl",
}

#: Files ReShade's installer creates. The DLL is the proof of a real install; the
#: ini is what makes it count as installed in detection, because a stray ini
#: without a DLL is residue from something else.
INSTALLED_DLL = "dxgi.dll"
INSTALLED_INI = "ReShade.ini"

#: Proton prefixes need a few variables to behave outside Steam. Measured against
#: `proton-cachyos`; GE-Proton and Valve Proton accept the same set.
PROTON_ENV_PREFIX = "steamapps/compatdata"


class ReshadeError(RuntimeError):
    """ReShade could not be installed. Never silent: always carries a reason."""


@dataclass
class ProtonRuntime:
    """The Proton build that will run the installer, and its prefix."""

    name: str
    root: Path
    data_dir: Path
    prefix: Path
    needs_prefix_init: bool
    source: str

    @property
    def proton_script(self) -> Path:
        return self.root / "proton"

    @property
    def usable(self) -> bool:
        return self.proton_script.is_file()

    def describe(self, language: str | None = None) -> str:
        state = text(
            language,
            "rh.proton.state.create" if self.needs_prefix_init else "rh.proton.state.exists",
        )
        return text(
            language,
            "rh.proton.describe",
            name=self.name,
            source=self.source,
            state=state,
        )


# --------------------------------------------------------------- proton lookup


def _compat_tool_name(prefix_dir: Path) -> str | None:
    """The Proton build recorded for this prefix, if any.

    `config_info` is written by Proton on first run and names the exact tool. Its
    absence is how a never-launched game is recognised.
    """
    info = prefix_dir / "config_info"
    try:
        first = info.read_text(encoding="utf-8", errors="replace").split("\n")[0].strip()
    except OSError:
        return None
    return first or None


def _compat_tool_roots(steam_root: Path | None = None) -> list[Path]:
    """Directories that may hold a Proton build, in the order Steam looks.

    The caller's Steam root comes first, and its own ``compatibilitytools.d`` is
    the only per-user location consulted when it is set. That is not just for
    tests: a second Steam install keeps its Proton builds under its own root, and
    guessing ``~/.local/share/Steam`` would then install into a prefix using a
    build from a different installation.
    """
    roots: list[Path] = [
        Path("/usr/share/steam/compatibilitytools.d"),
        Path("/usr/lib/steam/compatibilitytools.d"),
    ]
    if steam_root is not None:
        roots.append(steam_root / "compatibilitytools.d")
        return roots
    home = Path.home()
    roots += [
        home / ".local/share/Steam/compatibilitytools.d",
        home / ".steam/steam/compatibilitytools.d",
        home / ".steam/root/compatibilitytools.d",
    ]
    return roots


def _steam_common_roots(steam_root: Path | None) -> list[Path]:
    """`steamapps/common` directories holding Valve's own Proton builds.

    The caller's Steam root comes first and suppresses the guessed locations, so a
    sandboxed `Paths` does not silently reach into the real Steam install — which
    is exactly what made the first version of these tests pass for the wrong
    reason.
    """
    if steam_root is not None:
        return [steam_root / "steamapps/common"]
    home = Path.home()
    return [
        home / ".local/share/Steam/steamapps/common",
        home / ".steam/steam/steamapps/common",
    ]


def find_proton(
    game: Game,
    paths: Paths,
    *,
    logger=None,
    language: str | None = None,
) -> ProtonRuntime | None:
    """Locate the Proton build and prefix this game would use.

    Preference order, strongest evidence first:

    1. the tool recorded in the game's own ``config_info``, which is what Steam
       itself last used;
    2. any Proton in the usual ``compatibilitytools.d`` directories;
    3. Valve's own ``Proton <version>`` directories under ``steamapps/common``.

    A game whose prefix has no ``config_info`` has never been launched through
    Proton, so whichever build is chosen will also be the one to create the
    prefix. That is reported rather than hidden, because it changes what the
    operation does.
    """
    prefix_dir = game.proton_prefix
    if prefix_dir is None:
        return None
    # `proton_prefix` points at `<compatdata>/<appid>/pfx`; the data dir is its
    # parent, which is what Proton takes as STEAM_COMPAT_DATA_PATH.
    data_dir = prefix_dir.parent
    recorded = _compat_tool_name(data_dir)

    candidates: list[tuple[str, Path, str]] = []
    for root in _compat_tool_roots(paths.steam_root):
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            # `entry.is_dir()` would exclude a symlinked build, and symlinking is
            # exactly how people install a Proton on a different filesystem.
            # Whether it is usable is decided by the `proton` script check below.
            if not (entry.is_dir() or entry.is_symlink()):
                continue
            source = "system" if str(root).startswith("/usr") else "user"
            candidates.append((entry.name, entry, source))
    for common in _steam_common_roots(paths.steam_root):
        try:
            entries = sorted(common.glob("Proton*"))
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() or entry.is_symlink():
                candidates.append((entry.name, entry, "valve"))

    chosen: tuple[str, Path, str] | None = None
    recorded_present = False
    if recorded:
        for name, root, source in candidates:
            if name == recorded:
                chosen = (name, root, source)
                recorded_present = True
                break
        if chosen is None and logger is not None:
            logger(
                "  "
                + text(
                    language,
                    "rh.log.recorded_tool_missing",
                    tool=repr(recorded),
                )
            )
    if chosen is None:
        # Prefer the CachyOS/GE builds, which carry the ntsync and FSR4 patches
        # this machine's other prefixes already use, over Valve's stock Proton.
        ordered = sorted(candidates, key=lambda c: (not c[0].startswith("proton-"), c[0]))
        chosen = ordered[0] if ordered else None
    if chosen is None:
        return None

    name, root, source = chosen
    runtime = ProtonRuntime(
        name=name,
        root=root,
        data_dir=data_dir,
        prefix=prefix_dir,
        # The prefix needs creating when nothing recorded has run in it: either
        # there is no `config_info` at all, or it names a build that is no longer
        # installed and therefore cannot be the one that built the prefix.
        needs_prefix_init=not recorded_present,
        source=source,
    )
    return runtime if runtime.usable else None


# ------------------------------------------------------------------ installer


def setup_path(paths: Paths) -> Path:
    # Named after the asset, so a previously cached standard installer is never
    # mistaken for the add-on build.
    return paths.download_cache() / SETUP_ASSET


def _verify_setup(path: Path, *, language: str | None = None) -> None:
    """Check the download is the expected installer, not an error page."""
    size = path.stat().st_size
    if size != SETUP_SIZE:
        raise ReshadeError(
            text(
                language,
                "rh.error.installer_size",
                actual=human_size(size),
                expected=human_size(SETUP_SIZE),
            )
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SETUP_SHA256:
        raise ReshadeError(
            text(
                language,
                "rh.error.installer_digest",
                actual=digest[:16],
                expected=SETUP_SHA256[:16],
            )
        )
    # A PE with an embedded ZIP is the shape this tool relies on; the zip holds
    # ReShade64.dll and ReShade32.dll and is what the installer extracts.
    head = path.read_bytes()[:2]
    if head != b"MZ":
        raise ReshadeError(text(language, "rh.error.not_executable"))


def fetch_setup(
    paths: Paths,
    *,
    logger=print,
    force: bool = False,
    language: str | None = None,
) -> Path:
    """Download and verify the official installer, caching it."""
    from . import providers

    destination = setup_path(paths)
    if destination.is_file() and not force:
        try:
            _verify_setup(destination, language=language)
            logger(
                "  "
                + text(
                    language,
                    "rh.log.cached_installer",
                    size=human_size(destination.stat().st_size),
                )
            )
            return destination
        except ReshadeError as exc:
            logger("  " + text(language, "rh.log.cached_rejected", error=exc))
            destination.unlink(missing_ok=True)

    logger("  " + text(language, "rh.log.downloading", url=DOWNLOAD_URL))
    blob = providers.http_get(DOWNLOAD_URL, timeout=120, attempts=3, logger=None)
    if not blob:
        raise ReshadeError(text(language, "rh.error.download_empty", url=DOWNLOAD_URL))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(blob)
    _verify_setup(destination, language=language)
    logger(
        "  "
        + text(language, "rh.log.verified_sha", digest=SETUP_SHA256[:16])
    )
    return destination


# ------------------------------------------------------------------- effects

#: The effect packages ReShade's own setup offers, read from the manifest its
#: updater uses. Only the package upstream marks `Required=1` is installed
#: automatically: it is the small utility set ReShade itself expects, and pulling
#: a contributor's shader collection by default would be a decision the user never
#: made.
EFFECTS_MANIFEST_URL = (
    "https://raw.githubusercontent.com/crosire/reshade-shaders/list/EffectPackages.ini"
)

#: Fallback for the one package that is always wanted. The manifest is preferred
#: because it is the publisher's own record; this keeps the feature working if the
#: manifest cannot be fetched.
STANDARD_EFFECTS_URL = "https://github.com/crosire/reshade-shaders/archive/slim.zip"

#: Where ReShade.ini looks for effects, relative to the executable.
EFFECTS_DIR = "reshade-shaders"


def _parse_effect_packages(text: str) -> list[dict]:
    """Read `EffectPackages.ini`, which is a reStructuredText-ish INI, not VDF.

    Sections are `[NN]` and values are `Key=Value`; there is no quoting or
    nesting, so a small parser is honest and avoids dragging in the VDF reader
    that expects a different shape.
    """
    packages: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = {"_section": line[1:-1]}
            packages.append(current)
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        current[key.strip()] = value.strip()
    return packages


def required_effects_urls(
    *, logger=None, language: str | None = None
) -> list[str]:
    """Download URLs for the packages upstream marks as required."""
    from . import providers

    try:
        body = providers.http_get(EFFECTS_MANIFEST_URL, timeout=60, attempts=2, logger=None)
        packages = _parse_effect_packages(
            body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
        )
    except Exception as exc:
        if logger is not None:
            logger(
                "  "
                + text(language, "rh.log.manifest_unreadable", error=exc)
            )
        return [STANDARD_EFFECTS_URL]

    urls = [
        p["DownloadUrl"]
        for p in packages
        if p.get("Required", "").strip() in ("1", "true", "yes") and p.get("DownloadUrl")
    ]
    if not urls:
        return [STANDARD_EFFECTS_URL]
    return urls


def install_effects(
    paths: Paths,
    target_dir: Path,
    *,
    logger=print,
    journal: FileJournal | None = None,
    language: str | None = None,
) -> dict:
    """Download and unpack ReShade's required effect files beside the game.

    Until these exist ReShade reports, in its own overlay:

        no effect files (.fx) found in the effect search paths

    The proxy still injects, so it looks like a partial success — which is exactly
    why the files are installed as part of the same operation rather than left as
    a note.
    """
    import io
    import zipfile

    from . import providers

    destination = target_dir / EFFECTS_DIR
    written: list[str] = []
    for url in required_effects_urls(logger=logger, language=language):
        logger(
            "  "
            + text(language, "rh.log.fetching_effects", host=url.split("/")[2])
        )
        try:
            blob = providers.http_get(url, timeout=180, attempts=3, logger=None)
        except Exception as exc:
            logger("  " + text(language, "rh.log.effects_fetch_failed", url=url, error=exc))
            continue
        if not blob:
            continue
        try:
            archive = zipfile.ZipFile(io.BytesIO(blob))
        except Exception as exc:
            logger("  " + text(language, "rh.log.not_zip", url=url, error=exc))
            continue

        for member in archive.namelist():
            if member.endswith("/"):
                continue
            # Archives nest everything under a single top directory, and only the
            # Shaders/ and Textures/ trees belong beside the executable.
            parts = member.split("/")
            rel = None
            for index, part in enumerate(parts):
                if part in ("Shaders", "Textures"):
                    rel = "/".join(parts[index:])
                    break
            if rel is None:
                continue
            out = destination / rel
            if journal is not None:
                if out.exists():
                    journal.adopt(out, source_label=f"ReShade effects {rel}")
                else:
                    journal.record_absent(out, source_label=f"ReShade effects {rel}")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(archive.read(member))
            written.append(rel)

    return {"directory": str(destination), "files": sorted(written)}


# ------------------------------------------------------------------ prefix ops


def _prefix_env(runtime: ProtonRuntime, paths: Paths) -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(
        paths.steam_root or Path.home() / ".local/share/Steam"
    )
    env["STEAM_COMPAT_DATA_PATH"] = str(runtime.data_dir)
    env["WINEPREFIX"] = str(runtime.prefix)
    # Proton reads its own libraries from here; without it the prefix can be
    # created with the wrong runtime and the installer then cannot start.
    env.setdefault("STEAM_COMPAT_INSTALL_PATH", str(runtime.root))
    return env


def ensure_prefix(
    runtime: ProtonRuntime,
    paths: Paths,
    *,
    logger=print,
    timeout: int = 900,
    language: str | None = None,
) -> None:
    """Create the Proton prefix if the game has never been launched.

    Running ``proton run`` with a literal command is the documented way to make
    Proton build a prefix without Steam. `wineboot` is not enough: the prefix
    also needs Proton's registry patches and its .NET, which this exercises.

    Measured: a fresh data directory produced
    ``Proton: Upgrading prefix from None to CachyOS-11.0-100`` and a working
    prefix that ran a Windows program.
    """
    if not runtime.needs_prefix_init:
        logger("  " + text(language, "rh.log.prefix_ready", prefix=runtime.prefix))
        return

    runtime.data_dir.mkdir(parents=True, exist_ok=True)
    logger("  " + text(language, "rh.log.prefix_creating", tool=runtime.name))
    runtime.prefix.mkdir(parents=True, exist_ok=True)
    # A short-lived command so Proton sets the prefix up and exits. `cmd /c exit`
    # needs no display and no console, unlike most Windows programs.
    result = subprocess.run(
        ["python3", str(runtime.proton_script), "run", "cmd", "/c", "exit"],
        env=_prefix_env(runtime, paths),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0 or not (runtime.prefix / "drive_c").is_dir():
        detail = (result.stdout + result.stderr).strip().splitlines()
        tail = (
            " | ".join(detail[-4:])
            if detail
            else text(language, "rh.error.prefix_exit", code=result.returncode)
        )
        raise ReshadeError(
            text(language, "rh.error.prefix_create_failed", detail=tail)
        )
    runtime.needs_prefix_init = False
    logger("  " + text(language, "rh.log.prefix_created", prefix=runtime.prefix))


def windows_path(target: Path) -> str:
    """The ``Z:`` form of a Linux path, as Wine maps it.

    Proton maps ``Z:`` to ``/``, which is how a target outside the prefix is
    reachable. Verified with a directory on a different mount.
    """
    resolved = target.resolve()
    parts = resolved.parts[1:]  # drop the leading "/"
    return "Z:\\" + "\\".join(parts)


#: Files ReShade's setup creates besides the proxy DLL. `INSTALLED_INI` is one of
#: them, so the two tuples are merged through `_written_names()` rather than
#: concatenated — concatenating listed `ReShade.ini` twice, which adopted it twice
#: and made rollback restore it twice.
CREATED_BY_INSTALLER = ("ReShadePreset.ini", "ReShade.log")


def _written_names() -> tuple[str, ...]:
    """Every file the installer may write, each named once, in a stable order."""
    seen: list[str] = []
    for name in (INSTALLED_DLL, INSTALLED_INI, *CREATED_BY_INSTALLER):
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def resolve_directory(
    game: Game, *, logger=None, language: str | None = None
) -> Path | None:
    """Which directory the executable that matters lives in.

    A game can contain the same executable name in several places. Hogwarts
    Legacy has both ``Phoenix/Binaries/Win64`` and ``Engine/Binaries/Win64``, and
    installing into the wrong one produces a silent no-op: the copy that runs
    never loads the proxy. So every candidate is inspected and the choice is
    reported rather than made quietly.
    """
    if game.launch_exe is None or not game.launch_exe.is_file():
        return None
    primary = game.launch_exe.parent
    if game.launch_exe.name.lower() != "win64shipping.exe":
        return primary

    name = game.launch_exe.name
    root = game.install_dir.parent if game.install_dir.name == "Win64" else game.install_dir
    # Bounded: a game tree is deep, but the candidates we care about are shallow.
    candidates: list[Path] = []
    for depth in range(1, 4):
        pattern = "/".join(["*"] * depth) + "/" + name
        try:
            candidates.extend(sorted(root.glob(pattern))[:20])
        except OSError:
            continue
    candidates = [c for c in candidates if c.is_file()]
    if len(candidates) <= 1:
        return primary

    scored: list[tuple[int, Path, list[str]]] = []
    for candidate in candidates:
        score = 0
        reasons: list[str] = []
        directory = candidate.parent
        try:
            size = candidate.stat().st_size
        except OSError:
            continue
        if directory == primary:
            score += 100
            reasons.append(text(language, "rh.reason.ranking"))
        # The real shipping binary is the big one; the other is a stub.
        score += min(size // (1024 * 1024), 5000)
        reasons.append(f"{human_size(size)}")
        if game.proton_prefix is not None:
            # A shared engine component usually has a sibling `Engine` directory
            # rather than a project directory.
            if (directory.parent.parent / "Engine").is_dir():
                score -= 400
                reasons.append(text(language, "rh.reason.shared_engine"))
        if (directory.parent / "Binaries").is_dir() and directory.name == "Win64":
            score += 20
        scored.append((score, directory, reasons))

    if not scored:
        return primary
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_dir, best_reasons = scored[0]
    if logger is not None and len(scored) > 1:
        logger("  " + text(language, "rh.log.copies_found", count=len(scored), name=name))
        for score, directory, reasons in scored:
            mark = "->" if directory == best_dir else "  "
            logger(f"    {mark} {directory}  [{text(language, 'rh.sep.comma').join(reasons)}]")
    return best_dir


def _run_installer(
    runtime: ProtonRuntime,
    paths: Paths,
    target: Path,
    *,
    logger=print,
    timeout: int = 900,
    update: bool = False,
    language: str | None = None,
) -> list[str]:
    """Run ReShade's setup headless against one target. Returns its output.

    ``update`` passes ``--state update``. Without it the setup tool refuses to
    touch a directory that already holds a ReShade proxy — "Existing ReShade
    installation for another API found ... uninstall the existing one first" —
    even when the file it would replace is its own. The flag is only ever used
    when a journal has already adopted a pre-image of every file at risk, so the
    replacement is undoable.
    """
    setup = fetch_setup(paths, logger=logger, language=language)
    staged = runtime.prefix / "drive_c" / "ReShadeSetup.exe"
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(setup, staged)
    try:
        result = subprocess.run(
            [
                "python3",
                str(runtime.proton_script),
                "run",
                str(staged),
                "--headless",
                "--api",
                "dxgi",
                *(["--state", "update"] if update else []),
                windows_path(target),
            ],
            env=_prefix_env(runtime, paths),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        staged.unlink(missing_ok=True)

    output = (result.stdout or "") + (result.stderr or "")
    return [
        line.strip()
        for line in output.splitlines()
        if line.strip() and not re.match(r"^[0-9a-f]{4}:", line)
    ]


def install_reshade(
    runtime: ProtonRuntime,
    game: Game,
    paths: Paths,
    *,
    target_exe: Path,
    logger=print,
    timeout: int = 900,
    journal: FileJournal | None = None,
    language: str | None = None,
) -> dict:
    """Run the installer headless and record what it produced.

    Everything the installer creates is journalled *after* it runs, by diffing
    the directory. That ordering is deliberate: the installer chooses its own file
    names and writes a generated log the tool cannot predict, so the honest record
    is the observed one. A rollback therefore deletes exactly what appeared.

    Its own uninstall path exists (``--state uninstall``) and is not used. A
    journal is preferred because it restores byte-exact pre-images of anything
    that was overwritten, which the installer's own removal cannot do.
    """
    directory = target_exe.parent
    before = {p.name: p for p in directory.iterdir() if p.is_file()}

    # Capture pre-images *before* the installer runs, for every name it can write.
    # The list cannot be discovered from the result: by then an overwritten file
    # holds the new contents and its original bytes are gone.
    adopted: set[str] = set()
    if journal is not None:
        for name in _written_names():
            candidate = directory / name
            if candidate.is_file():
                journal.adopt(candidate, source_label=f"ReShade {VERSION} will write {name}")
                adopted.add(name)

    output = _run_installer(
        runtime,
        paths,
        target_exe,
        logger=logger,
        timeout=timeout,
        # Only a directory that already holds a ReShade needs the update state, and
        # by this point every such file has a journalled pre-image.
        update=bool(adopted),
        language=language,
    )
    after = {p.name: p for p in directory.iterdir() if p.is_file()}

    created = [name for name in after if name not in before]
    overwritten = [name for name in adopted if name in after]
    if INSTALLED_DLL not in after:
        tail = "\n".join(output)[-600:]
        raise ReshadeError(
            text(language, "rh.error.no_dll", dll=INSTALLED_DLL)
            + (f"\n{tail}" if tail else "")
        )

    # Refuse to leave a ReShade that cannot load the bridge. The standard installer
    # produces exactly that, and it looks like success until the game runs and the
    # add-ons are skipped.
    installed_bytes = after[INSTALLED_DLL].read_bytes()
    if LIMITED_ADDON_MARKER in installed_bytes:
        raise ReshadeError(
            text(
                language,
                "rh.error.limited_addon",
                dll=INSTALLED_DLL,
                asset=SETUP_ASSET,
            )
        )

    if journal is not None:
        # Only files that were not there before are ours to delete on rollback.
        # Iterating the whole directory instead was a bug that deleted the game's
        # own executable: `after` holds every file in the directory, not only the
        # ones the installer produced.
        for name in sorted(created):
            path = after.get(name)
            if path is None or name in adopted:
                continue
            journal.record_absent(path, source_label=f"ReShade {VERSION} created {name}")
        if created:
            journal.note("ReShade created: " + ", ".join(sorted(created)))
        if overwritten:
            journal.note("ReShade replaced: " + ", ".join(sorted(overwritten)))

    return {
        "files": {
            name: str(path)
            for name, path in sorted(after.items())
            if name in _written_names()
        },
        "created": created,
        "overwritten": overwritten,
        "said": output[-6:],
    }


# ----------------------------------------------------------------------- plan


def check(
    paths: Paths,
    game: Game,
    *,
    logger=None,
    nested: bool = False,
    language: str | None = None,
) -> RoutePlan:
    """What installing ReShade for this game would involve."""
    checks = Checks()
    actions: list[Action] = []
    missing: list[Missing] = []

    exe = game.launch_exe
    if exe is None or not exe.is_file():
        checks.block(
            text(language, "rh.check.launch_exe"),
            text(language, "rh.check.launch_exe.block_detail"),
            text(language, "rh.check.launch_exe.fix"),
        )
    else:
        checks.ok(text(language, "rh.check.launch_exe"), str(exe))

    runtime = find_proton(game, paths, logger=logger, language=language)
    if runtime is None:
        checks.block(
            text(language, "rh.check.proton"),
            text(language, "rh.check.proton.block_detail"),
            text(language, "rh.check.proton.fix"),
        )
    else:
        checks.ok(text(language, "rh.check.proton"), runtime.describe(language=language))
        if runtime.needs_prefix_init:
            checks.warn(
                text(language, "rh.check.prefix"),
                text(language, "rh.check.prefix.warn_detail", prefix=runtime.prefix),
                text(language, "rh.check.prefix.warn_fix"),
            )
        else:
            checks.ok(
                text(language, "rh.check.prefix"),
                text(language, "rh.check.prefix.ok_detail", prefix=runtime.prefix),
            )

    if game.reshade_files:
        checks.ok(
            text(language, "rh.check.reshade"),
            text(language, "rh.check.reshade.ok_detail"),
        )
    else:
        checks.warn(
            text(language, "rh.check.reshade"),
            text(language, "rh.check.reshade.warn_detail"),
            text(language, "rh.check.reshade.warn_fix", version=VERSION),
        )

    api = game.rendering_api
    if api == "Vulkan":
        checks.block(
            text(language, "rh.check.api"),
            text(language, "rh.check.api.vulkan_detail"),
            text(language, "rh.check.api.vulkan_fix"),
        )
    elif api in ("DirectX 11", "DirectX 12", None):
        checks.ok(
            text(language, "rh.check.api"),
            text(
                language,
                "rh.check.api.ok_detail",
                api=api or text(language, "rh.unknown"),
            ),
        )
    else:
        checks.warn(
            text(language, "rh.check.api"),
            str(api),
            text(language, "rh.check.api.other_fix"),
        )

    target_dir = resolve_directory(game, logger=logger, language=language)
    if target_dir is not None and exe is not None and target_dir != exe.parent:
        checks.warn(
            text(language, "rh.check.install_dir"),
            text(
                language,
                "rh.check.install_dir.warn_detail",
                chosen=target_dir,
                other=exe.parent,
            ),
            text(language, "rh.check.install_dir.warn_fix"),
        )

    if exe is not None and target_dir is not None:
        actions.append(
            Action(
                kind="write",
                destination=str(target_dir / INSTALLED_DLL),
                source=f"ReShade {VERSION} {INSTALLED_DLL}",
                reason=text(language, "rh.action.proxy_reason"),
            )
        )
        actions.append(
            Action(
                kind="write",
                destination=str(target_dir / INSTALLED_INI),
                source=f"ReShade {VERSION} {INSTALLED_INI}",
                reason=text(language, "rh.action.ini_reason"),
            )
        )
        actions.append(
            Action(
                kind="note",
                destination=text(
                    language,
                    "rh.action.run_installer",
                    version=VERSION,
                    target=windows_path(target_dir / exe.name),
                    runtime=(
                        runtime.name
                        if runtime
                        else text(language, "rh.proton.placeholder")
                    ),
                ),
                reason=text(language, "rh.action.run_installer_reason"),
            )
        )
    if runtime is not None and runtime.needs_prefix_init:
        actions.append(
            Action(
                kind="note",
                destination=text(
                    language, "rh.action.create_prefix", prefix=runtime.prefix
                ),
                reason=text(language, "rh.action.create_prefix_reason"),
            )
        )

    return RoutePlan(
        route=ROUTE,
        # Nested, the title is a component name rather than an option in a list: the
        # route list has two entries, and this is one of A1's steps.
        title=text(
            language,
            "rh.title.nested" if nested else "rh.title.full",
            version=VERSION,
        ),
        game_name=game.name,
        game_dir=game.install_dir,
        summary=text(language, "rh.summary"),
        checks=checks,
        actions=actions,
        missing=missing,
        manual_steps=[
            text(language, "rh.manual.overlay"),
            text(language, "rh.manual.check_log"),
        ],
        read_only=False,
    )


def install(
    paths: Paths,
    game: Game,
    *,
    logger=print,
    yes: bool = False,
    language: str | None = None,
) -> InstallResult:
    """Install ReShade for real, after re-checking every precondition.

    Journalled like the DLL routes, so ``nvfku rollback`` restores the
    directory byte for byte — including a ``dxgi.dll`` that was already there.
    """
    plan = check(paths, game, logger=logger, language=language)
    if not plan.viable:
        blockers = text(language, "rh.sep.semicolon").join(
            f"{c.name}: {c.detail}" for c in plan.checks.blockers
        )
        raise InstallRefused(text(language, "rh.refuse.blocked", blockers=blockers))
    if not yes:
        raise InstallRefused(text(language, "rh.refuse.no_yes"))

    exe = game.launch_exe
    assert exe is not None
    runtime = find_proton(game, paths, logger=logger, language=language)
    if runtime is None:
        raise InstallRefused(text(language, "rh.refuse.no_proton"))

    target_dir = resolve_directory(game, logger=logger, language=language)
    if target_dir is None:
        raise InstallRefused(text(language, "rh.refuse.no_directory"))
    target_exe = target_dir / exe.name

    logger(text(language, "rh.install.header", version=VERSION, game=game.name))
    logger("  " + text(language, "rh.install.target", target=target_exe))

    journal = FileJournal(paths, game.install_dir, ROUTE, game_key=game.key)
    journal.note(f"ReShade {VERSION} via {runtime.name} into {target_dir}")
    try:
        report = install_reshade(
            runtime,
            game,
            paths,
            target_exe=target_exe,
            logger=logger,
            journal=journal,
            language=language,
        )
    except Exception:
        # A half-run install must not leave a journal claiming success.
        try:
            journal.rollback()
        except Exception:
            pass
        raise
    # The effects are part of a working install, not an optional extra: without
    # them ReShade's overlay reports that it found no .fx files, and the add-on
    # chain has nothing to render through.
    effects: dict = {"directory": str(target_dir / EFFECTS_DIR), "files": []}
    try:
        effects = install_effects(
            paths, target_dir, logger=logger, journal=journal, language=language
        )
    except Exception as exc:
        logger("  " + text(language, "rh.install.effects_failed", error=exc))

    manifest = journal.finish()

    verified = [
        text(
            language,
            "rh.verified.written",
            name=name,
            size=human_size(Path(path).stat().st_size),
        )
        for name, path in sorted(report["files"].items())
    ]
    notes = [
        text(language, "rh.note.installed_by", version=VERSION),
        text(language, "rh.note.prefix", prefix=runtime.prefix),
    ]
    if report["created"]:
        notes.append(
            text(
                language,
                "rh.note.created",
                names=text(language, "rh.sep.comma").join(sorted(report["created"])),
            )
        )
    if report["overwritten"]:
        notes.append(
            text(
                language,
                "rh.note.replaced",
                names=text(language, "rh.sep.comma").join(sorted(report["overwritten"])),
            )
        )
    if runtime.needs_prefix_init:
        notes.append(text(language, "rh.note.prefix_created"))
    if effects["files"]:
        notes.append(
            text(
                language,
                "rh.note.effects",
                count=len(effects["files"]),
                directory=EFFECTS_DIR,
            )
        )
    else:
        notes.append(text(language, "rh.note.effects_none"))
    notes.append(text(language, "rh.note.manifest", manifest=manifest))

    try:
        from .steam import invalidate_scan_cache

        invalidate_scan_cache(paths, game.install_dir)
    except Exception:
        pass

    return InstallResult(
        route=ROUTE,
        game=game.name,
        game_dir=target_dir,
        journal_id=journal.journal_id,
        verified=verified,
        notes=notes,
        manual_steps=plan.manual_steps,
    )
