"""A2 - OptiScaler's DLSS-NR pass.

Why this is the cleanest route on Linux
---------------------------------------
OptiScaler is a **local DLL proxy**: it is placed beside the game executable
under the name the loader already looks for (``dxgi.dll``, or ``winmm.dll`` when
the game has no DXGI to hijack) and intercepts the upscaler call from inside the
process.  It therefore never asks ``winevulkan`` for a layer, which is the
constraint that kills every layer-based approach under Proton.

What it needs that the other routes do not
------------------------------------------
The game must already be **using its own DLSS** (or have FSR2/3 or XeSS
redirected into DLSS).  OptiScaler replaces an upscaler; it does not invent one.
That is the opposite of the Feeder route, which exists for games with no DLSS.

Redistribution
--------------
OptiScaler publishes a single ``.7z`` per release.  We download the official
archive from the official release page and extract it; nothing is bundled.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..journal import FileJournal
from ..messages import text
from ..paths import Paths, human_size
from ..plan import Action, Checks, InstallRefused, InstallResult, Missing, RoutePlan
from ..steam import Game
from .. import providers
from ..model import (
    MODEL_NAME as NR_MODEL_NAME,
    TESTED_SHA256 as NR_MODEL_TESTED_SHA256,
    discover as discover_models,
    tested_count,
)

ROUTE = "a2"

#: English fallback for callers that render a route label without a language
#: (``__main__`` prints it in an error message).  The plan itself takes its
#: title from ``a2.title`` via :func:`text`.
TITLE = "A2 — OptiScaler DLSS-NR (DLL proxy)"

# OptiScaler can be installed under any name the loader resolves before the
# system one.  dxgi is preferred because D3D11/D3D12 games all load it; winmm is
# the fallback for a game that links neither.
PROXY_CHOICES = ("dxgi.dll", "winmm.dll", "d3d11.dll", "d3d12.dll")


# The DLSS-NR knobs that exist in OptiScaler's own config.  WorkingScale is the
# cost dial: the neural pass is the expensive part and it scales with the square
# of this.
DEFAULT_DLSSNR_SECTION = {
    "Enabled": "true",
    "WorkingScale": "100",
    "ModelStyle": "0",
    "NrIntensity": "1.0",
    "StructureIntensity": "1.0",
    "GlobalIntensity": "1.0",
}


@dataclass
class ProxyConflict:
    name: str
    reason: str


def _occupied_proxy_names(exe_dir: Path) -> set[str]:
    """Which proxy filenames already exist beside the executable."""
    return {name for name in PROXY_CHOICES if (exe_dir / name).is_file()}


def _existing_proxies(exe_dir: Path) -> list[ProxyConflict]:
    """Proxy filenames taken by *something*, for the plan's warning list.

    Installing OptiScaler as ``dxgi.dll`` when ReShade already lives there would
    silently shadow one of them.  OptiScaler and ReShade can coexist through
    ReShade's own add-on support, but not by fighting over the same filename.
    """
    return [
        ProxyConflict(
            name=name,
            reason="already present; installing over it would replace another proxy",
        )
        for name in sorted(_occupied_proxy_names(exe_dir))
    ]


def launch_options_snippet() -> str:
    return 'WINEDLLOVERRIDES="dxgi=n,b" %command%'


def is_viable(game: Game, language: str | None = None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if game.bitness != 64:
        reasons.append(text(language, "a2.viable.not_64bit"))
    if game.rendering_api not in ("DirectX 11", "DirectX 12"):
        reasons.append(
            text(
                language,
                "a2.viable.api",
                api=game.rendering_api or text(language, "a2.value.unknown"),
            )
        )
    if not game.native_dlss and not game.nvngx_dlssnr:
        reasons.append(text(language, "a2.viable.no_dlss"))
    if reasons:
        return False, reasons
    reasons.append(text(language, "a2.viable.intended"))
    return True, reasons


def plan(paths: Paths, game: Game, language: str | None = None) -> RoutePlan:
    checks = Checks()
    actions: list[Action] = []
    missing: list[Missing] = []
    game_dir = game.install_dir
    exe_dir = game.launch_exe.parent if game.launch_exe else game_dir
    exe_name = (
        game.launch_exe.name if game.launch_exe else text(language, "a2.value.exe_unknown")
    )
    # Joins lists of identifiers (DLL names, anti-cheat products): English uses
    # ", ", Chinese the enumeration comma.
    sep = text(language, "a2.list_separator")

    plan_obj = RoutePlan(
        route=ROUTE,
        title=text(language, "a2.title"),
        game_name=game.name,
        game_dir=game_dir,
        summary=text(language, "a2.summary"),
        detail=text(language, "a2.detail"),
    )

    if game.bitness == 64:
        checks.ok(text(language, "a2.check.bitness"), text(language, "a2.detail.bitness_ok"))
    else:
        checks.block(
            text(language, "a2.check.bitness"),
            text(
                language,
                "a2.detail.bitness_block",
                bits=game.bitness or text(language, "a2.value.unknown"),
            ),
            text(language, "a2.fix.optiscaler_64bit"),
        )

    api = game.rendering_api
    if api in ("DirectX 11", "DirectX 12"):
        checks.ok(
            text(language, "a2.check.api"),
            text(language, "a2.detail.api_ok", api=api),
        )
    else:
        checks.block(
            text(language, "a2.check.api"),
            api or text(language, "a2.value.unknown"),
            text(language, "a2.fix.api"),
        )

    if game.native_dlss:
        names = sorted({p.name for p in game.native_dlss})
        checks.ok(
            text(language, "a2.check.native_dlss"),
            text(language, "a2.detail.native_dlss_ok", names=sep.join(names)),
        )
    else:
        checks.block(
            text(language, "a2.check.native_dlss"),
            text(language, "a2.detail.native_dlss_missing"),
            text(language, "a2.fix.native_dlss"),
        )

    conflicts = _existing_proxies(exe_dir)
    if conflicts:
        checks.warn(
            text(language, "a2.check.proxy_conflict"),
            text(
                language,
                "a2.detail.proxy_conflict",
                names=sep.join(c.name for c in conflicts),
            ),
            text(language, "a2.fix.proxy_conflict"),
        )
    else:
        checks.ok(
            text(language, "a2.check.proxy_slot"),
            text(language, "a2.detail.proxy_slot", name=PROXY_CHOICES[0], exe=exe_name),
        )

    if providers.have_7z():
        checks.ok(
            text(language, "a2.check.extractor"),
            text(language, "a2.detail.extractor_ok", path=providers.have_7z()),
        )
    else:
        checks.block(
            text(language, "a2.check.extractor"),
            text(language, "a2.detail.extractor_missing"),
            text(language, "a2.fix.extractor"),
        )

    try:
        # Cached: `plan` runs on every game-detail open, and an uncached call here
        # meant a synchronous GitHub API request — 0.9-2.4 s behind a proxy — before
        # the page could render a single check.
        component = providers.resolve_rolling_cached(paths, "optiscaler")
        checks.ok(
            text(language, "a2.check.upstream"),
            text(
                language,
                "a2.detail.upstream",
                version=component.version,
                name=component.name,
                size=human_size(component.size or 0),
            ),
        )
        actions.append(
            Action(
                kind="copy",
                destination=str(exe_dir / "OptiScaler.dll"),
                source=text(
                    language,
                    "a2.action.optiscaler_source",
                    name=component.name,
                    version=component.version,
                ),
                reason=text(language, "a2.action.copy_reason"),
            )
        )
    except Exception as exc:
        checks.warn(
            text(language, "a2.check.upstream"),
            text(language, "a2.detail.upstream_failed", error=exc),
            text(language, "a2.fix.upstream"),
        )

    # OptiScaler needs the NR model beside the executable, same as A1, so the
    # discovery and digest classification is shared rather than reimplemented.
    candidates = discover_models(paths, game)
    usable = [c for c in candidates if c.usable]
    if usable:
        chosen = usable[0]
        if tested_count(candidates):
            checks.ok(
                text(language, "a2.check.nr_model"),
                text(language, "a2.detail.nr_model_tested", path=chosen.path),
            )
        else:
            checks.warn(
                text(language, "a2.check.nr_model"),
                text(language, "a2.detail.nr_model_untested", model=chosen.describe(language)),
                text(
                    language,
                    "a2.fix.nr_model_untested",
                    digest=NR_MODEL_TESTED_SHA256[:16],
                ),
            )
        actions.append(
            Action(
                kind="copy",
                destination=str(exe_dir / NR_MODEL_NAME),
                source=str(chosen.path),
                reason=text(language, "a2.action.model_reason"),
                optional=chosen.inside_game,
            )
        )
    else:
        checks.block(
            text(language, "a2.check.nr_model"),
            text(language, "a2.detail.nr_model_missing", name=NR_MODEL_NAME),
            text(language, "a2.fix.nr_model_missing"),
        )
        missing.append(
            Missing(
                # The file name itself is an identifier: never translated.
                what=NR_MODEL_NAME,
                why=text(language, "a2.missing.model.why"),
                how_to_get=text(language, "a2.missing.model.how"),
                blocking=True,
            )
        )

    actions.append(
        Action(
            kind="write",
            destination=str(exe_dir / "OptiScaler.ini"),
            reason=text(language, "a2.action.ini_reason"),
        )
    )
    actions.append(
        Action(
            kind="note",
            destination=text(language, "a2.action.enable_dlss"),
            reason=text(language, "a2.action.enable_dlss_reason"),
        )
    )

    from ..anticheat import detect_anticheat

    ac = detect_anticheat(game)
    if ac:
        checks.block(
            text(language, "a2.check.anticheat"),
            text(language, "a2.detail.anticheat", names=sep.join(ac)),
            text(language, "a2.fix.anticheat"),
        )

    plan_obj.checks = checks
    plan_obj.actions = actions
    plan_obj.missing = missing
    plan_obj.launch_options = launch_options_snippet()
    plan_obj.launch_options_note = text(language, "a2.launch_options_note")
    plan_obj.manual_steps = [
        text(language, "a2.manual.install"),
        text(language, "a2.manual.launch"),
        text(language, "a2.manual.overlay"),
        text(language, "a2.manual.tune"),
    ]
    return plan_obj


def render_ini(existing: str | None, *, working_scale: int = 100) -> str:
    """Merge the ``[DlssNr]`` section into an existing OptiScaler.ini.

    OptiScaler's ini carries comments and the user's own tuning, so rewriting the
    whole file would discard work.  Only the keys this tool owns are touched.

    The implementation is deliberately not an incremental state machine: the
    section is located first, its extent determined, and then the file is
    reassembled.  A blank line inside the section must not be mistaken for its
    end -- an earlier version appended the section a second time when it did,
    producing two ``WorkingScale`` keys with unpredictable precedence.
    """
    section = dict(DEFAULT_DLSSNR_SECTION)
    section["WorkingScale"] = str(working_scale)
    header = "[DlssNr]"
    body = "\n".join(f"{key}={value}" for key, value in section.items())

    if not existing:
        return (
            "; written by nvfku\n"
            "; OptiScaler's own keys are left to its overlay/UI.\n"
            f"{header}\n{body}\n"
        )

    lines = existing.splitlines()

    # 1. Locate the section header and the line where it ends.
    header_index: int | None = None
    end_index = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith("[") and stripped.endswith("]")):
            continue
        if header_index is None:
            if stripped.lower() == header.lower():
                header_index = index
            continue
        end_index = index
        break

    # 2. No section yet: append one.
    if header_index is None:
        out = list(lines)
        if out and out[-1].strip():
            out.append("")
        out.extend([header, body])
        return "\n".join(out).rstrip() + "\n"

    # 3. Section exists: drop its key lines and rebuild it, keeping any
    #    unrecognised keys the user or OptiScaler added.
    kept: list[str] = []
    seen: set[str] = set()
    for line in lines[header_index + 1 : end_index]:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip().lower() if "=" in stripped else ""
        if key and key in {k.lower() for k in section}:
            seen.add(key)
            continue
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        kept.append(line)

    rebuilt = [header]
    rebuilt.extend(f"{key}={value}" for key, value in section.items())
    for line in kept:
        key = line.split("=", 1)[0].strip().lower() if "=" in line else ""
        if key and key in seen:
            continue
        rebuilt.append(line)

    out = lines[:header_index] + rebuilt + lines[end_index:]
    # Collapse any run of blank lines the rebuild introduced.
    cleaned: list[str] = []
    for line in out:
        if not line.strip() and cleaned and not cleaned[-1].strip():
            continue
        cleaned.append(line)
    return "\n".join(cleaned).rstrip() + "\n"


# ------------------------------------------------------------------ install

PROXY_PAYLOAD_NAMES = ("optiscaler.dll", "optiscaler_x64.dll", "optiscaler_amd.dll")
PROXY_PREFAB_NAMES = {"dxgi.dll", "winmm.dll", "d3d11.dll", "d3d12.dll", "version.dll", "dinput8.dll"}


def _choose_proxy_source(extracted: list[Path], preferred: str) -> Path | None:
    """Pick the DLL to install.

    OptiScaler's archive ships its payload as ``OptiScaler.dll`` plus a set of
    already-renamed proxy copies.  We want the *payload*: it is the same binary,
    and installing the pristine copy under a name we choose ourselves is what
    makes the recorded ``proxy_name`` authoritative.  Picking a pre-renamed copy
    instead made a reinstall choose a different name each time and shadow the
    previous install.
    """
    payloads = [p for p in extracted if p.suffix.lower() == ".dll" and p.name.lower() in PROXY_PAYLOAD_NAMES]
    if not payloads:
        # No canonical payload: fall back to a pre-renamed proxy, honouring the
        # name we want last so it wins over the others.
        prefabs = [
            p
            for p in extracted
            if p.suffix.lower() == ".dll" and p.name.lower() in PROXY_PREFAB_NAMES
        ]
        prefabs.sort(key=lambda p: (p.name.lower() != preferred.lower(), len(str(p))))
        payloads = prefabs
    if not payloads:
        payloads = [p for p in extracted if p.suffix.lower() == ".dll"]
    if not payloads:
        return None
    # Prefer a copy inside a DX12 folder when the archive is laid out by API.
    payloads.sort(key=lambda p: ("dx12" not in str(p).lower(), len(str(p))))
    return payloads[0]


def _find_seed_ini(extracted: list[Path]) -> Path | None:
    """OptiScaler's own default OptiScaler.ini, if the archive carries one.

    Seeding from it means the user gets a complete, current config with our
    ``[DlssNr]`` section merged in, instead of a two-key file that drops every
    other OptiScaler setting.
    """
    for path in extracted:
        if path.name.lower() == "optiscaler.ini":
            return path
    return None


def install(
    paths: Paths,
    game: Game,
    *,
    working_scale: int | None = None,
    skip_download: bool = False,
    logger=print,
) -> InstallResult:
    """Apply A2.

    The proxy filename is persisted in the route state before anything else, so
    a later reinstall reuses the same name instead of installing a second proxy.
    """
    route_plan = plan(paths, game)
    if not route_plan.viable:
        blockers = [c for c in route_plan.checks.checks if c.severity == "blocker"]
        detail = "; ".join(f"{c.name}: {c.detail}" for c in blockers) or "missing required files"
        raise InstallRefused(f"A2 cannot install: {detail}")

    exe_dir = game.launch_exe.parent if game.launch_exe else game.install_dir
    result = InstallResult(route=ROUTE, game=game.name, game_dir=game.install_dir)

    state = providers.read_route_state(paths, game.key, ROUTE)
    scale = working_scale if working_scale is not None else int(state.get("working_scale", 100))
    if not 25 <= scale <= 100:
        raise InstallRefused(f"working_scale must be between 25 and 100, got {scale}")

    # --- 1. the usable proxy name, decided before any write ---------------
    occupied = _occupied_proxy_names(exe_dir)
    recorded = state.get("proxy_name")
    own_marker = state.get("installed_proxy_name")

    # A reinstall must reuse the slot we already own.  Treating our own file as
    # "taken" is what made an earlier version pick winmm.dll on the second run
    # and install a second copy of the same tool under a different name.
    if recorded and own_marker == recorded:
        proxy_name = recorded
        reusing = True
    elif recorded and recorded not in occupied:
        proxy_name = recorded
        reusing = False
    else:
        proxy_name = next((name for name in PROXY_CHOICES if name not in occupied), None)
        reusing = False
    if proxy_name is None:
        raise InstallRefused(
            "every proxy name this tool uses is already taken beside the executable: "
            + ", ".join(sorted(occupied))
        )
    logger(f"proxy name: {proxy_name}" + (" (replacing our previous install)" if reusing else ""))

    # --- 2. fetch and unpack OptiScaler -----------------------------------
    component = providers.resolve_rolling("optiscaler")
    logger(f"component: {component.name} {component.version}")
    if skip_download and not component.local_path(paths).is_file():
        raise InstallRefused(f"{component.name} is not cached and --skip-download was given")
    if skip_download:
        archive = component.local_path(paths)
        logger(f"  cached   {archive.name}")
    else:
        archive = providers.fetch(component, paths, logger=logger)

    extract_dir = paths.download_cache() / "optiscaler" / f"extract-{component.version}"
    if not extract_dir.is_dir() or skip_download:
        extracted = providers.extract_7z(archive, extract_dir, logger=logger)
    else:
        extracted = [p for p in extract_dir.rglob("*") if p.is_file()]
        logger(f"  cached   {len(extracted)} extracted files")

    proxy_source = _choose_proxy_source(extracted, proxy_name)
    if proxy_source is None:
        raise InstallRefused(
            f"no DLL found inside {archive.name}; the archive layout may have changed "
            f"(looked in {extract_dir})"
        )
    logger(f"proxy source: {proxy_source.relative_to(extract_dir)}")

    # --- 3. model ---------------------------------------------------------
    candidates = discover_models(paths, game)
    chosen = next((c for c in candidates if c.usable), None)
    if chosen is None:
        raise InstallRefused(f"no usable {NR_MODEL_NAME} found; A2 cannot run without it")

    # --- 4. apply, journalled ---------------------------------------------
    journal = FileJournal(paths, game.install_dir, ROUTE, game_key=game.key)
    result.journal_id = journal.journal_id
    logger(f"journal {journal.journal_id} in {journal.dir}")

    logger(f"  [1/3] proxy DLL -> {proxy_name}")
    journal.install_file(proxy_source, exe_dir / proxy_name, source_label=f"OptiScaler {component.version}")

    logger("  [2/3] model")
    if chosen.path.parent == exe_dir:
        journal.note(f"{NR_MODEL_NAME} already beside the executable; left as it is")
    else:
        journal.install_file(chosen.path, exe_dir / NR_MODEL_NAME, source_label=f"NVIDIA model ({chosen.verdict})")

    logger(f"  [3/3] OptiScaler.ini ([DlssNr] WorkingScale={scale})")
    ini_path = exe_dir / "OptiScaler.ini"
    if ini_path.is_file():
        existing = ini_path.read_text(encoding="utf-8", errors="replace")
    else:
        seed = _find_seed_ini(extracted)
        existing = seed.read_text(encoding="utf-8", errors="replace") if seed else None
        if seed:
            logger(f"  seed     {seed.name} from the archive")
    journal.write_text(
        ini_path,
        render_ini(existing, working_scale=scale),
        source_label="nvfku generated [DlssNr] section",
    )

    journal.finish()

    # --- 5. record --------------------------------------------------------
    state.update(
        {
            "installed_at": journal._journal.created_at,
            "journal_id": journal.journal_id,
            "exe_dir": str(exe_dir),
            "proxy_name": proxy_name,
            "installed_proxy_name": proxy_name,
            "working_scale": scale,
            "optiscaler_version": component.version,
            "model_source": str(chosen.path),
            "model_verdict": chosen.verdict,
        }
    )
    providers.write_route_state(paths, game.key, ROUTE, state)
    if chosen.verdict == "tested":
        result.verified.append(f"{NR_MODEL_NAME} is the measured-stable build")
    else:
        result.warnings.append(
            f"{NR_MODEL_NAME} is not the measured-stable build "
            f"(sha256 {(chosen.sha256 or '?')[:16]}...)"
        )
    result.notes.append(f"state written to {providers.route_state_path(paths, game.key, ROUTE)}")

    result.manual_steps.extend(route_plan.manual_steps)
    result.launch_options = route_plan.launch_options
    return result
