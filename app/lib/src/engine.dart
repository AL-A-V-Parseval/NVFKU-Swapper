/// The engine boundary: a Python process, driven over JSON.
///
/// There is no FFI and no code generation. The engine is a subprocess, so the
/// UI can be replaced without touching detection logic, and the CLI and the GUI
/// run the *same* code — a plan the UI shows is the plan the CLI would print.
///
/// `install` streams rather than returning, because §1 of the design spec
/// requires feedback to be continuous *during* the operation, not delivered at
/// the end.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'l10n.dart';
import 'models.dart';

/// Thrown when the engine exits non-zero. Carries stderr, which the engine uses
/// for refusals and blockers, so the UI can show the real reason.
class EngineException implements Exception {
  EngineException(this.message, {this.exitCode = -1});

  final String message;
  final int exitCode;

  @override
  String toString() => message;
}

/// Locates and runs `python -m nvfku`.
class Engine {
  Engine({String? projectRoot, String? pythonOverride})
      : projectRoot = projectRoot ?? _defaultProjectRoot(),
        _pythonOverride = pythonOverride;

  /// The checkout root, i.e. the directory containing `engine/`.
  final String projectRoot;
  final String? _pythonOverride;

  String? _resolvedPython;

  /// Walks up from the executable looking for `engine/nvfku`. A build run
  /// from the project directory finds the checkout; an installed build relies
  /// on `NVFKU_ENGINE`.
  ///
  /// The walk goes to the filesystem root rather than stopping at a fixed depth.
  /// A depth was tried first and was wrong: `app/build/linux/x64/release/bundle` is
  /// **seven** levels below the checkout root, so a limit of six examined the bundle
  /// and five of its ancestors, never reached the root, and fell back to
  /// `Directory.current` — which then looked for the engine beside the executable.
  /// The symptom was `/usr/bin/python3: No module named nvfku` in a window that had
  /// otherwise started perfectly. There is no depth that is obviously right, and the
  /// check is one `stat` per level, so it simply keeps going.
  static String _defaultProjectRoot() {
    final fromEnv = Platform.environment['NVFKU_ENGINE'];
    if (fromEnv != null && fromEnv.isNotEmpty) return fromEnv;
    var dir = File(Platform.resolvedExecutable).parent;
    while (true) {
      if (Directory('${dir.path}/engine/nvfku').existsSync()) {
        return dir.path;
      }
      final parent = dir.parent;
      if (parent.path == dir.path) break;
      dir = parent;
    }
    return Directory.current.path;
  }

  /// The project venv if it exists, else the system interpreter.
  ///
  /// The venv is preferred because `tools/env.sh` creates it and the engine is
  /// developed against it; a system Python is a working fallback since the
  /// engine is standard-library only.
  String get python {
    final cached = _resolvedPython;
    if (cached != null) return cached;
    final override = _pythonOverride;
    if (override != null && override.isNotEmpty) {
      return _resolvedPython = override;
    }
    final venv = File('$projectRoot/.venv/bin/python');
    if (venv.existsSync()) {
      // Canonicalised on purpose: an unresolved path containing ".." makes
      // CPython warn "Unexpected value in sys.prefix" on every interpreter
      // start, which would pollute the engine's stderr -- the stream the UI
      // shows as progress narration.
      return _resolvedPython = venv.resolveSymbolicLinksSync();
    }
    return _resolvedPython = 'python3';
  }

  Map<String, String> get _environment => {
        ...Platform.environment,
        'PYTHONPATH': '$projectRoot/engine',
        'PYTHONDONTWRITEBYTECODE': '1',
      };

  /// The language the engine should produce user-facing text in.
  ///
  /// Read from the same notifier the shell uses, so a route plan and the UI
  /// around it cannot be in different languages. This is only ever *text*: file
  /// names, digests and identifiers are identical in both.
  static String get textLanguage =>
      appLanguage.value == AppLanguage.chinese ? 'zh' : 'en';

  /// Runs a command to completion and decodes its JSON stdout.
  Future<dynamic> _json(List<String> arguments) async {
    final result = await Process.run(
      python,
      ['-m', 'nvfku', '--json', ...arguments],
      workingDirectory: projectRoot,
      environment: _environment,
    );
    final stdoutText = (result.stdout as String).trim();
    final stderrText = (result.stderr as String).trim();

    // A non-zero exit code is *information*, not failure, whenever stdout holds a
    // document. `plan` deliberately exits 2 when any route is blocked — it still
    // prints all of them — and the UI needs those plans to render anything at all.
    // Treating the code as fatal here made the detail view show an error instead
    // of the routes, and made the harness fail on a perfectly good answer.
    if (stdoutText.isNotEmpty) {
      try {
        return jsonDecode(stdoutText);
      } on FormatException {
        // Not a document after all: fall through to the failure path.
      }
    }

    throw EngineException(
      stderrText.isNotEmpty
          ? stderrText
          : 'the engine produced no document (exit ${result.exitCode})',
      exitCode: result.exitCode,
    );
  }

