/// Value types mirroring the engine's JSON contract.
///
/// These are deliberately thin. The engine is the single source of truth for
/// detection, viability and digests; the UI's job is to render what it says
/// without rounding it up. Where a field could be misread as a stronger claim
/// than it is (a model "verdict", a check's "severity"), the raw string is kept
/// rather than collapsed into a bool.
library;

import 'package:flutter/widgets.dart' show Locale;

import 'l10n.dart';

/// A check the engine ran, with the fix it recommends.
class EngineCheck {
  const EngineCheck({
    required this.name,
    required this.severity,
    required this.detail,
    this.fix,
  });

  final String name;

  /// `ok`, `warning` or `blocker`. Kept as a string so an unknown severity from
  /// a newer engine renders as-is instead of being silently treated as fine.
  final String severity;
  final String detail;
  final String? fix;

  bool get isOk => severity == 'ok';
  bool get isWarning => severity == 'warning';
  bool get isBlocker => severity == 'blocker';

  factory EngineCheck.fromJson(Map<String, dynamic> json) => EngineCheck(
        name: json['name'] as String? ?? '',
        severity: json['severity'] as String? ?? 'warning',
        detail: json['detail'] as String? ?? '',
        fix: json['fix'] as String?,
      );
}

/// One filesystem change the route would make.
class EngineAction {
  const EngineAction({
    required this.kind,
    required this.destination,
    this.source,
    this.reason = '',
    this.optional = false,
  });

  final String kind;
  final String destination;
  final String? source;
  final String reason;
  final bool optional;

  factory EngineAction.fromJson(Map<String, dynamic> json) => EngineAction(
        kind: json['kind'] as String? ?? 'note',
        destination: json['destination'] as String? ?? '',
        source: json['source'] as String?,
        reason: json['reason'] as String? ?? '',
        optional: json['optional'] as bool? ?? false,
      );
}

/// A file the route needs but may not redistribute.
class EngineMissing {
  const EngineMissing({
    required this.what,
    required this.why,
    required this.howToGet,
    this.blocking = true,
  });

  final String what;
  final String why;
  final String howToGet;
  final bool blocking;

  factory EngineMissing.fromJson(Map<String, dynamic> json) => EngineMissing(
        what: json['what'] as String? ?? '',
        why: json['why'] as String? ?? '',
        howToGet: json['how_to_get'] as String? ?? '',
        blocking: json['blocking'] as bool? ?? true,
      );
}

/// A dry-run plan for one route against one game.
class RoutePlan {
  const RoutePlan({
    required this.route,
    required this.title,
    required this.gameName,
    required this.gameDir,
    required this.summary,
    required this.viable,
    required this.readOnly,
    required this.checks,
    required this.actions,
    required this.missing,
    required this.manualSteps,
    this.detail = '',
    this.launchOptions,
    this.steamRunning = false,
    this.prerequisite,
  });

  final String route;
  final String title;
  final String gameName;
  final String gameDir;
  final String summary;
  final bool viable;
  final bool readOnly;
  final List<EngineCheck> checks;
  final List<EngineAction> actions;
  final List<EngineMissing> missing;
  final List<String> manualSteps;

  /// The mechanism, for the "how it works" disclosure. Kept out of [summary],
  /// which answers a different question: which of the two do I want.
  final String detail;

  /// True when a Steam client is up, which blocks writing the launch options.
  ///
  /// The engine reports it because the UI has to know *before* offering the
  /// install: Steam keeps this value in memory and writes its copy back, so a
  /// write made while it runs is silently reverted.
  final bool steamRunning;

  /// A component this route needs, planned as a step inside it.
  ///
  /// ReShade is the prerequisite of A1, not a route of its own: presenting it as a
  /// sibling made the list read as three options when there are two.
  final RoutePlan? prerequisite;
  final String? launchOptions;

  Iterable<EngineCheck> get blockers => checks.where((c) => c.isBlocker);
  Iterable<EngineCheck> get warnings => checks.where((c) => c.isWarning);

