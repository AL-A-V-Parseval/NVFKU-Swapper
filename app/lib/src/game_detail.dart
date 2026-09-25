/// Game detail: what this game is, which routes can serve it, and the guarded
/// launch-option writer.
///
/// Structure follows the design spec's §16 Simplicity rather than Swapper's
/// tabbed dialog: everything about one game is on **one scrolling page**, ordered
/// by what the user needs first. Facts, then routes, then the selected route's
/// plan, then the Steam launch options. Nothing is hidden behind a tab, and the
/// common path stays at the top.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'design.dart';
import 'engine.dart';
import 'l10n.dart';
import 'launch_options.dart';
import 'models.dart';
import 'widgets.dart';

class GameDetailView extends StatefulWidget {
  const GameDetailView({
    super.key,
    required this.game,
    required this.engine,
    required this.onBack,
    required this.onChanged,
    this.onLoaded,
    this.scrollController,
    this.embedded = false,
    this.onOpenInstall,
    this.component,
    this.onComponentDone,
  });

  final Game game;
  final Engine engine;
  final VoidCallback onBack;
  final Future<void> Function() onChanged;

  /// Fired once the plans are in hand, so a driver can capture deterministically.
  final VoidCallback? onLoaded;

  /// Supplied by the sheet so it can scroll to the install panel.
  final ScrollController? scrollController;

  /// True when rendered inside the sheet: the header row is dropped, because the
  /// sheet already draws a hero with the cover, the title and a close button.
  final bool embedded;

  /// Asks the shell to run a component's own install command. A prerequisite is
  /// not a route, so it does not go through the route installer.
  final void Function(String route)? onOpenInstall;

  /// When set, the view shows that component's plan instead of the route list.
  final String? component;

  /// Fired after a component install finishes.
  final VoidCallback? onComponentDone;

  @override
  State<GameDetailView> createState() => _GameDetailViewState();
}

class _GameDetailViewState extends State<GameDetailView> {
  /// Known routes and whether each can serve this game, cheap to obtain.
  List<RoutePlan>? _plans;

  /// The selected route's *full* plan, which is the expensive part.
  RoutePlan? _detailed;
  String? _error;
  String? _selected;

  @override
  void initState() {
    super.initState();
    _load();
  }

