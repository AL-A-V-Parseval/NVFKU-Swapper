# NVFKU-Swapper

**English** · [简体中文](README.zh.md)

A Linux-native installer for community DLSS 5 routes, in the spirit of
[DLSS5-Swapper](https://github.com/rakanki911/DLSS5-Swapper) but built around
one fact that tool does not have to deal with:

> **Wine's Vulkan loader never enumerates third-party layers.**
> `winevulkan`'s `vkEnumerateInstanceLayerProperties` returns zero layers and its
> loader only understands `HKLM\Software\Khronos\Vulkan\Drivers` (the ICD key).
> No tool can register a Vulkan layer for a Proton game, because the game's
> `vkCreateInstance` would fail with `VK_ERROR_LAYER_NOT_PRESENT`.

Every design decision here follows from that, plus four more measured
constraints:

| Constraint | Consequence |
| --- | --- |
| Driver-dispatched NGX feature 18 fails under Proton (`FAIL_OutOfDate`) | the neural consumer must drive the feature directly from a DLL |
| Drivers 32.0.16.1664 / 1686 route feature 18 into a snippet that faults | pinning and reporting matter more than "latest" |
| On Linux ReShade's proxy descriptors must be left native (`unwrap=0`), the opposite of the Windows default | the bridge config is where a naive port crashes |
| Game directories on a dual-boot machine often already hold the proprietary model | it is discovered and classified by digest first, and downloaded only when nothing usable is present |

## Layout

```
engine/                 pure-Python, stdlib only, no GUI dependency
  nvfku/
    paths.py            filesystem layer; atomic, symlink-safe writes
    pe.py               hand-written PE reader (bitness, imports, strings)
    steam.py            Steam library discovery, API/bitness/DLSS detection
    journal.py          transactional file journal with exact rollback
    providers.py        upstream release resolution + hash pinning
    model.py            location and digest classification of nvngx_dlssnr.dll
    anticheat.py        evidence-based anti-cheat detection
    plan.py             RoutePlan/Action/Check vocabulary (dry-run == installer's first half)
    route/
      a1_bridge.py      ReShade + dlss5-bridge + addon-dlssnr-linux
      a2_optiscaler.py  OptiScaler DLSS-NR via DLL proxy
    __main__.py         CLI
  tests/                232 tests, stdlib unittest
app/                    Flutter UI (Flutter SDK only, no third-party packages)
tools/env.sh            isolation: project venv + pinned SDK + local pub cache
tools/install_desktop.py  a menu entry for a checkout, in the user XDG dirs
```

## Isolation

Nothing is installed into the system Python, nothing pollutes `~/.pub-cache`,
and no root is required:

```sh
source tools/env.sh        # project .venv, pinned Flutter SDK, local pub cache, local CMake
nvfku scan              # engine CLI
flutter build linux        # UI
```

Everything lives in one of three places, all outside the repository tree:

| What | Where | Why there |
| --- | --- | --- |
| Python venv | `<project>/.venv` | system Python stays untouched |
| Flutter SDK 3.47.5 | `~/.local/opt/flutter` | no system package, version pinned |
| pub cache | `<project>/.pub-cache` | `~/.pub-cache` stays clean |
| CMake 4.2.0 | `~/.local/opt/cmake` | Flutter's Linux build needs CMake, which a base CachyOS install lacks and which would otherwise need `sudo pacman -S cmake` |
| engine state | `~/.local/share/nvfku` | journals, backups, component cache |

`tools/env.sh` picks up the local CMake automatically when the system has none.

To put the app in the desktop application menu without installing anything
system-wide:

```sh
python3 tools/install_desktop.py            # writes into ~/.local/share
python3 tools/install_desktop.py --check    # report, change nothing
python3 tools/install_desktop.py --uninstall
```

The `.deb` ships its own menu entry, but that one points at `/usr/bin/nvfku-swapper`;
a checkout needs its own, and this writes it plus the icon into the *user* XDG
directories, so it needs no root and is undone by `--uninstall`. Re-run it after
moving the checkout — the `Exec` line holds an absolute path, and a stale one gives
you a menu entry that silently does nothing.

## Usage

```sh
python -m nvfku scan                        # what is installed and what each game supports
python -m nvfku scan --routable             # only games a route can serve
python -m nvfku show 1091500                # one game, with per-route viability
python -m nvfku plan 1091500 a1             # dry-run: exactly what would change
python -m nvfku install 1091500 a1 --yes    # apply it (a journal is written first)
python -m nvfku providers --resolve         # component versions and hashes
python -m nvfku backups                     # every journal ever written
python -m nvfku rollback <journal-id>       # undo one, exactly

python -m nvfku model --list                # every known build of the model, by digest
python -m nvfku model --verify <path>       # what a DLL on this machine actually is
python -m nvfku model --fetch               # download the tested build, digest-checked
python -m nvfku model --mirror-sync         # keep a verified copy inside the project

python -m nvfku launch-options 1091500                      # show what Steam has now
python -m nvfku launch-options 1091500 --route a1 --dry-run  # what A1 would write
python -m nvfku launch-options 1091500 --route a1            # write it (guarded)
python -m nvfku launch-options 1091500 --clear               # remove the key
```

The Flutter UI drives the same engine as a subprocess, so a plan the UI shows is
the plan the CLI would print.

### The `--json` contract

`--json` is the machine interface the UI uses, and it is strict: **stdout carries
one JSON document and nothing else.** That includes the failure paths, which is
where a naive implementation leaks:

| Situation | Document |
| --- | --- |
| installed | `{"ok": true, "plan": ..., "result": ...}` |
| route is blocked | `{"ok": false, "refused": ..., "blockers": [...], "plan": ...}` |
| not confirmed | `{"ok": false, "needs_confirmation": true, "plan": ...}` |
| install refused at runtime | `{"ok": false, "refused": ..., "plan": ...}` |
| no such game | `{"ok": false, "error": ...}` |

The engine's own step logger is redirected to stderr under `--json` for the same
reason. This exists because the first UI draft scraped the journal id out of the
human-readable rendering with a regex, which is exactly the kind of parsing that
breaks silently.

## Networking

Two measured facts shaped the transport layer:

- A direct connection to GitHub intermittently times out (`Errno 110`) while
  succeeding seconds later, so retries with backoff are not optional.
- GitHub release downloads redirect to `release-assets.githubusercontent.com`,
  which is **unreachable directly** on this machine while `raw.githubusercontent.com`
  and `api.github.com` are fine. The local proxy reaches it.

So `http_get` retries, then **falls back from direct to proxy**, and reports every
route it tried when all of them fail. Order is configurable:

```sh
DLSS5_HTTP_PROXY=direct                      # default: direct first, proxy as fallback
DLSS5_HTTP_PROXY=http://127.0.0.1:7897       # proxy first, direct as fallback
```

Only transport-shaped failures are retried. A `ValueError` out of the opener is a
bug and surfaces immediately rather than being retried into a slow, misleading
timeout.

## Routes

There are **two** routes. They are named for what they do rather than for an
internal code, because the codes leaked into the UI and made a two-way choice read
as three.

| | Route | Attaches via | Needs | Writes |
| --- | --- | --- | --- | --- |
| **ReShade overlay** | ReShade + dlss5-bridge + addon-dlssnr-linux | local `dxgi.dll` and ReShade add-ons | D3D11/D3D12, 64-bit, Proton, the NR model, **and its ReShade prerequisite** | yes (journalled) |
| **OptiScaler direct** | OptiScaler DLSS-NR | local proxy DLL (`dxgi.dll`) | D3D11/D3D12, 64-bit, game must already use DLSS | yes (journalled) |

ReShade is **not** a third route. It is a component the overlay route needs, so it
is planned as a nested prerequisite of that route and keeps its own install action
(and its own `nvfku reshade` command) without appearing in the route list as a
sibling. Presenting it alongside made the plan read as three options when there are
two.

A Vulkan-layer route is deliberately absent; see the constraint at the top. There
is no OpenDLSS-NR probe either: it only ever reported what a native port would
need, and a feasibility report that cannot change anything is not worth the screen
it occupies.

## Status

**232 tests, all passing.** Working and verified against the real Steam library on
the development machine (20 games, 9 runtimes filtered out):

- Steam discovery across multiple libraries, Proton prefix and tool resolution
  (`CachyOS-10.1000-200` vs `11.0-100` are distinguished, and the launch options
  follow: `PROTON_FORCE_NVAPI` for custom builds, `PROTON_ENABLE_NVAPI` for Valve's)
- API/bitness detection including the cases that break a naive classifier:
  Cyberpunk 2077 imports only `sl.interposer.dll` and no `d3d12.dll`; Hogwarts
  Legacy ships a 0.3 MB launcher stub next to its 429 MB renderer under
  `Phoenix/Binaries/Win64/`; ACC's renderer is under `AC2/Binaries/Win64/`
- DLSS NR model discovery with digest classification against the measured build
- **A1 and A2 install for real**, journalled, with rollback verified byte-for-byte
  in tests (including symlink fidelity and multi-level `mkdir` chains)
- Component fetching with exponential backoff, pinned sizes, and optional
  verification against the publisher's `SHA256SUMS`

Install safety properties that are tested rather than asserted:

| Property | Test |
| --- | --- |
| Nothing is written when a route is refused | `test_nothing_is_written_when_refused` |
| Rollback restores the directory exactly | `test_install_then_rollback_restores_the_directory` (A1 and A2) |
| A reinstall reuses its own proxy slot instead of installing a second proxy | `test_reinstall_reuses_the_recorded_proxy_name` |
| A model already in place is not copied and gets no journal entry | `test_model_already_beside_the_executable_is_not_copied` |
| The user's own `OptiScaler.ini` keys survive the merge | `test_existing_keys_are_updated_and_others_preserved` |
| A Vulkan game is refused, by name | `test_vulkan_game_is_refused` |
| A running Steam client blocks the launch-option write, and the file is untouched | `test_write_is_refused_while_steam_runs` |
| An escaped quote in a launch-option value round-trips | `test_quotes_and_backslashes_are_escaped` |
| The inserted key lands at the file's own indentation, not the appid line's | `test_inserted_key_uses_the_file_s_own_indentation` |
| A damaged config is refused *before* any backup is made | `test_a_damaged_file_is_refused_before_any_backup` |

**Guarded Steam launch-option writer** (`nvfku launch-options`). An experiment
([docs/experiment-localconfig.md](docs/experiment-localconfig.md)) measured what
Steam does to `localconfig.vdf`, and the writer's preconditions are those
measurements rather than defensive style:

| Measured | Turned into |
| --- | --- |
| Steam **merges**; it preserved unknown keys and their exact indentation | the file is edited by single-line surgery, never regenerated |
| An edit written while Steam is **closed** survives a full restart | writing is allowed in that state |
| An edit written while Steam is **running** is **reverted** | a running client makes the write refuse outright |
| The file also holds friends, avatars, cloud-sync state and packed fields | only one line is touched, and brace balance is re-checked afterwards |

It backs the file up first (verifying the backup's digest), writes atomically,
re-reads the key, and restores the backup if either check fails. It refuses to
guess which account to edit when a machine has several.

Not implemented yet:

- Round-tripping the launch-option change through **Steam Cloud**. Whether a
  cloud sync can revert it on a later launch is untested (see the experiment's
  limitations).

## The UI

`app/` is a Flutter desktop app. It has no third-party dependencies: the engine
is a subprocess the UI drives over JSON, so there is no FFI and nothing to keep
in step with a package release.

```
app/lib/
  main.dart              entry point
  src/design.dart        type scale, colours, motion constants
  src/models.dart        the engine's JSON contract as value types
  src/engine.dart        the subprocess boundary (scan/plan/install/rollback)
  src/l10n.dart          English and Chinese, one map each, side by side
  src/app.dart           the shell: sidebar, status bar, view switching
  src/games_view.dart    the library as poster cards, with a context menu
  src/game_sheet.dart    the modal sheet a card opens
  src/game_detail.dart   facts, routes, plan, install, undo
  src/home_view.dart     drop a folder, recent games, the activity log
  src/addons_view.dart   component versions and hashes
  src/history_view.dart  every journal, with exact rollback
  src/settings_view.dart persisted settings
  src/about_view.dart    what it is, and what it will not do
  src/launch_options.dart  the guarded Steam launch-option panel
  src/cover.dart         Steam cover art, with an initials placeholder
  src/widgets.dart       HoldButton, Disclosure, Notice, StatusPill, FieldRow
docs/ui-design.md        the design decisions, before the widgets
```

The design follows `docs/ui-design.md`, which applies Emil Kowalski's
`apple-design` skill (WWDC's *Designing Fluid Interfaces*, translated to a UI
toolkit). The parts that changed the code rather than decorating it:

- **Press feedback on pointer-down**, not on release — installing is slow, so a
  button that waits for the process reads as broken.
- **Continuous feedback during the operation** — the install streams step by step
  instead of reporting at the end.
- **One translucent layer at most** — Flutter has no `backdrop-filter`, and the
  skill warns that stacking translucent surfaces collapses legibility, so the
  status bar is tonal rather than fake glass.
- **Size-specific tracking and leading** — no single `letterSpacing` applied to
  all text.
- **Reduced motion gets a gentler equivalent, not nothing** — durations collapse
  via `MediaQuery.disableAnimations` while state still updates.
- **Momentum projection and rubber-banding are deliberately absent** — there is no
  flingable, bounded surface here, and adding one would be decoration.

The UI never says "DLSS 5 installed and working". It says which files were
written, which digest was verified, which build of the model was used, and what
remains manual.

## Licensing

This project's own code is released under the **WTFPL**. See [LICENSE](LICENSE).

**That covers this project's code and nothing else.** One of the files a release
archive carries is NVIDIA's, and several components are fetched from their own
releases under their own licences. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
lists them in full; the short version:

| | How it reaches you | Its licence |
|---|---|---|
| This project's engine and UI | in the source | WTFPL |
| `nvngx_dlssnr.dll` (the DLSS NR model) | **in a release archive**, digest-verified | NVIDIA's, proprietary |
| `dlss5-bridge` | fetched from its publisher at install time | MIT |
| `addon-dlssnr-linux`, `OptiScaler` | fetched from their publishers at install time | GPL-3.0 |
| ReShade 6.8.0 | fetched from reshade.me at install time | BSD 3-Clause |
| Flutter runtime | in a release archive | BSD 3-Clause |

**The model is the one thing this project redistributes without a licence to do so.**
It has no official download: the DLSS SDK ships headers and an import library only,
and the Linux driver carries no NR model at all. So a release archives it rather than
leaving every user to find 158 MiB by hand — with the digest recorded in
`RELEASE.json` and checked by `tools/package.py` before packaging. The full
reasoning, and the alternatives, are in [docs/weights.md](docs/weights.md).

The GPL-3.0 components are **separate programs**, fetched from their own release pages
and placed beside a game as data. Nothing here links against them, and no GPL source
is compiled into or imported by this project, so their copyleft does not extend to
this project's code. If that ever changes — if any of their source is incorporated
rather than invoked — this project's licence has to become GPL-3.0 too.

## Packaging

```bash
flutter build linux --release      # in app/, once
python3 tools/package.py           # all three formats into dist/
```

| Format | Size | Model inside? |
|---|---|---|
| `.tar.gz` | 9.5 MiB | no |
| `.deb` | 9.5 MiB | **never** |
| `.AppImage` | 9.6 MiB | no |

Three formats, and a `SHA256SUMS` beside them.

**None of them contains `nvngx_dlssnr.dll`.** It is 158 MiB, it is NVIDIA's, and
nothing licenses its redistribution — so a package carrying it would be 119 MiB and
not distributable. Every format fetches and verifies it on first use instead:

```bash
nvfku model --mirror-sync
```

The tool says so at the moment it matters (`RELEASE.json` records it, and the plan
offers the fetch as an action), rather than failing later with a missing-file error.

`--with-model` bundles it for a private build. It **refuses to combine with
`--format deb`**, because that is the one combination that causes real trouble: a
`.deb` carrying a proprietary NVIDIA binary is rejected by every Debian archive.

The `.deb` is assembled by `tools/package.py` directly — no `dpkg-deb`, which is not
installable on this machine. A `.deb` is an `ar` archive of `debian-binary`,
`control.tar.gz` and `data.tar.gz`, and all three are formats Python already writes.

### What is in each one

```
/usr/lib/nvfku/            payload (engine, app bundle, docs)
/usr/bin/nvfku-swapper     GUI
/usr/bin/nvfku             CLI
/usr/share/applications/   desktop entry
/usr/share/icons/          icon
/usr/share/doc/nvfku-swapper/
```

The AppImage puts the same payload under `usr/lib/nvfku` inside its AppDir, and the
tarball puts it at its root; all three use the same launcher, which resolves its own
directory so the tree can live anywhere.

The `.deb` carries a `model_source_url` and `model_source_note` in its
`RELEASE.json` too, so an unpacked archive still says where the model came from and
what that source is.
