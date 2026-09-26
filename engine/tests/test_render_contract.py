"""Rendering must not crash on any value a producer can emit.

Two bugs of the same shape lived here, and both shipped:

* `Action(kind="fetch")` raised `KeyError: 'fetch'` from `Action.line()`. The
  producer was added with the model-download action and neither the verb dict nor
  the `Literal` learned about it.
* `Operation.describe()` raised the same for `"adopted"` and `"absent"`, which
  `FileJournal.adopt` and `record_absent` had been producing all along.

Neither was caught, for the same reason: the dict lookup only runs on the branch
that produces the kind, and no test drove that branch. A probe over the declared
values is what catches the next one, so that is what these are — rather than a test
per kind, which would have to be written again each time.
"""

from __future__ import annotations

import typing
import unittest
from pathlib import Path

from nvfku.journal import OpKind, Operation
from nvfku.plan import Action, ActionKind


def _literal_members(alias) -> list[str]:
    """The string members of a `Literal[...]` alias."""
    return [m for m in typing.get_args(alias) if isinstance(m, str)]


class ActionKindsTest(unittest.TestCase):
    """Every declared `kind` must be renderable."""

    def test_every_declared_kind_renders(self) -> None:
        kinds = _literal_members(ActionKind)
        self.assertTrue(kinds, "Action.kind has no literal members to check")
        for kind in kinds:
            with self.subTest(kind=kind):
                action = Action(
                    kind=kind,
                    destination="somewhere",
                    source="somewhere else",
                    reason="because",
                )
                # The assertion is that this does not raise.
                line = action.line()
                self.assertTrue(line.strip(), f"{kind} rendered as nothing")

    def test_the_producers_only_emit_declared_kinds(self) -> None:
        """No call site may produce a kind the `Literal` omits.

        The `Literal` is what `line()` is checked against, so a producer that
        invents a kind is a crash that no amount of rendering tests will find.
        """
        import re

        declared = set(_literal_members(ActionKind))
        root = Path(__file__).resolve().parents[1] / "nvfku"
        found: dict[str, list[str]] = {}
        for source in root.rglob("*.py"):
            for match in re.finditer(r'Action\(\s*\n?\s*kind="([^"]+)"', source.read_text()):
                found.setdefault(match.group(1), []).append(source.name)
        self.assertTrue(found, "no Action(kind=...) producers found; the pattern is stale")
        undeclared = {k: v for k, v in found.items() if k not in declared}
        self.assertEqual(
            undeclared,
            {},
            f"these kinds are produced but not declared: {undeclared}",
        )

    def test_a_fetch_action_reads_as_a_download_not_a_copy(self) -> None:
        """A URL is not a file, so it does not get the `source -> destination` form."""
        action = Action(
            kind="fetch",
            destination="https://example.invalid/model.zip",
            source="DLSS NR 310.8.0",
            reason="not on this machine",
        )
        line = action.line()
        self.assertIn("fetch", line)
        self.assertIn("example.invalid", line)
        self.assertNotIn("->", line, "a fetch has no local origin to arrow from")


class OperationKindsTest(unittest.TestCase):
    """Every kind `FileJournal` records must be describable."""

    def test_every_declared_op_kind_describes(self) -> None:
        for kind in _literal_members(OpKind):
            with self.subTest(kind=kind):
                described = Operation(kind=kind, path="/game/x.dll", note="why").describe()
                self.assertTrue(described.strip(), f"{kind} described as nothing")

    def test_the_journal_only_records_declared_kinds(self) -> None:
        """The other direction: a recorded kind the `Literal` omits is the same bug.

        `adopted` and `absent` were exactly this, and the annotation being wrong
        also forced a `type: ignore` at the one call site that stored a computed
        kind.
        """
        import re

        declared = set(_literal_members(OpKind))
        source = (Path(__file__).resolve().parents[1] / "nvfku/journal.py").read_text()
        recorded = set(re.findall(r'Operation\(\s*\n?\s*kind="([^"]+)"', source))
        self.assertTrue(recorded, "no Operation(kind=...) writers found; pattern is stale")
        undeclared = recorded - declared
        self.assertEqual(undeclared, set(), f"recorded but not declared: {undeclared}")


if __name__ == "__main__":
    unittest.main()