  /// Loads the viability of every route and the detail of one.
  ///
  /// Planning all three at once cost roughly ten seconds on this machine — almost
  /// all of it in routes the user had not asked to see — so the detail page asks
  /// for the recommended route first and fetches the others only when chosen.
  Future<void> _load({String? route}) async {
    setState(() {
      _plans = null;
      _detailed = null;
      _error = null;
    });
    try {
      // One call, not one per route. Planning every route at once costs barely
      // more than planning the slowest single one — the expensive part is starting
      // Python at all — so looping spawned processes for no gain.
      final summaries = await widget.engine.plan(widget.game.appid);
      if (!mounted) return;
      if (summaries.isEmpty) {
        setState(() => _error = 'no route could be planned for this game');
        return;
      }
      final target = route ??
          summaries
              .where((p) => p.viable && !p.readOnly)
              .firstOrNull
              ?.route ??
          summaries.first.route;
      final detail = summaries.where((p) => p.route == target).firstOrNull;
      setState(() {
        _plans = summaries;
        _selected = target;
        _detailed = detail;
      });
      widget.onLoaded?.call();
    } on EngineException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  /// Finds a component's plan: it lives inside the route that needs it, because a
  /// prerequisite is nested rather than listed.
  RoutePlan? _componentPlanFor(List<RoutePlan> plans) {
    for (final plan in plans) {
      if (plan.route == widget.component) return plan;
      if (plan.prerequisite?.route == widget.component) return plan.prerequisite;
    }
    return null;
  }

  Future<void> _select(String route) async {
    setState(() {
      _selected = route;
      _detailed = null;
    });
    try {
      final plans = await widget.engine.plan(widget.game.appid, route: route);
      if (!mounted) return;
      setState(() => _detailed = plans.firstOrNull);
    } on EngineException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final game = widget.game;
    final plans = _plans;
    final selected = _detailed;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.embedded)
          // The cover overlaps the hero's bottom edge, so the title starts below
          // it rather than behind it.
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpace.xl + 92 + AppSpace.md,
              42,
              AppSpace.xl,
              0,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(game.name, style: AppText.title),
                const SizedBox(height: 3),
                SelectableText(
                  game.installDir,
                  style: AppText.mono.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          )
        else
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpace.lg,
              AppSpace.lg,
              AppSpace.xl,
              0,
            ),
            child: Row(
              children: [
                IconButton(
                  onPressed: widget.onBack,
                  icon: const Icon(Icons.arrow_back),
                  tooltip: context.t('plan.backToGames'),
                ),
                const SizedBox(width: AppSpace.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(game.name, style: AppText.display),
                      const SizedBox(height: 2),
                      SelectableText(
                        game.installDir,
                        style: AppText.mono.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: AppSpace.lg),
        Expanded(
          child: _error != null
              ? EmptyState(
                  title: context.t('plan.couldNotPlan'),
                  body: _error!,
                  icon: Icons.error_outline,
                  action: FilledButton.icon(
                    onPressed: _load,
                    icon: const Icon(Icons.refresh, size: 17),
                    label: Text(context.t('common.tryAgain')),
                  ),
                )
              : plans == null
                  ? const Center(child: CircularProgressIndicator())
                  : SingleChildScrollView(
                      controller: widget.scrollController,
                      padding: EdgeInsets.fromLTRB(
                        AppSpace.xl,
                        widget.embedded ? AppSpace.lg : 0,
                        AppSpace.xl,
                        AppSpace.xxl,
                      ),
                      child: Center(
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(
                            maxWidth: AppSpace.contentMaxWidth,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              _Facts(game: game),
                              const SizedBox(height: AppSpace.xxl),
                              // A component's own install panel, reached from the
                              // "Needs" row under a route. It is deliberately not
                              // in the route list: it is a step, not an option.
                              if (widget.component != null)
                                _InstallSection(
                                  key: ValueKey(
                                    'component-${game.appid}-${widget.component}',
                                  ),
                                  engine: widget.engine,
                                  game: game,
                                  plan: _componentPlanFor(plans)!,
                                  onChanged: () async {
                                    await widget.onChanged();
                                    widget.onComponentDone?.call();
                                  },
                                )
                              else ...[
                              SectionHeader(
                                title: context.t('plan.routesTitle'),
                                subtitle: context.t('plan.routesSubtitle'),
                              ),
                              for (final plan in plans) ...[
                                _RouteCard(
                                  plan: plan,
                                  selected: plan.route == _selected,
                                  onTap: () => _select(plan.route),
                                ),
                                // A prerequisite is a component of the route above
                                // it, indented and labelled as such, so the list
                                // still reads as two routes rather than three.
                                if (plan.prerequisite != null)
                                  _PrerequisiteRow(
                                    plan: plan.prerequisite!,
                                    parentSelected: plan.route == _selected,
                                    onInstall: () =>
                                        widget.onOpenInstall?.call(
                                      plan.prerequisite!.route,
                                    ),
                                  ),
                              ],
                              const SizedBox(height: AppSpace.xl),
                              if (selected == null)
                                const Padding(
                                  padding: EdgeInsets.all(AppSpace.xl),
                                  child: Center(child: CircularProgressIndicator()),
                                )
                              else
                                _InstallSection(
                                  key: ValueKey('install-${game.appid}-${selected.route}'),
                                  engine: widget.engine,
                                  game: game,
                                  plan: selected,
                                  onChanged: () async {
                                    await widget.onChanged();
                                    await _load(route: selected.route);
                                  },
                                ),
                              ],
                              const SizedBox(height: AppSpace.xxl),
                              Divider(
                                color: theme.colorScheme.outlineVariant
                                    .withValues(alpha: 0.5),
                              ),
                              const SizedBox(height: AppSpace.xl),
                              if (game.source == 'folder')
                                Notice(
                                  title: 'No Steam launch options for this game',
                                  body: 'It was added by hand, so Steam has no appid to '
                                      'attach options to. Set the environment variables in '
                                      'whatever launches it.',
                                  tone: AppColors.warning(context),
                                  icon: Icons.info_outline,
                                )
                              else
                                LaunchOptionsPanel(
                                  engine: widget.engine,
                                  gameKey: game.appid,
                                  gameName: game.name,
                                  routeValue: selected?.launchOptions,
                                  routeLabel: selected?.title ?? '',
                                ),
                            ],
                          ),
                        ),
                      ),
                    ),
        ),
      ],
    );
  }
}

