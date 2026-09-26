"""Guard-steam launch-option writer.

This module exists because an experiment
([docs/experiment-localconfig.md](../../docs/experiment-localconfig.md)) measured
what Steam actually does to ``localconfig.vdf``, and the answer is specific
enough to build against:

*   **Steam merges rather than clobbers.** It rewrites the whole file on its own
    schedule and preserves keys it does not know about, including their exact
    indentation.
*   **An edit written while Steam is closed survives** a startup-and-rewrite
    cycle, because on startup Steam *reads* the file.
*   **An edit written while Steam is running is reverted**, because Steam keeps
    each app's ``LaunchOptions`` in memory and writes its copy back.

So the rules below are not defensive coding style; each one is one of those
measurements turned into a precondition:

1.  Refuse to write while a Steam client is running.
2.  Edit exactly one line, by brace/indent surgery. The file also holds friends,
    avatars, cloud-sync state and packed fields, none of which are ours.
3.  Back up first and verify the backup's digest.
4.  Write atomically, then validate: brace balance still zero, the key re-reads
    with the value we intended.
5.  Report that Steam must be restarted for the change to be adopted, and that a
    verification should happen after that restart rather than after the write.

Nothing here is allowed to "fix up" the file. If a precondition fails, the
correct answer is to refuse and say why.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .paths import Paths, atomic_write_text, sha256_file

# The binaries that mean "a Steam client is up". `ubuntu12_32/steam` is the
# client itself; the runtime wrappers are not.
STEAM_CLIENT_SUFFIXES = (
    "ubuntu12_32/steam",
    "ubuntu12_64/steam",
    "steam.sh",
)

def parse_vdf_line(line: str) -> tuple[str, str, str | None] | None:
    """``(indent, key, value)`` for a key/value line, ``value=None`` for a block.

    Indentation in this dialect is tabs only: 5 for an app key, 6 for its children,
    and two tabs between a key and its value. Measured, not guessed.

    Written as a small scanner rather than a regular expression because a VDF
    value may contain an escaped quote: the lexical shape is the same as
    ``read_launch_options`` needs, and ``"VAR=\"a b\" %command%"`` is a value
    this tool itself can produce. A ``".*"`` pattern silently fails on that,
    because the closing quote it finds is the escaped one.
    """
    indent_len = len(line) - len(line.lstrip("\t"))
    indent = line[:indent_len]
    rest = line[indent_len:].rstrip("\r\n")
    if not rest:
        return None
    if rest == "{":
        return indent, "", None

    def scan_quoted(text: str, start: int) -> tuple[str, int] | None:
        if start >= len(text) or text[start] != '"':
            return None
        out: list[str] = []
        index = start + 1
        while index < len(text):
            char = text[index]
            if char == "\\" and index + 1 < len(text):
                out.append(text[index + 1])
                index += 2
                continue
            if char == '"':
                return "".join(out), index + 1
            out.append(char)
            index += 1
        return None

    scanned_key = scan_quoted(rest, 0)
    if scanned_key is None:
        return None
    key, after_key = scanned_key
    tail = rest[after_key:]
    if not tail.strip():
        return indent, key, None  # a block header
    if not tail.startswith("\t"):
        return None
    value_start = after_key + len(tail) - len(tail.lstrip("\t"))
    scanned_value = scan_quoted(rest, value_start)
    if scanned_value is None:
        return None
    return indent, key, scanned_value[0]


class SteamConfigError(RuntimeError):
    """A precondition failed. Nothing was written."""


@dataclass
class WriteResult:
    path: Path
    appid: str
    value: str
    previous: str | None
    #: None when nothing was written because the value was already correct. There is
    #: no backup in that case because the file was not modified.
    backup: Path | None
    backup_sha256: str
    created_key: bool
    verified: bool
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        if self.backup is None:
            action = "unchanged"
        else:
            action = "added" if self.created_key else "updated"
        lines = [
            f"{action} LaunchOptions for appid {self.appid}",
            f"  value:  {self.value}",
            f"  file:   {self.path}",
        ]
        if self.backup is not None:
            lines.append(f"  backup: {self.backup}")
        if self.previous is not None:
            lines.append(f"  was:    {self.previous}")
        lines.append(f"  verified: {self.verified}")
        for note in self.notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)


# --------------------------------------------------------------- steam state


def running_steam_processes(*, proc_root: str = "/proc") -> list[tuple[int, str]]:
    """Every running Steam client process as ``(pid, argv0)``.

    Scans ``/proc/*/cmdline`` directly instead of shelling out to ``pgrep -f``.
    That is not a style preference: a ``-f`` pattern matches the *caller's own*
    command line when the pattern appears in it, which in this project's own
    development killed the caller three times.
    """
    found: list[tuple[int, str]] = []
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return found
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, entry, "cmdline"), "rb") as handle:
                raw = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        argv = [part for part in raw.split("\x00") if part]
        if not argv:
            continue
        for candidate in argv[:1]:
            if any(candidate.endswith(suffix) for suffix in STEAM_CLIENT_SUFFIXES):
                found.append((int(entry), candidate))
    return found


def _assert_steam_closed(*, proc_root: str = "/proc") -> None:
    running = running_steam_processes(proc_root=proc_root)
    if running:
        pids = ", ".join(str(pid) for pid, _ in running)
        raise SteamConfigError(
            "a Steam client is running (pid "
            f"{pids}). Steam keeps each app's LaunchOptions in memory and would "
            "write its copy back over ours, so the change would be silently "
            "reverted. Exit Steam completely (including the tray icon) and retry."
        )


# ------------------------------------------------------------ vdf text layer


def _brace_balance(text: str) -> int:
    return sum(
        1 if ch == "{" else (-1 if ch == "}" else 0)
        for ch in re.sub(r'"[^"]*"', "", text)
    )


def escape_vdf(value: str) -> str:
    """Escape a value for a quoted VDF string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')



def _find_apps_section(text: str) -> tuple[int, int]:
    """Byte offsets of the ``apps`` section's opening and closing braces."""
    match = re.search(r'\n(\t*)"apps"\n\t*\{', text)
    if not match:
        raise SteamConfigError('the "apps" section was not found; refusing to guess')
    open_brace = text.index("{", match.start())
    depth = 0
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return open_brace, index
    raise SteamConfigError('the "apps" section is not brace-balanced; the file is already damaged')


def _find_app_block(
    text: str, apps_open: int, apps_close: int, appid: str
) -> tuple[int, int, int] | None:
    """``(block_open, block_close, key_indent)`` for an appid, or ``None``.

    The appid is matched as a key at its own indent level, then its enclosing
    braces are located. Only blocks *inside* the apps section are considered, so
    an identically numbered key elsewhere in the file cannot be picked up by
    mistake. Indentation is read from the file rather than assumed, though it is
    5 tabs in practice.
    """
    pattern = re.compile(r'\n(\t*)"%s"\n\t*\{' % re.escape(appid))
    for match in pattern.finditer(text, apps_open, apps_close):
        open_brace = text.index("{", match.start())
        depth = 0
        for index in range(open_brace, apps_close + 1):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    return open_brace, index, len(match.group(1))
    return None


def read_launch_options(text: str, appid: str) -> str | None:
    """The current value, or ``None`` if the app has no ``LaunchOptions``."""
    section_open, section_close = _find_apps_section(text)
    block = _find_app_block(text, section_open, section_close, appid)
    if block is None:
        return None
    open_brace, close_brace, _ = block
    for line in text[open_brace:close_brace].splitlines():
        parsed = parse_vdf_line(line)
        if parsed and parsed[1] == "LaunchOptions" and parsed[2] is not None:
            return parsed[2]
    return None


def merge_launch_options(text: str, appid: str, value: str) -> tuple[str, bool]:
    """Return ``(new_text, created_key)`` with exactly one line changed.

    Pure and side-effect free, so the surgery can be tested without touching a
    real Steam configuration.
    """
    if not value.strip():
        raise SteamConfigError("refusing to write an empty launch-option value")
    if "\n" in value or "\r" in value:
        raise SteamConfigError("a launch-option value cannot contain a newline")

    section_open, section_close = _find_apps_section(text)
    block = _find_app_block(text, section_open, section_close, appid)
    if block is None:
        raise SteamConfigError(
            f'appid {appid} has no block under "apps"; Steam creates one when the '
            "game is first configured, so start Steam once with the game installed "
            "and retry"
        )
    open_brace, close_brace, key_indent = block
    child_indent = "\t" * (key_indent + 1)
    new_line = f'{child_indent}"LaunchOptions"\t\t"{escape_vdf(value)}"'

    body = text[open_brace:close_brace]
    lines = body.splitlines(keepends=True)
    out: list[str] = []
    replaced = False
    for line in lines:
        parsed = parse_vdf_line(line)
        if parsed and parsed[1] == "LaunchOptions" and parsed[2] is not None:
            indent = parsed[0]
            ending = "\n" if line.endswith("\n") else ""
            out.append(f'{indent}"LaunchOptions"\t\t"{escape_vdf(value)}"{ending}')
            replaced = True
            continue
        out.append(line)

    if not replaced:
        # `body` is the text between the app block's braces, so its first split
        # line is always the opening brace itself. The new key therefore belongs
        # at index 1: inserting at 0 would put it *before* the brace, outside the
        # block, where it would inherit the appid line's trailing tabs and come
        # out at the wrong depth. Steam writes these keys in its own order and
        # re-sorts nothing, so position is not significant; the depth is.
        assert lines and lines[0].strip() == "{", "unexpected app-block framing"
        out.insert(1, new_line + "\n")

    new_body = "".join(out)
    new_text = text[:open_brace] + new_body + text[close_brace:]
    if _brace_balance(new_text) != 0:
        raise SteamConfigError("the edit would unbalance the file's braces; refusing to write")
    return new_text, not replaced


def remove_launch_options(text: str, appid: str) -> tuple[str, bool]:
    """Drop the ``LaunchOptions`` line for an app. Returns ``(text, removed)``."""
    section_open, section_close = _find_apps_section(text)
    block = _find_app_block(text, section_open, section_close, appid)
    if block is None:
        return text, False
    open_brace, close_brace, _ = block
    body = text[open_brace:close_brace]
    out: list[str] = []
    removed = False
    for line in body.splitlines(keepends=True):
        parsed = parse_vdf_line(line)
        if parsed and parsed[1] == "LaunchOptions" and parsed[2] is not None:
            removed = True
            continue
        out.append(line)
    if not removed:
        return text, False
    new_text = text[:open_brace] + "".join(out) + text[close_brace:]
    if _brace_balance(new_text) != 0:
        raise SteamConfigError("the edit would unbalance the file's braces; refusing to write")
    return new_text, True


# --------------------------------------------------------------- file layer


def find_config_files(paths: Paths) -> list[Path]:
    """Every ``localconfig.vdf`` under every userdata account."""
    if paths.steam_root is None:
        return []
    userdata = paths.steam_root / "userdata"
    if not userdata.is_dir():
        return []
    found = []
    try:
        for account in sorted(userdata.iterdir()):
            candidate = account / "config/localconfig.vdf"
            if account.is_dir() and candidate.is_file():
                found.append(candidate)
    except OSError:
        pass
    return found


def config_file_for(paths: Paths, *, steam_root: Path | None = None) -> Path:
    """The config file to edit.

    With one account there is no ambiguity. With several, refusing is correct:
    guessing which account owns the game would risk editing the wrong one.
    """
    candidates = find_config_files(paths)
    if not candidates and steam_root is not None:
        candidates = [
            account / "config/localconfig.vdf"
            for account in sorted((steam_root / "userdata").glob("*"))
            if (account / "config/localconfig.vdf").is_file()
        ]
    if not candidates:
        raise SteamConfigError(
            "no localconfig.vdf found; has Steam been started at least once on this machine?"
        )
    if len(candidates) > 1:
        raise SteamConfigError(
            "several Steam accounts exist ("
            + ", ".join(p.parts[-3] for p in candidates)
            + "); pass one explicitly rather than letting this tool guess"
        )
    return candidates[0]


@dataclass
class SteamState:
    """Whether Steam is up, and what the app's launch options currently say.

    Both halves matter to a caller that is about to install: the write is refused
    while Steam runs, and knowing the current value lets the plan show what it
    would *change* rather than only what it would write.
    """

    running_pids: list[int]
    config: Path | None
    current: str | None
    error: str | None = None

    @property
    def running(self) -> bool:
        return bool(self.running_pids)

    def describe(self) -> str:
        if self.error:
            return self.error
        if self.running:
            pids = ", ".join(str(pid) for pid in self.running_pids)
            return f"a Steam client is running (pid {pids})"
        return "Steam is not running"


def steam_state(paths: Paths, appid: str, *, proc_root: str = "/proc") -> SteamState:
    """Read the two things an install must know about Steam.

    Never raises: a missing or ambiguous config is reported in ``error`` so the
    caller can still tell the user *why* it cannot proceed, which is more useful
    than a stack trace.
    """
    running = [pid for pid, _ in running_steam_processes(proc_root=proc_root)]
    try:
        config = config_file_for(paths)
    except SteamConfigError as exc:
        return SteamState(running_pids=running, config=None, current=None, error=str(exc))
    try:
        text = config.read_text(encoding="utf-8")
    except OSError as exc:
        return SteamState(running_pids=running, config=config, current=None, error=str(exc))
    try:
        current = read_launch_options(text, appid)
    except SteamConfigError as exc:
        return SteamState(running_pids=running, config=config, current=None, error=str(exc))
    return SteamState(running_pids=running, config=config, current=current)


def set_launch_options(
    paths: Paths,
    appid: str,
    value: str,
    *,
    config_path: Path | None = None,
    proc_root: str = "/proc",
    dry_run: bool = False,
) -> WriteResult:
    """Apply ``value`` as the app's ``LaunchOptions``, guarded.

    Order is deliberate: all preconditions, then a verified backup, then a
    single atomic write, then validation against the intended value.
    """
    _assert_steam_closed(proc_root=proc_root)

    path = config_path or config_file_for(paths)
    original = path.read_text(encoding="utf-8")
    if _brace_balance(original) != 0:
        raise SteamConfigError(
            f"{path} is not brace-balanced before we touch it; fix or restore it first"
        )

    previous = read_launch_options(original, appid)
    new_text, created = merge_launch_options(original, appid, value)
    if new_text == original:
        # Already correct. That is a success, not a failure: a reinstall, or an
        # install whose earlier attempt got this far, must not be refused for being
        # in the state it was trying to reach. Refusing here also meant a *later*
        # step could not distinguish "nothing to do" from "could not write", which
        # is how a reinstall ended up refused after its files were already in place.
        return WriteResult(
            path=path,
            appid=appid,
            value=value,
            previous=previous,
            backup=None,
            backup_sha256="",
            created_key=False,
            verified=True,
            notes=["already set; nothing to write"],
        )

    if dry_run:
        return WriteResult(
            path=path,
            appid=appid,
            value=value,
            previous=previous,
            backup=path,
            backup_sha256="",
            created_key=created,
            verified=False,
            notes=["dry run: nothing was written"],
        )

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = paths.ensure_state_dir() / "steam-config-backups" / f"{path.name}.{stamp}.bak"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    backup_digest = sha256_file(backup)
    if backup_digest != sha256_file(path):
        raise SteamConfigError(f"backup at {backup} does not match the original; refusing to continue")

    # Atomic replace: the original stays intact until the new content is
    # complete, so an interrupted write cannot leave a half-written config.
    atomic_write_text(path, new_text)

    reread = path.read_text(encoding="utf-8")
    if _brace_balance(reread) != 0:
        shutil.copy2(backup, path)
        raise SteamConfigError("the written file is not brace-balanced; the backup was restored")
    verified = read_launch_options(reread, appid) == value
    if not verified:
        shutil.copy2(backup, path)
        raise SteamConfigError("the value did not read back; the backup was restored")

    return WriteResult(
        path=path,
        appid=appid,
        value=value,
        previous=previous,
        backup=backup,
        backup_sha256=backup_digest,
        created_key=created,
        verified=True,
        notes=[
            "Start Steam again for the change to be adopted.",
            "Steam can revert this value if it was edited while a client was "
            "running; verify in the game's Properties after Steam has restarted.",
        ],
    )


def clear_launch_options(
    paths: Paths,
    appid: str,
    *,
    config_path: Path | None = None,
    proc_root: str = "/proc",
) -> WriteResult:
    """Remove the app's ``LaunchOptions`` line, guarded the same way."""
    _assert_steam_closed(proc_root=proc_root)
    path = config_path or config_file_for(paths)
    original = path.read_text(encoding="utf-8")
    previous = read_launch_options(original, appid)
    if previous is None:
        raise SteamConfigError(f"appid {appid} has no LaunchOptions to remove")
    new_text, removed = remove_launch_options(original, appid)
    if not removed:
        raise SteamConfigError(f"appid {appid} has no LaunchOptions to remove")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = paths.ensure_state_dir() / "steam-config-backups" / f"{path.name}.{stamp}.bak"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    digest = sha256_file(backup)
    atomic_write_text(path, new_text)
    reread = path.read_text(encoding="utf-8")
    if _brace_balance(reread) != 0 or read_launch_options(reread, appid) is not None:
        shutil.copy2(backup, path)
        raise SteamConfigError("removal did not validate; the backup was restored")
    return WriteResult(
        path=path,
        appid=appid,
        value="(removed)",
        previous=previous,
        backup=backup,
        backup_sha256=digest,
        created_key=False,
        verified=True,
        notes=["Start Steam again for the change to be adopted."],
    )
