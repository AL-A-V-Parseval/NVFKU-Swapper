/// The guarded Steam launch-option surface.
///
/// Why this is not a plain "write it for me" button: an experiment
/// ([docs/experiment-localconfig.md]) measured that Steam **reverts** an edit made
/// while a client is running, because it keeps each app's `LaunchOptions` in
/// memory and writes its copy back. So the button's enabled state is driven by
/// whether Steam is up, and the reason is stated where the button is rather than
/// discovered later when the value mysteriously disappears.
///
/// The panel also never claims more than it verified. It reports the file it
/// wrote, where the backup is, and that Steam must be restarted — it does not say
/// "launch options applied" as though Steam had already accepted them.
library;

import 'package:flutter/material.dart';

import 'design.dart';
import 'engine.dart';
import 'l10n.dart';
import 'models.dart';
import 'widgets.dart';

class LaunchOptionsPanel extends StatefulWidget {
  const LaunchOptionsPanel({
    super.key,
    required this.engine,
    required this.gameKey,
    required this.gameName,
    required this.routeValue,
    required this.routeLabel,
  });

  final Engine engine;
  final String gameKey;
  final String gameName;

  /// The value this route would write, shown before anything is written.
  final String? routeValue;
  final String routeLabel;

  @override
  State<LaunchOptionsPanel> createState() => _LaunchOptionsPanelState();
}

class _LaunchOptionsPanelState extends State<LaunchOptionsPanel> {
  LaunchOptionsState? _state;
  LaunchOptionsWrite? _result;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final state = await widget.engine.launchOptions(widget.gameKey);
      if (!mounted) return;
      setState(() => _state = state);
    } on EngineException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    }
  }

  Future<void> _write({bool clear = false}) async {
    setState(() {
      _busy = true;
      _error = null;
      _result = null;
    });
    try {
      final result = await widget.engine.setLaunchOptions(
        widget.gameKey,
        route: clear ? null : 'a1',
        value: clear ? null : widget.routeValue,
        clear: clear,
      );
      if (!mounted) return;
      setState(() {
        _busy = false;
        _result = result;
      });
      await _load();
    } on EngineException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = _state;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(
          title: context.t('lo.title'),
          subtitle: state == null
              ? context.t('lo.reading')
              : context.t(state.steamRunning ? 'lo.blockedHint' : 'lo.readyHint'),
          trailing: state == null
              ? null
              : StatusPill(
                  label: context.t(state.steamRunning ? 'lo.blocked' : 'lo.ready'),
                  tone: state.steamRunning
                      ? AppColors.warning(context)
                      : AppColors.success(context),
                ),
        ),

        if (state != null) ...[
          FieldRow(
            label: context.t('lo.current'),
            value: state.hasValue ? state.launchOptions! : context.t('lo.noneSet'),
            mono: true,
            valueColour: state.hasValue ? null : theme.colorScheme.onSurfaceVariant,
          ),
          FieldRow(label: context.t('lo.config'), value: state.config, mono: true),

          if (state.steamRunning)
            Notice(
              title: context.t('lo.exitSteamTitle'),
              body: context.t('lo.exitSteamBody'),
              tone: AppColors.warning(context),
              icon: Icons.pause_circle_outline,
              actions: [
                TextButton(onPressed: _busy ? null : _load, child: Text(context.t('common.refresh'))),
              ],
            )
          else ...[
            if (widget.routeValue != null) ...[
              Text(
                context.t('lo.wouldWrite', {'route': widget.routeLabel}),
                style: AppText.label.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: AppSpace.xs),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(AppSpace.md),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(AppSpace.radius),
                ),
                child: SelectableText(widget.routeValue!, style: AppText.mono),
              ),
            ],
            const SizedBox(height: AppSpace.md),
            Row(
              children: [
                HoldButton(
                  label: context.t(state.hasValue ? 'lo.update' : 'lo.write'),
                  icon: Icons.save_alt,
                  busy: _busy,
                  onPressed: widget.routeValue != null && !_busy
                      ? () => _write()
                      : null,
                  tooltip: context.t('lo.writeTip'),
                ),
                if (state.hasValue) ...[
                  const SizedBox(width: AppSpace.md),
                  HoldButton(
                    label: context.t('lo.clear'),
                    icon: Icons.backspace_outlined,
                    busy: _busy,
                    onPressed: _busy ? null : () => _write(clear: true),
                  ),
                ],
              ],
            ),
          ],
        ],

        if (_result != null) ...[
          const SizedBox(height: AppSpace.md),
          Notice(
            title: context.t(_result!.createdKey ? 'lo.addedTitle' : 'lo.updatedTitle'),
            mono: _result!.value,
            tone: AppColors.success(context),
            icon: Icons.save_outlined,
          ),
          const SizedBox(height: AppSpace.sm),
          FieldRow(label: context.t('lo.backup'), value: _result!.backup, mono: true),
          for (final note in _result!.notes)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                note,
                style: AppText.caption.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          if (_result!.previous != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                context.t('lo.was', {'value': _result!.previous}),
                style: AppText.mono.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
        ],

        if (_error != null) ...[
          const SizedBox(height: AppSpace.md),
          Notice(
            title: context.t('common.notWritten'),
            mono: _error,
            tone: AppColors.warning(context),
            icon: Icons.info_outline,
          ),
        ],
      ],
    );
  }
}
