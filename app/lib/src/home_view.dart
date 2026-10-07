/// Home: what you can do, what you last did, and what the tool has been doing.
///
/// Three blocks, in that order, because that is the order the questions get asked:
///
/// 1. **Drop a folder** — adding a game is the one thing a first-time user needs,
///    and it should not require finding the Games page first. Drag a folder onto
///    the window, or browse for one.
/// 2. **Recent** — the games this tool has touched, newest first. Recognition beats
///    search when you came back to continue something.
/// 3. **Activity** — the journal as a log, because every entry here is a reversible
///    operation and seeing them listed is what makes the History page believable.
///
/// The reference calls these "Recent Games" and "Activity Log" and puts them on its
/// own Home. The structure is the same; the data here is the journal, so an entry
/// is a real recorded operation rather than a message.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'cover.dart';
import 'design.dart';
import 'engine.dart';
import 'l10n.dart';
import 'models.dart';
import 'widgets.dart';

/// `just now` / `3 min ago` / `2 h ago` / `4 d ago`.
///
/// The reference's own wording, and the reason to have it: a timestamp makes you
/// do arithmetic, and the only question here is "how long ago was that".
String relativeTime(BuildContext context, double? seconds) {
  if (seconds == null) return '—';
  final at = DateTime.fromMillisecondsSinceEpoch((seconds * 1000).round());
  final delta = DateTime.now().difference(at);
  if (delta.inMinutes < 1) return context.t('home.justNow');
  if (delta.inMinutes < 60) {
    return context.t('home.minAgo', {'n': delta.inMinutes});
  }
  if (delta.inHours < 24) {
    return context.t('home.hourAgo', {'n': delta.inHours});
  }
  return context.t('home.dayAgo', {'n': delta.inDays});
}

class HomeView extends StatefulWidget {
  const HomeView({
    super.key,
    required this.engine,
    required this.games,
    required this.artwork,
    required this.onOpen,
    required this.onAddFolder,
    required this.onRescan,
  });

  final Engine engine;
  final List<Game> games;
  final Map<String, String?> artwork;
  final void Function(Game game) onOpen;

  /// Opens the folder picker, owned by the games view so both entry points share
  /// one implementation.
  final Future<void> Function() onAddFolder;
  final Future<void> Function() onRescan;

  @override
  State<HomeView> createState() => _HomeViewState();
}

class _HomeViewState extends State<HomeView> {
  List<JournalEntry>? _journals;
  String? _error;
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    widget.engine.revision.addListener(_stateChanged);
    _load();
  }

  void _stateChanged() => unawaited(_load());

  @override
  void didUpdateWidget(HomeView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.engine, widget.engine)) {
      oldWidget.engine.revision.removeListener(_stateChanged);
      widget.engine.revision.addListener(_stateChanged);
      unawaited(_load());
    }
  }

  @override
  void dispose() {
    widget.engine.revision.removeListener(_stateChanged);
    super.dispose();
  }

  Future<void> _load() async {
    final request = ++_loadGeneration;
    try {
      final journals = await widget.engine.backups();
      if (!mounted || request != _loadGeneration) return;
      setState(() {
        _journals = journals;
        _error = null;
      });
    } on EngineException catch (error) {
      if (!mounted || request != _loadGeneration) return;
      setState(() => _error = error.message);
    }
  }

  /// Matches a journal to a game by directory, which is what both sides record.
  Game? _gameFor(JournalEntry entry) {
    for (final game in widget.games) {
      if (game.installDir == entry.gameDir) return game;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final journals = _journals;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(
        AppSpace.xl,
        AppSpace.xl,
        AppSpace.xl,
        AppSpace.xxl,
      ),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: AppSpace.contentMaxWidth),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              DropZone(
                onDrop: (path) async {
                  await widget.engine.addGameFolder(path);
                  await widget.onRescan();
                },
                onBrowse: widget.onAddFolder,
              ),
              const SizedBox(height: AppSpace.xxl),

              SectionHeader(
                title: context.t('home.recentTitle'),
                subtitle: context.t('home.recentSubtitle'),
                trailing: HoldButton(
                  dense: true,
                  label: context.t('home.refresh'),
                  icon: Icons.refresh,
                  onPressed: _load,
                ),
              ),
              if (journals == null)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpace.xl),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (journals.isEmpty)
                EmptyState(
                  title: context.t('home.nothingTitle'),
                  body: context.t('home.nothingBody'),
                  icon: Icons.inbox_outlined,
                )
              else
                _RecentRow(
                  journals: journals,
                  gameFor: _gameFor,
                  artwork: widget.artwork,
                  onOpen: widget.onOpen,
                ),

              const SizedBox(height: AppSpace.xxl),
              SectionHeader(
                title: context.t('home.activityTitle'),
                subtitle: context.t('home.activitySubtitle'),
              ),
              if (_error != null)
                Notice(
                  title: context.t('home.logError'),
                  mono: _error,
                  tone: AppColors.warning(context),
                  icon: Icons.info_outline,
                )
              else if (journals != null && journals.isNotEmpty)
                _ActivityLog(journals: journals),
            ],
          ),
        ),
      ),
    );
  }
}

