/// Add-ons: the components, their versions, and their pinned digests.
///
/// This is Swapper's "Add-ons" page translated. It exists because the tool's most
/// common failure is not a missing route but a *wrong build* of something — the
/// DLSS NR model in particular, where the add-on's author documented that a
/// mismatched model "reported Success on every evaluate and then crashed the game
/// minutes into gameplay". Showing the digest the tool will verify against, before
/// anything is installed, is the honest version of that page.
library;

import 'package:flutter/material.dart';

import 'design.dart';
import 'engine.dart';
import 'l10n.dart';
import 'models.dart';
import 'widgets.dart';

class AddonsView extends StatefulWidget {
  const AddonsView({super.key, required this.engine});

  final Engine engine;

  @override
  State<AddonsView> createState() => _AddonsViewState();
}

class _AddonsViewState extends State<AddonsView> {
  List<ProviderRow>? _rows;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool resolve = true}) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await widget.engine.providers(resolve: resolve);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } on EngineException catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final rows = _rows;
    final pinned = rows?.where((r) => r.pinned).toList() ?? const [];
    final rolling = rows?.where((r) => !r.pinned).toList() ?? const [];

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(AppSpace.xl, AppSpace.xl, AppSpace.xl, AppSpace.xxl),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: AppSpace.contentMaxWidth),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SectionHeader(
                title: context.t('addons.title'),
                subtitle: context.t('addons.subtitle'),
                trailing: HoldButton(
                  label: context.t('common.refresh'),
                  icon: Icons.refresh,
                  busy: _loading,
                  onPressed: _loading ? null : () => _load(),
                ),
              ),

              if (_error != null)
                Notice(
                  title: context.t('addons.readError'),
                  mono: _error,
                  tone: AppColors.danger(context),
                  icon: Icons.error_outline,
                  actions: [
                    TextButton(onPressed: () => _load(), child: Text(context.t('common.tryAgain'))),
                  ],
                )
              else if (rows == null)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpace.xxl),
                  child: Center(child: CircularProgressIndicator()),
                )
              else ...[
                Text(
                  'Pinned',
                  style: AppText.label.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
                const SizedBox(height: AppSpace.sm),
                Text(
                  context.t('addons.pinnedNote'),
                  style: AppText.caption.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: AppSpace.md),
                for (final row in pinned) _ComponentCard(row: row),

                const SizedBox(height: AppSpace.xl),
                Text(
                  'Rolling',
                  style: AppText.label.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
                const SizedBox(height: AppSpace.sm),
                Text(
                  context.t('addons.rollingNote'),
                  style: AppText.caption.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: AppSpace.md),
                for (final row in rolling) _ComponentCard(row: row),

                const SizedBox(height: AppSpace.xl),
                Notice(
                  title: context.t('addons.neverTitle'),
                  body: context.t('addons.neverBody'),
                  tone: AppColors.accent(context),
                  icon: Icons.shield_outlined,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _ComponentCard extends StatelessWidget {
  const _ComponentCard({required this.row});

  final ProviderRow row;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
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
              Expanded(
                child: Text(row.key, style: AppText.subtitle),
              ),
              StatusPill(
                label: context.t(row.pinned ? 'addons.pinnedPill' : 'addons.rollingPill'),
                tone: row.pinned ? AppColors.success(context) : null,
              ),
              const SizedBox(width: AppSpace.sm),
              Text(row.version, style: AppText.mono),
            ],
          ),
          if (row.error != null) ...[
            const SizedBox(height: AppSpace.sm),
            Text(
              row.error!,
              style: AppText.caption.copyWith(color: AppColors.warning(context)),
            ),
          ],
          if (row.sha256 != null) ...[
            const SizedBox(height: AppSpace.sm),
            SelectableText(
              row.sha256!,
              style: AppText.mono.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
          if (row.size != null) ...[
            const SizedBox(height: AppSpace.xs),
            Text(
              _humanSize(row.size!),
              style: AppText.caption.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
          if (row.url != null) ...[
            const SizedBox(height: AppSpace.xs),
            SelectableText(
              row.url!,
              style: AppText.mono.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
              maxLines: 2,
            ),
          ],
        ],
      ),
    );
  }

  String _humanSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    final kib = bytes / 1024;
    if (kib < 1024) return '${kib.toStringAsFixed(1)} KiB';
    return '${(kib / 1024).toStringAsFixed(1)} MiB';
  }
}