  /// A human-readable failure from an engine document that reports one.
  ///
  /// The engine answers `{"ok": false, ...}` for several refusals, and the useful
  /// sentence is in `refused` or `error` — not in the exit code. `_json` returns
  /// the document in those cases, so each caller needs to look inside it.
  static String _refusalFrom(dynamic document, String fallback) {
    if (document is Map<String, dynamic>) {
      final refused = document['refused'];
      if (refused is String && refused.isNotEmpty) return refused;
      final error = document['error'];
      if (error is String && error.isNotEmpty) return error;
      final blockers = document['blockers'];
      if (blockers is List && blockers.isNotEmpty) {
        final first = blockers.first;
        if (first is Map<String, dynamic>) {
          final name = first['name'];
          final detail = first['detail'];
          if (name is String && detail is String) return '$name: $detail';
        }
      }
    }
    return fallback;
  }

  /// The engine's own version string, e.g. `nvfku 0.1.0`.
  ///
  /// `--version` is handled by the argument parser before any subcommand runs, so
  /// it prints a bare line rather than a JSON document and cannot go through
  /// `_json`.
  Future<String> version() async {
    final result = await Process.run(
      python,
      ['-m', 'nvfku', '--version'],
      workingDirectory: projectRoot,
      environment: _environment,
    );
    final text = (result.stdout as String).trim();
    if (text.isEmpty) {
      throw EngineException(
        (result.stderr as String).trim().isEmpty
            ? 'the engine reported no version'
            : (result.stderr as String).trim(),
        exitCode: result.exitCode,
      );
    }
    return text;
  }

