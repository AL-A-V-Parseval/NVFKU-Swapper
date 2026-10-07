/// History: every journal this tool has written, with exact rollback.
///
/// Swapper calls this section History and pairs it with "Restore originals". The
/// equivalent here is stronger, because the engine records a pre-image of every
/// file before it replaces it: rolling back a journal restores the game directory
/// byte for byte, which the test suite asserts rather than assumes.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import 'design.dart';
import 'engine.dart';
import 'l10n.dart';
import 'models.dart';
import 'widgets.dart';

class HistoryView extends StatefulWidget {
  const HistoryView({super.key, required this.engine});

  final Engine engine;

  @override
  State<HistoryView> createState() => _HistoryViewState();
}

class _HistoryViewState extends State<HistoryView> {
  List<JournalEntry>? _entries;
  String? _error;
  String? _rollbackError;
  String? _busyId;
  String? _report;
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    widget.engine.revision.addListener(_stateChanged);
    _load();
  }

  void _stateChanged() => unawaited(_load());

  @override
  void didUpdateWidget(HistoryView oldWidget) {
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
      final entries = await widget.engine.backups();
      if (!mounted || request != _loadGeneration) return;
      setState(() {
        _entries = entries;
        _error = null;
      });
    } on EngineException catch (e) {
      if (!mounted || request != _loadGeneration) return;
      setState(() => _error = e.message);
    }
  }

  Future<void> _rollback(JournalEntry entry) async {
    setState(() {
      _busyId = entry.id;
      _report = null;
      _rollbackError = null;
    });
    try {
      final report = await widget.engine.rollback(entry.id);
      if (!mounted) return;
      setState(() {
        _busyId = null;
        _report = report;
      });
      // Engine.revision refreshes this view and the Shell after rollback.
    } on EngineException catch (e) {
      if (!mounted) return;
      setState(() {
        _busyId = null;
        _rollbackError = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final entries = _entries;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(AppSpace.xl, AppSpace.xl, AppSpace.xl, AppSpace.xxl),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: AppSpace.contentMaxWidth),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SectionHeader(
                title: context.t('history.title'),
                subtitle: context.t('history.subtitle'),
                trailing: HoldButton(
                  label: context.t('common.refresh'),
                  icon: Icons.refresh,
                  onPressed: _load,
                ),
              ),

              if (_rollbackError != null)
                Notice(
                  title: context.t('history.rollbackFailedTitle'),
                  mono: _rollbackError,
                  tone: AppColors.danger(context),
                  icon: Icons.error_outline,
                ),
              if (_error != null)
                Notice(
                  title: context.t('history.readError'),
                  mono: _error,
                  tone: AppColors.danger(context),
                  icon: Icons.error_outline,
                )
              else if (entries == null)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpace.xxl),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (entries.isEmpty)
                EmptyState(
                  title: context.t('history.emptyTitle'),
                  body: context.t('history.emptyBody'),
                  icon: Icons.history_toggle_off,
                )
              else
                for (final entry in entries)
                  _JournalCard(
                    entry: entry,
                    busy: _busyId == entry.id,
                    onRollback: () => _rollback(entry),
                  ),

              if (_report != null) ...[
                const SizedBox(height: AppSpace.lg),
                Notice(
                  title: context.t('history.rolledBackTitle'),
                  mono: _report,
                  tone: AppColors.success(context),
                  icon: Icons.undo,
                ),
              ],

              const SizedBox(height: AppSpace.xl),
              Text(
                context.t('history.note'),
                style: AppText.caption.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _JournalCard extends StatelessWidget {
  const _JournalCard({
    required this.entry,
    required this.busy,
    required this.onRollback,
  });

  final JournalEntry entry;
  final bool busy;
  final VoidCallback onRollback;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final stateKey = entry.rolledBack
        ? 'history.rolledBack'
        : entry.live
            ? 'history.complete'
            : 'history.incomplete';

    return Container(
      margin: const EdgeInsets.only(bottom: AppSpace.sm),
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
              Text(entry.route, style: AppText.subtitle),
              const SizedBox(width: AppSpace.sm),
              StatusPill(
                label: context.t(stateKey),
                tone: entry.rolledBack
                    ? theme.colorScheme.onSurfaceVariant
                    : entry.live ? AppColors.success(context) : AppColors.warning(context),
              ),
              const SizedBox(width: AppSpace.sm),
              Text(
                '${entry.operations} operations',
                style: AppText.caption.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const Spacer(),
              HoldButton(
                dense: true,
                label: context.t(entry.rolledBack ? 'history.undoAgain' : 'history.rollBack'),
                icon: Icons.undo,
                busy: busy,
                onPressed: busy ? null : onRollback,
                tooltip: context.t('history.rollBackTip'),
              ),
            ],
          ),
          const SizedBox(height: AppSpace.sm),
          SelectableText(entry.gameDir, style: AppText.mono),
          const SizedBox(height: 2),
          SelectableText(
            entry.id,
            style: AppText.mono.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}
