/// Application shell: sidebar navigation plus one content area.
///
/// The navigation set follows DLSS5-Swapper's shape — a persistent sidebar with
/// **Games / Add-ons / History / Settings** — because that is the interaction
/// model a user of that tool already knows. What changed is the presentation,
/// per the apple-design skill:
///
/// * The sidebar is a **tonal** surface, not translucent glass. Flutter desktop
///   has no `backdrop-filter`, and the skill is explicit that stacking
///   translucent layers collapses legibility (§12), so hierarchy is built from
///   material steps instead.
/// * The selected item is marked by a filled capsule **and** a weight change, so
///   it reads correctly without relying on colour alone.
/// * View changes are a short cross-fade along one path (§7 spatial consistency)
///   rather than a directional slide that would imply travel the user did not
///   make.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'about_view.dart';
import 'addons_view.dart';
import 'design.dart';
import 'engine.dart';
import 'game_sheet.dart';
import 'games_view.dart';
import 'home_view.dart';
import 'l10n.dart';
import 'history_view.dart';
import 'models.dart';
import 'settings_view.dart';
import 'widgets.dart';

enum AppView { home, games, addons, history, settings, about }

class Dlss5CtlApp extends StatelessWidget {
  const Dlss5CtlApp({super.key, this.engine});

  /// Injectable so tests and the screenshot harness can drive the UI.
  final Engine? engine;

  @override
  Widget build(BuildContext context) {
    // Rebuilds when the language changes, so the picker takes effect without a
    // restart.
    return ValueListenableBuilder<AppLanguage>(
      valueListenable: appLanguage,
      builder: (context, preference, _) {
        final platform = WidgetsBinding.instance.platformDispatcher.locale;
        return MaterialApp(
          onGenerateTitle: (context) => context.t('app.windowTitle'),
          debugShowCheckedModeBanner: false,
          theme: buildTheme(Brightness.light),
          darkTheme: buildTheme(Brightness.dark),
          themeMode: ThemeMode.system,
          locale: effectiveLocale(preference, platform),
          supportedLocales: const [Locale('en'), Locale('zh')],
          // The global delegates, not the defaults: the defaults carry English
          // only, so a zh locale left Material widgets without localisations.
          localizationsDelegates: const [
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          home: Shell(engine: engine ?? Engine()),
        );
      },
    );
  }

  /// The palette seen in the tool this project reworks, expressed as a Material
  /// scheme.
  ///
  /// Built by hand rather than from `ColorScheme.fromSeed`, because seeding
  /// derives surfaces from the accent and the whole point here is that the accent
  /// is the *only* saturated colour while every surface is a near-black step. A
  /// seeded scheme tints the neutrals toward the seed and loses exactly that.
  static ThemeData buildTheme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    // The reference's two-step neutral ramp, plus the lime accent.
    final scheme = dark
        ? const ColorScheme.dark(
            primary: AppColors.accentGreen,
            onPrimary: Color(0xFF0B1400),
            primaryContainer: Color(0xFF2A4A05),
            onPrimaryContainer: Color(0xFFD6F0A8),
            secondary: Color(0xFF8FA3B8),
            onSecondary: Color(0xFF0B1016),
            surface: Color(0xFF0A0A0B),
            onSurface: Color(0xFFF0F4F9),
            onSurfaceVariant: Color(0xFF9AA7B6),
            // One step up from the page, then another. Visible, not subtle.
            surfaceContainerLowest: Color(0xFF0E0E10),
            surfaceContainerLow: Color(0xFF12171F),
            surfaceContainer: Color(0xFF121214),
            surfaceContainerHigh: Color(0xFF1A1A1D),
            surfaceContainerHighest: Color(0xFF242428),
            outline: Color(0xFF3A4552),
            outlineVariant: Color(0xFF26262A),
            error: Color(0xFFEF7B7B),
            onError: Color(0xFF2A0A0A),
          )
        : const ColorScheme.light(
            primary: AppColors.accentGreenDeep,
            onPrimary: Colors.white,
            primaryContainer: Color(0xFFDDF3BC),
            onPrimaryContainer: Color(0xFF1B2E00),
            secondary: Color(0xFF5A6A7A),
            surface: Color(0xFFEEF1F4),
            onSurface: Color(0xFF1B2229),
            onSurfaceVariant: Color(0xFF6B7885),
            surfaceContainerLowest: Color(0xFFF7F9FA),
            surfaceContainerLow: Color(0xFFFFFFFF),
            surfaceContainer: Color(0xFFF1F5F8),
            surfaceContainerHigh: Color(0xFFE3E8EC),
            surfaceContainerHighest: Color(0xFFD8DEE4),
            outline: Color(0xFFB4C0CC),
            outlineVariant: Color(0xFFD3DAE1),
            error: Color(0xFFB3261E),
          );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: scheme.surface,
      dividerTheme: DividerThemeData(
        color: dark
            ? Colors.white.withValues(alpha: 0.055)
            : Colors.black.withValues(alpha: 0.08),
        thickness: 1,
        space: 1,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: scheme.surfaceContainerLow,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpace.radiusLarge),
          side: BorderSide(
            color: dark
                ? Colors.white.withValues(alpha: 0.075)
                : Colors.black.withValues(alpha: 0.10),
          ),
        ),
      ),
      // Hierarchy is weight + size + leading as a set, not size alone.
      textTheme: TextTheme(
        headlineMedium: AppText.display,
        titleLarge: AppText.title,
        titleMedium: AppText.subtitle,
        bodyMedium: AppText.body,
        bodySmall: AppText.caption,
        labelLarge: AppText.label,
      ),
      inputDecorationTheme: InputDecorationTheme(
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpace.md,
          vertical: AppSpace.sm,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpace.radius),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpace.radius),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      sliderTheme: SliderThemeData(
        trackHeight: 3,
        thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 7),
      ),
    );
  }
}

