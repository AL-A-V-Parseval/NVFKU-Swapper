# nvfku_ui

The Flutter front end for **NVFKU-Swapper**. The project's README is at
[`../README.md`](../README.md); this file only covers building this directory.

## Building

```bash
export PUB_CACHE=../.pub-cache          # keeps packages out of $HOME
flutter build linux --release
```

The bundle lands in `build/linux/x64/release/bundle/`. Run it with
`NVFKU_ENGINE` pointing at the checkout root, or it will look for `engine/nvfku`
by walking up from its own executable:

```bash
NVFKU_ENGINE=$(cd .. && pwd) ./build/linux/x64/release/bundle/nvfku_ui
```

## Tests

```bash
flutter test                            # 59 tests
flutter analyze                         # must stay at 0 errors
```

`NVFKU_ENGINE` is read by `test/engine_language_test.dart`; without it, that file
skips rather than fails, so the engine contract is checked where a checkout is
available and not assumed where it is not.

## Layout

| Path | What |
|---|---|
| `lib/src/app.dart` | the shell: sidebar, status bar, view switching |
| `lib/src/design.dart` | type scale, colours, motion. Every value is deliberate |
| `lib/src/engine.dart` | the whole boundary to Python — subprocesses and JSON |
| `lib/src/models.dart` | the engine's documents as Dart types |
| `lib/src/l10n.dart` | English and Chinese, side by side, one map each |
| `lib/src/*_view.dart` | one file per page |
| `tool/screenshot.dart` | a second entrypoint that drives the UI and captures it |

## Two things that will bite you

**The screenshot harness is a separate `main`.** `flutter build linux -t
tool/screenshot.dart` writes the *same* bundle path as a normal build, so copy the
bundle out before rebuilding the app, or the next `nvfku_ui` will be the harness.

**Impeller encodes the last rasterised layer.** `RenderRepaintBoundary.toImage`
therefore needs the boundary's `GlobalKey` recreated before each capture, and a
capture taken on the frame a `setState` lands on still shows the previous content.
Both are why the harness waits on a signal *and* settles afterwards.
