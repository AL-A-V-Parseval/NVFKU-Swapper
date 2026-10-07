"""Locating and classifying the proprietary DLSS NR model.

``nvngx_dlssnr.dll`` is NVIDIA's and is roughly 158 MiB.  This module only *finds
and classifies* it.  ``weights.py`` is where the pinned, digest-verified download
lives and ``nvfku model --fetch`` is how a user reaches it — this file no longer
claims otherwise.  Every route that runs neural rendering needs the model beside
the game executable, so the discovery logic lives here once instead of being
reimplemented per route.

Two lessons are baked into this file, both from measuring the real machine:

*   **The digest is what matters, not the file's presence.**  The Linux add-on's
    author measured one specific build as stable and documented the failure mode
    of the others: "a mismatched model reported Success on every evaluate and then
    **crashed the game minutes into gameplay**".  Reporting "found a model"
    without saying *which* build would be actively misleading, so every candidate
    carries a verdict.
*   **Discovery must be bounded.**  An earlier version searched with recursive
    ``**/name`` globs.  On the development machine that walked entire mounted
    Steam libraries, cost ~3.4 s per plan, and made the GUI look hung.  The search
    is now anchored patterns first, then a walk bounded in depth, entries and
    wall-clock time.

The expensive hash is memoised per process, keyed on (path, size, mtime), so a
replaced file is re-hashed rather than trusted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .paths import Paths, human_size, sha256_file
from .steam import Game

MODEL_NAME = "nvngx_dlssnr.dll"

# The build NapXDD measured as stable with addon-dlssnr-linux v0.2.2.
TESTED_SHA256 = "e16bcf15e16e13f527491cdf7845b2fe6521a738d8f7c9c721866a8496e1fc8e"
TESTED_SIZE = 165_840_496

# Where the community tools leave this file.  These are *anchored* patterns, not
# recursive globs: the documented layout is `<mount>/DLSS5-Tools/Magpie-*/name`,
# so a fixed shape finds it in milliseconds.
_TOOL_PATTERNS = (
    "DLSS5-Tools/Magpie*/{name}",
    "DLSS5-Tools/*/{name}",
    "DLSS5-Tools/{name}",
    "Magpie*/{name}",
    "DLSS5*/{name}",
)

# Bounds for the fallback search, which exists only because a user may have put
# the file somewhere arbitrary.
_FALLBACK_DEPTH = 4
_FALLBACK_ENTRIES = 6000
_PRUNE_DIRS = {
    "steamapps", "compatdata", "shadercache", "node_modules", ".git", ".cache",
    "windows", "appdata", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "temp", "tmp", "wine",
    "content", "paks", "movies", "audio", "textures", "shaders",
}

# Directories inside a *game* tree that never hold this file but do hold
# thousands of entries. Deliberately NOT applied to paths the anchored search
# found: an earlier version reused the walk's prune list here too, and since the
# word "documents" was on it, the real candidate was discarded for nothing more
# than living on a volume with that name.
_GAME_TREE_PRUNE = _PRUNE_DIRS | {"documents", "downloads", "desktop", "pictures"}


@dataclass
class ModelCandidate:
    path: Path
    size: int
    sha256: str | None
    verdict: str  # "tested" | "untested" | "unknown-size"
    inside_game: bool = False

    @property
    def usable(self) -> bool:
        return self.verdict in ("tested", "untested")

    def describe(self, language: str | None = None) -> str:
        """One line about this build, for a plan's `{model}` placeholder.

        The verdict and the location phrase are words a user reads, so they follow
        the plan's language. The size, digest and path do not: they are values.
        """
        from .messages import text

        digest = f"{self.sha256[:16]}..." if self.sha256 else text(language, "model.unhashed")
        if self.inside_game:
            where = text(language, "model.in_game_folder")
        else:
            where = str(self.path.parent)
        verdict = text(language, f"model.verdict.{self.verdict}")
        return f"{human_size(self.size)}, sha256 {digest}, {verdict} ({where})"


def _search_volume(
    mount: Path, filename: str, *, limit: int = 6, budget_seconds: float = 0.6
) -> list[Path]:
    """Anchored patterns first, then one bounded walk as a fallback."""
    found: list[Path] = []
    for pattern in _TOOL_PATTERNS:
        try:
            for hit in list(mount.glob(pattern.format(name=filename)))[:limit]:
                if hit.is_file():
                    found.append(hit)
        except (OSError, ValueError):
            continue
        if found:
            return found

    deadline = time.monotonic() + budget_seconds
    visited = 0
    stack: list[tuple[Path, int]] = [(mount, 0)]
    while stack:
        if time.monotonic() > deadline or visited > _FALLBACK_ENTRIES:
            break
        directory, depth = stack.pop()
        try:
            entries = list(directory.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            visited += 1
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            if entry.name.lower() in _PRUNE_DIRS:
                continue
            try:
                if (entry / filename).is_file():
                    found.append(entry / filename)
                    if len(found) >= limit:
                        return found
            except OSError:
                pass
            if depth + 1 < _FALLBACK_DEPTH:
                stack.append((entry, depth + 1))
    return found


# Test seam.  A route's behaviour around the model -- refusal when it is absent, a
# warning when the digest is not the measured one, no copy when it is already in
# place -- is worth testing, but fabricating a 165,840,496-byte file with a
# specific SHA-256 is not.  Tests assign to this name; production code never does.
_OVERRIDE_DISCOVERY = None


def set_discovery_override(function) -> None:
    """Install (or clear, with ``None``) a discovery override for tests."""
    global _OVERRIDE_DISCOVERY
    _OVERRIDE_DISCOVERY = function


_SHA_CACHE: dict[tuple[str, int, int], str] = {}


def cached_sha256(path: Path) -> str:
    """SHA-256 of ``path``, memoised on (path, size, mtime).

    Hashing this file is the most expensive single step a plan can take, and it
    does not change between plans.  The key includes size and mtime, so a replaced
    file is re-hashed rather than trusted.  The cache lives for one process, which
    mainly serves the UI's engine session and the test suite.
    """
    try:
        stat = path.stat()
    except OSError:
        return sha256_file(path)
    key = (str(path), stat.st_size, int(stat.st_mtime_ns))
    hit = _SHA_CACHE.get(key)
    if hit is not None:
        return hit
    digest = sha256_file(path)
    if len(_SHA_CACHE) > 64:
        _SHA_CACHE.clear()
    _SHA_CACHE[key] = digest
    return digest


def discover(paths: Paths, game: Game) -> list[ModelCandidate]:
    """Every distinct build of the model reachable from this machine."""
    if _OVERRIDE_DISCOVERY is not None:
        return list(_OVERRIDE_DISCOVERY(paths, game))

    found: dict[str, Path] = {}

    def consider(path: Path) -> None:
        try:
            if path.is_file():
                found.setdefault(str(path).lower(), path)
        except OSError:
            pass

    # 1. Reuse the bounded game inventory. A hand-created/legacy Game has no
    # completeness marker and needs one scan; a detected Game never rewalks.
    from .steam import _inventory_game, _is_backup_path

    if game.detection_complete is None:
        _inventory_game(game)
    for existing in game.nvngx_dlssnr:
        if not _is_backup_path(existing, game.install_dir):
            consider(existing)
    if game.launch_exe is not None:
        consider(game.launch_exe.parent / MODEL_NAME)

    # 2. What `nvfku model` has already downloaded and verified.
    #
    # Checked before the volume sweep because it is one directory rather than a
    # filesystem, and because a user who deliberately fetched the tested build
    # should have it chosen without a disk scan to find it.
    weights_cache = paths.download_cache() / "weights"
    if weights_cache.is_dir():
        for hit in weights_cache.rglob(MODEL_NAME):
            consider(hit)

    # 3. The mounted volumes.
    #
    # Swept when the game has nothing *or* when what it has is not the tested
    # build. The original condition was `if not found`, which meant a game shipping
    # some other 158 MiB build would hide a good copy sitting three directories away
    # — the common case, since most recent titles carry one.
    def _has_tested() -> bool:
        for path in found.values():
            try:
                if path.stat().st_size == TESTED_SIZE and cached_sha256(path) == TESTED_SHA256:
                    return True
            except OSError:
                continue
        return False

    if not found or not _has_tested():
        for mount in paths.windows_mounts + paths.extra_search_dirs:
            if any(
                part.lower() in {"$recycle.bin", "system volume information"}
                for part in mount.parts
            ):
                continue
            for hit in _search_volume(mount, MODEL_NAME):
                consider(hit)
            if _has_tested():
                break

    candidates: list[ModelCandidate] = []
    seen_digests: set[str] = set()
    for path in found.values():
        try:
            size = path.stat().st_size
        except OSError:
            continue
        inside = _is_inside(path, game.install_dir)
        if size != TESTED_SIZE:
            candidates.append(
                ModelCandidate(
                    path=path, size=size, sha256=None, verdict="unknown-size", inside_game=inside
                )
            )
            continue
        digest = cached_sha256(path)
        if digest in seen_digests:
            continue
        seen_digests.add(digest)
        candidates.append(
            ModelCandidate(
                path=path,
                size=size,
                sha256=digest,
                verdict="tested" if digest == TESTED_SHA256 else "untested",
                inside_game=inside,
            )
        )

    def rank(candidate: ModelCandidate) -> tuple:
        return (
            candidate.verdict != "tested",
            not candidate.inside_game,
            len(str(candidate.path)),
        )

    candidates.sort(key=rank)
    if not candidates and game.detection_complete is False:
        raise RuntimeError("model discovery incomplete; absence is not established: "
                           + "; ".join(game.detection_warnings))
    return candidates


def _is_inside(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except (ValueError, OSError):
        return False


def best(candidates: list[ModelCandidate]) -> ModelCandidate | None:
    for candidate in candidates:
        if candidate.verdict == "tested":
            return candidate
    for candidate in candidates:
        if candidate.verdict == "untested":
            return candidate
    return None


def tested_count(candidates: list[ModelCandidate]) -> int:
    return sum(1 for c in candidates if c.verdict == "tested")
