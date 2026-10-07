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

import 'package:flutter/foundation.dart';

import 'install_task.dart';
import 'l10n.dart';
import 'models.dart';

/// Thrown when the engine exits non-zero. Carries stderr, which the engine uses
/// for refusals and blockers, so the UI can show the real reason.
/// A settings document and whether the file behind it exists yet.
class SettingsDocument {
  const SettingsDocument({required this.settings, required this.stored});

  final Map<String, dynamic> settings;

  /// False when no settings file has been written: every field is then a default,
  /// and a caller applying preferences should leave existing values alone.
  final bool stored;
}

class EngineException implements Exception {
  EngineException(this.message, {this.exitCode = -1});

  final String message;
  final int exitCode;

  @override
  String toString() => message;
}

/// Locates and runs `python -m nvfku`.
class Engine implements EngineLike {
  Engine({String? projectRoot, String? pythonOverride, String? stateDir})
    : projectRoot = projectRoot ?? _defaultProjectRoot(),
      _pythonOverride = pythonOverride,
      _stateDir = stateDir;

  /// The checkout root, i.e. the directory containing `engine/`.
  final String projectRoot;
  final String? _pythonOverride;

  /// An alternate state directory, passed through as `--state-dir`.
  ///
  /// The engine already had this flag; the UI had no way to reach it, which meant
  /// anything with its own state — a test, or a second profile — would have written
  /// to the real `~/.local/share/nvfku`. Threading it here is what lets a test assert
  /// on persistence without touching the user's settings.
  final String? _stateDir;

  String? _resolvedPython;
  final Map<(String, String), InstallTask> _installations = {};
  final ValueNotifier<int> _revision = ValueNotifier(0);

  /// Changes after an install succeeds or a rollback may have changed state.
  ValueListenable<int> get revision => _revision;

  InstallTask installationFor(String gameKey, String route) =>
      _installations.putIfAbsent((gameKey, route), () {
        final task = InstallTask();
        var seen = task.completion;
        task.addListener(() {
          if (task.completion == seen) return;
          seen = task.completion;
          if (task.result != null && task.result!.refusal == null) {
            _revision.value++;
          }
        });
        return task;
      });

  void startInstallation({
    required String gameKey,
    required String route,
    int? workingScale,
  }) {
    if (_installations.entries.any(
      (entry) => entry.key.$1 == gameKey && entry.value.running,
    )) {
      throw EngineException(
        'An installation for this game is already running.',
      );
    }
    installationFor(gameKey, route).start(
      () => install(gameKey: gameKey, route: route, workingScale: workingScale),
    );
  }

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

  /// Only process startup failures are translated here; programming errors are
  /// not hidden behind a generic catch.
  Future<ProcessResult> _run(List<String> arguments) async {
    try {
      return await Process.run(
        python,
        arguments,
        workingDirectory: projectRoot,
        environment: _environment,
      );
    } on ProcessException catch (error) {
      throw EngineException(
        'Cannot start engine: ${error.message}',
        exitCode: error.errorCode,
      );
    }
  }

  /// Decode at the engine seam, so malformed field types cannot escape into UI
  /// state machines. Catch only contract errors from this decoding closure.
  Future<T> _decode<T>(
    List<String> arguments,
    T Function(dynamic) decode,
  ) async {
    final data = await _json(arguments);
    try {
      return decode(data);
    } on TypeError catch (error) {
      throw EngineException(
        'Invalid engine document (${arguments.first}): $error',
      );
    } on FormatException catch (error) {
      throw EngineException(
        'Invalid engine document (${arguments.first}): $error',
      );
    }
  }

