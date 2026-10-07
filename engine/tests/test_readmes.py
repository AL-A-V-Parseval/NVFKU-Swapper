"""Both READMEs must exist, agree on structure, and stay reachable from each other.

The English README drifted once already: it advertised a `--verbose` flag that did
not exist, listed two `app/lib` files that had been deleted, called ReShade a third
route after it became a prerequisite, and quoted a test count forty times too small.
A translated copy of a wrong document is worse than no translation, so the pair is
checked rather than trusted.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EN = ROOT / "README.md"
ZH = ROOT / "README.zh.md"


def headings(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("## ")]


def links(path: Path) -> set[str]:
    """Relative link targets, which are the ones that can rot."""
    text = path.read_text(encoding="utf-8")
    return {
        target
        for target in re.findall(r"\]\(([^)]+)\)", text)
        if not target.startswith(("http://", "https://", "#"))
    }


class ReadmePairTest(unittest.TestCase):
    def test_both_exist(self) -> None:
        self.assertTrue(EN.is_file(), "README.md is missing")
        self.assertTrue(ZH.is_file(), "README.zh.md is missing")

    def test_the_same_number_of_sections(self) -> None:
        """Structure parity, without demanding identical wording.

        A section quietly dropped in translation is how a translated README ends up
        describing less than the original — and nobody notices, because they read
        only one of the two.
        """
        self.assertEqual(
            len(headings(EN)),
            len(headings(ZH)),
            f"section counts differ:\n  en: {headings(EN)}\n  zh: {headings(ZH)}",
        )

    def test_each_links_to_the_other(self) -> None:
        self.assertIn("README.zh.md", EN.read_text(encoding="utf-8"))
        self.assertIn("README.md", ZH.read_text(encoding="utf-8"))

    def test_every_relative_link_resolves_in_both(self) -> None:
        for path in (EN, ZH):
            for target in sorted(links(path)):
                with self.subTest(readme=path.name, target=target):
                    self.assertTrue(
                        (ROOT / target).exists(),
                        f"{path.name} links to {target}, which does not exist",
                    )

    def test_neither_claims_the_model_is_never_downloaded(self) -> None:
        """A claim that stopped being true when `weights.py` landed.

        It survived in four code comments and two *user-facing* error strings, so
        it is worth guarding in the prose too.
        """
        for path in (EN, ZH):
            text = path.read_text(encoding="utf-8").lower()
            for phrase in ("never downloaded", "从不下载", "永不下载"):
                self.assertNotIn(
                    phrase,
                    text,
                    f"{path.name} still says {phrase!r}, which is not true",
                )

    def test_both_link_to_reproducible_checks_instead_of_freezing_a_test_count(self) -> None:
        for path in (EN, ZH):
            with self.subTest(readme=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("docs/release-workflow.md", links(path))
                self.assertNotRegex(text, r"\*\*\d+ (?:tests|项测试)")
        workflow = (ROOT / "docs/release-workflow.md").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s engine/tests -q", workflow)
        self.assertIn("flutter test --no-pub", workflow)
        self.assertIn("python tools/verify_release.py", workflow)


if __name__ == "__main__":
    unittest.main()