  factory RoutePlan.fromJson(Map<String, dynamic> json) => RoutePlan(
        route: json['route'] as String? ?? '',
        title: json['title'] as String? ?? '',
        gameName: json['game'] as String? ?? '',
        gameDir: json['game_dir'] as String? ?? '',
        summary: json['summary'] as String? ?? '',
        viable: json['viable'] as bool? ?? false,
        readOnly: json['read_only'] as bool? ?? false,
        checks: (json['checks'] as List<dynamic>? ?? [])
            .map((e) => EngineCheck.fromJson(e as Map<String, dynamic>))
            .toList(growable: false),
        actions: (json['actions'] as List<dynamic>? ?? [])
            .map((e) => EngineAction.fromJson(e as Map<String, dynamic>))
            .toList(growable: false),
        missing: (json['missing'] as List<dynamic>? ?? [])
            .map((e) => EngineMissing.fromJson(e as Map<String, dynamic>))
            .toList(growable: false),
        manualSteps:
            (json['manual_steps'] as List<dynamic>? ?? []).cast<String>(),
        detail: json['detail'] as String? ?? '',
        launchOptions: json['launch_options'] as String?,
        steamRunning: json['steam_running'] as bool? ?? false,
        prerequisite: json['prerequisite'] == null
            ? null
            : RoutePlan.fromJson(json['prerequisite'] as Map<String, dynamic>),
      );
}

/// The final component of a path: the file name.
///
/// Split out so [Game.hasReshade] can compare names without a regex. A character
/// class for the two separators was written wrong three times; this cannot be.
String fileBaseName(String path) => path.substring(parentDirLength(path) + 1);

/// Where [fileBaseName] starts, or -1 for a path with no separator.
int parentDirLength(String path) {
  final slash = path.lastIndexOf('/');
  final backslash = path.lastIndexOf('\\');
  return slash > backslash ? slash : backslash;
}

/// The directory part of a path, or null when there is no separator.
///
/// Dart's `substring(0, -1)` throws, so every "directory of this path" operation
/// has to tolerate a bare filename. Both separators are accepted because the
/// engine's own data is POSIX while anything Windows-derived may not be.
String? parentDir(String path) {
  final slash = path.lastIndexOf('/');
  final backslash = path.lastIndexOf('\\');
  final index = slash > backslash ? slash : backslash;
  if (index < 0) return null;
  return index == 0 ? '/' : path.substring(0, index);
}

class Game {
  const Game({
    required this.appid,
    required this.name,
    required this.installDir,
    this.protonPrefix,
    this.protonTool,
    this.launchExe,
    this.bitness,
    this.renderingApi,
    this.apiEvidence = const [],
    this.nativeDlss = const [],
    this.dlssnrModels = const [],
    this.reshadeFiles = const [],
    this.source = 'steam',
  });

  final String appid;
  final String name;
  final String installDir;
  final String? protonPrefix;
  final String? protonTool;
  final String? launchExe;
  final int? bitness;
  final String? renderingApi;
  final List<String> apiEvidence;
  final List<String> nativeDlss;
  final List<String> dlssnrModels;
  final List<String> reshadeFiles;

  /// ``steam`` for a Steam appid, ``folder`` for a hand-added directory.
  final String source;

  /// True when the game ships any DLSS runtime of its own.
  ///
  /// Derived rather than sent: the engine reports the files it found, and "has
  /// DLSS" is the question every caller actually asks.
  bool get hasNativeDlss => nativeDlss.isNotEmpty;

  /// True when the DLSS Neural Rendering model is present.
  ///
  /// The model is what this whole tool drives, so its absence is the single most
  /// useful thing a card can say about a game.
  bool get hasNrModel => dlssnrModels.isNotEmpty;

  /// True when ReShade's proxy is installed *and* configured beside the executable.
  ///
  /// Both halves are required, and in one directory. A `ReShade.ini` alone is
  /// residue from another tool's install, and a `dxgi.dll` alone is a proxy with no
  /// preset — reporting either as installed would tell the user to skip a step they
  /// still owe. The check is on the file names because that is all the engine
  /// reports; whether they are ReShade's own is decided by the install, not here.
  bool get hasReshade {
    for (final file in reshadeFiles) {
      final dir = parentDir(file);
      final name = fileBaseName(file).toLowerCase();
      if (name != 'dxgi.dll') continue;
      // A dll is one half. Look for its ini in the same directory, not merely
      // somewhere in the list.
      for (final other in reshadeFiles) {
        if (parentDir(other) != dir) continue;
        if (fileBaseName(other).toLowerCase() == 'reshade.ini') return true;
      }
    }
    return false;
  }

