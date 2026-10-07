"""Cooperative route transactions, not protection against power loss or Steam writes."""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import fcntl
import hashlib
import os
from pathlib import Path
import threading

from ..plan import InstallRefused

_local = threading.local()


@contextmanager
def game_lock(paths, game_dir):
    """Serialize install and rollback for a canonical game within a state root.

    Nonblocking across processes/threads; reentrant on the owning thread so a
    failed install can invoke rollback without deadlocking itself. Lock files
    remain in place: deleting them would allow concurrent locks on two inodes.
    """
    key = hashlib.sha256(str(Path(game_dir).resolve()).encode()).hexdigest()
    lock_path = paths.backups_root() / ".locks" / (key + ".lock")
    token = (os.getpid(), str(lock_path.resolve()))
    held = getattr(_local, "held", None)
    if held is None:
        held = _local.held = set()
    if token in held:
        yield
        return
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstallRefused(
                f"Another install or rollback is active for {game_dir}. "
                "Wait for it to finish and retry."
            ) from None
        held.add(token)
        try:
            yield
        finally:
            held.remove(token)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def preflight_files(game_dir, sources, destinations):
    """Reject missing inputs and unsafe destinations before any route mutation."""
    root = Path(game_dir).resolve()
    for source in sources:
        if not Path(source).is_file():
            raise InstallRefused(f"Required source is missing: {source}")
    for destination in destinations:
        target = Path(destination)
        if not target.parent.resolve().is_relative_to(root):
            raise InstallRefused(f"Destination escapes the game directory: {target}")
        if target.is_dir():
            raise InstallRefused(f"A directory occupies the required file: {target}")


def locked_install(function):
    """Keep the public route signature and prevent installing over partial work."""
    @wraps(function)
    def wrapped(paths, game, *args, **kwargs):
        from ..journal import list_journals

        with game_lock(paths, game.install_dir):
            pending = [entry for entry in list_journals(paths, game_dir=game.install_dir)
                       if (not entry.get("finished") or entry.get("rollback_started"))
                       and not entry.get("rolled_back")]
            if pending:
                ids = ", ".join(entry["id"] for entry in pending)
                raise InstallRefused(
                    f"Incomplete transaction for this game: {ids}. "
                    "Run rollback for that journal and resolve any reported failures before retrying."
                )
            return function(paths, game, *args, **kwargs)
    return wrapped


@contextmanager
def transaction(journal):
    """Compensate synchronous failures; retain an actionable journal on failure."""
    try:
        yield journal
        journal.finish()
    except BaseException as original:
        try:
            report = journal.rollback()
            ok = report.ok
        except BaseException as recovery:
            raise InstallRefused(
                f"Install failed ({original}); automatic rollback failed ({recovery}). "
                f"Incomplete transaction {journal.journal_id}: retry rollback for this journal "
                "before installing again."
            ) from original
        if not ok:
            raise InstallRefused(
                f"Install failed ({original}); automatic rollback is incomplete. "
                f"Retry rollback for journal {journal.journal_id} before installing again. "
                + "; ".join(report)
            ) from original
        raise
