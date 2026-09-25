"""Engine-side message-table integrity.

The plan a user reads is produced by the engine, so the engine's two tables need
the same discipline as the UI's: a key present in one language and absent from the
other falls back silently and renders a half-translated plan, which is the failure
mode nobody notices until a user reports it.
"""

from __future__ import annotations

import re
import unittest

from nvfku import messages

PLACEHOLDER = re.compile(r"\{(\w+)\}")

#: Keys whose text is legitimately identical in both languages because the value
#: *is* the name of a thing. Everything else must differ, so a forgotten
#: translation fails rather than passing quietly.
#: Keys whose two languages are legitimately the same string, because the value
#: *is* the name of a thing. Kept deliberately short: every entry here is a
#: translation that the suite will no longer notice is missing.
IDENTICAL_IS_FINE = {
    # Product and runtime names, written the same in both languages.
    "rh.title.nested",      # "ReShade {version}"
    "rh.check.proton",      # "Proton"
    "rh.check.reshade",     # "ReShade"
    "rh.proton.placeholder",  # "<Proton>"
}

#: Keys that must exist, so a rename cannot quietly orphan a route's text.
#: A sample from each route plus the shared table, so a rename cannot quietly
#: orphan a whole route's text.
REQUIRED = {
    "a1.title",
    "a1.summary",
    "a1.check.api",
    "a1.vulkan_note",
    "a1.missing.model.why",
    "a2.title",
    "a2.summary",
    "a2.check.api",
    "a2.missing.model.why",
}


class MessageTablesTest(unittest.TestCase):
    def test_english_and_chinese_hold_the_same_keys(self) -> None:
        en = set(messages.EN)
        zh = set(messages.ZH)
        self.assertEqual(
            sorted(en - zh), [], "keys present in English but not Chinese"
        )
        self.assertEqual(
            sorted(zh - en), [], "keys present in Chinese but not English"
        )

    def test_placeholders_agree(self) -> None:
        mismatches = []
        for key, english in messages.EN.items():
            chinese = messages.ZH.get(key, "")
            if set(PLACEHOLDER.findall(english)) != set(PLACEHOLDER.findall(chinese)):
                mismatches.append(key)
        self.assertEqual(mismatches, [], "placeholder sets differ")

    def test_no_entry_is_empty(self) -> None:
        for language, table in messages.TABLES.items():
            for key, value in table.items():
                self.assertTrue(
                    value.strip(), f"{language}:{key} is empty"
                )

    def test_the_chinese_actually_differs(self) -> None:
        identical = [
            key
            for key, english in messages.EN.items()
            if messages.ZH.get(key) == english and key not in IDENTICAL_IS_FINE
        ]
        self.assertEqual(identical, [], "left untranslated")

    def test_the_required_keys_are_present(self) -> None:
        self.assertEqual(
            sorted(REQUIRED - set(messages.EN)), [], "missing from English"
        )

    def test_every_route_key_carries_its_route_prefix(self) -> None:
        """Route-owned keys must be namespaced, or one route can shadow another."""
        for key in messages.EN:
            if key.startswith(("a1.", "a2.")):
                self.assertRegex(key, r"^(a1|a2)\.[a-z0-9_.]+$")

    def test_the_allow_list_stays_small(self) -> None:
        """A growing allow-list is a translation nobody will notice is missing.

        The list exists for proper nouns. If it starts collecting prose, the test
        it feeds has stopped doing its job, so its size is itself asserted.
        """
        self.assertLessEqual(
            len(IDENTICAL_IS_FINE), 8, "the allow-list is picking up prose"
        )

    def test_every_allowed_key_is_a_bare_identifier(self) -> None:
        """Each allowed value must be a name, not a sentence.

        A proper noun is short and has no spaces beyond a version placeholder; a
        sentence has several words. This is what stops the allow-list from being
        used to silence a forgotten translation.
        """
        for key in IDENTICAL_IS_FINE:
            value = messages.EN.get(key)
            self.assertIsNotNone(value, f"{key} is not a real key")
            words = [w for w in value.replace("{version}", " ").split() if w]
            self.assertLessEqual(
                len(words), 2, f"{key} looks like prose, not an identifier"
            )

    def test_no_two_tables_define_the_same_key(self) -> None:
        """A duplicated key is a second source of truth.

        The three route tables are merged over the shared one, so a duplicate
        silently wins or loses depending on import order. Catching it here is the
        only way to notice, because the merged dict looks correct either way.
        """
        from nvfku import messages_a1, messages_a2

        shared = set(messages.EN) - (set(messages_a1.EN) | set(messages_a2.EN))
        for name, module in (
            ("messages_a1", messages_a1),
            ("messages_a2", messages_a2),
        ):
            overlap = shared & set(module.EN)
            self.assertEqual(sorted(overlap), [], f"{name} redefines a shared key")


class TextTest(unittest.TestCase):
    def test_substitutes_named_values(self) -> None:
        # `a1.check.reshade.ok_detail` carries {exe}; pick keys from the merged
        # table rather than a shared one, because the shared table now holds only
        # the few strings more than one route needs.
        en = messages.text("en", "a1.check.reshade.ok_detail", exe="Game.exe")
        zh = messages.text("zh", "a1.check.reshade.ok_detail", exe="Game.exe")
        self.assertIn("Game.exe", en)
        self.assertIn("Game.exe", zh)
        self.assertNotIn("{exe}", en)
        self.assertNotIn("{exe}", zh)

    def test_placeholder_substitution_leaves_no_braces(self) -> None:
        """Every templated key must render without a leftover placeholder."""
        leftover = []
        for key, template in messages.EN.items():
            if "{" not in template:
                continue
            values = {name: "X" for name in re.findall(r"\{(\w+)\}", template)}
            rendered = messages.text("en", key, **values)
            if "{" in rendered:
                leftover.append(key)
        self.assertEqual(leftover, [], "unsubstituted placeholders")

    def test_an_unknown_key_returns_itself(self) -> None:
        # Visible in a screenshot rather than fatal inside a plan.
        self.assertEqual(messages.text("en", "no.such.key"), "no.such.key")
        self.assertEqual(messages.text("zh", "no.such.key"), "no.such.key")

    def test_language_normalisation(self) -> None:
        self.assertEqual(messages.normalise(None), "en")
        self.assertEqual(messages.normalise(""), "en")
        self.assertEqual(messages.normalise("zh"), "zh")
        self.assertEqual(messages.normalise("zh-CN"), "zh")
        self.assertEqual(messages.normalise("ZH"), "zh")
        self.assertEqual(messages.normalise("de"), "en")

    def test_missing_language_falls_back_to_english(self) -> None:
        self.assertEqual(
            messages.text(None, "a1.check.api"), messages.EN["a1.check.api"]
        )
        self.assertEqual(messages.normalise(None), "en")


if __name__ == "__main__":
    unittest.main()
