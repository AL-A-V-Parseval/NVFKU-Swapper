"""Game artwork: Steam's own cover images, cached locally.

Steam publishes several image families per app on its CDN, and — the part that
matters here — **localised variants** alongside the English ones:

    library_600x900.jpg              poster, 600x900, English
    library_600x900_schinese.jpg     the same poster with a Chinese title
    header.jpg                       landscape banner, 460x215
    header_schinese.jpg
    library_hero.jpg                 the wide hero used on a game page

Two things were measured on the development machine before writing this:

*   Only **47 of 250** cached appids have ``library_600x900.jpg`` in
    ``appcache/librarycache``, and the games in this library that lack it are
    exactly the ones a user would look for (Cyberpunk 2077, Hogwarts Legacy,
    F1 24, MSFS 2024). So the local cache alone is not enough.
*   The CDN answered ``200`` for every family, both directly and through the
    proxy, so downloading once and keeping the file is worth it: the library then
    renders offline and the UI never blocks on a socket.

The local cache is still consulted first, because Steam already downloaded those
files and re-fetching them would be wasteful. The lookup order is therefore:

    1. Steam's local cache, localised, then English
    2. the CDN, localised, then English
    3. nothing — the caller draws a placeholder

A game added by hand has no appid and therefore no artwork. That is returned as
"none" rather than guessed at.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .paths import Paths, atomic_write_text, human_size
from .steam import Game

#: Image families, widest use first. `library_600x900` is the portrait poster
#: Steam's own grid uses; `header` is the landscape banner and is far more widely
#: present in the local cache.
POSTER = "library_600x900"
HEADER = "header"
HERO = "library_hero"

#: Steam's language directory names, so a caller asks for a language rather than
#: a filename suffix.
LOCALE_SUFFIX = {
    "schinese": "_schinese",
    "tchinese": "_tchinese",
    "english": "",
}

STEAM_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps"

#: Where Steam keeps what it has already downloaded.
LOCAL_CACHE_DIR = Path("appcache/librarycache")

# Candidate widths, best first. `_2x` is the high-DPI variant and is what a
# desktop with a scaled display should show.
_SCALE_SUFFIXES = ("_2x", "")


class ArtworkError(RuntimeError):
    """Artwork could not be fetched. Never fatal to the caller."""


@dataclass
class ArtworkResult:
    """What was found for one game, and where it came from."""

    appid: str
    path: Path | None
    source: str  # "cache" | "cdn" | "none"
    family: str | None = None
    localised: bool = False
    bytes: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.path is not None and self.path.is_file()

    def describe(self) -> str:
        if not self.found:
            return f"{self.appid}: no artwork"
        where = "Steam cache" if self.source == "cache" else "downloaded"
        lang = "localised" if self.localised else "English"
        return f"{self.appid}: {self.family} ({lang}) from {where}, {human_size(self.bytes)}"


def artwork_dir(paths: Paths) -> Path:
    directory = paths.ensure_state_dir() / "artwork"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def local_cache_dir(paths: Paths) -> Path | None:
    if paths.steam_root is None:
        return None
    candidate = paths.steam_root / LOCAL_CACHE_DIR
    return candidate if candidate.is_dir() else None


def _families_for(kind: str) -> list[str]:
    if kind == "poster":
        return [POSTER, HERO, HEADER]
    if kind == "hero":
        return [HERO, HEADER, POSTER]
    return [HEADER, POSTER, HERO]


def _suffixes(language: str | None) -> list[tuple[str, bool]]:
    """``(filename suffix, is_localised)`` pairs, best first."""
    if language and language in LOCALE_SUFFIX and LOCALE_SUFFIX[language]:
        return [(LOCALE_SUFFIX[language], True), ("", False)]
    return [("", False)]


def cdn_url(appid: str, family: str, *, suffix: str = "", scale: str = "") -> str:
    """The CDN URL for one image.

    ``scale`` is ``_2x`` for the high-DPI variant or empty.
    """
    return f"{STEAM_CDN}/{appid}/{family}{suffix}{scale}.jpg"


def find_local(paths: Paths, appid: str, kind: str, language: str | None) -> tuple[Path, str, bool] | None:
    """Artwork already on disk from Steam, if any.

    Returns ``(path, family, localised)``.
    """
    cache = local_cache_dir(paths)
    if cache is None:
        return None
    # Steam also keeps files under a hashed subdirectory in some versions.
    for directory in (cache / appid, cache):
        if not directory.is_dir():
            continue
        for family in _families_for(kind):
            for suffix, localised in _suffixes(language):
                for scale in _SCALE_SUFFIXES:
                    candidate = directory / f"{family}{suffix}{scale}.jpg"
                    if candidate.is_file() and candidate.stat().st_size > 0:
                        return candidate, family, localised
    return None


def target_name(appid: str, family: str, *, suffix: str = "", scale: str = "") -> str:
    return f"{appid}-{family}{suffix}{scale}.jpg"


def _download(url: str, destination: Path, *, logger, timeout: int = 30) -> bool:
    """Fetch one image, reusing the engine's transport (retries + proxy fallback)."""
    from . import providers

    try:
        blob = providers.http_get(url, timeout=timeout, attempts=2, logger=None)
    except Exception as exc:
        logger(f"  could not fetch {url}: {exc}")
        return False
    if not blob:
        logger(f"  empty response from {url}")
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(blob)
    return True


