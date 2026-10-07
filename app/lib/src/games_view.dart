/// Games: the library, and the one-click install flow.
///
/// The interaction model follows DLSS5-Swapper: a row per game with its state on
/// the right and a primary action inline, so the common path — pick a game,
/// press Install — needs no navigation. Adding a game folder by dropping it on
/// the window is Swapper's other affordance and is supported here for installs
/// Steam does not manage.
///
/// Where it deliberately departs from Swapper: the inline action **expands the
/// plan first**. A single press that immediately writes files into a game
/// directory is the one thing this tool will not do, because the plan is the only
/// place the user can see what will change and what is missing before it does.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'design.dart';
import 'cover.dart';
import 'engine.dart';
import 'l10n.dart';
import 'models.dart';
import 'widgets.dart';

class GamesView extends StatefulWidget {
  const GamesView({
    super.key,
    required this.games,
    required this.filter,
    required this.onFilter,
    required this.onOpen,
    required this.onRescan,
    required this.onOpenFolder,
    required this.engine,
    required this.busy,
    this.artwork = const {},
  });

  final List<Game> games;
  final String filter;
  final ValueChanged<String> onFilter;

  /// Opens a game's sheet. `install: true` lands on the install panel, which is
  /// what a card's install button asks for.
  final void Function(Game game, {bool install}) onOpen;
  final Future<void> Function() onRescan;

  /// Opens a game's directory in the desktop's file manager.
  final Future<void> Function(Game game) onOpenFolder;
  final Engine engine;
  final bool busy;

  /// Cached cover path per appid. Empty while the first query runs.
  final Map<String, String?> artwork;

  @override
  State<GamesView> createState() => _GamesViewState();
}

class _GamesViewState extends State<GamesView> {
  String? _dropError;
  bool _dropping = false;
  late final TextEditingController _filterController;

  @override
  void initState() {
    super.initState();
    _filterController = TextEditingController(text: widget.filter);
  }

