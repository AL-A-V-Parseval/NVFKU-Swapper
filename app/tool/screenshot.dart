/// Screenshot harness: renders the real shell against the real engine and writes
/// PNGs.
///
/// This exists because the machine's compositor does not expose screen capture to
/// `xdg-desktop-portal`, so an external screenshot of a running window is not
/// obtainable. Rendering the widget tree to an image sidesteps the compositor
/// entirely, and unlike a screenshot it needs no window to be visible or focused.
///
/// Three things this harness learned the hard way, each now a rule:
///
/// 1. **Render the real Shell, not the views.** An earlier version mounted the
///    views directly and its captures had no sidebar, so they could not be used to
///    review layout.
/// 2. **Disable animations.** `toImage` encodes whatever the boundary currently
///    holds, including a cross-fade caught mid-flight, which produced washed-out
///    captures of the whole UI.
/// 3. **Wait for content, do not guess a delay.** A `plan` call shells out to
///    Python and can take seconds; a fixed wait captured loading spinners.
///
/// Output goes to `$NVFKU_SHOT_DIR` (default `/tmp/nvfku-shots`).
library;

import 'dart:async';
import 'dart:io';
import 'package:flutter/scheduler.dart';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter/rendering.dart';

import 'package:nvfku_ui/src/app.dart';
import 'package:nvfku_ui/src/engine.dart';
import 'package:nvfku_ui/src/l10n.dart';
import 'package:nvfku_ui/src/models.dart';

/// Recreated before every capture.
///
/// A single long-lived key was the bug: `RenderRepaintBoundary.toImage` encodes
/// the layer the boundary last rasterized, and reusing the boundary while the
/// shell switched views internally left the captures one view behind — the file
/// named `01-games` contained the Add-ons page. A new key remounts the boundary,
/// so the image is always taken from a fresh paint.
GlobalKey _shotKey = GlobalKey();

/// Swaps in a fresh boundary key.
void _resetBoundary() => _shotKey = GlobalKey();

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Chinese, so the captures show the localisation rather than the fallback.
  // The harness has no settings file to read, and the point of the capture is
  // to review the translated layout.
  appLanguage.value = AppLanguage.chinese;
  runApp(const _HarnessApp());
}

class _HarnessApp extends StatelessWidget {
  const _HarnessApp();

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'nvfku screenshot harness',
      debugShowCheckedModeBanner: false,
      theme: Dlss5CtlApp.buildTheme(Brightness.light),
      darkTheme: Dlss5CtlApp.buildTheme(Brightness.dark),
      themeMode: ThemeMode.dark,
      // The harness does not go through Dlss5CtlApp, so it must set the locale
      // itself. Without this the captures stayed English while the app was
      // pinned to Chinese, which is how the omission was noticed.
      locale: effectiveLocale(appLanguage.value, null),
      supportedLocales: const [Locale('en'), Locale('zh')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      // Animations off so every capture lands on a settled frame.
      home: const MediaQuery(
        data: MediaQueryData(disableAnimations: true),
        child: _Harness(),
      ),
    );
  }
}

class _Harness extends StatefulWidget {
  const _Harness();

  @override
  State<_Harness> createState() => _HarnessState();
}

class _HarnessState extends State<_Harness> {
  final Engine _engine = Engine();
  List<Game>? _games;
  Game? _open;
  AppView _view = AppView.games;

  /// Whether the sheet should open at its install panel. Mutable, because only
  /// one of the captures wants that.
  bool _openForInstall = false;

  /// Grows the capture viewport so a shot reaches below the fold.
  bool _tall = false;

  /// Completed by whichever view is loading. Replaced before each capture.
  Completer<void>? _ready;

  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    final outDir = Directory(
      Platform.environment['NVFKU_SHOT_DIR'] ?? '/tmp/nvfku-shots',
    );
    outDir.createSync(recursive: true);
    final log = File('${outDir.path}/harness.log').openWrite();

    void say(String message) {
      log.writeln(message);
      stdout.writeln(message);
    }

