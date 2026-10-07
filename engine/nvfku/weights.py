"""Acquiring the DLSS Neural Rendering model.

The model is `nvngx_dlssnr.dll`, a 158 MiB DLL that is genuinely NVIDIA's. It is
not a set of weights in a container, and it has no official public download: the
DLSS SDK ships headers and an import library only, and on this machine's Linux
driver the whole NGX payload is three files totalling 12 MiB with no NR model in
it at all. The file reaches a machine one of three ways, and every one of them is
recorded here rather than assumed:

1. **A game already ships it.** Owning a recent title is a legitimate source, and
   this machine has three builds from four games. `model.discover` finds these.
2. **An NVIDIA Windows driver package contains it.** This is what the community
   documentation tells people to do, and it is the only source that is NVIDIA's
   own. It is not automated here because the package is ~900 MiB and its internal
   layout is not pinned.
3. **A community release re-hosts it.** This module pins one, with its digest, so
   a download is verified rather than trusted.

Why pin a third-party mirror at all, when the rest of this tool refuses to fetch
NVIDIA binaries? Because the alternatives are worse. The status quo is a warning
that says the tested build is missing and leaves the user to find a 158 MiB file
with no digest to check it against -- which is how people end up running a build
that reports success on every evaluate and then crashes the game. A pinned URL
plus a pinned digest is checkable; a Discord link and a hope are not.

The upstream this pins is a community repository, not NVIDIA. It is labelled as
such in the UI, in `Build.source`, and in `docs/weights.md`, so nobody has to
guess where a 158 MiB binary came from or who signed it.
"""

from __future__ import annotations

import os
import shutil
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .paths import Paths, human_size, sha256_file

#: The build NapXDD measured as stable with addon-dlssnr-linux v0.2.2, and the one
#: `model.TESTED_SHA256` names. Kept as a literal here too so this module does not
#: import the model finder just to state a constant.
TESTED_SHA256 = "e16bcf15e16e13f527491cdf7845b2fe6521a738d8f7c9c721866a8496e1fc8e"
TESTED_SIZE = 165_840_496

MODEL_NAME = "nvngx_dlssnr.dll"


@dataclass(frozen=True)
class Build:
    """One known build of the model, and everything needed to judge it."""

    sha256: str
    size: int
    label: str
    version: str
    source: str
    vendor: str
    tested: bool
    note: str

    @property
    def short(self) -> str:
        return self.sha256[:16]


@dataclass(frozen=True)
class Source:
    """A pinned, verifiable place to get a build.

    ``vendor_signed`` is the field that matters and the one a user cannot check for
    themselves without opening the file's properties: it says whether the DLL is
    NVIDIA's own signed binary or a community rebuild. Both are recorded because
    both are in use, and conflating them would be the single most useful lie this
    module could tell.
    """

    build: Build
    url: str
    archive: str
    inner: str
    vendor_signed: bool
    origin: str

    def describe(self) -> str:
        signer = "NVIDIA-signed" if self.vendor_signed else "community rebuild"
        return f"{self.build.label} ({signer})"


#: The RTX 50 build: NVIDIA's own signed 310.8 runtime, as named by
#: NapXDD/addon-dlssnr-linux and by wilsjo2's install guide. This is the one the
#: add-on was measured against.
RTX50 = Build(
    sha256=TESTED_SHA256,
    size=TESTED_SIZE,
    label="DLSS NR 310.8.0 — RTX 50",
    version="310.8.0",
    source="NVIDIA-signed runtime, redistributed by RankFTW/rhi-repo",
    vendor="nvidia",
    tested=True,
    note="the build addon-dlssnr-linux v0.2.2 was measured against",
)

#: The cross-generation build, so a card that is not Blackwell has a route. Listed
#: but not downloadable: no pinned archive was found for it, and guessing a URL
#: would be worse than saying so.
CROSSGEN = Build(
    sha256="e67dee209320cdafe0e93e45675d7aa34323a53acc57a72b2e40a181581c989a",
    size=0,
    label="DLSS NR 310.8 — ShortFuse cross-generation",
    version="310.8",
    source="ShortFuse rebuild, referenced by wilsjo2/OptiScaler-DLSSNR-PreSR-Multipass",
    vendor="community",
    tested=False,
    note="for RTX 20/30/40; not the build the add-on was measured against",
)

#: What this machine's games and tools were found to carry. Recorded so a user can
#: see that a build is *recognised* rather than merely unrecognised, which is a
#: different and more useful statement.
KNOWN_UNPINNED: tuple[Build, ...] = (
    Build(
        sha256="984bee0f775c277d5829b8fd6775d53a7b0f75396c852b3aaf06a18375f81014",
        size=TESTED_SIZE,
        label="NVNGX DLSSNR (Magpie-Experimental)",
        version="unknown",
        source="DLSS5-Tools/Magpie-Experimental on this machine",
        vendor="nvidia",
        tested=False,
        note="same size as the tested build, different digest",
    ),
    Build(
        sha256="8270b350cd82de5ce89806872cdd6b6a9249b80836b91bbeb3573470744cc206",
        size=TESTED_SIZE,
        label="NVNGX DLSSNR (shipped in games)",
        version="unknown",
        source="bundled by DLSS5-Swapper 2.2.7 and shipped by Cyberpunk 2077, MSFS2024",
        vendor="nvidia",
        tested=False,
        note="same size as the tested build, different digest",
    ),
)

#: The one downloadable build. `archive` is the zip's name on disk; `inner` is the
#: member inside it.
RTX50_SOURCE = Source(
    build=RTX50,
    url=(
        "https://github.com/RankFTW/rhi-repo/releases/download/"
        "dlssnr-310.8.0/nvngx_dlssnr_310.8.0.zip"
    ),
    archive="nvngx_dlssnr_310.8.0.zip",
    inner=MODEL_NAME,
    vendor_signed=True,
    origin="feeder",
)