/// The drop target and the browse button.
///
/// The dashed-looking ring is a solid border at low opacity: a real dashed border
/// needs a painter, and at this size the difference is not worth one.
class DropZone extends StatefulWidget {
  const DropZone({super.key, required this.onDrop, required this.onBrowse});

  final Future<void> Function(String path) onDrop;
  final Future<void> Function() onBrowse;

  @override
  State<DropZone> createState() => _DropZoneState();
}

class _DropZoneState extends State<DropZone> {
  bool _over = false;
  String? _error;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final over = _over;

    return DragTarget<String>(
      onWillAcceptWithDetails: (_) {
        setState(() => _over = true);
        return true;
      },
      onLeave: (_) => setState(() => _over = false),
      onAcceptWithDetails: (details) async {
        setState(() {
          _over = false;
          _error = null;
        });
        try {
          await widget.onDrop(details.data);
        } on EngineException catch (error) {
          if (mounted) setState(() => _error = error.message);
        }
      },
      builder:
          (context, candidate, rejected) => AnimatedContainer(
            duration: AppMotion.resolve(context, AppMotion.fast),
            curve: AppMotion.settle,
            width: double.infinity,
            padding: const EdgeInsets.symmetric(
              vertical: AppSpace.xxl,
              horizontal: AppSpace.xl,
            ),
            decoration: BoxDecoration(
              color:
                  over
                      ? AppColors.accentSoft(context)
                      : AppColors.card(context).withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(AppSpace.radiusLarge),
              border: Border.all(
                color:
                    over
                        ? AppColors.accentGreen
                        : AppColors.stroke(context).withValues(alpha: 0.7),
                width: over ? 2 : 1,
              ),
            ),
            child: Column(
              children: [
                Container(
                  width: 84,
                  height: 84,
                  decoration: BoxDecoration(
                    color: AppColors.accentSoft(context),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    Icons.create_new_folder_outlined,
                    size: 38,
                    color: AppColors.accentGreen,
                  ),
                ),
                const SizedBox(height: AppSpace.lg),
                Text(
                  context.t('home.dropTitle'),
                  style: AppText.subtitle,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpace.xs),
                Text(
                  context.t('home.dropHint'),
                  style: AppText.caption.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpace.lg),
                HoldButton(
                  label: context.t('home.browse'),
                  icon: Icons.folder_open,
                  onPressed: () => widget.onBrowse(),
                ),
                if (_error != null) ...[
                  const SizedBox(height: AppSpace.md),
                  Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpace.xl,
                    ),
                    child: Notice(
                      title: context.t('games.dropFailedTitle'),
                      mono: _error,
                      tone: AppColors.warning(context),
                      icon: Icons.info_outline,
                    ),
                  ),
                ],
              ],
            ),
          ),
    );
  }
}

/// Recently touched games, as posters.
class _RecentRow extends StatelessWidget {
  const _RecentRow({
    required this.journals,
    required this.gameFor,
    required this.artwork,
    required this.onOpen,
  });

  final List<JournalEntry> journals;
  final Game? Function(JournalEntry) gameFor;
  final Map<String, String?> artwork;
  final void Function(Game) onOpen;

