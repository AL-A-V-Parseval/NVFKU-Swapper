"""Shared vocabulary for route plans.

Every route answers the same three questions, and answers them *before*
touching the filesystem:

*   **is it viable here?** (:class:`Checks` -> hard blockers vs advisories)
*   **what exactly would change?** (:class:`Action` list, each with a source
    and a destination)
*   **what is missing?** (:class:`Missing`, e.g. a proprietary file we may not
    redistribute)

A plan is inert data.  ``render_plan`` turns it into text for the CLI, and the
Flutter UI renders the same object.  Installation is a separate step that takes
a plan and a journal, which is what makes ``--dry-run`` trustworthy: the dry
run is not a simulation of the installer, it *is* the installer's first half.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["blocker", "warning", "ok"]


@dataclass
class Check:
    name: str
    severity: Severity
    detail: str
    fix: str | None = None

    @property
    def ok(self) -> bool:
        return self.severity == "ok"

    def line(self) -> str:
        mark = {"ok": "ok  ", "warning": "warn", "blocker": "FAIL"}[self.severity]
        out = f"    [{mark}] {self.name}: {self.detail}"
        if self.fix and self.severity != "ok":
            out += f"\n           fix: {self.fix}"
        return out


@dataclass
class Checks:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, severity: Severity, detail: str, fix: str | None = None) -> Check:
        check = Check(name=name, severity=severity, detail=detail, fix=fix)
        self.checks.append(check)
        return check

    def ok(self, name: str, detail: str) -> Check:
        return self.add(name, "ok", detail)

    def warn(self, name: str, detail: str, fix: str | None = None) -> Check:
        return self.add(name, "warning", detail, fix)

    def block(self, name: str, detail: str, fix: str | None = None) -> Check:
        return self.add(name, "blocker", detail, fix)

    def __iter__(self):
        """Iterate the checks.

        Without this, `for check in plan.checks` raises, and `plan.checks` reads
        like a sequence at every call site while actually being a container. Three
        separate authors wrote that loop while working on this codebase, which is
        the signal that the API should support it rather than that they were all
        wrong.
        """
        return iter(self.checks)

    def __len__(self) -> int:
        return len(self.checks)

    def __getitem__(self, index):
        return self.checks[index]

    @property
    def blockers(self) -> list[Check]:
        return [c for c in self.checks if c.severity == "blocker"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.severity == "warning"]

    @property
    def viable(self) -> bool:
        return not self.blockers


#: Every kind of action a route may propose.
#:
#: A named alias rather than an inline `Literal`, because `from __future__ import
#: annotations` turns a field annotation into a *string* — so a test cannot read
#: `Action.__annotations__["kind"]` to learn what `line()` has to handle. The alias
#: is a real object and can be introspected.
ActionKind = Literal[
    "copy", "write", "delete", "mkdir", "note", "launch-option", "fetch"
]


@dataclass
class Action:
    kind: ActionKind
    destination: str
    source: str | None = None
    reason: str = ""
    optional: bool = False

    def line(self) -> str:
        verb = {
            "copy": "copy",
            "write": "write",
            "delete": "delete",
            "mkdir": "mkdir",
            "note": "note",
            "launch-option": "launch",
            # Added with the model-download action. Its absence was a KeyError on
            # every `plan`/`install` that reached it — which no test did, because the
            # branch needs a machine without the tested model build on it.
            "fetch": "fetch",
        }[self.kind]
        target = self.destination
        if self.kind in ("launch-option", "note", "fetch"):
            body = target
        else:
            origin = f" <- {self.source}" if self.source else ""
            body = f"{origin} -> {target}" if origin else target
        suffix = " (optional)" if self.optional else ""
        reason = f"   # {self.reason}" if self.reason else ""
        return f"    {verb:<6} {body}{suffix}{reason}"


@dataclass
class Missing:
    what: str
    why: str
    how_to_get: str
    blocking: bool = True


@dataclass
class RoutePlan:
    route: str
    title: str
    game_name: str
    game_dir: Path
    summary: str
    """One sentence naming what distinguishes this route from the other.

    Deliberately not the mechanism. The route name and this line are what a chooser
    scans; how the proxy is loaded belongs in `detail`, behind a disclosure.
    """

    detail: str = ""
    """The mechanism, shown behind "technical detail".

    Kept separate from `summary` because the two answer different questions: which
    one do I want, and what does it actually do to my game. Merging them made the
    chooser read as a wall of prose for someone who only wanted a recommendation.
    """
    checks: Checks = field(default_factory=Checks)
    actions: list[Action] = field(default_factory=list)
    missing: list[Missing] = field(default_factory=list)
    launch_options: str | None = None
    launch_options_note: str | None = None
    steam_running: bool = False
    """True when a Steam client is up, which blocks writing the launch options.

    It lives on the plan because it is a *precondition* the UI has to know before
    offering the install button: an experiment showed Steam keeps each app's
    `LaunchOptions` in memory and writes its copy back, so a write made while it
    runs is silently reverted. Reporting it here is what lets the button be
    disabled with the reason attached instead of failing after the fact.
    """

    prerequisite: "RoutePlan | None" = None
    """A component this route needs, planned as a step inside it.

    A route's prerequisite is not a route. ReShade is part of what A1 installs, and
    presenting it as a sibling made the list read as three options when there are
    two. It keeps its own plan because it genuinely needs its own confirmation — it
    downloads a binary and can create a Proton prefix — but it is nested here so
    the shape matches the model.
    """
    manual_steps: list[str] = field(default_factory=list)
    read_only: bool = False
    """True for a route that only reports and writes nothing.

    No shipped route sets this any more — it is kept because the CLI, the renderer
    and the UI all honour it, and a future read-only probe should not have to
    reintroduce the plumbing.
    """

    @property
    def viable(self) -> bool:
        if self.missing and any(m.blocking for m in self.missing):
            return False
        return self.checks.viable

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "title": self.title,
            "game": self.game_name,
            "game_dir": str(self.game_dir),
            "summary": self.summary,
            "detail": self.detail,
            "viable": self.viable,
            "read_only": self.read_only,
            "checks": [
                {
                    "name": c.name,
                    "severity": c.severity,
                    "detail": c.detail,
                    "fix": c.fix,
                }
                for c in self.checks.checks
            ],
            "actions": [
                {
                    "kind": a.kind,
                    "destination": a.destination,
                    "source": a.source,
                    "reason": a.reason,
                    "optional": a.optional,
                }
                for a in self.actions
            ],
            "missing": [
                {
                    "what": m.what,
                    "why": m.why,
                    "how_to_get": m.how_to_get,
                    "blocking": m.blocking,
                }
                for m in self.missing
            ],
            "launch_options": self.launch_options,
            "steam_running": self.steam_running,
            "prerequisite": self.prerequisite.to_dict() if self.prerequisite else None,
            "manual_steps": self.manual_steps,
        }


def render_plan(plan: RoutePlan) -> str:
    lines: list[str] = []
    verdict = "READY" if plan.viable else "BLOCKED"
    lines.append(f"=== {plan.title} [{plan.route}] - {verdict}" + (" (read-only)" if plan.read_only else ""))
    lines.append(f"    game: {plan.game_name}")
    lines.append(f"    dir:  {plan.game_dir}")
    lines.append(f"    {plan.summary}")
    lines.append("  checks:")
    for check in plan.checks.checks:
        lines.append(check.line())
    if plan.actions:
        lines.append("  actions:")
        for action in plan.actions:
            lines.append(action.line())
    if plan.missing:
        lines.append("  missing files (must be supplied by you):")
        for item in plan.missing:
            flag = "required" if item.blocking else "optional"
            lines.append(f"    - {item.what} ({flag})")
            lines.append(f"        why: {item.why}")
            lines.append(f"        get: {item.how_to_get}")
    if plan.launch_options:
        lines.append("  steam launch options:")
        lines.append(f"    {plan.launch_options}")
        if plan.launch_options_note:
            lines.append(f"    note: {plan.launch_options_note}")
    if plan.manual_steps:
        lines.append("  manual steps:")
        for step in plan.manual_steps:
            lines.append(f"    - {step}")
    return "\n".join(lines)


class InstallRefused(RuntimeError):
    """Raised before anything is written, when a route cannot proceed.

    Installation is refused rather than partially applied: the caller can fix
    the reported condition and re-run, and the game directory is untouched.
    """


@dataclass
class InstallResult:
    """What an install actually did, and what is still on the user."""

    route: str
    game: str
    game_dir: Path
    journal_id: str | None = None
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)
    manual_steps: list[str] = field(default_factory=list)
    launch_options: str | None = None

    def render(self) -> str:
        lines = [f"=== installed {self.route} for {self.game}"]
        lines.append(f"    dir:     {self.game_dir}")
        if self.journal_id:
            lines.append(f"    journal: {self.journal_id}")
            lines.append(f"             undo with: nvfku rollback {self.journal_id}")
        for item in self.verified:
            lines.append(f"    [ok  ] {item}")
        for item in self.warnings:
            lines.append(f"    [warn] {item}")
        for item in self.notes:
            lines.append(f"    [note] {item}")
        if self.launch_options:
            lines.append("    steam launch options:")
            lines.append(f"        {self.launch_options}")
        if self.manual_steps:
            lines.append("    still to do:")
            for step in self.manual_steps:
                lines.append(f"      - {step}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "game": self.game,
            "game_dir": str(self.game_dir),
            "journal_id": self.journal_id,
            "notes": self.notes,
            "warnings": self.warnings,
            "verified": self.verified,
            "manual_steps": self.manual_steps,
            "launch_options": self.launch_options,
        }