  /// ``steam`` for a Steam appid, ``folder`` for a hand-added directory.
  bool get isSteam => source == 'steam';

  /// The launcher's file name, or the game's name when there is no launcher.
  ///
  /// A bare name rather than the full path: this is shown in a facts table beside
  /// other short values, and a 90-character path there wraps and pushes everything
  /// below it out of view. The fallback matters too — a hand-added folder need not
  /// declare an executable, and an empty cell reads as a bug.
  String get exeName {
    final exe = launchExe;
    if (exe == null || exe.isEmpty) return name;
    final cut = [exe.lastIndexOf('/'), exe.lastIndexOf('\\')]
        .reduce((a, b) => a > b ? a : b);
    return cut == -1 ? exe : exe.substring(cut + 1);
  }

  /// How to describe the DLSS NR model for a reader of [locale].
  ///
  /// Takes the locale rather than reading the app's language notifier, because
  /// this is called from `build` where the ambient `Localizations` is the
  /// authority — and the two can differ for one frame while a language change is
  /// being applied.
  String nrModelLabel(Locale locale) {
    if (dlssnrModels.isEmpty) return translate(locale, 'games.nrNone');
    return translate(locale, 'games.nrPresent', {'n': dlssnrModels.length});
  }

  factory Game.fromJson(Map<String, dynamic> json) => Game(
        appid: json['appid'] as String? ?? '',
        name: json['name'] as String? ?? '',
        installDir: json['install_dir'] as String? ?? '',
        protonPrefix: json['proton_prefix'] as String?,
        protonTool: json['proton_tool'] as String?,
        launchExe: json['launch_exe'] as String?,
        bitness: json['bitness'] as int?,
        renderingApi: json['rendering_api'] as String?,
        apiEvidence: (json['api_evidence'] as List<dynamic>? ?? []).cast<String>(),
        nativeDlss: (json['native_dlss'] as List<dynamic>? ?? []).cast<String>(),
        dlssnrModels: (json['nvngx_dlssnr'] as List<dynamic>? ?? []).cast<String>(),
        reshadeFiles: (json['reshade_files'] as List<dynamic>? ?? []).cast<String>(),
        source: json['source'] as String? ?? 'steam',
      );
}

/// The outcome of an install, including what is still manual.
class InstallResult {
  const InstallResult({
    required this.route,
    required this.game,
    required this.gameDir,
    this.journalId,
    this.notes = const [],
    this.warnings = const [],
    this.verified = const [],
    this.manualSteps = const [],
    this.launchOptions,
    this.refusal,
  });

  final String route;
  final String game;
  final String gameDir;
  final String? journalId;
  final List<String> notes;
  final List<String> warnings;
  final List<String> verified;
  final List<String> manualSteps;

  final String? launchOptions;

  /// Set when the engine refused rather than failing: a blocked plan, a missing
  /// file, a digest mismatch. `ok` in the document is false in that case.
  final String? refusal;

  factory InstallResult.fromJson(Map<String, dynamic> json) => InstallResult(
        route: json['route'] as String? ?? '',
        game: json['game'] as String? ?? '',
        gameDir: json['game_dir'] as String? ?? '',
        journalId: json['journal_id'] as String?,
        notes: (json['notes'] as List<dynamic>? ?? []).cast<String>(),
        warnings: (json['warnings'] as List<dynamic>? ?? []).cast<String>(),
        verified: (json['verified'] as List<dynamic>? ?? []).cast<String>(),
        manualSteps:
            (json['manual_steps'] as List<dynamic>? ?? []).cast<String>(),
        launchOptions: json['launch_options'] as String?,
        refusal: json['refused'] as String?,
      );
}