  @override
  Widget build(BuildContext context) {
    // One card per game, keeping the first (newest) occurrence.
    final seen = <String>{};
    final entries = <(JournalEntry, Game)>[];
    for (final entry in journals) {
      final game = gameFor(entry);
      if (game == null || !seen.add(game.appid)) continue;
      entries.add((entry, game));
      if (entries.length == 8) break;
    }
    if (entries.isEmpty) {
      return EmptyState(
        title: context.t('home.nothingTitle'),
        body: context.t('home.nothingBody'),
        icon: Icons.inbox_outlined,
      );
    }

    return SizedBox(
      height: 216,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: entries.length,
        separatorBuilder: (_, __) => const SizedBox(width: AppSpace.md),
        itemBuilder: (context, index) {
          final (entry, game) = entries[index];
          return _RecentCard(
            game: game,
            entry: entry,
            coverPath: artwork[game.appid],
            onTap: () => onOpen(game),
          );
        },
      ),
    );
  }
}

class _RecentCard extends StatelessWidget {
  const _RecentCard({
    required this.game,
    required this.entry,
    required this.coverPath,
    required this.onTap,
  });

  final Game game;
  final JournalEntry entry;
  final String? coverPath;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SizedBox(
      width: 132,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Stack(
                children: [
                  Positioned.fill(
                    child: CoverThumb(
                      path: coverPath,
                      name: game.name,
                      width: double.infinity,
                      height: double.infinity,
                      radius: AppSpace.radius,
                    ),
                  ),
                  // The install state reads at a glance: a green dot means the
                  // journal for it is still live.
                  Positioned(
                    left: 6,
                    top: 6,
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color:
                            entry.rolledBack
                                ? theme.colorScheme.onSurfaceVariant
                                : entry.live
                                ? AppColors.accentGreen
                                : AppColors.warning(context),
                        shape: BoxShape.circle,
                        boxShadow:
                            !entry.live
                                ? null
                                : [
                                  BoxShadow(
                                    color: AppColors.accentGreen.withValues(
                                      alpha: 0.6,
                                    ),
                                    blurRadius: 8,
                                  ),
                                ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpace.sm),
            Text(
              game.name,
              style: AppText.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            Text(
              relativeTime(context, entry.createdAt),
              style: AppText.caption.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The journal as a log, newest first.
class _ActivityLog extends StatelessWidget {
  const _ActivityLog({required this.journals});

  final List<JournalEntry> journals;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final shown = journals.take(12).toList(growable: false);

    return Container(
      decoration: BoxDecoration(
        color: AppColors.chrome(context),
        borderRadius: BorderRadius.circular(AppSpace.radiusLarge),
        border: Border.all(color: AppColors.stroke(context)),
      ),
      padding: const EdgeInsets.all(AppSpace.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final entry in shown)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    margin: const EdgeInsets.only(top: 5),
                    width: 5,
                    height: 5,
                    decoration: BoxDecoration(
                      color:
                          entry.rolledBack
                              ? theme.colorScheme.onSurfaceVariant
                              : entry.live
                              ? AppColors.accentGreen
                              : AppColors.warning(context),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: AppSpace.md),
                  SizedBox(
                    width: 66,
                    child: Text(
                      _clock(entry.createdAt),
                      style: AppText.mono.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      '${entry.route}  ·  ${entry.gameDir}',
                      style: AppText.mono,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: AppSpace.md),
                  Text(
                    context.t(
                      entry.rolledBack
                          ? 'home.stateRolledBack'
                          : entry.live
                          ? 'home.stateLive'
                          : 'home.stateIncomplete',
                    ),
                    style: AppText.caption.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          if (journals.length > shown.length)
            Padding(
              padding: const EdgeInsets.only(top: AppSpace.xs),
              child: Text(
                context.t('home.more', {'n': journals.length - shown.length}),
                style: AppText.caption.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// `14:03:22` from a unix timestamp.
String _clock(double? seconds) {
  if (seconds == null) return '--:--:--';
  final at = DateTime.fromMillisecondsSinceEpoch((seconds * 1000).round());
  String two(int value) => value.toString().padLeft(2, '0');
  return '${two(at.hour)}:${two(at.minute)}:${two(at.second)}';
}
