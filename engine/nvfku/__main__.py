"""Command line entry point: ``python -m nvfku`` (or the ``nvfku`` script).

This is the same engine the Flutter UI drives, exposed for scripting and for
debugging.  Every mutating command supports ``--dry-run``, and every command
that changes a game directory writes a journal that ``rollback`` can replay.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, mirror, providers, steam, weights
from .paths import Paths, human_size
from .journal import list_journals, rollback_journal


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nvfku",
        description="Community DLSS 5 routes for Linux/Proton games.",
    )
    parser.add_argument("--version", action="version", version=f"nvfku {__version__}")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--language",
        default="en",
        choices=["en", "zh"],
        help="language for the plan text the routes produce (the UI passes zh)",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="override the journal/backup/cache root",
    )
    parser.add_argument(
        "--steam-root",
        type=Path,
        default=None,
        help="override the primary Steam install",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="show detection evidence"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="list games and what each one supports")
    scan.add_argument(
        "--filter",
        default=None,
        help="substring match on the game name",
    )
    scan.add_argument(
        "--routable",
        action="store_true",
        help="only games where at least one route is viable",
    )

    show = sub.add_parser("show", help="detail one game by appid or name substring")
    show.add_argument("game")

    prov = sub.add_parser("providers", help="show component versions and hashes")
    prov.add_argument(
        "--resolve",
        action="store_true",
        help="query the GitHub API for the rolling components' current versions",
    )

    plan = sub.add_parser("plan", help="dry-run a route against a game")
    plan.add_argument("game")
    plan.add_argument(
        "route",
        nargs="?",
        default=None,
        choices=["a1", "a2"],
        help="route to plan; omit for all viable routes",
    )
    plan.add_argument(
        "--with-reshade",
        action="store_true",
        help="for route a1, include its ReShade prerequisite in the plan",
    )

    inst = sub.add_parser("install", help="install a route into a game")
    inst.add_argument("game")
    inst.add_argument("route", choices=["a1", "a2"])
    inst.add_argument(
        "--yes",
        action="store_true",
        help="required: confirms you accept the anti-cheat risk and that files will change",
    )
    inst.add_argument(
        "--working-scale",
        type=int,
        default=None,
        help="A2 only: DLSS-NR neural pass resolution, 25-100 (cost scales with its square)",
    )
    inst.add_argument(
        "--skip-download",
        action="store_true",
        help="use only the local component cache; fail instead of fetching",
    )
    inst.add_argument(
        "--no-upstream-verify",
        action="store_true",
        help="skip comparing components against the publisher's SHA256SUMS",
    )
    inst.add_argument(
        "--with-reshade",
        action="store_true",
        help="for route a1, also install its ReShade prerequisite in the same run",
    )
    inst.add_argument(
        "--proc-root",
        default=os.environ.get("NVFKU_PROC_ROOT", "/proc"),
        help="where to look for running processes (default /proc, or $NVFKU_PROC_ROOT)",
    )

    launch = sub.add_parser(
        "launch-options",
        help="show or set a game's Steam launch options (guarded; refuses while Steam runs)",
    )
    launch.add_argument("game", help="appid or name substring")
    launch.add_argument(
        "--route",
        choices=["a1", "a2"],
        default=None,
        help="take the value from this route's plan instead of --value",
    )
    launch.add_argument("--value", default=None, help="the exact launch-option string to write")
    launch.add_argument("--clear", action="store_true", help="remove the LaunchOptions key")
    launch.add_argument("--dry-run", action="store_true", help="show what would change")
    launch.add_argument(
        "--config",
        type=Path,
        default=None,
        help="path to localconfig.vdf (default: discovered, and refused if there are several accounts)",
    )

    games = sub.add_parser(
        "games", help="add or remove a game folder Steam does not know about"
    )
    games.add_argument("folder", nargs="?", help="folder to add; omit with --remove-all to clear")
    games.add_argument("--remove", action="store_true", help="remove instead of add")
    games.add_argument("--list", action="store_true", help="list registered folders")

    conf = sub.add_parser("settings", help="show or change persisted settings")
    conf.add_argument("--python", default=None, help="interpreter for the engine")
    conf.add_argument("--steam-root", default=None, help="primary Steam install")
    conf.add_argument("--download-cache", default=None, help="component cache directory")
    conf.add_argument(
        "--proxy",
        default=None,
        help="network mode: auto (direct then proxy), direct, or a proxy URL",
    )
    conf.add_argument(
        "--verify-upstream",
        choices=["yes", "no"],
        default=None,
        help="compare components against the publisher's published digests",
    )

    art = sub.add_parser(
        "artwork", help="fetch Steam cover images for the library (cached locally)"
    )
    art.add_argument("game", nargs="?", default=None, help="one game; omit for the whole library")
    art.add_argument(
        "--art-language",
        default="schinese",
        help="Steam language for the localised artwork, e.g. schinese, tchinese",
    )
    art.add_argument(
        "--kind",
        choices=["poster", "header", "hero"],
        default="poster",
        help="which image family to prefer",
    )
    art.add_argument("--force", action="store_true", help="re-fetch even if cached")
    art.add_argument(
        "--cached-only",
        action="store_true",
        help="report only what is already on disk; never touch the network",
    )

    reshade_parser = sub.add_parser(
        "reshade",
        help="install ReShade's DXGI proxy through Proton (its own official setup tool)",
    )
    reshade_parser.add_argument("game", help="game key, name or appid")
    reshade_parser.add_argument(
        "--yes", action="store_true", help="actually install; without it this only plans"
    )

    model = sub.add_parser(
        "model",
        help="show, verify, or fetch the DLSS Neural Rendering model",
    )
    model.add_argument(
        "game",
        nargs="?",
        default=None,
        help="place the model beside this game's executable",
    )
    model.add_argument(
        "--list",
        action="store_true",
        help="list every known build, its digest and where it comes from",
    )
    model.add_argument(
        "--fetch",
        action="store_true",
        help="download the pinned RTX 50 build and verify its digest",
    )
    model.add_argument(
        "--verify",
        metavar="PATH",
        default=None,
        help="report what a DLL at this path is, by digest",
    )
    model.add_argument(
        "--mirror-status",
        action="store_true",
        help="report the vendored copy kept in the project tree",
    )
    model.add_argument(
        "--mirror-sync",
        action="store_true",
        help="copy the verified pinned build into the project's vendor tree",
    )
    model.add_argument(
        "--mirror-prune",
        action="store_true",
        help="delete the vendored copy from the project's vendor tree",
    )
    # Accepted after the subcommand as well as before it, because that is where a
    # user types it (`nvfku model --mirror-status --json`). SUPPRESS is
    # load-bearing: an argparse subparser writes its own defaults over the
    # namespace the main parser already filled, so a plain default=False here would
    # silently unset the global `nvfku --json model --list`.
    model.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="machine-readable output (same as the global --json)",
    )

    backups = sub.add_parser("backups", help="list journals")
    backups.add_argument("game", nargs="?", default=None)

    undo = sub.add_parser("rollback", help="revert a journal by id")
    undo.add_argument("journal_id")

    return parser


def _paths_from(args) -> Paths:
    paths = Paths.discover(state_root=args.state_dir)
    if args.steam_root is not None:
        paths = Paths(
            home=paths.home,
            state_root=paths.state_root,
            steam_root=args.steam_root,
            windows_mounts=paths.windows_mounts,
            extra_search_dirs=paths.extra_search_dirs,
        )
    return paths


def _find_game(games: list[steam.Game], needle: str) -> steam.Game | None:
    needle_l = needle.lower()
    for game in games:
        if game.appid == needle:
            return game
    exact = [g for g in games if g.name.lower() == needle_l]
    if exact:
        return exact[0]
    partial = [g for g in games if needle_l in g.name.lower()]
    return partial[0] if partial else None


def _resolve_one(paths, needle: str) -> "steam.Game | None":
    """One game, by the cheapest route that works.

    An appid names its own manifest, so it is a direct lookup; a name only exists
    inside the manifests, so it needs the scan. Falling back costs a second when the
    fast path finds nothing, and saves ten on every command a UI makes.
    """
    game = steam.scan_one(paths, needle)
    if game is not None:
        return game
    return _find_game(steam.scan_with_cache(paths), needle)


def cmd_scan(args) -> int:
    from . import settings as settings_module

    paths = _paths_from(args)
    settings = settings_module.load_settings(paths)
    if settings.steam_root and args.steam_root is None:
        paths = Paths(
            home=paths.home,
            state_root=paths.state_root,
            steam_root=Path(settings.steam_root),
            windows_mounts=paths.windows_mounts,
            extra_search_dirs=paths.extra_search_dirs,
        )
    games = steam.scan_with_cache(paths)
    # Hand-added folders, for installs Steam does not know about.
    games.extend(settings_module.scan_added_games(paths))
    games.sort(key=lambda g: g.name.lower())
    if args.filter:
        needle = args.filter.lower()
        games = [g for g in games if needle in g.name.lower() or needle == g.appid]
    if args.routable:
        from .route import a1_bridge, a2_optiscaler

        games = [
            g
            for g in games
            if any(
                module.is_viable(g)[0]
                for module in (a1_bridge, a2_optiscaler)
            )
        ]

    if args.json:
        print(json.dumps([g.to_dict() for g in games], indent=2))
        return 0

    if not games:
        print("no games found")
        return 0

    print(f"{len(games)} games")
    print(
        f"{'appid':>8}  {'name':<38} {'api':<11} {'bits':<5} {'DLSS':<9} {'proton':<20}"
    )
    print("-" * 100)
    for game in games:
        dlss = ("DLSS" if game.native_dlss else "-") + ("+NR" if game.nvngx_dlssnr else "")
        print(
            f"{game.appid:>8}  {game.name[:38]:<38} {(game.rendering_api or '?'):<11} "
            f"{str(game.bitness or '?'):<5} {dlss:<9} {(game.proton_tool or '-')[:20]:<20}"
        )
        if args.verbose:
            print(f"          exe  {game.launch_exe}")
            print(f"          why  {', '.join(game.api_evidence) or '(no evidence)'}")
    return 0


def cmd_show(args) -> int:
    paths = _paths_from(args)
    games = steam.scan_with_cache(paths)
    game = _find_game(games, args.game)
    if game is None:
        print(f"no game matching {args.game!r}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(game.to_dict(), indent=2))
        return 0

    from .route import a1_bridge, a2_optiscaler

    print(f"{game.name}  (appid {game.appid})")
    print(f"  install dir   {game.install_dir}")
    print(f"  launch exe    {game.launch_exe}")
    print(f"  rendering API {game.rendering_api or 'unknown'}")
    print(f"  bitness       {game.bitness or 'unknown'}")
    print(f"  evidence      {', '.join(game.api_evidence) or '(none)'}")
    print(f"  proton prefix {game.proton_prefix or '(none)'}")
    print(f"  proton tool   {game.proton_tool or '(unknown)'}")
    print(f"  native DLSS   {[p.name for p in game.native_dlss] or 'none'}")
    print(f"  DLSS NR model {[str(p) for p in game.nvngx_dlssnr] or 'none'}")
    print("  routes:")
    for label, module in (("A1 bridge", a1_bridge), ("A2 optiscaler", a2_optiscaler)):
        viable, reasons = module.is_viable(game)
        mark = "viable" if viable else "not viable"
        print(f"    {label:<16} {mark}")
        for reason in reasons:
            print(f"        - {reason}")
    return 0


def cmd_providers(args) -> int:
    paths = _paths_from(args)
    rows = []
    for key, component in providers.PINNED.items():
        rows.append(
            {
                "key": key,
                "name": component.name,
                "version": component.version,
                "pinned": True,
                "sha256": component.sha256,
                "size": component.size,
                "url": component.url,
            }
        )
    for key in providers.ROLLING:
        spec = providers.ROLLING[key]
        entry = {
            "key": key,
            "name": key,
            "version": "(resolved at install)",
            "pinned": False,
            "homepage": spec["homepage"],
        }
        if args.resolve:
            # Cached, for the same reason the plan path is: this page is opened
            # repeatedly, and an uncached call here was three synchronous GitHub API
            # requests (~1 s behind a proxy, and a 60-per-hour budget spent three at
            # a time). The cache also means a rate limit degrades to a known version
            # instead of an error in the table.
            try:
                resolved = providers.resolve_rolling_cached(paths, key)
                entry.update(
                    {
                        "version": resolved.version,
                        "size": resolved.size,
                        "url": resolved.url,
                    }
                )
            except Exception as exc:  # network or API failure must not kill the listing
                entry["error"] = str(exc)
        rows.append(entry)

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    for row in rows:
        pin = "pinned " if row["pinned"] else "rolling"
        size = human_size(row["size"]) if row.get("size") else "?"
        print(f"{pin}  {row['key']:<30} {row['version']:<20} {size:>10}")
        if row.get("sha256"):
            print(f"        sha256 {row['sha256']}")
        if row.get("url"):
            print(f"        {row['url']}")
        if row.get("error"):
            print(f"        error: {row['error']}")
    return 0


def cmd_plan(args) -> int:
    paths = _paths_from(args)
    game = _resolve_one(paths, args.game)
    if game is None:
        print(f"no game matching {args.game!r}", file=sys.stderr)
        return 1
    from .plan import render_plan
    from .route import a1_bridge, a2_optiscaler

    modules = {
        "a1": a1_bridge,
        "a2": a2_optiscaler,
    }
    chosen = [modules[args.route]] if args.route else list(modules.values())

    plans = [
        module.plan(
            paths,
            game,
            language=args.language,
            **({"with_reshade": True} if getattr(args, "with_reshade", False) else {}),
        )
        if module.ROUTE == "a1"
        else module.plan(paths, game, language=args.language)
        for module in chosen
    ]

    # A1 needs ReShade as its proxy, and ReShade is something this project downloads
    # rather than ships. It is attached to A1 as a *prerequisite* rather than
    # returned alongside: it is a component of that route, not a third option, and
    # listing it as a sibling made the plan read as three routes when there are two.
    if args.route in (None, "a1"):
        from . import reshade as reshade_module

        for plan in plans:
            if plan.route == "a1":
                plan.prerequisite = reshade_module.check(
                    paths,
                    game,
                    logger=None,
                    nested=True,
                    # Without this the prerequisite renders in English inside a
                    # Chinese plan, which is worse than not translating it at all.
                    language=args.language,
                )

    if args.json:
        print(json.dumps([p.to_dict() for p in plans], indent=2))
    else:
        for plan in plans:
            print(render_plan(plan))
            print()
    return 0 if all(p.viable for p in plans) else 2


def cmd_launch_options(args) -> int:
    """Show, set or clear a game's Steam launch options.

    Writing is guarded: it refuses while a Steam client is running, because the
    experiment in docs/experiment-localconfig.md showed Steam keeps this key in
    memory and writes its copy back over an external edit.
    """
    from . import steamconfig

    paths = _paths_from(args)
    games = steam.scan_with_cache(paths)
    game = _find_game(games, args.game)
    if game is None:
        message = f"no game matching {args.game!r}"
        print(json.dumps({"ok": False, "error": message}) if args.json else message,
              file=sys.stdout if args.json else sys.stderr)
        return 1

    config = args.config or steamconfig.config_file_for(paths)
    current = steamconfig.read_launch_options(config.read_text(encoding="utf-8"), game.appid)

    if not args.clear and args.value is None and args.route is None:
        # Read-only: report and stop.
        payload = {
            "appid": game.appid,
            "game": game.name,
            "config": str(config),
            "launch_options": current,
            "steam_running": bool(steamconfig.running_steam_processes()),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"{game.name}  (appid {game.appid})")
            print(f"  config:  {config}")
            print(f"  current: {current if current is not None else '(none)'}")
            if payload["steam_running"]:
                print("  Steam is running: writing is refused until it is closed.")
        return 0

    # Work out the value to write.
    if args.clear:
        value = ""
    elif args.value is not None:
        value = args.value
    else:
        from .route import a1_bridge, a2_optiscaler

        module = {"a1": a1_bridge, "a2": a2_optiscaler}[args.route]
        plan = module.plan(paths, game, language=args.language)
        if not plan.launch_options:
            print(f"{module.TITLE} produces no launch options", file=sys.stderr)
            return 2
        value = plan.launch_options

    try:
        if args.clear:
            result = steamconfig.clear_launch_options(paths, game.appid, config_path=config)
        else:
            result = steamconfig.set_launch_options(
                paths, game.appid, value, config_path=config, dry_run=args.dry_run
            )
    except steamconfig.SteamConfigError as exc:
        if args.json:
            print(json.dumps({"ok": False, "refused": str(exc), "appid": game.appid}))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "ok": True,
            "appid": game.appid,
            "game": game.name,
            "value": result.value,
            "previous": result.previous,
            "config": str(result.path),
            "backup": str(result.backup),
            "created_key": result.created_key,
            "verified": result.verified,
            "notes": result.notes,
        }, indent=2))
    else:
        print(result.render())
    return 0


def cmd_games(args) -> int:
    """Register or drop a game folder that Steam does not manage."""
    from . import settings as settings_module

    paths = _paths_from(args)
    if args.list or args.folder is None:
        entries = settings_module.load_added_games(paths)
        if args.json:
            print(json.dumps({"folders": entries, "file": str(settings_module.added_games_path(paths))}, indent=2))
        else:
            print(f"registered folders ({len(entries)}):")
            for entry in entries:
                exists = "ok" if Path(entry).is_dir() else "MISSING"
                print(f"  [{exists}] {entry}")
        return 0

    try:
        if args.remove:
            removed = settings_module.remove_game_folder(paths, args.folder)
            if args.json:
                print(json.dumps({"ok": removed, "removed": args.folder}))
            else:
                print(f"removed {args.folder}" if removed else f"{args.folder} was not registered")
            return 0 if removed else 1
        game = settings_module.add_game_folder(paths, args.folder)
    except settings_module.AddedGameError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"cannot add: {exc}", file=sys.stderr)
        return 2

    payload = {
        "ok": True,
        "key": game.appid,
        "name": game.name,
        "install_dir": str(game.install_dir),
        "launch_exe": str(game.launch_exe) if game.launch_exe else None,
        "rendering_api": game.rendering_api,
        "bitness": game.bitness,
        "file": str(settings_module.added_games_path(paths)),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"added {game.name}")
        print(f"  key:   {game.appid}")
        print(f"  exe:   {game.launch_exe}")
        print(f"  api:   {game.rendering_api or 'unknown'}  ({game.bitness or '?'}-bit)")
        print(f"  file:  {payload['file']}")
    return 0


def cmd_settings(args) -> int:
    from . import settings as settings_module

    paths = _paths_from(args)
    settings = settings_module.load_settings(paths)
    changed = False
    for attribute, value in (
        ("python_path", args.python),
        ("steam_root", args.steam_root),
        ("download_cache", args.download_cache),
        ("proxy_mode", args.proxy),
    ):
        if value is not None:
            setattr(settings, attribute, value)
            changed = True
    if args.verify_upstream is not None:
        settings.verify_upstream = args.verify_upstream == "yes"
        changed = True

    path = settings_module.save_settings(paths, settings) if changed else settings_module.settings_path(paths)
    if args.json:
        print(json.dumps({"settings": settings.to_dict(), "file": str(path)}, indent=2))
        return 0
    print(f"settings ({path})")
    for label, value in settings.describe():
        print(f"  {label:<24} {value}")
    if changed:
        print("  (saved)")
    return 0


def cmd_reshade(args) -> int:
    """Install ReShade for one game, through its own setup tool.

    Planning and installing are the same code path up to the write, so the plan a
    user approves is the plan that runs.
    """
    from . import reshade as reshade_module
    from .plan import InstallRefused, render_plan

    paths = _paths_from(args)
    games = steam.scan_with_cache(paths)
    game = _find_game(games, args.game)
    if game is None:
        message = f"no game matching {args.game!r}"
        print(json.dumps({"ok": False, "error": message}) if args.json else message,
              file=sys.stdout if args.json else sys.stderr)
        return 1

    log = (lambda m: None) if args.json else print
    plan = reshade_module.check(paths, game, logger=log, language=args.language)

    if not args.yes:
        if args.json:
            print(json.dumps({
                "ok": True,
                "needs_confirmation": True,
                "plan": plan.to_dict(),
            }, indent=2))
        else:
            print(render_plan(plan))
            if plan.viable:
                print("\nRe-run with --yes to install.")
        return 0 if plan.viable else 2

    try:
        result = reshade_module.install(
            paths, game, logger=log, yes=True, language=args.language
        )
    except reshade_module.ReshadeError as exc:
        if args.json:
            print(json.dumps({"ok": False, "refused": str(exc), "plan": plan.to_dict()}))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return 1
    except InstallRefused as exc:
        if args.json:
            print(json.dumps({"ok": False, "refused": str(exc), "plan": plan.to_dict()}))
        else:
            print(f"refused: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"ok": True, "plan": plan.to_dict(), "result": result.to_dict()}))
    else:
        print(result.render())
    return 0


def cmd_artwork(args) -> int:
    """Fetch and cache Steam cover images."""
    from . import artwork as artwork_module

    paths = _paths_from(args)

    if args.game is None:
        games = steam.scan_with_cache(paths)
    else:
        game = _find_game(steam.scan_with_cache(paths), args.game)
        if game is None:
            message = f"no game matching {args.game!r}"
            print(json.dumps({"ok": False, "error": message}) if args.json else message,
                  file=sys.stdout if args.json else sys.stderr)
            return 1
        games = [game]

    if args.cached_only:
        index = artwork_module.load_index(paths)
        payload = {
            "ok": True,
            "directory": str(artwork_module.artwork_dir(paths)),
            "artwork": {
                game.appid: (
                    index.get(game.appid, {}).get("path")
                    if Path(str(index.get(game.appid, {}).get("path") or "")).is_file()
                    else None
                )
                for game in games
            },
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            found = sum(1 for value in payload["artwork"].values() if value)
            print(f"{found}/{len(games)} games have a cached cover")
        return 0

    results = []
    for game in games:
        result = artwork_module.ensure_artwork(
            paths,
            game,
            kind=args.kind,
            language=None if args.art_language == "english" else args.art_language,
            force=args.force,
            logger=lambda m: None if args.json else print(m),
        )
        results.append((game, result))
        if not args.json:
            print(f"{game.name}: {result.describe()}")

    found = sum(1 for _g, r in results if r.found)
    if args.json:
        print(json.dumps({
            "ok": True,
            "directory": str(artwork_module.artwork_dir(paths)),
            "found": found,
            "total": len(results),
            "games": [
                {
                    "appid": g.appid,
                    "name": g.name,
                    "path": str(r.path) if r.found else None,
                    "source": r.source,
                    "family": r.family,
                    "localised": r.localised,
                }
                for g, r in results
            ],
        }, indent=2))
    else:
        print(f"\n{found}/{len(results)} games have artwork in {artwork_module.artwork_dir(paths)}")
    return 0


def cmd_backups(args) -> int:
    paths = _paths_from(args)
    game_dir = None
    if args.game:
        games = steam.scan_with_cache(paths)
        game = _find_game(games, args.game)
        if game is None:
            print(f"no game matching {args.game!r}", file=sys.stderr)
            return 1
        game_dir = game.install_dir
    entries = list_journals(paths, game_dir=game_dir)
    if args.json:
        print(json.dumps(entries, indent=2))
        return 0
    if not entries:
        print("no journals")
        return 0
    for entry in entries:
        state = "rolled back" if entry.get("rolled_back") else ("complete" if entry.get("finished") else "incomplete")
        print(
            f"{entry['id']}  {entry['route']:<10} {state:<12} {entry['operations']:>3} ops  {entry['game_dir']}"
        )
    return 0


def cmd_rollback(args) -> int:
    paths = _paths_from(args)
    lines = rollback_journal(paths, args.journal_id)
    for line in lines:
        print(line)
    return 0 if lines else 1


def cmd_install(args) -> int:
    paths = _paths_from(args)
    games = steam.scan_with_cache(paths)
    game = _find_game(games, args.game)
    if game is None:
        if args.json:
            print(json.dumps({"ok": False, "error": f"no game matching {args.game!r}"}))
            return 1
        print(f"no game matching {args.game!r}", file=sys.stderr)
        return 1

    from .route import a1_bridge, a2_optiscaler

    module = {"a1": a1_bridge, "a2": a2_optiscaler}[args.route]

    # Show the plan first, always: installing is the second half of planning,
    # so the user sees exactly what will change before it changes.
    from .plan import render_plan

    route_plan = module.plan(
        paths,
        game,
        language=args.language,
        **({"with_reshade": True}
           if args.route == "a1" and getattr(args, "with_reshade", False)
           else {}),
    )
    if not args.json:
        print(render_plan(route_plan))
        print()

    if not route_plan.viable:
        blockers = [c for c in route_plan.checks.checks if c.severity == "blocker"]
        if args.json:
            # `refused` carries the specific reason, not a category, so a caller
            # that only reads one field still learns what to fix.
            reason = "; ".join(f"{c.name}: {c.detail}" for c in blockers) or "the route is blocked"
            print(json.dumps({
                "ok": False,
                "refused": reason,
                "blockers": [
                    {"name": c.name, "detail": c.detail, "fix": c.fix} for c in blockers
                ],
                "plan": route_plan.to_dict(),
            }))
            return 2
        print("refusing to install:", file=sys.stderr)
        for check in blockers:
            print(f"  - {check.name}: {check.detail}", file=sys.stderr)
            if check.fix:
                print(f"      fix: {check.fix}", file=sys.stderr)
        return 2

    if not args.yes:
        if args.json:
            print(json.dumps({
                "ok": False,
                "needs_confirmation": True,
                "plan": route_plan.to_dict(),
            }))
            return 3
        print("this would change files in the game directory.", file=sys.stderr)
        print("re-run with --yes to apply.", file=sys.stderr)
        return 3

    from .plan import InstallRefused

    # Under --json nothing human-readable may reach stdout, including the
    # engine's own step-by-step logger, or the document stops being parseable.
    def _quiet(message: str) -> None:
        print(message, file=sys.stderr)

    kwargs = {
        "skip_download": args.skip_download,
        "logger": _quiet if args.json else print,
    }
    if args.route == "a2":
        kwargs["working_scale"] = args.working_scale
    else:
        kwargs["verify_against_upstream"] = not args.no_upstream_verify
        kwargs["with_reshade"] = bool(getattr(args, "with_reshade", False))
        kwargs["proc_root"] = args.proc_root

    try:
        result = module.install(paths, game, **kwargs)
    except InstallRefused as exc:
        if args.json:
            print(json.dumps({"ok": False, "refused": str(exc), "plan": route_plan.to_dict()}))
            return 2
        print(f"install refused: {exc}", file=sys.stderr)
        return 2

    if args.json:
        # A single JSON document, so a consumer never has to scrape the
        # human-readable rendering for the journal id.
        print(json.dumps({"ok": True, "plan": route_plan.to_dict(), "result": result.to_dict()}))
        return 0

    print()
    print(result.render())
    return 0


def _mirror_payload(state: mirror.MirrorState) -> dict:
    """One MirrorState as JSON-ready values.

    A Path and a missing string are not the same kind of thing to a consumer, so
    the path is rendered or nulled here rather than left to json.dumps.
    """
    return {
        "path": str(state.path) if state.path is not None else None,
        "present": state.present,
        "verified": state.verified,
        "sha256": state.sha256,
        "size": state.size,
        "url": state.url,
    }


def cmd_model(args) -> int:
    """Inspect and obtain the DLSS Neural Rendering model.

    Three separate questions, deliberately not merged into one command: what builds
    exist, what a file on this machine is, and getting the pinned one. Merging them
    would mean a user who only wants to identify a file has to pass flags to stop it
    downloading 104 MiB.

    The three mirror flags ask a fourth question -- what a *checkout* keeps -- and
    are answered before the "no flags means --list" branch below, which would
    otherwise print the build table for a mirror-only invocation.
    """

    if args.mirror_status:
        state = mirror.inspect()
        if args.json:
            print(json.dumps(_mirror_payload(state), indent=2))
            return 0
        print(state.describe())
        if not state.present:
            print(f"  path    {mirror.VENDOR_DIR / weights.MODEL_NAME}")
            print("  run `nvfku model --mirror-sync` to put the pinned build there")
        elif not state.verified:
            print("  run `nvfku model --mirror-sync` to replace it with the pinned build")
        return 0

    if args.mirror_sync:
        log = (lambda *_: None) if args.json else print
        try:
            state = mirror.sync(paths=_paths_from(args), logger=log)
        except weights.WeightsError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}))
                return 2
            print(f"model: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({"ok": True, **_mirror_payload(state)}, indent=2))
            return 0
        print()
        print("vendored:")
        print(f"  {state.path}")
        print(f"  sha256 {state.sha256}")
        return 0

    if args.mirror_prune:
        try:
            removed = mirror.prune()
        except weights.WeightsError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}))
                return 2
            print(f"model: {exc}", file=sys.stderr)
            return 2
        target = mirror.VENDOR_DIR / weights.MODEL_NAME
        if args.json:
            print(
                json.dumps(
                    {"ok": True, "removed": removed, "path": str(target)}, indent=2
                )
            )
            return 0
        print(f"removed {target}" if removed else f"nothing to remove at {target}")
        return 0

    if args.verify:
        target = Path(args.verify).expanduser()
        if not target.is_file():
            print(f"no such file: {target}", file=sys.stderr)
            return 1
        digest = weights._digest(target)
        build = weights.identify(digest)
        info = {
            "path": str(target),
            "size": target.stat().st_size,
            "sha256": digest,
            "known": build is not None,
            "tested": bool(build and build.tested),
            "label": build.label if build else None,
            "source": build.source if build else None,
            "note": build.note if build else None,
        }
        if args.json:
            print(json.dumps(info, indent=2))
            return 0
        print(f"{target}")
        print(f"  size    {human_size(info['size'])}")
        print(f"  sha256  {digest}")
        if build:
            print(f"  build   {build.label}")
            print(f"  source  {build.source}")
            print(f"  tested  {'yes' if build.tested else 'no'} — {build.note}")
        else:
            print("  build   not one this tool knows")
        return 0

    if args.list or (not args.fetch and not args.game):
        rows = []
        for build in weights.builds():
            source = weights.source_for(build)
            rows.append(
                {
                    "label": build.label,
                    "version": build.version,
                    "sha256": build.sha256,
                    "size": build.size,
                    "tested": build.tested,
                    "vendor": build.vendor,
                    "source": build.source,
                    "note": build.note,
                    "downloadable": source is not None,
                    "url": source.url if source else None,
                    "vendor_signed": source.vendor_signed if source else None,
                }
            )
        if args.json:
            print(json.dumps({"builds": rows}, indent=2))
            return 0
        print("Known builds of nvngx_dlssnr.dll")
        print()
        for row in rows:
            mark = "tested stable" if row["tested"] else "             "
            print(f"  {row['sha256'][:16]}  [{mark}]  {row['label']}")
            print(f"      source  {row['source']}")
            if row["downloadable"]:
                signed = "NVIDIA-signed" if row["vendor_signed"] else "community rebuild"
                print(f"      get it  {signed}, {row['url']}")
            else:
                print(f"      note    {row['note']}")
            print()
        print("  The pinned download is a community mirror of NVIDIA's own signed")
        print("  runtime, not an NVIDIA download. Its digest is checked on arrival.")
        return 0

    source = weights.RTX50_SOURCE
    log = (lambda *_: None) if args.json else print
    try:
        if args.game and not args.fetch:
            lookup = _paths_from(args)
            games = steam.scan_with_cache(lookup)
            match = _find_game(games, args.game)
            if match is None:
                print(f"no game matching {args.game!r}", file=sys.stderr)
                return 1
            exe_dir = (
                match.launch_exe.parent if match.launch_exe else match.install_dir
            )
            placed = weights.install(lookup, exe_dir, source, logger=log)
            if args.json:
                print(json.dumps({"ok": True, "placed": str(placed), "sha256": source.build.sha256}))
                return 0
            print()
            print(f"placed the model beside {match.name}:")
            print(f"  {placed}")
            print(f"  sha256 {source.build.sha256}")
            return 0

        fetched = weights.download(_paths_from(args), source, logger=log)
        if args.json:
            print(json.dumps({"ok": True, "cached": str(fetched), "sha256": source.build.sha256}))
            return 0
        print()
        print("verified and cached:")
        print(f"  {fetched}")
        print(f"  sha256 {source.build.sha256}")
        return 0
    except weights.WeightsError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 2
        print(f"model: {exc}", file=sys.stderr)
        return 2


COMMANDS = {
    "model": cmd_model,
    "install": cmd_install,
    "artwork": cmd_artwork,
    "reshade": cmd_reshade,
    "games": cmd_games,
    "settings": cmd_settings,
    "launch-options": cmd_launch_options,
    "scan": cmd_scan,
    "show": cmd_show,
    "providers": cmd_providers,
    "plan": cmd_plan,
    "backups": cmd_backups,
    "rollback": cmd_rollback,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
