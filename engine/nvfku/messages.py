"""Engine-side user-facing text, in English and Chinese.

The plan a user reads is produced by the engine, not the UI: route titles,
summaries, every check, and the explanation beside a failure all originate here.
Localising only the Dart shell therefore left the most important half of the
interface in English, which is precisely the half a user reads before deciding
whether to let the tool write into a game directory.

Where the two languages differ, they differ deliberately:

* **Identifiers are not translated.** Route names, digests, environment variable
  names, `%command%`, file names and API names appear verbatim. A user compares
  this text against Steam's properties dialog and against ReShade.log, so
  translating an identifier would break the correspondence.
* **A count picks its own phrasing.** Chinese does not inflect for plurals, so
  the plural/singular split that English needs collapses into one string.
"""

from __future__ import annotations

LANGUAGES = ("en", "zh")
DEFAULT_LANGUAGE = "en"


def normalise(language: str | None) -> str:
    """Maps anything to a supported language, defaulting to English."""
    if not language:
        return DEFAULT_LANGUAGE
    lowered = language.strip().lower()
    if lowered in LANGUAGES:
        return lowered
    if lowered.startswith("zh"):
        return "zh"
    return DEFAULT_LANGUAGE


#: English text, keyed. Kept together so the two tables can be diffed — the test
#: suite asserts they hold the same keys, because a missing entry silently falls
#: back and produces a half-translated screen.
EN: dict[str, str] = {

    "model.unhashed": "unhashed",
    "model.in_game_folder": "in the game folder",
    "model.verdict.tested": "tested",
    "model.verdict.untested": "untested",
    "model.verdict.unknown-size": "unknown size",
}

#: Chinese text. Technical identifiers stay as they are, matching EN.
ZH: dict[str, str] = {

    "model.unhashed": "未计算摘要",
    "model.in_game_folder": "在游戏目录内",
    "model.verdict.tested": "已测试",
    "model.verdict.untested": "未测试",
    "model.verdict.unknown-size": "大小未知",
}

# Route-owned tables, merged in. Each route keeps its own file so the three can
# be edited independently without one edit overwriting another.
from .messages_a1 import EN as _A1_EN, ZH as _A1_ZH  # noqa: E402
from .messages_a2 import EN as _A2_EN, ZH as _A2_ZH  # noqa: E402
from .messages_reshade import EN as _RESHADE_EN, ZH as _RESHADE_ZH  # noqa: E402

EN.update(_A1_EN)
EN.update(_A2_EN)
EN.update(_RESHADE_EN)
ZH.update(_A1_ZH)
ZH.update(_A2_ZH)
ZH.update(_RESHADE_ZH)

TABLES = {"en": EN, "zh": ZH}


def text(language: str | None, key: str, **values: object) -> str:
    """Looks up ``key`` and substitutes ``{name}`` placeholders.

    An unknown key returns the key itself: a missing translation should be obvious
    in a screenshot or a log, not raise from deep inside a plan.
    """
    code = normalise(language)
    table = TABLES[code]
    template = table.get(key) or EN.get(key) or key
    if values:
        for name, value in values.items():
            template = template.replace("{" + name + "}", str(value))
    return template