class Shell extends StatefulWidget {
  const Shell({
    super.key,
    required this.engine,
    this.initialView = AppView.home,
    this.initialGame,
    this.initialGames,
    this.initialForInstall = false,
    this.onGameReady,
  });

  final Engine engine;

  /// Where to open. Used by the screenshot harness so captures include the real
  /// chrome; the app itself always starts on Games.
  final AppView initialView;
  final Game? initialGame;

  /// Pre-supplied library, so a capture does not wait for a scan it will not
  /// show.
  final List<Game>? initialGames;

  /// Opens the initial game at its install panel rather than the top.
  final bool initialForInstall;


  /// Called when the detail view has finished loading a game's plans. A
  /// deterministic signal for a driver: polling for "enough pixels" cannot
  /// distinguish the detail page from the list, and will happily capture the
  /// wrong view.
  final VoidCallback? onGameReady;


  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  late AppView _view = widget.initialView;
  late Game? _open = widget.initialGame;
  late List<Game>? _games = widget.initialGames;

  /// True when the sheet was opened from a card's install button, so it lands on
  /// the install panel instead of the top of the page.
  late bool _openForInstall = widget.initialForInstall;

  /// Set when a component (rather than a route) asked to be installed. A
  /// prerequisite has its own command, so it cannot go through the route installer.
  String? _component;

