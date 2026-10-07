"""A1 - ReShade add-on chain under Proton (ReShade + dlss5-bridge + NapXDD add-on).

Why this route is shaped the way it is
--------------------------------------
*   ReShade is installed as a **local ``dxgi.dll``** inside the game folder, not
    as a Vulkan layer.  This is the whole trick on Linux: Wine's
    ``vkEnumerateInstanceLayerProperties`` always reports zero layers and its
    loader only understands ``HKLM\\Software\\Khronos\\Vulkan\\Drivers``, so
    *no* tool can register a Vulkan layer for a Proton game.  A DLL next to the
    executable is loaded by the normal loader and works.
*   The neural consumer is NapXDD's add-on plus its forwarder DLL, not
    ``renodx-dlss5``.  The RenoDX add-on produces a black screen under Proton
    because driver-dispatched NGX feature 18 fails ``FAIL_OutOfDate`` (no NGX
    OTA updater inside a prefix).  NapXDD's add-on drives the feature directly.
*   ``unwrap=0`` is written into ``dlss5-bridge.cfg``.  On Windows the default
    is ``1``; on Linux the ReShade proxy device's descriptors are already
    native and vkd3d re-translating them faults.  This is the difference
    between the documented Linux success report and a crash.
*   ``nvngx_dlssnr.dll`` is NVIDIA's.  This module locates and verifies it,
    and ``install()`` copies the chosen build beside the executable.  When no
    tested build is present the plan offers a pinned download rather than only
    complaining; see ``weights.py``.
"""

from __future__ import annotations

from pathlib import Path

from ..journal import FileJournal
from .transaction import locked_install, preflight_files, transaction
from ..messages import text
from ..paths import Paths, human_size
from ..plan import Action, Checks, InstallRefused, InstallResult, Missing, RoutePlan
from ..steam import Game
from .. import providers

ROUTE = "a1"
#: English title, kept importable because the CLI reads ``module.TITLE``.  The
#: plan itself goes through ``text(language, "a1.title")``.
TITLE = "A1 — ReShade + dlss5-bridge + addon-dlssnr-linux (Proton)"

# The model is NVIDIA's and is shared with the other routes, so discovery and
# digest classification live in nvfku.model.
from ..model import (  # noqa: E402
    MODEL_NAME as NR_MODEL_NAME,
    TESTED_SHA256 as NR_MODEL_TESTED_SHA256,
    TESTED_SIZE as NR_MODEL_TESTED_SIZE,
    best as best_model,
    discover as discover_models,
    tested_count,
)


# ReShade's own DLLs and the add-ons this route installs, all beside the
# executable.  D3D12 and D3D11 both resolve dxgi.dll, which is why A1 cannot
# serve a Vulkan game -- that would need ReShade's Vulkan layer, and Wine's
# loader never enumerates third-party layers.
RESHADE_PROXY_DLL = "dxgi.dll"

BRIDGE_ADDON = "dlss5-bridge.addon64"
ADDON_DLL = "dlssnr-linux.addon64"
ADDON_FORWARDER = "nvngx.dll_nrfwd.dll"
BRIDGE_CFG = "dlss5-bridge.cfg"

def launch_options(game: Game, language: str | None = None) -> tuple[str, str]:
    """Steam launch options, correct for this Proton build.

    ``PROTON_ENABLE_NVAPI`` does not exist on GE-Proton or proton-cachyos, which
    is what this machine runs; using the Valve name there silently does nothing.
    """
    tool = (game.proton_tool or "").lower()
    custom = any(token in tool for token in ("cachyos", "ge", "wine-ge", "glorious"))
    nvapi = "PROTON_FORCE_NVAPI=1" if custom else "PROTON_ENABLE_NVAPI=1"
    options = f'{nvapi} WINEDLLOVERRIDES="dxgi=n,b" %command%'
    note = text(
        language,
        "a1.launch.note.custom" if custom else "a1.launch.note.valve",
        tool=game.proton_tool or text(language, "a1.proton.unknown"),
    )
    return options, note