class _Facts extends StatelessWidget {
  const _Facts({required this.game});

  final Game game;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final api = game.renderingApi ?? 'unknown';
    return Container(
      padding: const EdgeInsets.all(AppSpace.lg),
      decoration: BoxDecoration(
        color: AppColors.card(context),
        borderRadius: BorderRadius.circular(AppSpace.radiusLarge),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(context.t('plan.thisGame'), style: AppText.title),
              const SizedBox(width: AppSpace.sm),
              if (game.source == 'folder')
                StatusPill(label: context.t('games.addedByHand'), tone: AppColors.accent(context)),
            ],
          ),
          const SizedBox(height: AppSpace.md),
          FieldRow(label: context.t('plan.appid'), value: game.appid, mono: true),
          FieldRow(
            label: context.t('plan.renderingApi'),
            value: api,
            valueColour: api == 'Vulkan' ? AppColors.danger(context) : null,
          ),
          FieldRow(
            label: context.t('plan.bitness'),
            value: game.bitness == null ? 'unknown' : '${game.bitness}-bit',
          ),
          FieldRow(label: context.t('plan.launchExe'), value: game.exeName, mono: true),
          FieldRow(
            label: context.t('plan.protonTool'),
            value: game.protonTool ?? context.t('plan.noPrefix'),
            valueColour: game.protonTool == null ? AppColors.warning(context) : null,
          ),
          FieldRow(
            label: context.t('plan.nativeDlss'),
            value: game.nativeDlss.isEmpty
                ? context.t('plan.none')
                : game.nativeDlss.map((p) => p.split('/').last).toSet().join(', '),
          ),
          FieldRow(
            label: context.t('plan.nrModel'),
            value: game.nrModelLabel(Localizations.localeOf(context)),
            valueColour: game.hasNrModel
                ? AppColors.success(context)
                : AppColors.warning(context),
          ),
          FieldRow(
            label: context.t('plan.reshade'),
            value: context.t(game.hasReshade ? 'plan.reshadeInstalled' : 'plan.reshadeNot'),
            valueColour: game.hasReshade ? null : AppColors.warning(context),
          ),
          if (game.apiEvidence.isNotEmpty) ...[
            const SizedBox(height: AppSpace.md),
            Text(
              context.t('plan.apiEvidence'),
              style: AppText.label.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: AppSpace.xs),
            for (final evidence in game.apiEvidence)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Text(
                  evidence,
                  style: AppText.mono.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _RouteCard extends StatefulWidget {
  const _RouteCard({
    required this.plan,
    required this.selected,
    required this.onTap,
  });

  final RoutePlan plan;
  final bool selected;
  final VoidCallback onTap;

  @override
  State<_RouteCard> createState() => _RouteCardState();
}

class _RouteCardState extends State<_RouteCard> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final plan = widget.plan;
    final verdictKey = plan.readOnly
        ? 'plan.probe'
        : (plan.viable ? 'common.viable' : 'plan.blocked');
    final tone = plan.readOnly
        ? theme.colorScheme.onSurfaceVariant
        : plan.viable
            ? AppColors.success(context)
            : AppColors.danger(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.sm),
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() => _hover = false),
        child: GestureDetector(
          onTap: widget.onTap,
          behavior: HitTestBehavior.opaque,
          child: AnimatedContainer(
            duration: AppMotion.resolve(context, AppMotion.fast),
            curve: AppMotion.settle,
            padding: const EdgeInsets.all(AppSpace.lg),
            decoration: BoxDecoration(
              // Selection reads as a ring plus a tonal step, not colour alone.
              color: widget.selected
                  ? theme.colorScheme.primary.withValues(alpha: 0.07)
                  : _hover
                      ? theme.colorScheme.onSurface.withValues(alpha: 0.03)
                      : Colors.transparent,
              border: Border.all(
                color: widget.selected
                    ? theme.colorScheme.primary.withValues(alpha: 0.55)
                    : theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
                width: widget.selected ? 1.5 : 1,
              ),
              borderRadius: BorderRadius.circular(AppSpace.radiusLarge),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(plan.title, style: AppText.subtitle),
                      const SizedBox(height: 3),
                      Text(
                        plan.summary,
                        style: AppText.body.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      // A blocked route is the one case where the reason must not
                      // be hidden: the pill says "blocked" and nothing else, which
                      // is the least useful thing this card could say. The blockers
                      // are listed inline, unopened, because that is the answer to
                      // the question the pill just raised.
                      if (!plan.viable && !plan.readOnly) ...[
                        const SizedBox(height: AppSpace.sm),
                        for (final check in plan.checks.where(
                          (c) => c.severity == 'blocker',
                        ))
                          Padding(
                            padding: const EdgeInsets.only(bottom: 2),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Padding(
                                  padding: const EdgeInsets.only(top: 2),
                                  child: Icon(
                                    Icons.error_outline,
                                    size: 13,
                                    color: AppColors.danger(context),
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Expanded(
                                  child: Text(
                                    '${check.name} — ${check.detail}',
                                    style: AppText.caption.copyWith(
                                      color: AppColors.danger(context),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        if (plan.blockers.isEmpty && plan.missing.isNotEmpty)
                          Text(
                            context.t('plan.blockedNoReason'),
                            style: AppText.caption.copyWith(
                              color: AppColors.danger(context),
                            ),
                          ),
                      ],
                      // The mechanism, behind a disclosure: a chooser wants to
                      // know which to pick, not how the proxy is loaded.
                      if (plan.detail.isNotEmpty) ...[
                        const SizedBox(height: AppSpace.xs),
                        _RouteDetail(detail: plan.detail),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: AppSpace.lg),
                StatusPill(label: context.t(verdictKey), tone: tone),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The route's mechanism, behind a disclosure.
///
/// Its own widget because the tap must not reach the card's selector underneath,
/// and because that is the kind of thing worth saying once rather than at every
/// call site. Blocked reasons are deliberately *not* behind this: they answer the
/// question the verdict pill raises, so they are shown outright.
class _RouteDetail extends StatelessWidget {
  const _RouteDetail({required this.detail});

  final String detail;

  @override
  Widget build(BuildContext context) => GestureDetector(
        // Swallow the tap so opening the disclosure does not also switch route.
        onTap: () {},
        child: Disclosure(
          dense: true,
          label: context.t('plan.technicalDetail'),
          child: Text(
            detail,
            style: AppText.caption.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
        ),
      );
}

/// Plan, apply, live progress, undo. One section, always in the same order.
class _InstallSection extends StatefulWidget {
  const _InstallSection({
    super.key,
    required this.engine,
    required this.game,
    required this.plan,
    required this.onChanged,
  });

  final Engine engine;
  final Game game;
  final RoutePlan plan;
  final Future<void> Function() onChanged;

  @override
  State<_InstallSection> createState() => _InstallSectionState();
}

class _InstallSectionState extends State<_InstallSection> {
  StreamSubscription<InstallEvent>? _subscription;
  InstallResult? _result;
  String? _refusal;
  bool _running = false;

  /// Live Steam state. The plan reports it once, but Steam can be closed while the
  /// sheet is open — and closing it is exactly what the gate is asking for — so the
  /// state is re-read on a timer rather than trusted from the plan.
  LaunchOptionsState? _steam;
  Timer? _steamPoll;
  bool _steamDialogShown = false;
  final List<String> _progress = [];

  @override
  void initState() {
    super.initState();
    _refreshSteam();
  }

  @override
  void dispose() {
    _steamPoll?.cancel();
    _subscription?.cancel();
    super.dispose();
  }

  /// Reads the Steam state, and keeps reading while it is running.
  ///
  /// Polling rather than a one-shot read because the user has to go and close Steam
  /// for the button to unlock, and making them reopen the sheet to notice would be
  /// a worse experience than a query every few seconds.
  Future<void> _refreshSteam() async {
    if (widget.game.source != 'steam') return;
    try {
      final state = await widget.engine.launchOptions(widget.game.appid);
      if (!mounted) return;
      setState(() => _steam = state);
      if (state.steamRunning) {
        _steamPoll ??= Timer.periodic(
          const Duration(seconds: 3),
          (_) => _refreshSteam(),
        );
        // Asked once per opening: a dialog that reappears every three seconds
        // would be worse than the problem it reports.
        if (!_steamDialogShown) {
          _steamDialogShown = true;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) _showSteamWarning();
          });
        }
      } else {
        _steamPoll?.cancel();
        _steamPoll = null;
      }
    } on EngineException {
      // A failed read leaves the gate closed rather than open: refusing to write
      // when the state is unknown is the safe direction.
    }
  }

  Future<void> _showSteamWarning() async {
    final proceed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        icon: Icon(Icons.pause_circle_outline, color: AppColors.warning(context)),
        title: Text(context.t('plan.steamTitle')),
        content: Text(context.t('plan.steamBody')),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(context.t('plan.steamWait')),
          ),
        ],
      ),
    );
    // There is no "install anyway": Steam would revert the write, so the only
    // honest action is to wait.
    if (proceed == true) await _refreshSteam();
  }

  Future<void> _install() async {
    setState(() {
      _running = true;
      _refusal = null;
      _result = null;
      _progress.clear();
    });
    _subscription = widget.engine
        .install(
      gameKey: widget.game.appid,
      route: widget.plan.route,
      workingScale: widget.plan.route == 'a2' ? _workingScale : null,
    )
        .listen(
      (event) {
        if (!mounted) return;
        switch (event.phase) {
          case 'log':
            setState(() => _progress.add(event.message));
          case 'done':
            setState(() {
              _running = false;
              _result = event.result;
            });
            widget.onChanged();
          case 'failed':
            setState(() {
              _running = false;
              _refusal = event.message;
            });
          default:
            break;
        }
      },
      onError: (Object error) {
        if (!mounted) return;
        setState(() {
          _running = false;
          _refusal = error.toString();
        });
      },
    );
  }

  int _workingScale = 100;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final plan = widget.plan;

    return Container(
      padding: const EdgeInsets.all(AppSpace.lg),
      decoration: BoxDecoration(
        color: AppColors.card(context),
        borderRadius: BorderRadius.circular(AppSpace.radiusLarge),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            title: context.t('plan.planTitle'),
            subtitle: context.t(plan.readOnly ? 'plan.planReadOnly' : 'plan.planSubtitle'),
            trailing: StatusPill(
              label: context.t(plan.viable ? 'plan.ready' : 'plan.blocked'),
              tone: plan.viable ? AppColors.success(context) : AppColors.danger(context),
            ),
          ),
          // What the engine inspected and would change. Folded away by default:
          // it is diagnostic detail, and a route that is simply ready should not
          // present seven checks before its install button.
          //
          // Opened automatically when something is wrong, because then it *is* the
          // answer to "why not" rather than reference material — and a blocker the
          // user has to go looking for is a blocker they will report as a bug.
          if (plan.checks.isNotEmpty || plan.actions.isNotEmpty) ...[
            const SizedBox(height: AppSpace.sm),
            Disclosure(
              tone: plan.viable ? null : AppColors.danger(context),
              icon: plan.viable ? null : Icons.error_outline,
              initiallyOpen: !plan.viable,
              label: context.t('plan.developerDetail'),
              hint: plan.viable
                  ? context.t('plan.developerDetailHint')
                  : plan.blockers.isEmpty
                      ? null
                      : '${plan.blockers.length}',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final check in plan.checks) _PlanCheck(check: check),
                  if (plan.actions.isNotEmpty) ...[
                    const SizedBox(height: AppSpace.md),
                    Text(
                      context.t('plan.whatWouldChange'),
                      style: AppText.label.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: AppSpace.sm),
                    for (final action in plan.actions) _PlanAction(action: action),
                  ],
                ],
              ),
            ),
          ],

          if (plan.missing.isNotEmpty) ...[
            const SizedBox(height: AppSpace.md),
            Text(
              context.t('plan.filesYouSupply'),
              style: AppText.label.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: AppSpace.sm),
            for (final missing in plan.missing) _MissingBlock(missing: missing),
          ],

          if (plan.launchOptions != null) ...[
            const SizedBox(height: AppSpace.md),
            Text(
              context.t('plan.launchNeeded'),
              style: AppText.label.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: AppSpace.xs),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(AppSpace.md),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(AppSpace.radius),
              ),
              child: SelectableText(plan.launchOptions!, style: AppText.mono),
            ),
          ],

          if (plan.route == 'a2') ...[
            const SizedBox(height: AppSpace.md),
            Row(
              children: [
                Text(context.t('plan.neuralResolution'), style: AppText.body),
                const SizedBox(width: AppSpace.md),
                SizedBox(
                  width: 200,
                  child: Slider(
                    value: _workingScale.toDouble(),
                    min: 25,
                    max: 100,
                    divisions: 15,
                    label: '$_workingScale%',
                    onChanged: _running
                        ? null
                        : (v) => setState(() => _workingScale = v.round()),
                  ),
                ),
                Text('$_workingScale%', style: AppText.mono),
              ],
            ),
            Text(
              context.t('plan.neuralCost'),
              style: AppText.caption.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],

          // Progress: the current line stays visible, the history folds away.
          //
          // An install prints one line per component, so leaving all of them on
          // screen buries the button under a transcript. The live line is what a
          // user watches; the rest is what they read afterwards, if ever.
          if (_running || _progress.isNotEmpty) ...[
            const SizedBox(height: AppSpace.md),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(AppSpace.md),
              decoration: BoxDecoration(
                color: AppColors.chrome(context),
                borderRadius: BorderRadius.circular(AppSpace.radius),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      if (_running)
                        const Padding(
                          padding: EdgeInsets.only(right: AppSpace.sm),
                          child: SizedBox(
                            width: 12,
                            height: 12,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        )
                      else
                        Padding(
                          padding: const EdgeInsets.only(right: AppSpace.sm),
                          child: Icon(
                            Icons.check_circle_outline,
                            size: 13,
                            color: AppColors.success(context),
                          ),
                        ),
                      Expanded(
                        child: Text(
                          _running
                              ? (_progress.isEmpty
                                  ? context.t('common.working')
                                  : _progress.last)
                              : context.t('common.lastRun'),
                          style: AppText.caption.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  if (_progress.length > 1) ...[
                    const SizedBox(height: AppSpace.sm),
                    Disclosure(
                      dense: true,
                      label: context.t('plan.installLog'),
                      hint: context.t('plan.installLogHint'),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          for (final line in _progress)
                            Padding(
                              padding: const EdgeInsets.only(bottom: 2),
                              child: SelectableText(line, style: AppText.mono),
                            ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],

          const SizedBox(height: AppSpace.lg),
          // The Steam gate. A1 cannot work without its launch options and they
          // cannot be written while Steam runs, so the button is held rather than
          // the write being attempted and reverted.
          if (_steam?.steamRunning == true) ...[
            Notice(
              title: context.t('plan.steamTitle'),
              body: context.t('plan.steamBody'),
              tone: AppColors.warning(context),
              icon: Icons.pause_circle_outline,
              actions: [
                HoldButton(
                  dense: true,
                  label: context.t('plan.steamRecheck'),
                  icon: Icons.refresh,
                  busy: _running,
                  onPressed: _refreshSteam,
                ),
              ],
            ),
            const SizedBox(height: AppSpace.md),
          ],

          Row(
            children: [
              HoldButton(
                emphasized: true,
                label: context.t(plan.readOnly
                    ? 'plan.nothingToInstall'
                    : (_running
                        ? 'common.installing'
                        : (_steam?.steamRunning == true
                            ? 'plan.steamBlocked'
                            : 'plan.confirm'))),
                icon: plan.readOnly ? Icons.info_outline : Icons.download,
                busy: _running,
                onPressed: plan.viable &&
                        !plan.readOnly &&
                        !_running &&
                        _steam?.steamRunning != true
                    ? _install
                    : null,
                tooltip: context.t(plan.readOnly
                    ? 'plan.probeTip'
                    : (_steam?.steamRunning == true
                        ? 'plan.steamBlockedTip'
                        : (plan.viable ? 'plan.confirmTip' : 'plan.resolveFirst'))),
              ),
            ],
          ),

          // What the install would set, including the launch options it now owns.
          if (plan.launchOptions != null && _steam != null) ...[
            const SizedBox(height: AppSpace.md),
            FieldRow(
              label: context.t('plan.launchOptionsCurrent'),
              value: _steam!.hasValue ? _steam!.launchOptions! : context.t('plan.none'),
              mono: true,
              valueColour: _steam!.hasValue ? null : AppColors.warning(context),
            ),
          ],

          if (_refusal != null) ...[
            const SizedBox(height: AppSpace.md),
            Notice(
              title: context.t('plan.refusedTitle'),
              mono: _refusal,
              tone: AppColors.danger(context),
              icon: Icons.block,
            ),
          ],

          if (_result != null) ...[
            const SizedBox(height: AppSpace.md),
            _InstallResultBlock(result: _result!),
          ],
        ],
      ),
    );
  }
}

class _InstallResultBlock extends StatelessWidget {
  const _InstallResultBlock({required this.result});

  final InstallResult result;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpace.lg),
      decoration: BoxDecoration(
        color: AppColors.raised(context),
        borderRadius: BorderRadius.circular(AppSpace.radiusLarge),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.check_circle_outline, size: 17, color: AppColors.success(context)),
              const SizedBox(width: AppSpace.sm),
              Text(context.t('common.installed'), style: AppText.subtitle),
            ],
          ),
          const SizedBox(height: AppSpace.md),
          if (result.journalId != null)
            FieldRow(label: context.t('common.journal'), value: result.journalId!, mono: true),
          for (final line in result.verified)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpace.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.verified_outlined, size: 14, color: AppColors.success(context)),
                  const SizedBox(width: AppSpace.sm),
                  Expanded(child: Text(line, style: AppText.body)),
                ],
              ),
            ),
          for (final line in result.warnings)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpace.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.warning_amber_outlined, size: 14, color: AppColors.warning(context)),
                  const SizedBox(width: AppSpace.sm),
                  Expanded(child: Text(line, style: AppText.body)),
                ],
              ),
            ),
          for (final line in result.notes)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpace.xs),
              child: Text(
                line,
                style: AppText.caption.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          if (result.manualSteps.isNotEmpty) ...[
            const SizedBox(height: AppSpace.md),
            Text(
              context.t('common.stillOnYou'),
              style: AppText.label.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: AppSpace.xs),
            for (final step in result.manualSteps)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Text('• $step', style: AppText.body),
              ),
          ],
          if (result.journalId != null) ...[
            const SizedBox(height: AppSpace.md),
            Text(
              context.t('history.undoHint'),
              style: AppText.caption.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 2),
            SelectableText('nvfku rollback ${result.journalId}', style: AppText.mono),
          ],
        ],
      ),
    );
  }
}