/// One line of live progress from a running install.
class InstallEvent {
  const InstallEvent({required this.phase, required this.message, this.result});

  /// `start`, `log`, `done` or `failed`.
  final String phase;
  final String message;

  /// Present on a successful terminal event, already parsed, so no caller has to
  /// scrape JSON out of [message].
  final InstallResult? result;

  bool get isTerminal => phase == 'done' || phase == 'failed';
}

/// A component the engine knows how to fetch, for the Providers view.
class ProviderRow {
  const ProviderRow({
    required this.key,
    required this.version,
    required this.pinned,
    this.size,
    this.sha256,
    this.url,
    this.error,
  });

  final String key;
  final String version;
  final bool pinned;
  final int? size;
  final String? sha256;
  final String? url;
  final String? error;

  factory ProviderRow.fromJson(Map<String, dynamic> json) => ProviderRow(
        key: json['key'] as String? ?? '',
        version: json['version'] as String? ?? '?',
        pinned: json['pinned'] as bool? ?? false,
        size: json['size'] as int?,
        sha256: json['sha256'] as String?,
        url: json['url'] as String?,
        error: json['error'] as String?,
      );
}

/// A journal entry, used by the rollback list.
class JournalEntry {
  const JournalEntry({
    required this.id,
    required this.route,
    required this.gameDir,
    required this.operations,
    required this.finished,
    required this.rolledBack,
    this.createdAt,
  });

  final String id;
  final String route;
  final String gameDir;
  final int operations;
  final bool finished;
  final bool rolledBack;

  /// When the journal was started, in unix seconds. Absent for a journal written
  /// before this field existed, which is why the log renders a placeholder rather
  /// than assuming zero.
  final double? createdAt;

  factory JournalEntry.fromJson(Map<String, dynamic> json) => JournalEntry(
        id: json['id'] as String? ?? '',
        route: json['route'] as String? ?? '',
        gameDir: json['game_dir'] as String? ?? '',
        operations: json['operations'] as int? ?? 0,
        finished: json['finished'] as bool? ?? false,
        rolledBack: json['rolled_back'] as bool? ?? false,
        createdAt: (json['created_at'] as num?)?.toDouble(),
      );
}


/// A game's Steam launch options as the engine sees them.
class LaunchOptionsState {
  const LaunchOptionsState({
    required this.appid,
    required this.game,
    required this.config,
    required this.steamRunning,
    this.launchOptions,
  });

  final String appid;
  final String game;
  final String config;

  /// True when a Steam client is up. Writing is refused in that state, because
  /// the experiment in docs/experiment-localconfig.md showed Steam keeps this key
  /// in memory and writes its copy back over an external edit.
  final bool steamRunning;
  final String? launchOptions;

  bool get hasValue => launchOptions != null && launchOptions!.isNotEmpty;
  bool get canWrite => !steamRunning;

  factory LaunchOptionsState.fromJson(Map<String, dynamic> json) => LaunchOptionsState(
        appid: json['appid'] as String? ?? '',
        game: json['game'] as String? ?? '',
        config: json['config'] as String? ?? '',
        steamRunning: json['steam_running'] as bool? ?? false,
        launchOptions: json['launch_options'] as String?,
      );
}

/// The outcome of a guarded launch-option write.
class LaunchOptionsWrite {
  const LaunchOptionsWrite({
    required this.value,
    required this.config,
    required this.backup,
    required this.createdKey,
    required this.verified,
    this.previous,
    this.notes = const [],
  });

  final String value;
  final String config;
  final String backup;
  final bool createdKey;
  final bool verified;
  final String? previous;
  final List<String> notes;

  factory LaunchOptionsWrite.fromJson(Map<String, dynamic> json) => LaunchOptionsWrite(
        value: json['value'] as String? ?? '',
        config: json['config'] as String? ?? '',
        backup: json['backup'] as String? ?? '',
        createdKey: json['created_key'] as bool? ?? false,
        verified: json['verified'] as bool? ?? false,
        previous: json['previous'] as String?,
        notes: (json['notes'] as List<dynamic>? ?? []).cast<String>(),
      );
}