def is_viable(game: Game, language: str | None = None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    api = game.rendering_api
    if api == "Vulkan":
        reasons.append(text(language, "a1.vulkan_note"))
    if api is None:
        reasons.append(text(language, "a1.reason.api_unknown"))
    if game.bitness == 32:
        reasons.append(text(language, "a1.reason.32bit"))
    if not reasons:
        reasons.append(text(language, "a1.reason.ok"))
    return (not reasons or all("D3D11/D3D12" in r for r in reasons)), reasons


def plan(
    paths: Paths,
    game: Game,
    language: str | None = None,
    with_reshade: bool = False,
) -> RoutePlan:
    checks = Checks()
    actions: list[Action] = []
    missing: list[Missing] = []
    game_dir = game.install_dir
    exe_dir = game.launch_exe.parent if game.launch_exe else game_dir

    plan_obj = RoutePlan(
        route=ROUTE,
        title=text(language, "a1.title"),
        game_name=game.name,
        game_dir=game_dir,
        summary=text(language, "a1.summary"),
        detail=text(language, "a1.detail"),
    )

    # --- API / bitness -----------------------------------------------------
    api = game.rendering_api
    if api in ("DirectX 11", "DirectX 12"):
        checks.ok(
            text(language, "a1.check.api"),
            text(language, "a1.check.api.ok_detail", api=api, dll=RESHADE_PROXY_DLL),
        )
    elif api == "Vulkan":
        checks.block(
            text(language, "a1.check.api"),
            text(language, "a1.check.api.vulkan_detail"),
            text(language, "a1.vulkan_note"),
        )
    else:
        checks.warn(
            text(language, "a1.check.api"),
            text(
                language,
                "a1.check.api.unknown_detail",
                evidence=text(language, "a1.sep.comma").join(game.api_evidence)
                or text(language, "a1.check.api.no_evidence"),
            ),
            text(language, "a1.check.api.fix"),
        )

    if game.bitness == 64:
        checks.ok(
            text(language, "a1.check.bitness"),
            text(language, "a1.check.bitness.ok_detail", bits=game.bitness),
        )
    elif game.bitness == 32:
        checks.block(
            text(language, "a1.check.bitness"),
            text(language, "a1.check.bitness.block_detail"),
            text(language, "a1.check.bitness.block_fix"),
        )
    else:
        checks.warn(
            text(language, "a1.check.bitness"),
            text(language, "a1.unknown"),
            text(language, "a1.check.bitness.fix"),
        )

    # --- Proton prefix -----------------------------------------------------
    if game.proton_prefix is not None:
        checks.ok(
            text(language, "a1.check.prefix"),
            text(
                language,
                "a1.check.prefix.ok_detail",
                prefix=game.proton_prefix,
                tool=game.proton_tool or text(language, "a1.unknown"),
            ),
        )
        # The prefix needs NGX.  DXVK-NVAPI installs nvngx.dll; without it the
        # add-on's forwarder has nothing to talk to.
        nvngx = game.proton_prefix / "drive_c/windows/system32/nvngx.dll"
        if nvngx.is_file():
            checks.ok(
                text(language, "a1.check.ngx"),
                text(
                    language,
                    "a1.check.ngx.ok_detail",
                    size=human_size(nvngx.stat().st_size),
                ),
            )
        else:
            checks.warn(
                text(language, "a1.check.ngx"),
                text(language, "a1.check.ngx.warn_detail"),
                text(language, "a1.check.ngx.fix"),
            )
    else:
        checks.warn(
            text(language, "a1.check.prefix"),
            text(language, "a1.check.prefix.warn_detail"),
            text(language, "a1.check.prefix.fix"),
        )

    # --- ReShade -----------------------------------------------------------
    reshade_dll = exe_dir / RESHADE_PROXY_DLL
    reshade_ini = exe_dir / "ReShade.ini"
    if reshade_dll.is_file() and reshade_ini.is_file() and game.reshade_installed:
        checks.ok(
            text(language, "a1.check.reshade"),
            text(language, "a1.check.reshade.ok_detail", exe=game.launch_exe.name),
        )
    else:
        checks.warn(
            text(language, "a1.check.reshade"),
            text(language, "a1.check.reshade.warn_detail"),
            text(language, "a1.check.reshade.fix"),
        )
        actions.append(
            Action(
                kind="note",
                destination=text(language, "a1.action.reshade_install"),
                reason=text(language, "a1.action.reshade_not_redistributed"),
            )
        )

    # --- Add-ons -----------------------------------------------------------
    for component_key, filename, reason_key in (
        ("dlss5-bridge", BRIDGE_ADDON, "a1.action.reason_bridge"),
        ("addon-dlssnr-linux", ADDON_DLL, "a1.action.reason_addon"),
        ("addon-dlssnr-linux-forwarder", ADDON_FORWARDER, "a1.action.reason_forwarder"),
    ):
        component = providers.PINNED[component_key]
        destination = exe_dir / filename
        state = text(
            language,
            "a1.action.state_present" if destination.is_file() else "a1.action.state_to_install",
        )
        actions.append(
            Action(
                kind="copy",
                destination=str(destination),
                source=f"{component.name} {component.version} ({state})",
                reason=text(language, reason_key),
            )
        )

    # --- Bridge config: the Linux-specific unwrap=0 ------------------------
    actions.append(
        Action(
            kind="write",
            destination=str(exe_dir / BRIDGE_CFG),
            reason=text(language, "a1.action.write_cfg_reason"),
        )
    )

    # --- Native DLSS / substitute decision ---------------------------------
    if game.native_dlss:
        checks.ok(
            text(language, "a1.check.native_dlss"),
            text(
                language,
                "a1.check.native_dlss.ok_detail",
                count=len(game.native_dlss),
            ),
        )
        actions.append(
            Action(
                kind="note",
                destination=text(language, "a1.action.leave_synth"),
                reason=text(language, "a1.action.native_dlss_reason"),
            )
        )
    else:
        checks.warn(
            text(language, "a1.check.native_dlss"),
            text(language, "a1.check.native_dlss.warn_detail"),
            text(language, "a1.check.native_dlss.fix"),
        )
        missing.append(
            Missing(
                what=text(language, "a1.missing.substitute.what"),
                why=text(language, "a1.missing.substitute.why"),
                how_to_get=text(language, "a1.missing.substitute.how"),
                blocking=False,
            )
        )

    # --- The proprietary model --------------------------------------------
    candidates = discover_models(paths, game)
    tested = [c for c in candidates if c.verdict == "tested"]
    same_size = [c for c in candidates if c.verdict == "untested"]

    if tested:
        best = tested[0]
        checks.ok(
            text(language, "a1.check.nr_model"),
            text(language, "a1.check.nr_model.ok_detail", path=best.path),
        )
        actions.append(
            Action(
                kind="copy",
                destination=str(exe_dir / NR_MODEL_NAME),
                source=str(best.path),
                reason=text(language, "a1.action.model_reason_tested"),
                optional=best.path.parent == exe_dir,
            )
        )
    elif same_size:
        best = same_size[0]
        others = [c for c in candidates if c.sha256 != best.sha256]
        checks.warn(
            text(language, "a1.check.nr_model"),
            text(
                language,
                "a1.check.nr_model.warn_detail",
                count=len(candidates),
                path=best.path,
                sha=best.sha256[:16],
            ),
            text(
                language,
                "a1.check.nr_model.fix",
                sha=NR_MODEL_TESTED_SHA256[:16],
            ),
        )
        # The tested build has no official download, so the choice is: run an
        # unmeasured build, or fetch the pinned one. Offered as an action rather
        # than done silently, because it is a 104 MiB download from a community
        # mirror and that is the user's call, not this tool's.
        from .. import weights

        source = weights.RTX50_SOURCE
        actions.append(
            Action(
                kind="fetch",
                destination=str(source.url),
                source=source.build.label,
                reason=text(
                    language,
                    "a1.action.model_fetch_reason",
                    sha=NR_MODEL_TESTED_SHA256[:16],
                ),
                optional=True,
            )
        )
        if others:
            checks.warn(
                text(language, "a1.check.nr_model_alternatives"),
                text(language, "a1.sep.semicolon").join(
                    text(
                        language,
                        "a1.check.nr_model.alt_detail",
                        sha=c.sha256[:12],
                        path=c.path,
                    )
                    for c in others[:3]
                ),
                text(language, "a1.check.nr_model.alt_fix"),
            )
        actions.append(
            Action(
                kind="copy",
                destination=str(exe_dir / NR_MODEL_NAME),
                source=str(best.path),
                reason=text(language, "a1.action.model_reason_untested"),
                optional=best.path.parent == exe_dir,
            )
        )
    else:
        checks.block(
            text(language, "a1.check.nr_model"),
            text(language, "a1.check.nr_model.block_detail", name=NR_MODEL_NAME),
            text(language, "a1.check.nr_model.block_fix"),
        )
        missing.append(
            Missing(
                what=text(
                    language,
                    "a1.missing.model.what",
                    name=NR_MODEL_NAME,
                    size=human_size(NR_MODEL_TESTED_SIZE),
                    sha=NR_MODEL_TESTED_SHA256[:16],
                ),
                why=text(language, "a1.missing.model.why"),
                how_to_get=text(language, "a1.missing.model.how"),
                blocking=True,
            )
        )

    if tested_count(candidates) and len(candidates) > 1:
        checks.warn(
            text(language, "a1.check.nr_model_multiple"),
            text(
                language,
                "a1.check.nr_model.multiple_detail",
                count=len(candidates),
            ),
            text(language, "a1.check.nr_model.multiple_fix"),
        )

    # --- Launch options ----------------------------------------------------
    #
    # A1 cannot work without them: the proxy is loaded because the override tells
    # Wine to prefer it, and the bridge needs the NGX override. So the plan treats
    # them as part of the install rather than an optional extra, and reports the
    # Steam precondition here — the UI gates its install button on it, because a
    # write made while Steam runs is silently reverted.
    options, note = launch_options(game, language=language)
    plan_obj.launch_options = options
    plan_obj.launch_options_note = note

    from ..steamconfig import steam_state

    state = steam_state(paths, game.appid)
    plan_obj.steam_running = state.running
    if state.error:
        checks.warn(
            text(language, "a1.check.launch_options"),
            state.error,
            text(language, "a1.check.launch_options.fix_error"),
        )
    elif state.running:
        checks.warn(
            text(language, "a1.check.launch_options"),
            text(
                language,
                "a1.check.launch_options.blocked",
                pids=", ".join(str(pid) for pid in state.running_pids),
            ),
            text(language, "a1.check.launch_options.fix_running"),
        )
    else:
        checks.ok(
            text(language, "a1.check.launch_options"),
            text(language, "a1.check.launch_options.ok"),
        )

    if game.source == "steam":
        actions.append(
            Action(
                kind="launch-option",
                destination=options,
                reason=text(language, "a1.action.launch_option_reason"),
            )
        )

    # --- Anti-cheat --------------------------------------------------------
    from ..anticheat import detect_anticheat

    ac = detect_anticheat(game)
    if ac:
        checks.block(
            text(language, "a1.check.anticheat"),
            text(language, "a1.check.anticheat.detail", list=text(language, "a1.sep.comma").join(ac)),
            text(language, "a1.check.anticheat.fix"),
        )

    plan_obj.checks = checks
    plan_obj.actions = actions
    plan_obj.missing = missing
    plan_obj.manual_steps = [
        text(language, "a1.manual.install_reshade"),
        text(language, "a1.manual.launch"),
        text(language, "a1.manual.overlay"),
        text(language, "a1.manual.f10"),
        text(language, "a1.manual.check_log"),
    ]
    return plan_obj


# ------------------------------------------------------------------ install


BRIDGE_CFG_HEADER = (
    "; DLSS 5 Bridge configuration written by nvfku.\n"
    "; The bridge rewrites unknown keys from its own defaults, so this file is\n"
    "; rewritten from scratch rather than merged: it is ours, not the user's.\n"
)

# unwrap=0 is the Linux-specific setting.  On Windows the default is 1; under
# vkd3d the ReShade proxy device's descriptors are already native and
# re-translating them faults.  This single key is the difference between the
# documented Linux success report and a crash.
def render_bridge_cfg(*, synth: bool, vk_mirror: bool = False) -> str:
    lines = [BRIDGE_CFG_HEADER.rstrip("\n"), "unwrap=0"]
    lines.append(f"synth={1 if synth else 0}")
    lines.append(f"vk_mirror={1 if vk_mirror else 0}")
    if synth:
        lines.append("; substitute path: needs nvngx_dlss.dll >= 3.1.13 beside the executable")
    return "\n".join(lines) + "\n"


@locked_install
def install(
    paths: Paths,
    game: Game,
    *,
    verify_against_upstream: bool = True,
    skip_download: bool = False,
    with_reshade: bool = False,
    logger=print,
    proc_root: str = "/proc",
) -> InstallResult:
    """Apply A1.

    Nothing is written until the plan is viable and every component has been
    fetched and digest-checked, so a failure leaves the game directory
    untouched rather than half-installed.
    """
    route_plan = plan(paths, game)
    if not route_plan.viable:
        blockers = [c for c in route_plan.checks.checks if c.severity == "blocker"]
        detail = "; ".join(f"{c.name}: {c.detail}" for c in blockers) or "missing required files"
        raise InstallRefused(f"A1 cannot install: {detail}")

    # The launch options are not optional for this route — without them Wine never
    # loads the proxy and the whole chain is inert — and they cannot be written
    # while Steam is up. So the install is refused *before* anything is written
    # rather than producing a game directory that looks installed and does nothing.
    from ..steamconfig import SteamConfigError, set_launch_options, steam_state

    state = (
        steam_state(paths, game.appid, proc_root=proc_root)
        if game.source == "steam"
        else None
    )
    if state is not None and state.error:
        raise InstallRefused(f"A1 requires readable Steam launch options: {state.error}")
    if state is not None and state.running:
        raise InstallRefused(
            "Steam is running (pid "
            f"{', '.join(str(pid) for pid in state.running_pids)}), and A1 needs "
            "launch options that Steam would silently revert. Exit Steam completely "
            "— including the tray icon — and retry."
        )

    exe_dir = game.launch_exe.parent if game.launch_exe else game.install_dir
    result = InstallResult(route=ROUTE, game=game.name, game_dir=game.install_dir)

    # --- 1. fetch and verify components (network first, disk second) -------
    logger("fetching components")
    sources: dict[str, Path] = {}
    sums: dict[str, str] = {}
    if verify_against_upstream:
        try:
            sums_file = providers.fetch_asset(
                providers.PINNED["dlss5-bridge"], "SHA256SUMS.txt", paths,
                logger=logger, skip_download=skip_download
            )
            sums = providers.parse_shasums(sums_file.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            logger(f"  note: upstream SHA256SUMS unavailable ({exc}); sizes still checked")
    for key in ("dlss5-bridge", "addon-dlssnr-linux", "addon-dlssnr-linux-forwarder"):
        component = providers.PINNED[key]
        try:
            sources[key] = providers.fetch(component, paths, logger=logger, skip_download=skip_download)
        except ValueError as exc:
            raise InstallRefused(str(exc)) from exc
        digest_verified = False
        if component.sha256:
            result.verified.append(f"{component.name} matches the pinned SHA-256")
            digest_verified = True
        if sums:
            verified, message = providers.verify_against_shasums(sources[key], sums, logger=logger)
            if verified:
                result.verified.append(message)
                logger(f"  verify   {message}")
                digest_verified = True
            elif "does NOT match" in message:
                raise InstallRefused(f"upstream digest mismatch: {message}")
        if not digest_verified:
            level = "size-only" if component.size is not None else "unverified"
            warning = f"{component.name}: {level}; no upstream or pinned SHA-256 verified"
            result.warnings.append(warning)
            logger(f"  warning  {warning}")

    # --- 2. the game-local DLSS NR model ----------------------------------
    candidates = discover_models(paths, game)
    chosen = best_model(candidates)
    if chosen is None or not chosen.usable:
        raise InstallRefused(
            f"no usable {NR_MODEL_NAME} found; A1 cannot run without it"
        )
    model_dest = exe_dir / NR_MODEL_NAME
    if chosen.verdict == "tested":
        result.verified.append(f"""{NR_MODEL_NAME} is the build the add-on author measured as stable""")
    else:
        result.warnings.append(
            f"{NR_MODEL_NAME} is not the measured-stable build "
            f"(using sha256 {chosen.sha256[:16]}...); watch ReShade.log for crashes"
        )

    preflight_files(game.install_dir, sources.values(), [
        exe_dir / BRIDGE_ADDON, exe_dir / ADDON_DLL, exe_dir / ADDON_FORWARDER,
        exe_dir / BRIDGE_CFG, model_dest,
    ])
    preflight_files(game.install_dir, [chosen.path], [])

    # --- 3. apply, journalled ---------------------------------------------
    journal = FileJournal(paths, game.install_dir, ROUTE, game_key=game.key)
    result.journal_id = journal.journal_id
    logger(f"journal {journal.journal_id} in {journal.dir}")

    with transaction(journal):
        # Recheck after downloads: Steam may have started while they ran.
        state = steam_state(paths, game.appid, proc_root=proc_root) if game.source == "steam" else None
        if state is not None and state.error:
            raise InstallRefused(
                f"A1 requires Steam launch options, but they could not be read: {state.error}"
            )
        if state is not None and state.running:
            raise InstallRefused("Steam started during download; exit Steam and retry.")
        if state is not None and route_plan.launch_options:
            steam_op = journal.snapshot_external(state.config, source_label="Steam launch options", steam_config=True)
            try:
                write = set_launch_options(
                    paths, game.appid, route_plan.launch_options, proc_root=proc_root
                )
            except SteamConfigError as exc:
                raise InstallRefused(
                    f"the launch options could not be written: {exc}"
                ) from None
            journal.seal_external(steam_op)
            logger(f"steam launch options set to {route_plan.launch_options}")
            result.launch_options = route_plan.launch_options
            result.verified.append(
                f"launch options written ({'added' if write.created_key else 'updated'}); "
                f"backup {write.backup}"
            )
            result.notes.append(
                "launch options before this install: "
                + (state.current if state.current else "(none set)")
            )

        for order, (key, filename, label) in enumerate(
            (
                ("dlss5-bridge", BRIDGE_ADDON, "dlss5-bridge add-on"),
                ("addon-dlssnr-linux", ADDON_DLL, "DLSSNR feature-18 add-on"),
                ("addon-dlssnr-linux-forwarder", ADDON_FORWARDER, "NGX forwarder"),
            )
        ):
            logger(f"  [{order + 1}/5] {label}")
            journal.install_file(sources[key], exe_dir / filename, source_label=label)

        logger("  [4/5] bridge configuration (unwrap=0)")
        synth = not bool(game.native_dlss)
        journal.write_text(
            exe_dir / BRIDGE_CFG,
            render_bridge_cfg(synth=synth),
            source_label="nvfku generated",
        )

        logger(f"  [5/5] {NR_MODEL_NAME}")
        if chosen.path.parent == exe_dir:
            # Already in place: no copy, and no journal entry.  A "note" here would
            # have to point at the game directory rather than the file, which makes
            # the journal less useful, not more; `notes` on the result carries it
            # instead.
            result.notes.append(f"{NR_MODEL_NAME} already beside the executable; left unchanged")
        else:
            journal.install_file(chosen.path, model_dest, source_label=f"NVIDIA model ({chosen.verdict})")

        # --- 4. record what was done ------------------------------------------
        state_op = journal.snapshot_external(
            providers.route_state_path(paths, game.key, ROUTE), source_label="route state"
        )
        state = providers.read_route_state(paths, game.key, ROUTE)
        state.update(
            {
                "installed_at": journal._journal.created_at,
                "journal_id": journal.journal_id,
                "exe_dir": str(exe_dir),
                "model_source": str(chosen.path),
                "model_sha256": chosen.sha256,
                "model_verdict": chosen.verdict,
                "synth": synth,
                "components": {key: providers.PINNED[key].version for key in sources},
            }
        )
        providers.write_route_state(paths, game.key, ROUTE, state)
        journal.seal_external(state_op)
        result.notes.append(f"state written to {providers.route_state_path(paths, game.key, ROUTE)}")

    # --- 5. what the user still has to do ---------------------------------
    if not (exe_dir / RESHADE_PROXY_DLL).is_file():
        result.manual_steps.append(
            f"ReShade is not beside {game.launch_exe.name if game.launch_exe else 'the executable'}: "
            "run ReShade's installer (dxgi variant, add-on support enabled) inside this game's Proton prefix"
        )
    result.manual_steps.extend(route_plan.manual_steps)
    if route_plan.launch_options:
        result.launch_options = route_plan.launch_options
    return result