  /// Runs a command to completion and decodes its JSON stdout.
  Future<dynamic> _json(List<String> arguments) async {
    final result = await _run([
      '-m',
      'nvfku',
      '--json',
      if (_stateDir != null) ...['--state-dir', _stateDir],
      ...arguments,
    ]);
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
    final result = await _run(['-m', 'nvfku', '--version']);
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

  Future<List<Game>> scan() => _decode(
    ['--language', textLanguage, 'scan'],
    (data) => (data as List<dynamic>)
        .map((e) => Game.fromJson(e as Map<String, dynamic>))
        .toList(growable: false),
  );

  Future<List<RoutePlan>> plan(String gameKey, {String? route}) async {
    final args = <String>['--language', textLanguage, 'plan', gameKey];
    if (route != null) args.add(route);
    return _decode(
      args,
      (data) => (data as List<dynamic>)
          .map((e) => RoutePlan.fromJson(e as Map<String, dynamic>))
          .toList(growable: false),
    );
  }

  Future<List<ProviderRow>> providers({bool resolve = true}) async {
    return _decode(
      resolve ? ['providers', '--resolve'] : ['providers'],
      (data) => (data as List<dynamic>)
          .map((e) => ProviderRow.fromJson(e as Map<String, dynamic>))
          .toList(growable: false),
    );
  }

  Future<List<JournalEntry>> backups({String? gameKey}) async {
    return _decode(
      gameKey == null ? ['backups'] : ['backups', gameKey],
      (data) => (data as List<dynamic>)
          .map((e) => JournalEntry.fromJson(e as Map<String, dynamic>))
          .toList(growable: false),
    );
  }

  /// Registers a game folder Steam does not manage.
  Future<void> addGameFolder(String folder) async {
    await _decode(['games', folder], (data) {
      final document = data as Map<String, dynamic>;
      if (document['ok'] != true) {
        throw EngineException(_refusalFrom(document, 'the folder was refused'));
      }
    });
  }

  /// Reverts one journal. Returns the engine's own report of what it put back.
  Future<String> rollback(String journalId) async {
    String? failure;
    try {
      final data = await _json(['rollback', journalId]);
      if (data is! Map<String, dynamic>) {
        throw EngineException('the engine returned an invalid rollback report');
      }
      if (data['ok'] != true) {
        final failures = data['failed'];
        throw EngineException(
          failures is List && failures.isNotEmpty
              ? failures.join('\n')
              : _refusalFrom(data, 'the journal could not be reverted'),
        );
      }
      final report = data['report'];
      if (report is! List || report.any((line) => line is! String)) {
        throw EngineException('the engine returned an invalid rollback report');
      }
      return report.join('\n');
    } on ProcessException catch (error) {
      failure = error.message;
      throw EngineException(error.message, exitCode: error.errorCode);
    } catch (error) {
      failure = error.toString();
      rethrow;
    } finally {
      // Even a refusal or an unreadable report cannot prove the files stayed
      // unchanged. Invalidate only this journal's receipt and re-read state;
      // never present a failed/partial restore as a successful installation.
      for (final task in _installations.values) {
        task.clearRolledBackResult(journalId, error: failure);
      }
      _revision.value++;
    }
  }

  /// The artwork already on disk, keyed by appid. Never fetches.
  ///
  /// `--cached-only` on purpose: the shell calls this while drawing the library,
  /// and a download per missing cover would make the grid's first paint depend on
  /// the network. A missing entry is a game that gets the initials placeholder.
  Future<Map<String, String?>> cachedArtwork() async {
    return _decode(['artwork', '--cached-only'], (data) {
      final document = data as Map<String, dynamic>;
      final artwork = document['artwork'] as Map<String, dynamic>;
      return {
        for (final entry in artwork.entries)
          entry.key:
              entry.value is String && (entry.value as String).isNotEmpty
                  ? entry.value as String
                  : null,
      };
    });
  }

  /// Reads a game's current Steam launch options.
  Future<LaunchOptionsState> launchOptions(String gameKey) async {
    return _decode([
      'launch-options',
      gameKey,
    ], (data) => LaunchOptionsState.fromJson(data as Map<String, dynamic>));
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
    return _decode(args, (data) {
      final document = data as Map<String, dynamic>;
      if (document['ok'] == false) {
        throw EngineException(
          _refusalFrom(document, 'the launch options were refused'),
        );
      }
      return LaunchOptionsWrite.fromJson(document);
    });
  }

  /// The persisted settings document.
  ///
  /// Every field has a working default, so this cannot say whether a value was
  /// chosen or merely defaulted. Use [readSettingsDocument] when that matters.
  Future<Map<String, dynamic>> readSettings() async =>
      (await readSettingsDocument()).settings;

  /// The settings document, plus whether anything was actually stored.
  ///
  /// `stored` is false until the file exists. It is the only way to tell an
  /// explicitly-chosen `system` from a profile that has never been written, and a
  /// preference loader that cannot tell them apart overwrites a deliberate choice
  /// on first run — which is exactly what a test caught here.
  @override
  Future<SettingsDocument> readSettingsDocument() async {
    return _decode(['settings'], (document) {
      final data = document as Map<String, dynamic>;
      final settings = data['settings'] as Map<String, dynamic>;
      _validateSettings(settings);
      return SettingsDocument(
        settings: settings,
        stored: data['stored'] as bool? ?? false,
      );
    });
  }

  static void _validateSettings(Map<String, dynamic> settings) {
    for (final field in [
      'python_path',
      'steam_root',
      'download_cache',
      'proxy_mode',
      'theme',
      'language',
    ]) {
      if (settings[field] != null && settings[field] is! String) {
        throw FormatException('settings.$field must be a string');
      }
    }
    if (settings['verify_upstream'] != null &&
        settings['verify_upstream'] is! bool) {
      throw const FormatException('settings.verify_upstream must be a boolean');
    }
  }

  /// Saves settings. Only the provided fields change; null leaves one alone.
  Future<Map<String, dynamic>> writeSettings({
    String? pythonPath,
    String? steamRoot,
    String? downloadCache,
    String? proxyMode,
    bool? verifyUpstream,
    String? routePreference,
    String? theme,
    String? language,
  }) async {
    final args = <String>['settings'];
    if (pythonPath != null) args.addAll(['--python', pythonPath]);
    if (steamRoot != null) args.addAll(['--steam-root', steamRoot]);
    if (downloadCache != null) args.addAll(['--download-cache', downloadCache]);
    if (proxyMode != null) args.addAll(['--proxy', proxyMode]);
    if (verifyUpstream != null) {
      args.addAll(['--verify-upstream', verifyUpstream ? 'yes' : 'no']);
    }
    if (routePreference != null) {
      args.addAll(['--route-preference', routePreference]);
    }
    if (theme != null) args.addAll(['--theme', theme]);
    if (language != null) args.addAll(['--language', language]);
    return _decode(args, (data) {
      final document = data as Map<String, dynamic>;
      if (document['ok'] == false) {
        throw EngineException(
          _refusalFrom(document, 'the settings were refused'),
        );
      }
      final settings = document['settings'] as Map<String, dynamic>;
      _validateSettings(settings);
      return settings;
    });
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
      '-m',
      'nvfku',
      '--json',
      '--language',
      textLanguage,
      if (_stateDir != null) ...['--state-dir', _stateDir],
      'install',
      gameKey,
      route,
      if (yes) '--yes',
      if (skipDownload) '--skip-download',
      if (!verifyUpstream) '--no-upstream-verify',
      if (workingScale != null) ...['--working-scale', '$workingScale'],
    ];

    late StreamController<InstallEvent> controller;
    final stdoutBuffer = StringBuffer();

    void emit(InstallEvent event) {
      if (!controller.isClosed) controller.add(event);
    }

    Future<void> close() async {
      if (!controller.isClosed) await controller.close();
    }

    controller = StreamController<InstallEvent>(
      onListen: () async {
        emit(const InstallEvent(phase: 'start', message: ''));
        late final Process process;
        try {
          process = await Process.start(
            python,
            args,
            workingDirectory: projectRoot,
            environment: _environment,
          );
        } on ProcessException catch (error) {
          emit(InstallEvent(phase: 'failed', message: error.message));
          await close();
          return;
        }

        final decoder = const Utf8Decoder(allowMalformed: true);
        final stderrDone = process.stderr
            .transform(decoder)
            .transform(const LineSplitter())
            .listen((line) {
              final text = line.trim();
              if (text.isEmpty) return;
              // Progress narration. It is deliberately *not* an error channel: the
              // engine prints step lines here even on a successful install.
              emit(InstallEvent(phase: 'log', message: text));
            });

        final stdoutDone = process.stdout
            .transform(decoder)
            .transform(const LineSplitter())
            .listen(stdoutBuffer.writeln);

        await Future.wait([
          stderrDone.asFuture<void>(),
          stdoutDone.asFuture<void>(),
        ]);
        final exitCode = await process.exitCode;
        final raw = stdoutBuffer.toString().trim();

        if (raw.isEmpty) {
          emit(
            InstallEvent(
              phase: 'failed',
              message: 'the engine produced no document (exit $exitCode)',
            ),
          );
          await close();
          return;
        }

        dynamic document;
        try {
          document = jsonDecode(raw);
        } on FormatException {
          emit(
            InstallEvent(
              phase: 'failed',
              message: 'the engine produced output that is not JSON',
            ),
          );
          await close();
          return;
        }

        if (document is! Map<String, dynamic> || document['ok'] != true) {
          // A refusal carries a sentence the user can act on; a bare exit code does
          // not. `--yes` is passed, so the only refusals left are real ones:
          // blockers, a running Steam, a digest mismatch.
          emit(
            InstallEvent(
              phase: 'failed',
              message: _refusalFrom(
                document,
                'the install was refused (exit $exitCode)',
              ),
            ),
          );
          await close();
          return;
        }

        try {
          final result = InstallResult.fromJson(
            document['result'] as Map<String, dynamic>,
          );
          emit(InstallEvent(phase: 'done', message: '', result: result));
        } on TypeError catch (error) {
          emit(
            InstallEvent(
              phase: 'failed',
              message:
                  EngineException(
                    'Invalid engine install result: $error',
                  ).message,
            ),
          );
        } finally {
          await close();
        }
      },
      // Installation is owned by Engine.installationFor, not by the sheet.
      // The UI never cancels this stream on navigation: an explicit cancel
      // operation would need to wait for Python's journal compensation first.
    );
    return controller.stream;
  }
}
