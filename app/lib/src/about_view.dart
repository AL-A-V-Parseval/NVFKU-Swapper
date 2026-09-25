/// About: what this is, what it can and cannot do, and what it stands on.
///
/// The reference has an About page that states its purpose in one sentence and
/// links out. This one does the same, plus the one thing a user of *this* tool
/// needs before trusting it: the two constraints that decide whether it can help
/// at all. Wine's Vulkan loader not enumerating layers is not a footnote — it is
/// the reason the route list is shaped the way it is, and hiding it turns a
/// predictable refusal into a mystery.
library;

import 'package:flutter/material.dart';

import 'design.dart';
import 'l10n.dart';
import 'widgets.dart';

class AboutView extends StatelessWidget {
  const AboutView({super.key, required this.version});

  /// Reported by the engine, so the page cannot disagree with the binary.
  final String? version;

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
          constraints: const BoxConstraints(maxWidth: 720),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(context.t('app.title'), style: AppText.display),
                  const SizedBox(width: AppSpace.md),
                  StatusPill(
                    label: version ?? '—',
                    tone: AppColors.accentGreen,
                  ),
                ],
              ),
              const SizedBox(height: AppSpace.sm),
              Text(
                context.t('about.tagline'),
                style: AppText.body.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: AppSpace.xxl),

              // Two coloured notice panels used to sit here. They made the page
              // read as a warning rather than an About, and one of them repeated
              // what a blocked route already says on its own card. A single line
              // stays because the Vulkan limitation is what explains the shape of
              // the route list at all.
              Text(
                context.t('about.whyTwoRoutes'),
                style: AppText.body.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: AppSpace.xxl),
              SectionHeader(title: context.t('about.standsOnTitle')),
              // Project and author names stay as they are written; only the
              // descriptive tail is localised.
              for (final line in [
                'ReShade 6.8.0 — crosire, BSD 3-Clause',
                'dlss5-bridge — NIGos',
                'addon-dlssnr-linux — NapXDD',
                'OptiScaler — ${context.t('about.byOptiscaler')}',
              ])
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpace.xs),
                  child: Text('• $line', style: AppText.body),
                ),

              const SizedBox(height: AppSpace.xl),
              Divider(color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5)),
              const SizedBox(height: AppSpace.lg),
              Text(
                context.t('about.undoNote'),
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

