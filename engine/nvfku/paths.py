"""Filesystem layer.

Everything that touches the disk goes through here so the rest of the engine
stays testable: callers pass a :class:`Paths` instance instead of reaching for
``os.path.expanduser`` themselves, and tests hand in a temporary root.

Two rules this module exists to enforce:

*   **Never write into a game directory without a journal.**  All mutating
    helpers return the operations they performed so a route can hand them to
    :mod:`nvfku.journal`.
*   **Never follow a symlink when replacing a file.**  Proton prefixes and the
    DXVK/NVAPI installs inside them are full of symlinks into the Steam runtime
    (see the ComfyUI Linux guide: "replacing symlinks rather than following
    them").  Replacing one by writing *through* it would edit the runtime.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

# Files above this size are hashed with a memory-bounded chunk size.  The DLSS
# NR model is ~158 MiB and shows up on several code paths, so hashing must not
# be a memory event.
_CHUNK = 1024 * 1024


def sha256_file(path: os.PathLike[str] | str, *, limit: int | None = None) -> str:
    """SHA-256 of a file, read in chunks.

    ``limit`` hashes only the first N bytes, which is what
    :func:`looks_like_lfs_pointer` needs and what a cheap "did this file change
    at all" check wants.
    """
    digest = hashlib.sha256()
    remaining = limit
    with open(path, "rb") as handle:
        while True:
            want = _CHUNK if remaining is None else min(_CHUNK, remaining)
            if want <= 0:
                break
            block = handle.read(want)
            if not block:
                break
            digest.update(block)
            if remaining is not None:
                remaining -= len(block)
    return digest.hexdigest()


def looks_like_lfs_pointer(path: os.PathLike[str] | str) -> bool:
    """True for a Git-LFS pointer file rather than the binary it stands for.

    The ComfyUI Linux PR calls this out explicitly: LFS placeholders have to be
    detected *before* launch, or you get a confusing runtime failure much
    later.  We apply the same check to every downloaded binary.
    """
    try:
        if os.path.getsize(path) > 1024:
            return False
        with open(path, "rb") as handle:
            head = handle.read(64)
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec")


def file_fingerprint(path: os.PathLike[str] | str) -> dict:
    """Size, SHA-256 and symlink status, or ``{"exists": False}``."""
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return {"exists": False}
    info: dict = {"exists": True, "symlink": path.is_symlink()}
    if path.is_symlink():
        info["target"] = os.readlink(path)
    try:
        st = path.stat()
        info["size"] = st.st_size
        info["readable"] = os.access(path, os.R_OK)
        info["lfs_pointer"] = looks_like_lfs_pointer(path)
    except OSError as exc:
        info["error"] = str(exc)
    return info


@dataclass(frozen=True)
class Paths:
    """Where this machine keeps the things we manage.

    ``steam_root`` is the *primary* Steam install (the one with
    ``steamapps/libraryfolders.vdf``); additional libraries are discovered by
    :mod:`nvfku.steam`.
    """

    home: Path
    state_root: Path
    steam_root: Path | None = None
    windows_mounts: tuple[Path, ...] = ()
    extra_search_dirs: tuple[Path, ...] = ()

    @classmethod
    def discover(
        cls,
        home: os.PathLike[str] | str | None = None,
        *,
        state_root: os.PathLike[str] | str | None = None,
        extra_search_dirs: Iterable[os.PathLike[str] | str] = (),
    ) -> "Paths":
        home_path = Path(home) if home else Path(os.path.expanduser("~"))
        state = Path(state_root) if state_root else home_path / ".local/share/nvfku"

        candidates = [
            home_path / ".local/share/Steam",
            home_path / ".steam/steam",
            home_path / ".steam/root",
            home_path / ".var/app/com.valvesoftware.Steam/data/Steam",  # Flatpak
        ]
        steam_root = next(
            (path for path in candidates if (path / "steamapps").is_dir()), None
        )

        # Mounted Windows volumes are the most likely place to find the
        # proprietary files we may never redistribute (nvngx_dlssnr.dll and
        # friends).  We only *report* them; nothing is copied automatically.
        mounts = []
        media = Path("/run/media") / home_path.name
        if media.is_dir():
            try:
                mounts.extend(sorted(entry for entry in media.iterdir() if entry.is_dir()))
            except OSError:
                pass
        for prefix in (Path("/mnt"), Path("/media")):
            if prefix.is_dir():
                try:
                    mounts.extend(sorted(e for e in prefix.iterdir() if e.is_dir()))
                except OSError:
                    pass

        return cls(
            home=home_path,
            state_root=state,
            steam_root=steam_root,
            windows_mounts=tuple(dict.fromkeys(mounts)),
            extra_search_dirs=tuple(Path(p) for p in extra_search_dirs),
        )

    # ---------------------------------------------------------------- helpers

    def _migrate_legacy_state(self) -> None:
        """Bring forward state written under the project's former name.

        The package was renamed from `dlss5ctl` to `nvfku`, which moved the default
        state root. That root holds the **only** copy of the files an install
        replaced, so silently starting fresh would strand every rollback the user
        had. Merging is one-directional: a file already present in the new root is
        never overwritten, because the old tree is a fallback rather than an
        authority.

        Runs once and leaves the old directory in place. Deleting someone's backups
        as a side effect of a rename would be indefensible.
        """
        legacy = self.home / ".local/share/dlss5ctl"
        if not legacy.is_dir() or legacy.resolve() == self.state_root.resolve():
            return
        marker = self.state_root / ".migrated-from-dlss5ctl"
        if marker.exists():
            return
        try:
            copied = 0
            for item in legacy.rglob("*"):
                if item.is_dir():
                    continue
                target = self.state_root / item.relative_to(legacy)
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                copied += 1
            atomic_write_text(
                marker,
                f"merged {copied} file(s) from {legacy}\n",
            )
        except OSError:
            # A migration failure must not stop the tool from running; the legacy
            # directory is still there for the user to copy by hand.
            pass

    def ensure_state_dir(self) -> Path:
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_state()
        return self.state_root

    def download_cache(self) -> Path:
        cache = self.ensure_state_dir() / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        return cache

    def backups_root(self) -> Path:
        root = self.ensure_state_dir() / "backups"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def profiles_root(self) -> Path:
        root = self.ensure_state_dir() / "profiles"
        root.mkdir(parents=True, exist_ok=True)
        return root


# --------------------------------------------------------------------- copies


def atomic_copy(src: os.PathLike[str] | str, dest: os.PathLike[str] | str) -> None:
    """Copy ``src`` over ``dest`` without ever writing through a symlink.

    If ``dest`` is a symlink it is replaced by a regular file (``replace_symlink``
    semantics), matching what the Linux DLSS setups require inside a Proton
    prefix.
    """
    src, dest = Path(src), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        dest.unlink()
    fd, tmp_name = tempfile.mkstemp(prefix=".nvfku-", dir=str(dest.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def atomic_write_text(
    dest: os.PathLike[str] | str, text: str, *, encoding: str = "utf-8"
) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        dest.unlink()
    fd, tmp_name = tempfile.mkstemp(prefix=".nvfku-", dir=str(dest.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def make_executable(path: os.PathLike[str] | str) -> None:
    path = Path(path)
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def human_size(num: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(num) < 1024 or unit == "GiB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024
    return f"{num:.1f} GiB"


def iter_files(root: os.PathLike[str] | str, *, max_depth: int = 6) -> Iterator[Path]:
    """Bounded walk.  Game directories contain shader caches with tens of
    thousands of files; an unbounded rglob over a Proton prefix is a hang."""
    root = Path(root)
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        if len(current.parts) - base_depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git"}]
        for name in filenames:
            yield current / name