  Future<List<Game>> scan() async {
    final data = await _json(['--language', textLanguage, 'scan']);
    return (data as List<dynamic>)
        .map((e) => Game.fromJson(e as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<RoutePlan>> plan(String gameKey, {String? route}) async {
    final args = <String>['--language', textLanguage, 'plan', gameKey];
    if (route != null) args.add(route);
    final data = await _json(args);
    return (data as List<dynamic>)
        .map((e) => RoutePlan.fromJson(e as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<ProviderRow>> providers({bool resolve = true}) async {
    final data = await _json(resolve ? ['providers', '--resolve'] : ['providers']);
    return (data as List<dynamic>)
        .map((e) => ProviderRow.fromJson(e as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<JournalEntry>> backups({String? gameKey}) async {
    final data = await _json(gameKey == null ? ['backups'] : ['backups', gameKey]);
    return (data as List<dynamic>)
        .map((e) => JournalEntry.fromJson(e as Map<String, dynamic>))
        .toList(growable: false);
  }

  /// Registers a game folder Steam does not manage.
  Future<void> addGameFolder(String folder) async {
    final data = await _json(['games', folder]);
    final document = data as Map<String, dynamic>;
    if (document['ok'] != true) {
      throw EngineException(document['error'] as String? ?? 'the folder was refused');
    }
  }

  /// Reverts one journal. Returns the engine's own report of what it put back.
  Future<String> rollback(String journalId) async {
    final data = await _json(['rollback', journalId]);
    if (data is Map<String, dynamic> && data['ok'] == false) {
      throw EngineException(
        _refusalFrom(data, 'the journal could not be reverted'),
      );
    }
    if (data is Map<String, dynamic>) {
      final report = data['report'] ?? data['message'];
      if (report is String && report.isNotEmpty) return report;
      final restored = data['restored'];
      if (restored is int) return 'restored $restored file(s)';
    }
    return 'reverted $journalId';
  }

  /// The artwork already on disk, keyed by appid. Never fetches.
  ///
  /// `--cached-only` on purpose: the shell calls this while drawing the library,
  /// and a download per missing cover would make the grid's first paint depend on
  /// the network. A missing entry is a game that gets the initials placeholder.
  Future<Map<String, String?>> cachedArtwork() async {
    final data = await _json(['artwork', '--cached-only']);
    final document = data as Map<String, dynamic>;
    final artwork = document['artwork'] as Map<String, dynamic>? ?? const {};
    return {
      for (final entry in artwork.entries)
        entry.key: entry.value is String && (entry.value as String).isNotEmpty
            ? entry.value as String
            : null,
    };
  }

  /// Reads a game's current Steam launch options.
  Future<LaunchOptionsState> launchOptions(String gameKey) async {
    final data = await _json(['launch-options', gameKey]);
    return LaunchOptionsState.fromJson(data as Map<String, dynamic>);
  }

  /// Writes or clears a game's launch options. Steam must not be running.
  Future<LaunchOptionsWrite> setLaunchOptions(
    String gameKey, {
    String? route,
    String? value,
    bool clear = false,
  }) async {
    final args = <String>['launch-options', gameKey];
    if (clear) {
      args.add('--clear');
    } else if (value != null && value.isNotEmpty) {
      // The value is passed explicitly rather than by `--route`: the route's own
      // plan is what the user approved on screen, and re-deriving it here could
      // write something different from what they read.
      args.addAll(['--value', value]);
    } else if (route != null) {
      args.addAll(['--route', route]);
    }
    final data = await _json(args);
    final document = data as Map<String, dynamic>;
    if (document['ok'] == false) {
      throw EngineException(_refusalFrom(document, 'the launch options were refused'));
    }
    return LaunchOptionsWrite.fromJson(document);
  }

  /// The persisted settings document.
  Future<Map<String, dynamic>> readSettings() async {
    final data = await _json(['settings']);
    return (data as Map<String, dynamic>)['settings'] as Map<String, dynamic>? ?? {};
  }

  /// Saves settings. Only the provided fields change; null leaves one alone.
  Future<Map<String, dynamic>> writeSettings({
    String? pythonPath,
    String? steamRoot,
    String? downloadCache,
    String? proxyMode,
    bool? verifyUpstream,
    String? routePreference,
  }) async {
    final args = <String>['settings'];
    if (pythonPath != null) args.addAll(['--python', pythonPath]);
    if (steamRoot != null) args.addAll(['--steam-root', steamRoot]);
    if (downloadCache != null) args.addAll(['--download-cache', downloadCache]);
    if (proxyMode != null) args.addAll(['--proxy', proxyMode]);
    if (verifyUpstream != null) {
      args.addAll(['--verify-upstream', verifyUpstream ? 'yes' : 'no']);
    }
    if (routePreference != null) args.addAll(['--route-preference', routePreference]);
    final data = await _json(args);
    final document = data as Map<String, dynamic>;
    if (document['ok'] == false) {
      throw EngineException(_refusalFrom(document, 'the settings were refused'));
    }
    return document['settings'] as Map<String, dynamic>? ?? {};
  }

  /// Applies a route, reporting progress as it goes.
  ///
  /// The engine writes its progress to **stderr** and its one JSON document to
  /// stdout, so the two streams are read separately: stderr becomes `log` events
  /// while the install runs, and stdout becomes the single terminal event. Reading
  /// stdout line-by-line would have produced nothing until the process exited,
  /// which is the opposite of the continuous feedback this is here for.
  Stream<InstallEvent> install({
    required String gameKey,
    required String route,
    int? workingScale,
    bool yes = true,
    bool skipDownload = false,
    bool verifyUpstream = true,
  }) {
    final args = <String>[
      '-m', 'nvfku',
      '--json',
      '--language', textLanguage,
      'install', gameKey, route,
      if (yes) '--yes',
      if (skipDownload) '--skip-download',
      if (!verifyUpstream) '--no-upstream-verify',
      if (workingScale != null) ...['--working-scale', '$workingScale'],
    ];

    late StreamController<InstallEvent> controller;
    Process? process;
    final stdoutBuffer = StringBuffer();

    Future<void> close() async {
      if (!controller.isClosed) await controller.close();
    }

    controller = StreamController<InstallEvent>(
      onListen: () async {
        controller.add(const InstallEvent(phase: 'start', message: ''));
        try {
          process = await Process.start(
            python,
            args,
            workingDirectory: projectRoot,
            environment: _environment,
          );
        } on ProcessException catch (error) {
          controller.add(InstallEvent(phase: 'failed', message: error.message));
          await close();
          return;
        }

        final decoder = const Utf8Decoder(allowMalformed: true);
        final stderrDone = process!.stderr
            .transform(decoder)
            .transform(const LineSplitter())
            .listen((line) {
          final text = line.trim();
          if (text.isEmpty) return;
          // Progress narration. It is deliberately *not* an error channel: the
          // engine prints step lines here even on a successful install.
          controller.add(InstallEvent(phase: 'log', message: text));
        });

        final stdoutDone = process!.stdout
            .transform(decoder)
            .transform(const LineSplitter())
            .listen(stdoutBuffer.writeln);

        await Future.wait([stderrDone.asFuture<void>(), stdoutDone.asFuture<void>()]);
        final exitCode = await process!.exitCode;
        final raw = stdoutBuffer.toString().trim();

        if (raw.isEmpty) {
          controller.add(InstallEvent(
            phase: 'failed',
            message: 'the engine produced no document (exit $exitCode)',
          ));
          await close();
          return;
        }

        dynamic document;
        try {
          document = jsonDecode(raw);
        } on FormatException {
          controller.add(InstallEvent(
            phase: 'failed',
            message: 'the engine produced output that is not JSON',
          ));
          await close();
          return;
        }

        if (document is! Map<String, dynamic> || document['ok'] != true) {
          // A refusal carries a sentence the user can act on; a bare exit code does
          // not. `--yes` is passed, so the only refusals left are real ones:
          // blockers, a running Steam, a digest mismatch.
          controller.add(InstallEvent(
            phase: 'failed',
            message: _refusalFrom(
              document,
              'the install was refused (exit $exitCode)',
            ),
          ));
          await close();
          return;
        }

        final result = document['result'];
        controller.add(InstallEvent(
          phase: 'done',
          message: '',
          result: result is Map<String, dynamic>
              ? InstallResult.fromJson(result)
              : null,
        ));
        await close();
      },
      onCancel: () async {
        // The child would otherwise outlive the sheet that started it and keep
        // writing into a game directory nobody is watching.
        process?.kill(ProcessSignal.sigterm);
        process = null;
      },
    );
    return controller.stream;
  }
}
