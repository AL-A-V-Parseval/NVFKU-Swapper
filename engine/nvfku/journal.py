"""Transactional file journal.

The whole point of this tool over "copy some DLLs in by hand" is that every
change is recorded before it happens and can be undone exactly.  This mirrors
what DLSS5-Swapper calls ``_DLSS5_Backup`` and what DLSS5-Feeder's installer
calls "automatic backups", but the record is written *first* and the operation
is only applied once the record is durable.

On-disk layout::

    <state_root>/backups/
        index.json                      # every journal ever written
        <game-key>/
            <journal-id>/
                manifest.json
                files/files/0000-original.dll   # a pre-image

The doubled `files/` is real, not a typo here: `_next_name` appends its tag to
`_files_dir`, and every caller passes the tag "files". That is the layout on disk
today and rollback reads it by path, so it is documented rather than changed. A
`created/` tree was described in this docstring for a while and never existed.

A journal is append-only while a route runs.  ``rollback()`` replays it
backwards: creations are deleted, replacements are restored from the pre-image.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from .paths import Paths, atomic_write_text, make_executable, sha256_file

#: Every kind this class can record. `adopted` and `absent` are produced by
#: `adopt` and `record_absent`, so they belong here: leaving them out was both a
#: wrong annotation — which is what the `type: ignore` in `install_file` was
#: papering over — and a KeyError waiting in `Operation.describe`.
OpKind = Literal[
    "created", "replaced", "deleted", "mkdir", "symlink", "note", "adopted", "absent"
]

MANIFEST_VERSION = 1


@dataclass
class Operation:
    kind: OpKind
    path: str
    """Absolute path inside the game directory."""
    backup: str | None = None
    """Relative path of the pre-image inside the journal directory, if any."""
    sha256: str | None = None
    size: int | None = None
    mode: int | None = None
    source: str | None = None
    """Where the new content came from (URL, cache path, ...). For reporting."""
    note: str | None = None
    at: float = field(default_factory=time.time)

    def describe(self) -> str:
        verb = {
            "created": "create",
            "replaced": "replace",
            "deleted": "delete",
            "mkdir": "mkdir",
            "symlink": "symlink",
            "note": "note",
            # Both are recorded by this class and neither had a verb, so describing
            # the operation raised KeyError — see the writer tests that adopt a file
            # and record an absence.
            "adopted": "adopt",
            "absent": "absent",
        }[self.kind]
        extra = f" <- {self.source}" if self.source else ""
        note = f"  ({self.note})" if self.note else ""
        return f"{verb} {self.path}{extra}{note}"


@dataclass
class Journal:
    id: str
    game_key: str
    game_dir: str
    route: str
    created_at: float
    operations: list[Operation] = field(default_factory=list)
    finished: bool = False
    rolled_back: bool = False
    tool: dict = field(default_factory=dict)

    # ------------------------------------------------------------ persistence

    def to_dict(self) -> dict:
        return {
            "version": MANIFEST_VERSION,
            "id": self.id,
            "game_key": self.game_key,
            "game_dir": self.game_dir,
            "route": self.route,
            "created_at": self.created_at,
            "finished": self.finished,
            "rolled_back": self.rolled_back,
            "tool": self.tool,
            "operations": [asdict(op) for op in self.operations],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Journal":
        return cls(
            id=data["id"],
            game_key=data["game_key"],
            game_dir=data["game_dir"],
            route=data["route"],
            created_at=data.get("created_at", 0.0),
            operations=[Operation(**op) for op in data.get("operations", [])],
            finished=data.get("finished", False),
            rolled_back=data.get("rolled_back", False),
            tool=data.get("tool", {}),
        )


def _same_path(a: str | os.PathLike[str], b: str | os.PathLike[str]) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class FileJournal:
    """Records and reverses changes to one game directory."""

    def __init__(self, paths: Paths, game_dir: os.PathLike[str] | str, route: str, game_key: str | None = None):
        self.paths = paths
        self.game_dir = Path(game_dir).resolve()
        self.route = route
        self.game_key = game_key or _key_for(self.game_dir)
        self.journal_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.dir = paths.backups_root() / self.game_key / self.journal_id
        self._files_dir = self.dir / "files"
        self._journal = Journal(
            id=self.journal_id,
            game_key=self.game_key,
            game_dir=str(self.game_dir),
            route=route,
            created_at=time.time(),
            tool={"name": "nvfku", "journal_version": MANIFEST_VERSION},
        )
        self._counter = 0

    # ------------------------------------------------------------- guardrails

    def _assert_inside_game(self, path: os.PathLike[str] | str) -> Path:
        resolved = Path(os.path.abspath(path))
        game = Path(os.path.abspath(self.game_dir))
        try:
            resolved.relative_to(game)
        except ValueError:
            raise ValueError(
                f"refusing to touch {resolved}: outside the game directory {game}"
            ) from None
        return resolved

    def _next_name(self, path: Path, tag: str) -> Path:
        self._counter += 1
        return self._files_dir / tag / f"{self._counter:04d}-{path.name}"

    def _flush(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        manifest = self.dir / "manifest.json"
        atomic_write_text(manifest, json.dumps(self._journal.to_dict(), indent=2))
        _update_index(self.paths, self._journal)
        return manifest

    def _record(self, op: Operation) -> None:
        self._journal.operations.append(op)
        self._flush()

    # ----------------------------------------------------------- mutating API

    def note(self, message: str) -> None:
        self._record(Operation(kind="note", path=str(self.game_dir), note=message))

    def mkdir(self, path: os.PathLike[str] | str) -> Path:
        """Create a directory chain, remembering where the chain *started*.

        ``mkdir(parents=True)`` can create several levels at once.  Recording
        only the leaf would leave the intermediate levels behind on rollback, so
        the deepest already-existing ancestor is stored in ``note`` and the
        whole created chain is removed on undo.
        """
        target = self._assert_inside_game(path)
        if target.is_dir():
            return target
        existing_ancestor = target.parent
        while not existing_ancestor.exists() and existing_ancestor != self.game_dir.parent:
            existing_ancestor = existing_ancestor.parent
        self._record(
            Operation(
                kind="mkdir",
                path=str(target),
                note=str(existing_ancestor),
            )
        )
        target.mkdir(parents=True, exist_ok=True)
        return target

    def install_file(
        self,
        src: os.PathLike[str] | str,
        dest: os.PathLike[str] | str,
        *,
        source_label: str | None = None,
        executable: bool = False,
    ) -> Operation:
        """Copy ``src`` to ``dest``, backing up whatever was there.

        Returns the recorded operation.  The pre-image is copied *before* the
        replacement, so a crash between the two leaves an unused backup rather
        than an unrecoverable file.
        """
        src_path = Path(src)
        if not src_path.is_file():
            raise FileNotFoundError(f"source missing: {src_path}")
        dest_path = self._assert_inside_game(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        existed = dest_path.exists() or dest_path.is_symlink()
        backup_rel: str | None = None
        sha: str | None = None
        size: int | None = None
        mode: int | None = None
        # Annotated so the type checker knows this is one of `OpKind`'s members
        # rather than a plain `str` — which is what the `type: ignore` here used to
        # suppress, back when `OpKind` was missing members this class produces.
        stored_as: OpKind = "replaced" if existed else "created"

        if existed:
            pre = self._next_name(dest_path, "files")
            pre.parent.mkdir(parents=True, exist_ok=True)
            if dest_path.is_symlink():
                # Store the link target as text; restoring a symlink by
                # materialising its target would silently change semantics
                # inside a Proton prefix.
                target = os.readlink(dest_path)
                atomic_write_text(pre, target)
                backup_rel = str(pre.relative_to(self.dir))
                self._record_marker(pre, symlink_target=target)
            else:
                pre.write_bytes(dest_path.read_bytes())
                backup_rel = str(pre.relative_to(self.dir))
                sha = sha256_file(dest_path)
                size = dest_path.stat().st_size
                mode = dest_path.stat().st_mode

        op = Operation(
            kind=stored_as,
            path=str(dest_path),
            backup=backup_rel,
            sha256=sha,
            size=size,
            mode=mode,
            source=source_label or str(src_path),
        )
        self._record(op)

        # Write via a temporary file in the destination directory, so a partial
        # copy can never be mistaken for a working DLL.
        tmp = dest_path.with_name(dest_path.name + ".nvfku-new")
        if tmp.exists():
            tmp.unlink()
        tmp.write_bytes(src_path.read_bytes())
        if executable:
            make_executable(tmp)
        os.replace(tmp, dest_path)
        return op

    def _record_marker(self, pre: Path, *, symlink_target: str) -> None:
        marker = pre.with_suffix(pre.suffix + ".symlink")
        atomic_write_text(marker, symlink_target)

    def write_text(
        self,
        dest: os.PathLike[str] | str,
        text: str,
        *,
        source_label: str = "generated",
        append: bool = False,
    ) -> Operation:
        """Write generated text, journalling any previous file.

        With ``append``, the existing contents are kept and the text added after
        them. Rollback is unaffected: the pre-image captured here is the whole
        original file, so undoing an append restores it exactly. This exists for
        logs, where the valuable part is what the *previous* run recorded.
        """

        dest_path = self._assert_inside_game(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        existed = dest_path.exists() or dest_path.is_symlink()
        backup_rel = None
        if existed:
            pre = self._next_name(dest_path, "files")
            pre.parent.mkdir(parents=True, exist_ok=True)
            if dest_path.is_symlink():
                target = os.readlink(dest_path)
                atomic_write_text(pre, target)
                self._record_marker(pre, symlink_target=target)
            else:
                pre.write_bytes(dest_path.read_bytes())
            backup_rel = str(pre.relative_to(self.dir))
        op = Operation(
            kind="replaced" if existed else "created",
            path=str(dest_path),
            backup=backup_rel,
            source=source_label,
        )
        self._record(op)
        if append:
            with open(dest_path, "a", encoding="utf-8") as handle:
                handle.write(text)
        else:
            atomic_write_text(dest_path, text)
        return op

    def adopt(self, path: os.PathLike[str] | str, *, source_label: str = "pre-existing") -> Operation:
        """Record a file's current contents as the pre-image, without writing it.

        For a file an external program is about to overwrite. Called *before* that
        program runs, it is what makes the overwrite undoable: rollback restores
        the recorded bytes. Calling it after would capture the wrong contents,
        which is why the ordering is in the name.
        """
        target = self._assert_inside_game(path)
        if not target.is_file():
            raise FileNotFoundError(target)
        pre = self._next_name(target, "files")
        pre.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            os.symlink(os.readlink(target), pre)
            self._record_marker(pre, symlink_target=os.readlink(target))
        else:
            pre.write_bytes(target.read_bytes())
        op = Operation(
            kind="adopted",
            path=str(target),
            backup=str(pre.relative_to(self.dir)),
            source=source_label,
        )
        self._record(op)
        return op

    def record_absent(self, path: os.PathLike[str] | str, *, source_label: str = "created") -> Operation:
        """Record that a file did **not** exist, so rollback may delete it.

        Used for files an external program created. Rollback removes the file only
        if no pre-image was adopted for it, so a newly-created file is cleaned up
        while a replaced one is restored instead of deleted.
        """
        target = self._assert_inside_game(path)
        # Refuse to claim a file is disposable when a pre-image exists for it: that
        # combination would delete a file rollback is supposed to restore. The
        # guard makes the mistake visible at record time rather than at undo time.
        if any(
            other.kind == "adopted" and other.path == str(target)
            for other in self._journal.operations
        ):
            raise ValueError(f"{target} has a pre-image; it is not disposable")
        op = Operation(kind="absent", path=str(target), source=source_label)
        self._record(op)
        return op

    def remove(self, path: os.PathLike[str] | str, *, source_label: str = "removed") -> Operation:
        target = self._assert_inside_game(path)
        if not (target.exists() or target.is_symlink()):
            raise FileNotFoundError(target)
        pre = self._next_name(target, "files")
        pre.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            atomic_write_text(pre, os.readlink(target))
            self._record_marker(pre, symlink_target=os.readlink(target))
        else:
            pre.write_bytes(target.read_bytes())
        op = Operation(
            kind="deleted",
            path=str(target),
            backup=str(pre.relative_to(self.dir)),
            source=source_label,
        )
        self._record(op)
        target.unlink()
        return op

    def finish(self) -> Path:
        self._journal.finished = True
        manifest = self._flush()
        # Detection for this game is now stale: the install just changed its
        # contents, and a cached verdict would keep reporting the old state.
        try:
            from .steam import invalidate_scan_cache

            invalidate_scan_cache(self.paths, self.game_dir)
        except Exception:
            # Cache invalidation must never fail an install that succeeded.
            pass
        return manifest

    # --------------------------------------------------------------- rollback

    def rollback(self) -> list[str]:
        """Undo every operation, newest first.  Returns human-readable lines."""
        lines: list[str] = []
        for op in reversed(self._journal.operations):
            try:
                lines.append(self._undo(op))
            except Exception as exc:  # keep going; report what failed
                lines.append(f"FAILED to undo {op.path}: {exc}")
        self._journal.rolled_back = True
        self._flush()
        return lines

    def _undo(self, op: Operation) -> str:
        target = Path(op.path)
        if op.kind == "mkdir":
            # Walk the created chain upwards, removing only empty directories,
            # and stop at the ancestor that existed before the install.
            stop_at = Path(op.note) if op.note else self.game_dir
            removed: list[str] = []
            current = target
            while True:
                try:
                    current.rmdir()
                    removed.append(str(current))
                except OSError:
                    break
                if os.path.normcase(str(current)) == os.path.normcase(str(stop_at)):
                    break
                parent = current.parent
                if parent == current:
                    break
                current = parent
            if removed:
                return f"rmdir {' , '.join(removed)}"
            return f"kept {target} (not empty)"
        if op.kind == "note":
            return f"skip note {op.note}"

        if op.kind == "created":
            if target.is_symlink() or target.exists():
                target.unlink()
                return f"deleted {target}"
            return f"already absent {target}"

        if op.kind == "absent":
            # Only delete when nothing was adopted for this path: an adopted entry
            # means the file existed before and is restored by its own operation.
            adopted = any(
                other.kind == "adopted" and other.path == op.path
                for other in self._journal.operations
            )
            if adopted:
                return f"kept {target} (a pre-image exists for it)"
            if target.is_symlink() or target.exists():
                target.unlink()
                return f"deleted {target} (did not exist before)"
            return f"already absent {target}"

        if not op.backup:
            return f"no pre-image for {target}"

        pre = self.dir / op.backup
        marker = pre.with_suffix(pre.suffix + ".symlink")
        if marker.exists():
            if target.is_symlink() or target.exists():
                target.unlink()
            os.symlink(marker.read_text().strip(), target)
            return f"restored symlink {target}"
        if not pre.exists():
            return f"MISSING pre-image for {target} ({pre})"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        target.write_bytes(pre.read_bytes())
        if op.mode:
            try:
                os.chmod(target, op.mode)
            except OSError:
                pass
        return f"restored {target}"


# ------------------------------------------------------------------ utilities


def _key_for(game_dir: Path) -> str:
    import hashlib

    return hashlib.sha256(str(game_dir).encode()).hexdigest()[:16]


def _update_index(paths: Paths, journal: Journal) -> None:
    index_path = paths.backups_root() / "index.json"
    try:
        index = json.loads(index_path.read_text())
    except (OSError, ValueError):
        index = {"version": MANIFEST_VERSION, "journals": []}
    journals = [j for j in index.get("journals", []) if j.get("id") != journal.id]
    journals.append(
        {
            "id": journal.id,
            "game_key": journal.game_key,
            "game_dir": journal.game_dir,
            "route": journal.route,
            "created_at": journal.created_at,
            "finished": journal.finished,
            "rolled_back": journal.rolled_back,
            "operations": len(journal.operations),
        }
    )
    journals.sort(key=lambda j: j.get("created_at", 0), reverse=True)
    index["journals"] = journals[:500]
    atomic_write_text(index_path, json.dumps(index, indent=2))


def load_journal(paths: Paths, journal_id: str) -> Journal:
    root = paths.backups_root()
    for manifest in root.glob(f"*/{journal_id}/manifest.json"):
        return Journal.from_dict(json.loads(manifest.read_text()))
    raise FileNotFoundError(f"no journal {journal_id}")


def journal_dir(paths: Paths, journal: Journal) -> Path:
    return paths.backups_root() / journal.game_key / journal.id


def list_journals(paths: Paths, *, game_dir: os.PathLike[str] | str | None = None) -> list[dict]:
    index_path = paths.backups_root() / "index.json"
    try:
        index = json.loads(index_path.read_text())
    except (OSError, ValueError):
        return []
    entries: Iterable[dict] = index.get("journals", [])
    if game_dir is not None:
        entries = [e for e in entries if _same_path(e.get("game_dir", ""), game_dir)]
    return list(entries)


def rollback_journal(paths: Paths, journal_id: str) -> list[str]:
    journal = load_journal(paths, journal_id)
    handle = FileJournal.__new__(FileJournal)  # rehydrate without a fresh dir
    handle.paths = paths
    handle.game_dir = Path(journal.game_dir)
    handle.route = journal.route
    handle.game_key = journal.game_key
    handle.journal_id = journal.id
    handle.dir = journal_dir(paths, journal)
    handle._files_dir = handle.dir / "files"
    handle._journal = journal
    handle._counter = len(journal.operations)
    return handle.rollback()
