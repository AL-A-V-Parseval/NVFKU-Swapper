/// Settings: the things a Linux user has to be able to correct.
///
/// Windows tools can assume a single Steam install and a single interpreter. Here
/// the engine may need a different Python, Steam may live somewhere unusual (a
/// Flatpak, a second drive), the component cache may need to move for space, and
/// the network may only reach GitHub through a proxy — measured on the
/// development machine, where GitHub's release assets were unreachable directly
/// while the shell's proxy worked.
///
/// Every field shows its current value, including the "use the default" state, so
/// nothing is invisible. Saving is explicit: there is no auto-apply, because a
/// wrong Steam root would silently make the library look empty.
library;

import 'package:flutter/material.dart';

import 'design.dart';
import 'engine.dart';
import 'l10n.dart';
import 'widgets.dart';

class SettingsView extends StatefulWidget {
  const SettingsView({super.key, required this.engine, required this.onChanged});

  final Engine engine;
  final Future<void> Function() onChanged;

  @override
  State<SettingsView> createState() => _SettingsViewState();
}

class _SettingsViewState extends State<SettingsView> {
  Map<String, dynamic>? _settings;
  String? _error;
  String? _saved;
  bool _busy = false;

  late final TextEditingController _python = TextEditingController();
  late final TextEditingController _steamRoot = TextEditingController();
  late final TextEditingController _cache = TextEditingController();
  bool _verify = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _python.dispose();
    _steamRoot.dispose();
    _cache.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final settings = await widget.engine.readSettings();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _python.text = settings['python_path'] as String? ?? '';
        _steamRoot.text = settings['steam_root'] as String? ?? '';
        _cache.text = settings['download_cache'] as String? ?? '';
        _verify = settings['verify_upstream'] as bool? ?? true;
        _busy = false;
      });
    } on EngineException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.message;
      });
    }
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
      _saved = null;
    });
    try {
      final settings = await widget.engine.writeSettings(
        pythonPath: _python.text.trim(),
        steamRoot: _steamRoot.text.trim(),
        downloadCache: _cache.text.trim(),
        verifyUpstream: _verify,
      );
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _busy = false;
        _saved = 'settings.saved';
      });
      await widget.onChanged();
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

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(AppSpace.xl, AppSpace.xl, AppSpace.xl, AppSpace.xxl),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 780),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SectionHeader(
                title: context.t('settings.title'),
                subtitle: context.t('settings.subtitle'),
              ),

              if (_error != null)
                Notice(
                  title: context.t('settings.readError'),
                  mono: _error,
                  tone: AppColors.danger(context),
                  icon: Icons.error_outline,
                )
              else if (_settings == null)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpace.xxl),
                  child: Center(child: CircularProgressIndicator()),
                )
              else ...[
                _TextField(
                  label: context.t('settings.python'),
                  hint: context.t('settings.pythonHint'),
                  help: context.t('settings.pythonHelp'),
                  controller: _python,
                  mono: true,
                ),
                _TextField(
                  label: context.t('settings.steamRoot'),
                  hint: context.t('settings.steamRootHint'),
                  help: context.t('settings.steamRootHelp'),
                  controller: _steamRoot,
                  mono: true,
                ),
                _TextField(
                  label: context.t('settings.cache'),
                  hint: context.t('settings.cacheHint'),
                  help: context.t('settings.cacheHelp'),
                  controller: _cache,
                  mono: true,
                ),

                const SizedBox(height: AppSpace.lg),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  value: _verify,
                  onChanged: (value) => setState(() => _verify = value),
                  title: Text(context.t('settings.verify'), style: AppText.label),
                  subtitle: Text(
                    context.t('settings.verifyHelp'),
                    style: AppText.caption.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),

                const SizedBox(height: AppSpace.lg),
                Text(context.t('settings.language'), style: AppText.label),
                const SizedBox(height: AppSpace.xs),
                Text(
                  context.t('settings.languageHelp'),
                  style: AppText.caption.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: AppSpace.sm),
                ValueListenableBuilder<AppLanguage>(
                  valueListenable: appLanguage,
                  builder: (context, preference, _) => SegmentedButton<AppLanguage>(
                    segments: [
                      for (final option in AppLanguage.values)
                        ButtonSegment(value: option, label: Text(option.label)),
                    ],
                    selected: {preference},
                    onSelectionChanged: (values) => appLanguage.value = values.first,
                  ),
                ),

                const SizedBox(height: AppSpace.xl),
                Row(
                  children: [
                    HoldButton(
                      emphasized: true,
                      label: context.t('common.save'),
                      icon: Icons.check,
                      busy: _busy,
                      onPressed: _busy ? null : _save,
                    ),
                    const SizedBox(width: AppSpace.md),
                    HoldButton(
                      label: context.t('common.reload'),
                      icon: Icons.refresh,
                      onPressed: _busy ? null : _load,
                    ),
                  ],
                ),

                if (_saved != null) ...[
                  const SizedBox(height: AppSpace.md),
                  Notice(
                    title: context.t(_saved!),
                    tone: AppColors.success(context),
                    icon: Icons.check_circle_outline,
                  ),
                ],

                const SizedBox(height: AppSpace.xl),
                Divider(color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5)),
                const SizedBox(height: AppSpace.lg),
                FieldRow(
                  label: context.t('settings.file'),
                  value: 'v${_settings!['version']} — ${context.t('settings.fileNote')}',
                  mono: false,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _TextField extends StatelessWidget {
  const _TextField({
    required this.label,
    required this.hint,
    required this.help,
    required this.controller,
    this.mono = false,
  });

  final String label;
  final String hint;
  final String help;
  final TextEditingController controller;
  final bool mono;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppText.label),
          const SizedBox(height: 2),
          Text(
            help,
            style: AppText.caption.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: AppSpace.sm),
          TextField(
            controller: controller,
            style: mono ? AppText.mono : AppText.body,
            decoration: InputDecoration(hintText: hint),
          ),
        ],
      ),
    );
  }
}