  /// Responds to the inputs changing, so a driver (the screenshot harness) can
  /// steer the shell. Without this, `initialView` behaved like a state
  /// initialiser only: the harness changed its own state and the mounted shell
  /// ignored it, which produced five byte-identical screenshots.
  @override
  void didUpdateWidget(Shell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialView != widget.initialView) {
      setState(() => _view = widget.initialView);
    }
    if (!identical(oldWidget.initialGame, widget.initialGame)) {
      setState(() => _open = widget.initialGame);
    }
    if (!identical(oldWidget.initialGames, widget.initialGames) &&
        widget.initialGames != null) {
      setState(() => _games = widget.initialGames);
    }
  }
  String _filter = '';
  String? _statusOverride;
  String _statusKey = 'status.starting';
  Map<String, Object?> _statusValues = const {};
  bool _busy = true;
  bool _failed = false;
  String? _version;
  Map<String, String?> _artwork = const {};

  @override
  void initState() {
    super.initState();
    _scan();
  }

  Future<void> _scan() async {
    setState(() {
      _busy = true;
      _failed = false;
      _statusKey = 'status.scanning';
      _statusValues = const {};
      _statusOverride = null;
    });
    try {
      // The version costs a whole Python start-up, so it is asked once.
      _version ??= await widget.engine.version();
      final games = await widget.engine.scan();
      if (!mounted) return;
      final withDlss = games.where((g) => g.hasNativeDlss).length;
      final withModel = games.where((g) => g.hasNrModel).length;
      setState(() {
        _games = games;
        _busy = false;
        _statusKey = withModel > 0 ? 'status.summaryModel' : 'status.summary';
        _statusValues = {
          'version': _version,
          'games': games.length,
          'dlss': withDlss,
          'model': withModel,
        };
      });

      // Covers are a separate, cheap query of what the engine already cached.
      // It never touches the network, so a slow connection cannot hold up the
      // library, and a failure only costs the thumbnails.
      unawaited(_loadArtwork());
    } on EngineException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _failed = true;
        _statusOverride = e.message;
      });
    }
  }

  String get _status => _statusOverride ?? context.t(_statusKey, _statusValues);

  Future<void> _loadArtwork() async {
    try {
      final artwork = await widget.engine.cachedArtwork();
      if (!mounted) return;
      setState(() => _artwork = artwork);
    } on EngineException {
      // Thumbnails are decoration; the library is still usable without them.
    }
  }

  /// Registers a folder by hand, then rescans so it appears.
  Future<void> _addFolder() async {
    final path = await promptForGameFolder(context);
    if (path == null || path.trim().isEmpty) return;
    try {
      await widget.engine.addGameFolder(path.trim());
    } on EngineException catch (error) {
      if (mounted) {
        ScaffoldMessenger.maybeOf(context)?.showSnackBar(
          SnackBar(content: Text(error.message)),
        );
      }
      return;
    }
    await _scan();
  }

  /// Hands a game's directory to the desktop's file manager.
  ///
  /// `xdg-open` is the portable entry point on Linux and is what a desktop
  /// integration is expected to use; a failure is reported rather than swallowed,
  /// because "nothing happened" is the worst possible outcome of a click.
  Future<void> _openFolder(Game game) async {
    try {
      final result = await Process.run('xdg-open', [game.installDir]);
      if (result.exitCode != 0 && mounted) {
        final detail = (result.stderr as String).trim();
        ScaffoldMessenger.maybeOf(context)?.showSnackBar(
          SnackBar(
            content: Text(detail.isEmpty ? game.installDir : detail),
          ),
        );
      }
    } on ProcessException catch (error) {
      if (mounted) {
        ScaffoldMessenger.maybeOf(context)?.showSnackBar(
          SnackBar(content: Text(error.message)),
        );
      }
    }
  }

  void _go(AppView view) {
    setState(() {
      _view = view;
      _open = null;
      _openForInstall = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final games = _games;

    final open = _open;
    return Scaffold(
      body: Stack(
        children: [
          Row(
        children: [
          _Sidebar(current: _view, onSelect: _go, disabled: _failed),
          Expanded(
            child: Column(
              children: [
                Expanded(
                  child: _failed
                      ? _EngineFailure(message: _status, onRetry: _scan)
                      : games == null
                          ? const Center(child: CircularProgressIndicator())
                          : AnimatedSwitcher(
                              duration: AppMotion.resolve(context, AppMotion.fast),
                              switchInCurve: AppMotion.enter,
                              switchOutCurve: AppMotion.exit,
                              child: _content(games),
                            ),
                ),
                _StatusBar(
                  message: _statusOverride ?? context.t(_statusKey, _statusValues),
                  busy: _busy,
                  failed: _failed,
                  trailing: _open?.name,
                ),
              ],
            ),
          ),
        ],
      ),
          // The sheet floats over the library rather than replacing it, so the
          // scroll position and filters survive. Esc or the backdrop closes it.
          if (open != null)
            GameSheet(
              key: ValueKey('sheet-${open.appid}'),
              game: open,
              coverPath: _artwork[open.appid],
              engine: widget.engine,
              startAtInstall: _openForInstall,
              component: _component,
              onOpenInstall: (route) => setState(() => _component = route),
              onComponentDone: () => setState(() => _component = null),
              onClose: () => setState(() {
                _open = null;
                _openForInstall = false;
                _component = null;
              }),
              onChanged: _scan,
              onLoaded: widget.onGameReady,
            ),
        ],
      ),
    );
  }

  Widget _content(List<Game> games) {
    switch (_view) {
      case AppView.home:
        return HomeView(
          key: const ValueKey('home'),
          engine: widget.engine,
          games: games,
          artwork: _artwork,
          onOpen: (game) => setState(() {
            _open = game;
            _openForInstall = false;
          }),
          onAddFolder: _addFolder,
          onRescan: _scan,
        );
      case AppView.games:
        return GamesView(
          key: const ValueKey('games'),
          games: games,
          filter: _filter,
          onFilter: (value) => setState(() => _filter = value),
          onOpen: (game, {bool install = false}) => setState(() {
            _open = game;
            _openForInstall = install;
          }),
          onOpenFolder: _openFolder,
          onRescan: _scan,
          engine: widget.engine,
          busy: _busy,
          artwork: _artwork,
        );
      case AppView.addons:
        return AddonsView(key: const ValueKey('addons'), engine: widget.engine);
      case AppView.history:
        return HistoryView(
          key: const ValueKey('history'),
          engine: widget.engine,
          onChanged: _scan,
        );
      case AppView.about:
        return AboutView(key: const ValueKey('about'), version: _version);
      case AppView.settings:
        return SettingsView(
          key: const ValueKey('settings'),
          engine: widget.engine,
          onChanged: _scan,
        );
    }
  }
}

class _Sidebar extends StatelessWidget {
  const _Sidebar({
    required this.current,
    required this.onSelect,
    required this.disabled,
  });

  final AppView current;
  final ValueChanged<AppView> onSelect;
  final bool disabled;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    return Container(
      width: AppSpace.sidebarWidth,
      margin: const EdgeInsets.all(AppSpace.md),
      decoration: BoxDecoration(
        color: AppColors.chrome(context),
        borderRadius: BorderRadius.circular(AppSpace.radiusShell),
        border: Border.all(color: AppColors.stroke(context)),
        // Two shadows: a tight one that seats the panel and a wide soft one that
        // lifts it. A single mid-sized shadow vanishes against a near-black page.
        boxShadow: dark
            ? const [
                BoxShadow(color: Color(0x8C000000), blurRadius: 5, offset: Offset(0, 2)),
                BoxShadow(color: Color(0x99000000), blurRadius: 60, offset: Offset(0, 26)),
              ]
            : const [
                BoxShadow(color: Color(0x1A14202D), blurRadius: 40, offset: Offset(0, 18)),
              ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpace.lg,
              AppSpace.xl,
              AppSpace.lg,
              AppSpace.md,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(context.t('app.title'), style: AppText.title),
                const SizedBox(height: 2),
                Text(
                  context.t('app.subtitle'),
                  style: AppText.caption.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
          _NavItem(
            icon: Icons.home_outlined,
            label: context.t('nav.home'),
            selected: current == AppView.home,
            onTap: disabled ? null : () => onSelect(AppView.home),
          ),
          _NavItem(
            icon: Icons.videogame_asset_outlined,
            label: context.t('nav.games'),
            selected: current == AppView.games,
            onTap: disabled ? null : () => onSelect(AppView.games),
          ),
          _NavItem(
            icon: Icons.extension_outlined,
            label: context.t('nav.addons'),
            selected: current == AppView.addons,
            onTap: disabled ? null : () => onSelect(AppView.addons),
          ),
          _NavItem(
            icon: Icons.history,
            label: context.t('nav.history'),
            selected: current == AppView.history,
            onTap: disabled ? null : () => onSelect(AppView.history),
          ),
          _NavItem(
            icon: Icons.tune,
            label: context.t('nav.settings'),
            selected: current == AppView.settings,
            onTap: disabled ? null : () => onSelect(AppView.settings),
          ),
          _NavItem(
            icon: Icons.info_outline,
            label: context.t('nav.about'),
            selected: current == AppView.about,
            onTap: disabled ? null : () => onSelect(AppView.about),
          ),
          const Spacer(),

        ],
      ),
    );
  }
}

/// A navigation item. The selected state is a filled capsule *and* a weight
/// change, never colour alone.
class _NavItem extends StatefulWidget {
  const _NavItem({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback? onTap;

  @override
  State<_NavItem> createState() => _NavItemState();
}

class _NavItemState extends State<_NavItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final enabled = widget.onTap != null;
    final selected = widget.selected;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpace.sm, vertical: 1),
      child: MouseRegion(
        cursor: enabled ? SystemMouseCursors.click : SystemMouseCursors.basic,
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() => _hover = false),
        child: GestureDetector(
          onTap: widget.onTap,
          behavior: HitTestBehavior.opaque,
          child: AnimatedContainer(
            duration: AppMotion.resolve(context, AppMotion.fast),
            curve: AppMotion.settle,
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpace.md,
              vertical: AppSpace.sm + 1,
            ),
            decoration: BoxDecoration(
              color: selected
                  ? theme.colorScheme.primary.withValues(alpha: 0.14)
                  : _hover
                      ? theme.colorScheme.onSurface.withValues(alpha: 0.05)
                      : Colors.transparent,
              borderRadius: BorderRadius.circular(AppSpace.radius),
            ),
            child: Row(
              children: [
                Icon(
                  widget.icon,
                  size: 17,
                  color: !enabled
                      ? theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4)
                      : selected
                          ? theme.colorScheme.primary
                          : theme.colorScheme.onSurfaceVariant,
                ),
                const SizedBox(width: AppSpace.md),
                Text(
                  widget.label,
                  style: AppText.label.copyWith(
                    color: !enabled
                        ? theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4)
                        : selected
                            ? theme.colorScheme.primary
                            : theme.colorScheme.onSurface,
                    fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _EngineFailure extends StatelessWidget {
  const _EngineFailure({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.terminal, size: 36, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(height: AppSpace.lg),
            Text(context.t('engine.failedTitle'), style: AppText.title),
            const SizedBox(height: AppSpace.sm),
            SelectableText(
              message,
              style: AppText.mono.copyWith(color: theme.colorScheme.onSurfaceVariant),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpace.lg),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh, size: 17),
              label: Text(context.t('common.tryAgain')),
            ),
          ],
        ),
      ),
    );
  }
}

/// The status bar: a tonal strip, not floating glass (§12).
class _StatusBar extends StatelessWidget {
  const _StatusBar({
    required this.message,
    required this.busy,
    required this.failed,
    this.trailing,
  });

  final String message;
  final bool busy;
  final bool failed;
  final String? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tone = failed ? AppColors.danger(context) : theme.colorScheme.onSurfaceVariant;

    return Container(
      decoration: BoxDecoration(
        color: AppColors.chrome(context),
        border: Border(
          top: BorderSide(
            color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
          ),
        ),
      ),
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpace.lg,
        vertical: AppSpace.sm + 1,
      ),
      child: Row(
        children: [
          if (busy)
            const Padding(
              padding: EdgeInsets.only(right: AppSpace.sm),
              child: SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          Expanded(
            child: Text(
              message,
              style: AppText.caption.copyWith(color: tone),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (trailing != null)
            Text(
              trailing!,
              style: AppText.caption.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
        ],
      ),
    );
  }
}