  @override
  void didUpdateWidget(GamesView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.filter != oldWidget.filter &&
        widget.filter != _filterController.text) {
      _filterController.value = TextEditingValue(
        text: widget.filter,
        selection: TextSelection.collapsed(offset: widget.filter.length),
      );
    }
  }

  @override
  void dispose() {
    _filterController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final needle = widget.filter.trim().toLowerCase();
    final visible =
        needle.isEmpty
            ? widget.games
            : widget.games
                .where(
                  (g) =>
                      g.name.toLowerCase().contains(needle) ||
                      g.appid.contains(needle),
                )
                .toList(growable: false);

    return _DropTarget(
      onHover: (over) => setState(() => _dropping = over),
      onDrop: _handleDrop,
      dropping: _dropping,
      child: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpace.xl,
                AppSpace.xl,
                AppSpace.xl,
                AppSpace.md,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(context.t('games.title'), style: AppText.display),
                  const SizedBox(height: AppSpace.xs),
                  Text(
                    _summary(context, widget.games),
                    style: AppText.body.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: AppSpace.lg),
                  LayoutBuilder(
                    builder:
                        (context, constraints) => Wrap(
                          spacing: AppSpace.md,
                          runSpacing: AppSpace.md,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            SizedBox(
                              width:
                                  constraints.maxWidth < 680
                                      ? constraints.maxWidth
                                      : 280,
                              child: ValueListenableBuilder<TextEditingValue>(
                                valueListenable: _filterController,
                                builder:
                                    (context, value, _) => TextField(
                                      controller: _filterController,
                                      onChanged: widget.onFilter,
                                      style: AppText.body,
                                      decoration: InputDecoration(
                                        hintText: context.t('games.filter'),
                                        prefixIcon: const Icon(
                                          Icons.search,
                                          size: 18,
                                        ),
                                        suffixIcon:
                                            value.text.isEmpty
                                                ? null
                                                : IconButton(
                                                  tooltip: context.t(
                                                    'games.clearSearch',
                                                  ),
                                                  icon: const Icon(
                                                    Icons.close,
                                                    size: 18,
                                                  ),
                                                  onPressed: () {
                                                    _filterController.clear();
                                                    widget.onFilter('');
                                                  },
                                                ),
                                      ),
                                    ),
                              ),
                            ),
                            HoldButton(
                              label: context.t('games.addFolder'),
                              icon: Icons.create_new_folder_outlined,
                              onPressed: _promptForFolder,
                              tooltip: context.t('games.addFolderTip'),
                            ),
                            HoldButton(
                              label: context.t('common.rescan'),
                              icon: Icons.refresh,
                              busy: widget.busy,
                              onPressed: widget.busy ? null : widget.onRescan,
                            ),
                          ],
                        ),
                  ),
                ],
              ),
            ),
          ),
          if (_dropError != null)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpace.xl,
                  0,
                  AppSpace.xl,
                  AppSpace.md,
                ),
                child: Notice(
                  title: context.t('games.dropFailedTitle'),
                  body: _dropError,
                  tone: AppColors.warning(context),
                  icon: Icons.info_outline,
                  actions: [
                    TextButton(
                      onPressed: () => setState(() => _dropError = null),
                      child: Text(context.t('common.dismiss')),
                    ),
                  ],
                ),
              ),
            ),
          if (visible.any((game) => !game.detectionComplete))
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpace.xl,
                  0,
                  AppSpace.xl,
                  AppSpace.md,
                ),
                child: Notice(
                  title: context.t('games.detectionIncomplete'),
                  body: context.t('games.detectionIncompleteBody'),
                  mono: visible
                      .where((game) => !game.detectionComplete)
                      .expand((game) => game.detectionWarnings)
                      .join('\n'),
                  tone: AppColors.warning(context),
                  icon: Icons.warning_amber_outlined,
                ),
              ),
            ),
          if (visible.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: EmptyState(
                title: context.t(
                  widget.games.isEmpty
                      ? 'games.emptyTitle'
                      : 'games.nothingMatches',
                ),
                body:
                    widget.games.isEmpty
                        ? context.t('games.emptyBody')
                        : context.t('games.nothingMatchesBody', {
                          'filter': widget.filter,
                        }),
                icon:
                    widget.games.isEmpty
                        ? Icons.videogame_asset_off
                        : Icons.search_off,
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(
                AppSpace.xl,
                0,
                AppSpace.xl,
                AppSpace.xl,
              ),
              sliver: SliverGrid(
                // 168px minimum, matching the reference's own grid. A poster is
                // 2:3, so the cards stay recognisable as covers rather than
                // becoming letterboxes at some widths.
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 196,
                  mainAxisSpacing: AppSpace.lg,
                  crossAxisSpacing: AppSpace.md,
                  childAspectRatio: 0.56,
                ),
                delegate: SliverChildBuilderDelegate(
                  (context, index) => _GameCard(
                    key: ValueKey('card-${visible[index].appid}'),
                    game: visible[index],
                    coverPath: widget.artwork[visible[index].appid],
                    onOpen: widget.onOpen,
                    onRescan: widget.onRescan,
                    onOpenFolder: widget.onOpenFolder,
                    engine: widget.engine,
                  ),
                  childCount: visible.length,
                ),
              ),
            ),
        ],
      ),
    );
  }

  String _summary(BuildContext context, List<Game> games) {
    if (games.isEmpty) return context.t('games.emptyTitle').toLowerCase();
    final withDlss = games.where((g) => g.hasNativeDlss).length;
    final withModel = games.where((g) => g.hasNrModel).length;
    final folders = games.where((g) => g.source == 'folder').length;
    final parts = <String>[
      context.t('games.summary', {'games': games.length}),
      context.t('games.summaryDlss', {'n': withDlss}),
    ];
    if (withModel > 0) {
      parts.add(context.t('games.summaryModel', {'n': withModel}));
    }
    if (folders > 0) {
      parts.add(context.t('games.summaryFolders', {'n': folders}));
    }
    return parts.join(' · ');
  }

  Future<void> _promptForFolder() async {
    final result = await promptForGameFolder(context);
    if (result == null || result.trim().isEmpty) return;
    await _handleDrop([result.trim()]);
  }

  Future<void> _handleDrop(List<String> paths) async {
    if (paths.isEmpty) return;
    setState(() => _dropError = null);
    for (final path in paths) {
      try {
        await widget.engine.addGameFolder(path);
      } on EngineException catch (e) {
        setState(() => _dropError = e.message);
        return;
      }
    }
    await widget.onRescan();
  }
}