    try {
      say('engine: ${_engine.python}');
      say('version: ${await _engine.version()}');
      final games = await _engine.scan();
      say('games: ${games.length}');
      setState(() => _games = games);
      await _settle(const Duration(seconds: 3));
      await _shoot(outDir, '01-games', say);

      // A game with its own DLSS exercises the most interesting route set.
      final pick = games.firstWhere(
        (g) => g.hasNativeDlss && (g.renderingApi ?? '').startsWith('DirectX'),
        orElse: () => games.first,
      );
      say('opening: ${pick.name} (${pick.appid}) · ${pick.renderingApi}');

      // Warm the engine's plan cache *before* opening the sheet, not after.
      //
      // A cold plan spawns a Python process that hashes a 158 MiB DLL and reads
      // seven more, so the first capture of this view landed on a loading spinner
      // in every run — four separate attempts at fixing it by waiting longer all
      // failed, because the wait was on a signal that could not arrive in time. The
      // wait was never the problem; the order was.
      say('warming the plan cache for ${pick.appid}…');
      await _engine.plan(pick.appid);
      say('cache warm');

      // The completer is seeded before the state change: the sheet starts loading
      // during the rebuild, so assigning it afterwards races the load and the wait
      // times out on a signal that already fired.
      _ready = Completer<void>();
      setState(() => _open = pick);
      await _waitForContent(outDir, '02-game-detail', say);
      await _shoot(outDir, '02-game-detail', say);

      // The install panel, in the sheet, for a game with a different route set.
      // Re-opening the same game cannot emit a second load signal — its plans are
      // already in hand — so this picks another one.
      final second = games.firstWhere(
        (g) => g.appid != pick.appid && g.hasNrModel,
        orElse: () => games.firstWhere((g) => g.appid != pick.appid,
            orElse: () => pick),
      );
      say('install panel: ${second.name} (${second.appid})');
      setState(() => _open = null);
      await _settle(const Duration(seconds: 1));
      _ready = Completer<void>();
      setState(() {
        _open = second;
        _openForInstall = true;
      });
      await _waitForContent(outDir, '06-install-panel', say);
      // The Steam gate and the confirm button sit below the facts and the route
      // list, so the capture has to be scrolled to them.
      await _settle(const Duration(seconds: 2));
      await _scrollTo(700);
      await _shoot(outDir, '06-install-panel', say);
      setState(() => _open = null);

      setState(() {
        _open = null;
        _view = AppView.addons;
      });
      await _settle(const Duration(seconds: 5));
      await _shoot(outDir, '03-addons', say);

      setState(() => _view = AppView.history);
      await _settle(const Duration(seconds: 4));
      await _shoot(outDir, '04-history', say);

      setState(() => _view = AppView.settings);
      await _settle(const Duration(seconds: 4));
      await _shoot(outDir, '05-settings', say);

      setState(() => _view = AppView.about);
      await _settle(const Duration(seconds: 2));
      await _shoot(outDir, '07-about', say);

      // Home loads its own journal list, so give it time to answer.
      setState(() => _view = AppView.home);
      await _settle(const Duration(seconds: 4));
      await _shoot(outDir, '08-home', say);

      say('done');
    } catch (error, stack) {
      say('FAILED: $error');
      say('$stack');
    } finally {
      await log.flush();
      await log.close();
      await Future<void>.delayed(const Duration(milliseconds: 300));
      exit(0);
    }
  }

  /// Tallens the viewport so a capture reaches content below the fold.
  ///
  /// The sheet scrolls internally and owns its controller, so the harness cannot
  /// drive it. Growing the frame is the honest alternative: `toImage` encodes the
  /// whole boundary, so a taller boundary holds more of the panel.
  Future<void> _scrollTo(double offset) async {
    setState(() => _tall = true);
    await _settle(const Duration(seconds: 2));
  }

  /// Waits for the engine calls the current view makes.
  Future<void> _settle([Duration extra = const Duration(seconds: 3)]) async {
    for (var i = 0; i < 12; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 150));
    }
    await Future<void>.delayed(extra);
  }

  void _signalReady() {
    final completer = _ready;
    if (completer != null && !completer.isCompleted) completer.complete();
  }

  /// Waits for the current view to report that it has finished loading.
  ///
  /// The encoded size was tried first and abandoned three times over: a loading
  /// spinner is already ~100 KB, and both the games grid and the settings page are
  /// large too, so "big enough" cannot distinguish them. A signal the view emits
  /// can.
  Future<void> _waitForContent(
    Directory dir,
    String name,
    void Function(String) say, {
    int attempts = 200,
  }) async {
    final completer = _ready;
    if (completer == null) {
      await _settle(const Duration(seconds: 3));
      return;
    }
    try {
      await completer.future.timeout(Duration(milliseconds: 500 * attempts));
    } on TimeoutException {
      say('timed out waiting for $name to load');
    }
    // The signal means the data arrived, not that it has been painted. The frame
    // in which `setState` lands still holds the spinner and the headings; the
    // content lays out on the frames after it. Capturing on that first frame is
    // why this came out as a spinner five times while the log cheerfully reported
    // the view as ready — the wait was never wrong, the assumption after it was.
    await _settle(const Duration(milliseconds: 1500));
  }

  Future<Uint8List?> _encode() async {
    final boundary =
        _shotKey.currentContext?.findRenderObject() as RenderRepaintBoundary?;
    if (boundary == null) return null;
    final image = await boundary.toImage(pixelRatio: 1.0);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    return bytes?.buffer.asUint8List();
  }

  Future<void> _shoot(
    Directory dir,
    String name,
    void Function(String) say,
  ) async {
    // Remount the boundary, let the frame finish, then encode.
    setState(_resetBoundary);
    await SchedulerBinding.instance.endOfFrame;
    await _settle(const Duration(milliseconds: 400));
    final data = await _encode();
    if (data == null) {
      say('encode failed for $name');
      return;
    }
    final file = File('${dir.path}/$name.png');
    file.writeAsBytesSync(data);
    say('wrote ${file.path} (${file.lengthSync()} bytes)');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: RepaintBoundary(
        key: _shotKey,
        child: SizedBox(
          width: 1440,
          height: _tall ? 1500 : 900,
          // The real shell, so captures include the sidebar and the status bar.
          child: Shell(
            engine: _engine,
            initialView: _view,
            initialGame: _open,
            initialGames: _games,
            initialForInstall: _openForInstall,
            onGameReady: _signalReady,
          ),
        ),
      ),
    );
  }
}
