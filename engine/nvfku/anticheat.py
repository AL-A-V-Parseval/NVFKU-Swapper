"""Anti-cheat detection.

Both DLSS5-Swapper and DLSS5-Autopilot refuse or warn loudly here, and they are
right to: a ReShade add-on injected into an anti-cheat protected game can cost
the account.  We do not block by publisher policy, we block on evidence found in
the game directory, and we name what was found so the user can judge.
"""

from __future__ import annotations

import re

from .steam import Game

# (label, filename/dir patterns)
_AC_SIGNATURES: list[tuple[str, tuple[str, ...]]] = [
    ("Easy Anti-Cheat", ("easyanticheat", "easyanticheat_x64.dll", "eac_launcher", "start_protected_game")),
    ("BattlEye", ("battleye", "beservice", "be_service", "belauncher")),
    ("Denuvo Anti-Cheat", ("denuvo", "denuvo_anticheat")),
    ("Vanguard", ("vgc.exe", "vgk.sys", "riot vanguard")),
    ("XIGNCODE3", ("xigncode", "x3.xem", "xmag.xem")),
    ("nProtect GameGuard", ("gameguard", "npggnt.des", "npgmup.des")),
    ("PunkBuster", ("punkbuster", "pbsvc", "pnkbstra")),
    ("FACEIT AC", ("faceit", "faceitclient")),
    ("Ricochet", ("ricochet",)),
    ("ACE (Anti-Cheat Expert)", ("anticheatexpert", "ace-game", "aceguard")),
    ("HoYoverse mhyprot", ("mhyprot", "anticheat_report")),
]

# Appids whose anti-cheat is well known and which the user should simply not
# touch.  Kept short and factual.
_AC_APPIDS = {
    "359550": "Rainbow Six Siege (BattlEye + Vanguard-class)",
    "1517290": "Battlefield 2042 (EA Javelin)",
    "1238810": "Battlefield V (FairFight/EA)",
}

_AC_NAME_HINT = re.compile(
    r"(rainbow six|battlefield|war thunder|destiny|apex legends|valorant|"
    r"call of duty|fortnite|rust|escape from tarkov|dead by daylight|"
    r"genshin|honkai|arknights|endfield|delta force)",
    re.IGNORECASE,
)


def detect_anticheat(game: Game, *, max_entries: int = 3000) -> list[str]:
    """Return the anti-cheat products evidenced in this game directory."""
    found: set[str] = set()
    if game.appid in _AC_APPIDS:
        found.add(_AC_APPIDS[game.appid])

    checked = 0
    try:
        for entry in game.install_dir.rglob("*"):
            checked += 1
            if checked > max_entries:
                break
            name = entry.name.lower()
            for label, needles in _AC_SIGNATURES:
                if label in found:
                    continue
                if any(needle == name or needle in name for needle in needles):
                    found.add(label)
                    break
            if len(found) == len(_AC_SIGNATURES):
                break
    except OSError:
        pass

    if not found and _AC_NAME_HINT.search(game.name):
        found.add("likely online multiplayer title (name heuristic)")
    return sorted(found)


def is_online_risk(game: Game) -> bool:
    return bool(detect_anticheat(game))