/// Accepts a folder dropped onto the window.
///
/// Flutter's desktop embedder delivers dropped paths as a `String` payload
/// through the platform channel that backs this widget. The implementation is
/// intentionally thin: if the platform does not deliver drops, the button next
/// to it is the documented fallback, and the UI says so rather than appearing
/// broken.
class _DropTarget extends StatelessWidget {
  const _DropTarget({
    required this.child,
    required this.onDrop,
    required this.onHover,
    required this.dropping,
  });

  final Widget child;
  final Future<void> Function(List<String>) onDrop;
  final ValueChanged<bool> onHover;
  final bool dropping;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return DragTarget<String>(
      onWillAcceptWithDetails: (_) {
        onHover(true);
        return true;
      },
      onLeave: (_) => onHover(false),
      onAcceptWithDetails: (details) async {
        onHover(false);
        final payload = details.data;
        final paths =
            payload
                .split('\n')
                .map(
                  (line) =>
                      line.startsWith('file://')
                          ? Uri.parse(line).toFilePath()
                          : line,
                )
                .where((line) => line.trim().isNotEmpty)
                .toList();
        await onDrop(paths);
      },
      builder: (context, candidate, rejected) {
        return Stack(
          children: [
            Positioned.fill(child: child),
            if (dropping)
              Positioned.fill(
                child: IgnorePointer(
                  child: Container(
                    color: theme.colorScheme.primary.withValues(alpha: 0.08),
                    alignment: Alignment.topCenter,
                    padding: const EdgeInsets.only(top: AppSpace.xxl),
                    child: Text(
                      context.t('games.dropHere'),
                      style: AppText.title.copyWith(
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

/// One game: identity on the left, state on the right, primary action inline.
/// One game as a poster card: the cover, then the facts a person scans for.
///
/// This replaces a list row. The reference's own grid is the argument: a cover
/// tells you which game it is faster than a name does, and a library is browsed by
/// recognition far more often than by reading. Facts that used to sit in columns
/// moved into the sheet, because a card has room for the cover and a status line,
/// not for a table.
///
/// Right-click is where the destructive and file-manager actions live, so nothing
/// a user cannot undo is one stray click away on the card itself.
class _GameCard extends StatefulWidget {
  const _GameCard({
    super.key,
    required this.game,
    required this.coverPath,
    required this.onOpen,
    required this.onRescan,
    required this.onOpenFolder,
    required this.engine,
  });

  final Game game;
  final String? coverPath;
  final void Function(Game game, {bool install}) onOpen;
  final Future<void> Function() onRescan;
  final Future<void> Function(Game game) onOpenFolder;
  final Engine engine;

  @override
  State<_GameCard> createState() => _GameCardState();
}

class _GameCardState extends State<_GameCard> {
  bool _hover = false;
  bool _focused = false;
  final FocusNode _focusNode = FocusNode();

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final game = widget.game;
    // A folder added by hand has no store, and a game with no renderer we can use
    // is shown but not offered an install.
    final unsupported = game.source == 'folder' && game.launchExe == null;

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: InkWell(
        focusNode: _focusNode,
        onFocusChange: (focused) => setState(() => _focused = focused),
        borderRadius: BorderRadius.circular(AppSpace.radius),
        onTap: () => widget.onOpen(game),
        onSecondaryTapDown: (details) => _showMenu(details.globalPosition),
        child: AnimatedContainer(
          duration: AppMotion.resolve(context, AppMotion.fast),
          curve: AppMotion.settle,
          // The lift is the reference's own hover: 3px up plus a deeper shadow.
          transform: Matrix4.translationValues(0, _hover ? -3 : 0, 0),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppSpace.radius),
            border: Border.all(
              color:
                  _focused
                      ? Theme.of(context).colorScheme.primary
                      : Colors.transparent,
              width: 2,
            ),
            boxShadow:
                _hover
                    ? const [
                      BoxShadow(
                        color: Color(0x66000000),
                        blurRadius: 22,
                        offset: Offset(0, 10),
                      ),
                    ]
                    : null,
          ),
          child: Opacity(
            opacity: unsupported ? 0.55 : 1,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Stack(
                    children: [
                      Positioned.fill(
                        child: CoverThumb(
                          path: widget.coverPath,
                          name: game.name,
                          width: double.infinity,
                          height: double.infinity,
                          radius: AppSpace.radius,
                        ),
                      ),
                      // The API badge, top-right, which is the one fact worth
                      // surfacing before you open anything.
                      Positioned(
                        top: 6,
                        right: 6,
                        child: _ApiBadge(game: game),
                      ),
                      Positioned(
                        bottom: 6,
                        right: 6,
                        child: Builder(
                          builder:
                              (buttonContext) => _CardTool(
                                icon: Icons.more_horiz,
                                tooltip: context.t('menu.more'),
                                onTap: () {
                                  final box =
                                      buttonContext.findRenderObject()
                                          as RenderBox;
                                  _showMenu(
                                    box.localToGlobal(
                                      box.size.center(Offset.zero),
                                    ),
                                  );
                                },
                              ),
                        ),
                      ),
                      if (_hover)
                        Positioned(
                          top: 6,
                          left: 6,
                          child: _CardTool(
                            icon: Icons.bolt,
                            tooltip: context.t('games.installTip'),
                            accent: true,
                            onTap: () => widget.onOpen(game, install: true),
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpace.sm),
                Text(
                  game.name,
                  style: AppText.label,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                _StatusLine(game: game),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

extension on _GameCardState {
  /// The actions that do not belong on the face of a card.
  ///
  /// A card is a single click target for opening, so anything destructive has to
  /// live somewhere deliberate — and "restore the originals" is exactly that.
  Future<void> _showMenu(Offset at) async {
    final game = widget.game;
    // Keep the context for localization and guard that exact context after awaits.
    final page = context;
    final overlay = Overlay.of(page).context.findRenderObject() as RenderBox?;
    if (overlay == null) return;
    final messenger = ScaffoldMessenger.maybeOf(page);

    // Whether there is anything to restore decides if that item is offered at all,
    // rather than showing it disabled with no explanation.
    var restorable = false;
    try {
      restorable = (await widget.engine.backups(
        gameKey: game.appid,
      )).any((entry) => entry.restorable);
    } on EngineException {
      // A journal listing failure must not stop the menu from opening.
    }
    if (!page.mounted) return;

    final choice = await showMenu<String>(
      context: page,
      position: RelativeRect.fromRect(
        Rect.fromLTWH(at.dx, at.dy, 1, 1),
        Offset.zero & overlay.size,
      ),
      items: [
        PopupMenuItem(
          value: 'open',
          child: _MenuRow(
            icon: Icons.open_in_new,
            label: page.t('menu.details'),
          ),
        ),
        PopupMenuItem(
          value: 'install',
          child: _MenuRow(icon: Icons.bolt, label: page.t('menu.install')),
        ),
        const PopupMenuDivider(),
        PopupMenuItem(
          value: 'folder',
          child: _MenuRow(
            icon: Icons.folder_open,
            label: page.t('menu.openFolder'),
          ),
        ),
        PopupMenuItem(
          value: 'copy',
          child: _MenuRow(
            icon: Icons.content_copy,
            label: page.t('menu.copyPath'),
          ),
        ),
        PopupMenuItem(
          value: 'refresh',
          child: _MenuRow(icon: Icons.refresh, label: page.t('menu.rescan')),
        ),
        if (restorable) ...[
          const PopupMenuDivider(),
          PopupMenuItem(
            value: 'restore',
            child: _MenuRow(
              icon: Icons.settings_backup_restore,
              label: page.t('menu.restore'),
              // Destructive, so it is coloured: the one item here that changes
              // files back cannot look like the others.
              danger: true,
            ),
          ),
        ],
      ],
    );

    if (!page.mounted || choice == null) return;
    switch (choice) {
      case 'open':
        widget.onOpen(game);
      case 'install':
        widget.onOpen(game, install: true);
      case 'folder':
        await widget.onOpenFolder(game);
      case 'copy':
        await Clipboard.setData(ClipboardData(text: game.installDir));
        if (page.mounted) {
          messenger?.showSnackBar(
            SnackBar(content: Text(page.t('menu.copied'))),
          );
        }
      case 'refresh':
        await widget.onRescan();
      case 'restore':
        await _confirmRestore(game);
    }
  }

  /// Restoring asks first, and asks for the same reason every time: it puts back
  /// the files a previous install replaced, which is not a thing to do on a stray
  /// click.
  Future<void> _confirmRestore(Game game) async {
    if (!mounted) return;
    final page = context;
    final messenger = ScaffoldMessenger.maybeOf(page);
    final confirmed = await showDialog<bool>(
      context: page,
      builder:
          (dialog) => AlertDialog(
            title: Text(dialog.t('menu.restoreTitle')),
            content: Text(dialog.t('menu.restoreBody')),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialog).pop(false),
                child: Text(dialog.t('common.cancel')),
              ),
              FilledButton(
                onPressed: () => Navigator.of(dialog).pop(true),
                child: Text(dialog.t('menu.restoreConfirm')),
              ),
            ],
          ),
    );
    if (confirmed != true || !mounted) return;

    try {
      final journals = await widget.engine.backups(gameKey: game.appid);
      // Newest first, so the most recent install is the one undone. Rolling back
      // all of them would fight with itself over the same files.
      if (journals.any((entry) => entry.restorable)) {
        await widget.engine.rollback(
          journals.firstWhere((entry) => entry.restorable).id,
        );
      }
    } on EngineException catch (error) {
      if (mounted) {
        messenger?.showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }
}

class _MenuRow extends StatelessWidget {
  const _MenuRow({
    required this.icon,
    required this.label,
    this.danger = false,
  });

  final IconData icon;
  final String label;
  final bool danger;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(icon, size: 16, color: danger ? AppColors.danger(context) : null),
      const SizedBox(width: AppSpace.md),
      Flexible(
        child: Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: AppText.body.copyWith(
            color: danger ? AppColors.danger(context) : null,
          ),
        ),
      ),
    ],
  );
}

/// `DirectX 12` in the accent when it is the path we can serve, muted otherwise.
class _ApiBadge extends StatelessWidget {
  const _ApiBadge({required this.game});

  final Game game;

  @override
  Widget build(BuildContext context) {
    final api = game.renderingApi;
    final servable = api == 'DirectX 11' || api == 'DirectX 12';
    final label = switch (api) {
      'DirectX 11' => 'DX11',
      'DirectX 12' => 'DX12',
      'Vulkan' => 'Vulkan',
      'OpenGL' => 'OpenGL',
      _ => context.t('games.unknownApi'),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color:
            servable
                ? AppColors.accentGreen.withValues(alpha: 0.92)
                : Colors.black.withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: AppText.caption.copyWith(
          fontSize: 10,
          fontWeight: FontWeight.w600,
          color: servable ? const Color(0xFF0B1405) : Colors.white,
        ),
      ),
    );
  }
}

/// The dots plus short words under the name: what state this game is in.
class _StatusLine extends StatelessWidget {
  const _StatusLine({required this.game});

  final Game game;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final parts = <(Color, String)>[
      if (game.hasReshade) (AppColors.accentGreen, 'ReShade'),
      if (game.hasNrModel) (AppColors.accentGreen, 'NR'),
      if (game.hasNativeDlss) (theme.colorScheme.onSurfaceVariant, 'DLSS'),
      if (game.source == 'folder')
        (theme.colorScheme.onSurfaceVariant, context.t('games.addedByHand')),
    ];
    if (!game.detectionComplete) {
      return Text(
        context.t('games.detectionIncomplete'),
        style: AppText.caption.copyWith(color: AppColors.warning(context)),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      );
    }
    if (parts.isEmpty) {
      return Text(
        context.t('plan.none'),
        style: AppText.caption.copyWith(
          color: theme.colorScheme.onSurfaceVariant,
        ),
      );
    }

    return Row(
      children: [
        for (final (colour, label) in parts.take(3)) ...[
          Container(
            width: 5,
            height: 5,
            decoration: BoxDecoration(color: colour, shape: BoxShape.circle),
          ),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              label,
              style: AppText.caption.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: AppSpace.sm),
        ],
      ],
    );
  }
}

/// A keyboard-accessible action over the cover; secondary actions stay visible.
class _CardTool extends StatelessWidget {
  const _CardTool({
    required this.icon,
    required this.tooltip,
    required this.onTap,
    this.accent = false,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    return Material(
      color:
          accent ? AppColors.accentGreen : Colors.black.withValues(alpha: 0.78),
      shape: const CircleBorder(),
      clipBehavior: Clip.antiAlias,
      child: IconButton(
        tooltip: tooltip,
        onPressed: onTap,
        constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
        iconSize: 18,
        color: accent ? const Color(0xFF0B1405) : Colors.white,
        icon: Icon(icon),
      ),
    );
  }
}