class _PlanCheck extends StatelessWidget {
  const _PlanCheck({required this.check});

  final EngineCheck check;

  @override
  Widget build(BuildContext context) {
    final (colour, icon) = switch (check.severity) {
      'ok' => (AppColors.success(context), Icons.check_circle_outline),
      'blocker' => (AppColors.danger(context), Icons.error_outline),
      _ => (AppColors.warning(context), Icons.warning_amber_outlined),
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(icon, size: 15, color: colour),
          ),
          const SizedBox(width: AppSpace.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(check.name, style: AppText.label),
                const SizedBox(height: 1),
                SelectableText(check.detail, style: AppText.body),
                if (check.fix != null && !check.isOk) ...[
                  const SizedBox(height: AppSpace.xs),
                  SelectableText(
                    check.fix!,
                    style: AppText.caption.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PlanAction extends StatelessWidget {
  const _PlanAction({required this.action});

  final EngineAction action;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final verbKey = switch (action.kind) {
      'copy' => 'plan.kind.copy',
      'write' => 'plan.kind.write',
      'delete' => 'plan.kind.delete',
      'mkdir' => 'plan.kind.mkdir',
      'launch-option' => 'plan.kind.launch',
      _ => 'plan.kind.note',
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 52,
            child: Text(
              context.t(verbKey),
              style: AppText.caption.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (action.source != null)
                  SelectableText(
                    action.source!,
                    style: AppText.mono.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                SelectableText(action.destination, style: AppText.mono),
                if (action.reason.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      action.reason + (action.optional ? '  (optional)' : ''),
                      style: AppText.caption.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MissingBlock extends StatelessWidget {
  const _MissingBlock({required this.missing});

  final EngineMissing missing;

  @override
  Widget build(BuildContext context) {
    final tone = missing.blocking
        ? AppColors.danger(context)
        : AppColors.warning(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.sm),
      child: Notice(
        title: missing.what,
        body: '${missing.why}\n\nHow to get it: ${missing.howToGet}',
        tone: tone,
        icon: Icons.folder_off_outlined,
      ),
    );
  }
}

/// A route's prerequisite: nested under the route, not a sibling of it.
///
/// ReShade is part of what A1 installs. It keeps its own install action because it
/// genuinely needs one — it downloads a binary from the publisher and can create a
/// Proton prefix — but presenting it as a third route made the plan read as three
/// options when there are two.
class _PrerequisiteRow extends StatelessWidget {
  const _PrerequisiteRow({
    required this.plan,
    required this.parentSelected,
    required this.onInstall,
  });

  final RoutePlan plan;
  final bool parentSelected;
  final VoidCallback onInstall;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      // Indented and with a leading rule, so the nesting is visible rather than
      // inferred from the wording.
      padding: const EdgeInsets.only(
        left: AppSpace.xl,
        right: AppSpace.sm,
        bottom: AppSpace.sm,
      ),
      child: Container(
        padding: const EdgeInsets.all(AppSpace.md),
        decoration: BoxDecoration(
          color: AppColors.chrome(context).withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(AppSpace.radius),
          border: Border(
            left: BorderSide(
              color: parentSelected
                  ? theme.colorScheme.primary
                  : AppColors.stroke(context),
              width: 2,
            ),
          ),
        ),
        child: Row(
          children: [
            Icon(
              Icons.subdirectory_arrow_right,
              size: 15,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            const SizedBox(width: AppSpace.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        context.t('plan.prerequisite'),
                        style: AppText.caption.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(width: AppSpace.sm),
                      Text(plan.title, style: AppText.label),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    plan.summary,
                    style: AppText.caption.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpace.md),
            StatusPill(
              label: context.t(plan.viable ? 'plan.ready' : 'plan.blocked'),
              tone: plan.viable ? AppColors.success(context) : AppColors.danger(context),
            ),
            const SizedBox(width: AppSpace.sm),
            HoldButton(
              dense: true,
              label: context.t('plan.installComponent'),
              icon: Icons.download,
              onPressed: plan.viable ? onInstall : null,
            ),
          ],
        ),
      ),
    );
  }
}