SOURCES: tuple[Source, ...] = (RTX50_SOURCE,)


class WeightsError(RuntimeError):
    """A model could not be obtained, with the reason a user can act on."""


def builds() -> tuple[Build, ...]:
    """Every build this tool can name, tested first."""
    return (RTX50, CROSSGEN, *KNOWN_UNPINNED)


def identify(digest: str) -> Build | None:
    """The build with this digest, or None if it is not one we know."""
    digest = digest.lower()
    for build in builds():
        if build.sha256.lower() == digest:
            return build
    return None


def source_for(build: Build) -> Source | None:
    for source in SOURCES:
        if source.build.sha256 == build.sha256:
            return source
    return None




def _proxy_url() -> str | None:
    """The configured proxy, if any.

    Read from the same environment the provider fetcher uses, so a machine behind a
    proxy does not have to configure it twice. GitHub's release CDN is unreachable
    directly from the network this was developed on, which is how the need for this
    was found.
    """
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        value = os.environ.get(name)
        if value:
            return value
    try:
        from . import providers

        return providers._ambient_proxy()
    except Exception:
        return None


def download(
    paths: Paths,
    source: Source = RTX50_SOURCE,
    *,
    logger=print,
    timeout: int = 120,
) -> Path:
    """Fetch and verify the source's archive, returning the cached file.

    Verified before it is moved into place, so a truncated or substituted download
    never becomes the file the rest of the tool trusts. The digest check is on the
    *inner* DLL, not the zip: a zip's digest changes whenever it is repacked, so
    pinning it would break on a re-upload that is otherwise identical.
    """
    cache = paths.download_cache() / "weights"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / source.archive

    if target.is_file() and target.stat().st_size > 0:
        logger(f"  cached   {source.archive} ({human_size(target.stat().st_size)})")
    else:
        logger(f"  fetch    {source.url}")
        partial = target.with_suffix(target.suffix + ".part")
        proxy = _proxy_url()
        if proxy:
            logger(f"  proxy    {proxy}")
        try:
            _stream(source.url, partial, proxy=proxy, timeout=timeout, logger=logger)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            partial.unlink(missing_ok=True)
            raise WeightsError(f"download failed: {exc}") from None
        os.replace(partial, target)
        logger(f"  saved    {source.archive} ({human_size(target.stat().st_size)})")

    inner = extract(source, target, cache)
    return inner


def _stream(url: str, target: Path, *, proxy: str | None, timeout: int, logger) -> None:
    """Download to ``target``, reporting progress at 16 MiB steps.

    Streamed rather than read whole: this file is 104 MiB, and holding it in memory
    alongside the zip is avoidable work.
    """
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"User-Agent": "nvfku"})
    with opener.open(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        step = 16 * 1024 * 1024
        next_report = step
        with target.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if done >= next_report:
                    if total:
                        pct = 100 * done / total
                        logger(f"  ...      {human_size(done)} / {human_size(total)} ({pct:.0f}%)")
                    else:
                        logger(f"  ...      {human_size(done)}")
                    next_report += step


def extract(source: Source, archive: Path, cache: Path) -> Path:
    """Pull the DLL out of the archive and verify its digest.

    Returns the extracted DLL's path. The archive stays on disk: re-extracting is
    free, and a user who wants to confirm the digest themselves should not have to
    download 104 MiB again to do it.
    """
    out = cache / source.build.short
    out.mkdir(parents=True, exist_ok=True)
    inner = out / MODEL_NAME

    if inner.is_file() and inner.stat().st_size == source.build.size and sha256_file(inner) == source.build.sha256:
        return inner

    try:
        with zipfile.ZipFile(archive) as zf:
            member = _find_member(zf, source.inner)
            if member is None:
                names = ", ".join(zf.namelist()[:8])
                archive.unlink(missing_ok=True)
                raise WeightsError(
                    f"{source.archive} does not contain {source.inner}; it holds: {names}"
                )
            with zf.open(member) as src, inner.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 256)
    except zipfile.BadZipFile:
        archive.unlink(missing_ok=True)
        raise WeightsError(
            f"{source.archive} is not a valid zip; it was removed, so retry the download"
        ) from None

    digest = sha256_file(inner)
    if digest != source.build.sha256:
        inner.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        raise WeightsError(
            "the downloaded model does not match the pinned digest\n"
            f"  expected {source.build.sha256}\n"
            f"  got      {digest}\n"
            "  the file was discarded rather than installed"
        )
    actual_size = inner.stat().st_size
    if actual_size != source.build.size:
        inner.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        raise WeightsError(
            f"the downloaded model is {actual_size} bytes, expected "
            f"{source.build.size}"
        )
    return inner


def _find_member(zf: zipfile.ZipFile, name: str) -> str | None:
    """Locate the DLL inside the archive, tolerating a directory prefix."""
    for info in zf.infolist():
        if info.is_dir():
            continue
        if Path(info.filename).name.lower() == name.lower():
            return info.filename
    return None


def install(
    paths: Paths,
    game_dir: Path,
    source: Source = RTX50_SOURCE,
    *,
    logger=print,
) -> Path:
    """Download the model and place it beside a game's executable.

    Copies rather than moves: the cached copy is the thing every future install
    draws on, and a game directory is something the user may delete at any time.
    """
    cached = download(paths, source, logger=logger)
    destination = game_dir / MODEL_NAME
    if destination.is_file() and sha256_file(destination) == source.build.sha256:
        logger(f"  present  {destination}")
        return destination
    shutil.copy2(cached, destination)
    logger(f"  placed   {destination} ({human_size(destination.stat().st_size)})")
    return destination