def ensure_artwork(
    paths: Paths,
    game: Game,
    *,
    kind: str = "poster",
    language: str | None = "schinese",
    force: bool = False,
    logger=print,
) -> ArtworkResult:
    """Make sure one game has artwork on disk, fetching it if needed.

    Never raises for a missing image: a game without artwork is a normal state
    (hand-added folders have none at all), and the caller has a placeholder.
    """
    if not game.is_steam:
        return ArtworkResult(
            appid=game.appid,
            path=None,
            source="none",
            notes=["added by hand, so Steam has no artwork for it"],
        )
    appid = game.appid
    directory = artwork_dir(paths)

    # 1. Already downloaded by us.
    if not force:
        for family in _families_for(kind):
            for suffix, localised in _suffixes(language):
                for scale in _SCALE_SUFFIXES:
                    cached = directory / target_name(appid, family, suffix=suffix, scale=scale)
                    if cached.is_file() and cached.stat().st_size > 0:
                        return ArtworkResult(
                            appid=appid,
                            path=cached,
                            source="cdn",
                            family=family,
                            localised=localised,
                            bytes=cached.stat().st_size,
                            notes=["already downloaded"],
                        )

    # 2. Steam's own cache, which is free.
    local = find_local(paths, appid, kind, language)
    if local is not None and not force:
        source_path, family, localised = local
        destination = directory / target_name(
            appid, family, suffix=LOCALE_SUFFIX.get(language or "", "") if localised else ""
        )
        try:
            if destination.resolve() != source_path.resolve():
                shutil.copy2(source_path, destination)
        except OSError:
            destination = source_path
        return ArtworkResult(
            appid=appid,
            path=destination,
            source="cache",
            family=family,
            localised=localised,
            bytes=destination.stat().st_size,
            notes=["copied from Steam's library cache"],
        )

    # 3. The CDN, localised first.
    for family in _families_for(kind):
        for suffix, localised in _suffixes(language):
            for scale in _SCALE_SUFFIXES:
                url = cdn_url(appid, family, suffix=suffix, scale=scale)
                destination = directory / target_name(appid, family, suffix=suffix, scale=scale)
                logger(f"  fetch {url}")
                if _download(url, destination, logger=logger):
                    return ArtworkResult(
                        appid=appid,
                        path=destination,
                        source="cdn",
                        family=family,
                        localised=localised,
                        bytes=destination.stat().st_size,
                    )
                # A 404 for this combination is expected; try the next.
    return ArtworkResult(
        appid=appid,
        path=None,
        source="none",
        notes=["neither the Steam cache nor the CDN had an image"],
    )


def index_path(paths: Paths) -> Path:
    return artwork_dir(paths) / "index.json"


def load_index(paths: Paths) -> dict:
    try:
        data = json.loads(index_path(paths).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_index(paths: Paths, index: dict) -> None:
    atomic_write_text(index_path(paths), json.dumps(index, indent=2, sort_keys=True))


def ensure_library_artwork(
    paths: Paths,
    games: list[Game],
    *,
    kind: str = "poster",
    language: str | None = "schinese",
    force: bool = False,
    logger=print,
) -> list[ArtworkResult]:
    """Fetch artwork for a whole library, recording what was found.

    The index lets the UI answer "which games have a cover" without hitting the
    filesystem for every row on every frame.
    """
    index = load_index(paths) if not force else {}
    results: list[ArtworkResult] = []
    for game in games:
        result = ensure_artwork(paths, game, kind=kind, language=language, force=force, logger=logger)
        results.append(result)
        index[game.appid] = {
            "path": str(result.path) if result.found else None,
            "family": result.family,
            "localised": result.localised,
            "source": result.source,
            "at": time.time(),
        }
        if result.found:
            logger(f"  {game.name}: {result.describe()}")
    save_index(paths, index)
    return results
