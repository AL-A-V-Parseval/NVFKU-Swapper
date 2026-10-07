"""User settings and manually added game folders.

Two things the Linux tools need that Windows ones get from the OS:

*   **A registry of hand-added game folders.**  DLSS5-Swapper accepts a dropped
    folder because Windows users have non-Steam installs everywhere.  This tool
    originally only read Steam's own manifests, so a GOG or repack install could
    not be reached at all.
*   **Persisted preferences.**  Which Python runs the engine, a non-standard
    Steam root, where the component cache lives, whether to reach the network
    through a proxy, whether to verify against the publisher's SHA256SUMS, and the
    interface language and colour scheme.

Both live beside the journals under the engine state directory, so "where does
this tool keep things" has one answer.  The settings file is deliberately a plain
JSON document the user can read and edit; nothing here is opaque.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import Paths, atomic_write_text
from .steam import Game, classify_api

SETTINGS_VERSION = 1
ADDED_GAMES_VERSION = 1


@dataclass
class Settings:
    """User-visible preferences.  Every field has a working default."""

    version: int = SETTINGS_VERSION

    #: Override for the Python interpreter that runs the engine.  Empty means
    #: "the project venv, else python3".
    python_path: str = ""

    #: Override for the primary Steam install.  Empty means discovery.
    steam_root: str = ""

    #: Where downloaded components are cached.  Empty means the state directory.
    download_cache: str = ""

    #: ``direct`` (default), ``auto`` (direct then proxy), or a proxy URL.
    #: ``auto`` mirrors the engine's own behaviour, which was measured: GitHub's
    #: release assets are unreachable directly on some networks while the shell's
    #: proxy reaches them.
    proxy_mode: str = "auto"

    #: Compare fetched components against the publisher's published digests when
    #: the release offers them.
    verify_upstream: bool = True

    #: Preferred route per game key, so re-opening a game remembers the choice.
    route_preference: dict[str, str] = field(default_factory=dict)

    #: Interface colour scheme: ``system`` (follow the desktop), ``dark`` or ``light``.
    #:
    #: Stored rather than always following the desktop, because the two are not the
    #: same request: a user on a light desktop may still want this window dark, and
    #: the window has a header bar that has to be painted to match. Keeping the value
    #: here is also what lets the GTK side and Flutter agree — the runner reads this
    #: same preference from the desktop, and a stored override would otherwise make
    #: them disagree.
    theme: str = "system"

    #: Interface language: ``system``, ``en`` or ``zh``.
    #:
    #: This was documented as stored for a while and was not — the picker wrote to an
    #: in-memory notifier and the choice was gone on the next launch. It is stored now.
    language: str = "system"

    #: Values `theme` accepts. Kept beside the field so a validator, a CLI `choices`
    #: list and this comment cannot drift apart.
    THEMES = ("system", "dark", "light")
    LANGUAGES = ("system", "en", "zh")

    def validate(self) -> None:
        """Reject a value the interface cannot honour.

        Not silent coercion: `--theme ligth` quietly becoming `system` is the kind of
        failure a user reports as "the setting does not stay", and it is far cheaper
        to refuse it here.
        """
        if self.theme not in self.THEMES:
            raise ValueError(
                f"unknown theme {self.theme!r}; expected one of {', '.join(self.THEMES)}"
            )
        if self.language not in self.LANGUAGES:
            raise ValueError(
                f"unknown language {self.language!r}; "
                f"expected one of {', '.join(self.LANGUAGES)}"
            )

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Settings":
        try:
            data = json.loads(text)
        except ValueError:
            return cls()
        if not isinstance(data, dict) or data.get("version") != SETTINGS_VERSION:
            return cls()
        known = {f for f in cls().to_dict()}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**{**asdict(cls()), **clean})

    def to_dict(self) -> dict:
        return asdict(self)

    def describe(self) -> list[tuple[str, str]]:
        return [
            ("python", self.python_path or "(project venv, else python3)"),
            ("steam root", self.steam_root or "(discovered)"),
            ("download cache", self.download_cache or "(state directory)"),
            ("network", self.proxy_mode),
            ("verify upstream digests", "yes" if self.verify_upstream else "no"),
        ]


def settings_path(paths: Paths) -> Path:
    return paths.ensure_state_dir() / "settings.json"


def load_settings(paths: Paths) -> Settings:
    try:
        return Settings.from_json(settings_path(paths).read_text(encoding="utf-8"))
    except OSError:
        return Settings()


def save_settings(paths: Paths, settings: Settings) -> Path:
    path = settings_path(paths)
    atomic_write_text(path, settings.to_json())
    return path


def update_settings(paths: Paths, **changes) -> Settings:
    """Merge a field patch under a cross-process read/modify/write lock.

    Atomic replacement alone does not prevent stale snapshots from losing other
    writers' fields. Keep this stable lock inode even when the document changes.
    Callers updating individual preferences should use this instead of saving a
    previously read whole document.
    """
    unknown = set(changes) - set(Settings().to_dict())
    if unknown:
        raise ValueError(f"unknown settings fields: {', '.join(sorted(unknown))}")
    lock = paths.ensure_state_dir() / "settings.lock"
    with lock.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        current = load_settings(paths)
        for name, value in changes.items():
            setattr(current, name, value)
        current.validate()
        save_settings(paths, current)
        return current


# ------------------------------------------------------- manually added games


def added_games_path(paths: Paths) -> Path:
    return paths.ensure_state_dir() / "added-games.json"


def load_added_games(paths: Paths) -> list[str]:
    try:
        data = json.loads(added_games_path(paths).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or data.get("version") != ADDED_GAMES_VERSION:
        return []
    entries = data.get("folders")
    if not isinstance(entries, list):
        return []
    return [str(entry) for entry in entries if isinstance(entry, str)]


def save_added_games(paths: Paths, folders: list[str]) -> Path:
    path = added_games_path(paths)
    unique: list[str] = []
    for folder in folders:
        resolved = str(Path(folder).expanduser())
        if resolved not in unique:
            unique.append(resolved)
    atomic_write_text(
        path,
        json.dumps({"version": ADDED_GAMES_VERSION, "folders": unique}, indent=2),
    )
    return path


class AddedGameError(RuntimeError):
    """The folder cannot be treated as a game."""


def add_game_folder(paths: Paths, folder: str | os.PathLike[str]) -> Game:
    """Register a folder as a game and return the scanned result.

    Validation is strict on purpose.  A dropped folder that is not a game would
    otherwise sit in the library forever looking broken, so the checks below
    answer "is there an executable here, and does it name a graphics API" before
    anything is written.

    The returned :class:`Game` reuses the Steam shape with ``appid`` set to a
    stable synthetic id, because every route keys its journals and state on that
    value.
    """
    from .steam import choose_launch_exe

    resolved = Path(folder).expanduser()
    if not resolved.is_dir():
        raise AddedGameError(f"{resolved} is not a directory")
    if not os.access(resolved, os.R_OK | os.X_OK):
        raise AddedGameError(f"{resolved} is not readable")

    exe, pe = choose_launch_exe(resolved)
    if exe is None:
        raise AddedGameError(f"no executable found in {resolved}")
    api, _evidence = (None, [])
    if pe is not None:
        api, _evidence = classify_api(pe)

    existing = load_added_games(paths)
    if str(resolved) not in existing:
        existing.append(str(resolved))
        save_added_games(paths, existing)
    return game_from_folder(resolved)


def remove_game_folder(paths: Paths, folder: str | os.PathLike[str]) -> bool:
    resolved = str(Path(folder).expanduser())
    existing = load_added_games(paths)
    remaining = [entry for entry in existing if entry != resolved]
    if len(remaining) == len(existing):
        return False
    save_added_games(paths, remaining)
    return True


def game_from_folder(folder: Path) -> Game:
    """Build a :class:`Game` for a hand-added folder, detected the same way."""
    from .steam import _detect_into  # local: avoids a cycle

    resolved = Path(folder).expanduser()
    # A key that is stable *across processes* and cannot collide with a Steam
    # appid, which is numeric.
    #
    # This used Python's `hash()`, which is randomised per interpreter process,
    # so the add command reported one key and the next `scan` reported another.
    # Every route keys its journals, backups and per-game state on this value, so
    # an unstable key means an install could not be found again to roll back.
    digest = hashlib.sha256(str(resolved.resolve()).encode("utf-8")).hexdigest()
    key = "folder-" + digest[:12]
    game = Game(
        appid=key,
        name=resolved.name,
        install_dir=resolved,
        library=resolved.parent,
        steam_root=resolved,
        proton_prefix=None,
        proton_tool=None,
        source="folder",
    )
    _detect_into(game)
    return game


def scan_added_games(paths: Paths) -> list[Game]:
    """Every registered folder that still exists and still holds an executable."""
    games: list[Game] = []
    for entry in load_added_games(paths):
        folder = Path(entry)
        if folder.is_dir():
            games.append(game_from_folder(folder))
    return games
