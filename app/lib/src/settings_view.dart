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
  const SettingsView({
    super.key,
    required this.engine,
    required this.onChanged,
  });

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
  int _pending = 0;
  // Shared by views of the same engine: navigation must not start a second
  // queue, or reload stale preferences before the first view's intents drain.
  static final _writes = Expando<Future<void>>('settings intents');

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
      final engine = widget.engine;
      await (_writes[engine] ?? Future<void>.value());
      if (!mounted) return;
      final settings = await engine.readSettings();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _python.text = settings['python_path'] as String? ?? '';
        _steamRoot.text = settings['steam_root'] as String? ?? '';
        _cache.text = settings['download_cache'] as String? ?? '';
        _verify = settings['verify_upstream'] as bool? ?? true;
        appTheme.value = AppThemeX.fromCode(settings['theme'] as String?);
        appLanguage.value = AppLanguageX.fromCode(
          settings['language'] as String?,
        );
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

  /// Persists the appearance preferences the moment they change.
  ///
  /// Deliberately not deferred to the Save button: a colour scheme is applied
  /// instantly, so leaving it unsaved until an unrelated Save would have the window
  /// looking one way and behaving another after a restart. The language picker had
  /// exactly that problem — it wrote to the notifier and nothing else, so the choice
  /// was gone on the next launch even though the docstring claimed it was stored.
  Future<void> _enqueue(Future<void> Function() write) {
    setState(() {
      _pending++;
      _error = null;
      _saved = null;
    });
    final engine = widget.engine;
    final next = (_writes[engine] ?? Future<void>.value()).then((_) async {
      try {
        await write();
        if (mounted) {
          setState(() {
            _error = null;
            _saved = 'settings.saved';
          });
        }
      } on EngineException catch (error) {
        if (mounted) {
          setState(() {
            _error = error.message;
            _saved = null;
          });
        }
      } finally {
        if (mounted) setState(() => _pending--);
      }
    });
    // An unexpected programming error is still observable by the caller, but
    // must not poison later user requests in the queue.
    _writes[engine] = next.then<void>(
      (_) {},
      onError: (Object _, StackTrace __) {},
    );
    return next;
  }

  Future<void> _savePreferences() {
    final engine = widget.engine;
    final theme = appTheme.value.code;
    final language = appLanguage.value.code;
    return _enqueue(() async {
      await engine.writeSettings(theme: theme, language: language);
    });
  }

  Future<void> _save() async {
    final engine = widget.engine;
    final onChanged = widget.onChanged;
    final python = _python.text.trim();
    final steam = _steamRoot.text.trim();
    final cache = _cache.text.trim();
    final verify = _verify;
    final theme = appTheme.value.code;
    final language = appLanguage.value.code;
    setState(() => _busy = true);
    try {
      await _enqueue(() async {
        // Snapshot at intent time, in the same sequence as picker changes. Save
        // also retries appearance after a failed auto-save; any later picker
        // intent necessarily executes afterwards and remains authoritative.
        final settings = await engine.writeSettings(
          pythonPath: python,
          steamRoot: steam,
          downloadCache: cache,
          verifyUpstream: verify,
          theme: theme,
          language: language,
        );
        if (!mounted) return;
        setState(() => _settings = settings);
        await onChanged();
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(
        AppSpace.xl,
        AppSpace.xl,
        AppSpace.xl,
        AppSpace.xxl,
      ),
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
                ),
              if (_settings == null && _error == null)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpace.xxl),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_settings != null) ...[
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
                  title: Text(
                    context.t('settings.verify'),
                    style: AppText.label,
                  ),
                  subtitle: Text(
                    context.t('settings.verifyHelp'),
                    style: AppText.caption.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),

                const SizedBox(height: AppSpace.lg),
                Text(context.t('settings.theme'), style: AppText.label),
                const SizedBox(height: AppSpace.xs),
                Text(
                  context.t('settings.themeHelp'),
                  style: AppText.caption.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: AppSpace.sm),
                ValueListenableBuilder<AppTheme>(
                  valueListenable: appTheme,
                  builder:
                      (context, scheme, _) => SegmentedButton<AppTheme>(
                        segments: [
                          for (final option in AppTheme.values)
                            ButtonSegment(
                              value: option,
                              label: Text(option.label),
                            ),
                        ],
                        selected: {scheme},
                        onSelectionChanged: (values) {
                          appTheme.value = values.first;
                          _savePreferences();
                        },
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
                  builder:
                      (context, preference, _) => SegmentedButton<AppLanguage>(
                        segments: [
                          for (final option in AppLanguage.values)
                            ButtonSegment(
                              value: option,
                              label: Text(option.label),
                            ),
                        ],
                        selected: {preference},
                        onSelectionChanged: (values) {
                          appLanguage.value = values.first;
                          _savePreferences();
                        },
                      ),
                ),

                const SizedBox(height: AppSpace.xl),
                Wrap(
                  spacing: AppSpace.md,
                  runSpacing: AppSpace.sm,
                  children: [
                    HoldButton(
                      emphasized: true,
                      label: context.t('common.save'),
                      icon: Icons.check,
                      busy: _busy,
                      onPressed: _busy ? null : _save,
                    ),
                    HoldButton(
                      label: context.t('common.reload'),
                      icon: Icons.refresh,
                      onPressed: _busy || _pending > 0 ? null : _load,
                    ),
                  ],
                ),

                if (_pending > 0) ...[
                  const SizedBox(height: AppSpace.md),
                  Semantics(
                    liveRegion: true,
                    child: Text(
                      context.t('settings.pending'),
                      style: AppText.label,
                    ),
                  ),
                ],
                if (_pending == 0 && _saved != null) ...[
                  const SizedBox(height: AppSpace.md),
                  Notice(
                    title: context.t(_saved!),
                    tone: AppColors.success(context),
                    icon: Icons.check_circle_outline,
                  ),
                ],

                const SizedBox(height: AppSpace.xl),
                Divider(
                  color: theme.colorScheme.outlineVariant.withValues(
                    alpha: 0.5,
                  ),
                ),
                const SizedBox(height: AppSpace.lg),
                FieldRow(
                  label: context.t('settings.file'),
                  value:
                      'v${_settings!['version']} — ${context.t('settings.fileNote')}',
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
            style: AppText.caption.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
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
