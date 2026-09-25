/// Shared widgets.
///
/// Each encodes a rule from the design spec rather than being a generic
/// container. The two that matter most:
///
/// * [HoldButton] answers on **pointer-down**, not on release (§1 Response).
///   Installing is slow, so a button that waits for the process to start reads
///   as broken. The press is animated, but with **no bounce** — nothing here was
///   flicked, and §4 reserves overshoot for momentum gestures.
/// * [StatusPill] carries a word *and* a tone, so state never depends on colour
///   alone (§14 accessibility, and §16 Familiarity: predictability).
library;

import 'dart:io';

import 'package:flutter/material.dart';

import 'design.dart';
import 'l10n.dart';

/// A button that shows its pressed state immediately.
class HoldButton extends StatefulWidget {
  const HoldButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
    this.emphasized = false,
    this.busy = false,
    this.tooltip,
    this.dense = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool emphasized;
  final bool busy;
  final String? tooltip;
  final bool dense;

  @override
  State<HoldButton> createState() => _HoldButtonState();
}

class _HoldButtonState extends State<HoldButton> {
  bool _down = false;

  @override
  Widget build(BuildContext context) {
    final enabled = widget.onPressed != null && !widget.busy;
    final scale = _down && enabled ? 0.97 : 1.0;

    final child = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.busy)
          SizedBox(
            width: widget.dense ? 12 : 14,
            height: widget.dense ? 12 : 14,
            child: const CircularProgressIndicator(strokeWidth: 2),
          )
        else if (widget.icon != null)
          Icon(widget.icon, size: widget.dense ? 15 : 17),
        if (widget.busy || widget.icon != null)
          SizedBox(width: widget.dense ? AppSpace.xs + 2 : AppSpace.sm),
        Text(widget.dense ? widget.label : widget.label, style: AppText.label),
      ],
    );

    final button = widget.emphasized
        ? FilledButton(
            onPressed: enabled ? widget.onPressed : null,
            style: _style(context),
            child: child,
          )
        : OutlinedButton(
            onPressed: enabled ? widget.onPressed : null,
            style: _style(context),
            child: child,
          );

    final wrapped = AnimatedScale(
      scale: scale,
      // Critically damped and short: this is feedback, not decoration.
      duration: AppMotion.resolve(context, const Duration(milliseconds: 90)),
      curve: AppMotion.settle,
      child: Listener(
        onPointerDown: enabled ? (_) => setState(() => _down = true) : null,
        onPointerUp: (_) => setState(() => _down = false),
        onPointerCancel: (_) => setState(() => _down = false),
        child: MouseRegion(
          onExit: (_) => setState(() => _down = false),
          child: button,
        ),
      ),
    );

    final tip = widget.tooltip;
    return tip == null ? wrapped : Tooltip(message: tip, child: wrapped);
  }

  ButtonStyle _style(BuildContext context) {
    final padding = widget.dense
        ? const EdgeInsets.symmetric(horizontal: AppSpace.md, vertical: AppSpace.xs)
        : const EdgeInsets.symmetric(horizontal: AppSpace.lg, vertical: AppSpace.sm + 2);
    return ButtonStyle(
      padding: WidgetStatePropertyAll(padding),
      minimumSize: const WidgetStatePropertyAll(Size(0, 0)),
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      visualDensity: VisualDensity.compact,
    );
  }
}

/// A small state chip. Always carries a word, never colour alone.
class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.label, this.tone});

  final String label;
  final Color? tone;

  @override
  Widget build(BuildContext context) {
    final colour = tone ?? Theme.of(context).colorScheme.onSurfaceVariant;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: colour.withValues(alpha: 0.13),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Text(label, style: AppText.caption.copyWith(color: colour)),
    );
  }
}

/// A labelled value line, used throughout the detail and settings views.
class FieldRow extends StatelessWidget {
  const FieldRow({
    super.key,
    required this.label,
    required this.value,
    this.mono = false,
    this.valueColour,
    this.trailing,
    this.labelWidth = 148,
  });

  final String label;
  final String value;
  final bool mono;
  final Color? valueColour;
  final Widget? trailing;
  final double labelWidth;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: labelWidth,
            child: Text(
              label,
              style: AppText.caption.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(
            child: SelectableText(
              value,
              style: (mono ? AppText.mono : AppText.body).copyWith(color: valueColour),
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

/// A section heading with an optional trailing action.
class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.trailing,
  });

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: AppText.title),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    subtitle!,
                    style: AppText.caption.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

/// An empty state that says what to do next (§16 Wayfinding).
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.title,
    required this.body,
    this.icon = Icons.inbox_outlined,
    this.action,
  });

  final String title;
  final String body;
  final IconData icon;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 38, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(height: AppSpace.lg),
            Text(title, style: AppText.title, textAlign: TextAlign.center),
            const SizedBox(height: AppSpace.sm),
            Text(
              body,
              style: AppText.body.copyWith(color: theme.colorScheme.onSurfaceVariant),
              textAlign: TextAlign.center,
            ),
            if (action != null) ...[
              const SizedBox(height: AppSpace.lg),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}

/// A banner for the four kinds of feedback: status, warning, error, done.
class Notice extends StatelessWidget {
  const Notice({
    super.key,
    required this.title,
    this.body,
    this.mono,
    required this.tone,
    this.icon,
    this.actions = const [],
  });

  final String title;
  final String? body;
  final String? mono;
  final Color tone;
  final IconData? icon;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpace.md),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.08),
        border: Border.all(color: tone.withValues(alpha: 0.33)),
        borderRadius: BorderRadius.circular(AppSpace.radius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (icon != null) ...[
                Icon(icon, size: 16, color: tone),
                const SizedBox(width: AppSpace.sm),
              ],
              Expanded(
                child: Text(
                  title,
                  style: AppText.label.copyWith(color: tone, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          if (body != null) ...[
            const SizedBox(height: AppSpace.xs),
            Text(body!, style: AppText.body),
          ],
          if (mono != null) ...[
            const SizedBox(height: AppSpace.sm),
            SelectableText(mono!, style: AppText.mono),
          ],
          if (actions.isNotEmpty) ...[
            const SizedBox(height: AppSpace.md),
            Row(children: actions),
          ],
        ],
      ),
    );
  }
}

/// Whether the current platform can accept a dropped path at all.
///
/// Drag-and-drop from the desktop into a Flutter window depends on the
/// embedder; this reports what is actually true rather than assuming, so the UI
/// can say "use Add folder" instead of silently doing nothing.
bool get dragAndDropSupported => Platform.isLinux || Platform.isMacOS || Platform.isWindows;


/// Asks for a game folder path.
///
/// Text rather than a native file picker: this project has no file-picker
/// dependency, and a native dialog on Linux would need a portal that this
/// machine's compositor does not provide. Typing or pasting a path is the honest
/// substitute, and drag-and-drop covers the common case anyway.
///
/// Returns null when the user cancels, or an empty string if they confirm an empty
/// field.
Future<String?> promptForGameFolder(BuildContext context) async {
  final controller = TextEditingController();
  try {
    return await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(context.t('games.addTitle')),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(context.t('games.addBody'), style: AppText.body),
              const SizedBox(height: AppSpace.md),
              TextField(
                controller: controller,
                autofocus: true,
                style: AppText.mono,
                decoration: InputDecoration(hintText: context.t('games.addHint')),
                onSubmitted: (value) => Navigator.of(context).pop(value),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(context.t('common.cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(controller.text),
            child: Text(context.t('games.add')),
          ),
        ],
      ),
    );
  } finally {
    controller.dispose();
  }
}

/// A collapsed section that opens on demand.
///
/// Two things in this app are true and useful but not wanted on every visit: the
/// engine's reasoning (checks, actions, logs) and, on a blocked route, why it is
/// blocked. Both were previously always visible, which made the common case — a
/// route that is simply ready — read as a wall of diagnostics.
///
/// The disclosure is deliberately quiet: a chevron, a label, and a one-line hint.
/// A blocked route uses [tone] so its reason is the one thing that draws the eye.
class Disclosure extends StatefulWidget {
  const Disclosure({
    super.key,
    required this.label,
    required this.child,
    this.hint,
    this.tone,
    this.icon,
    this.initiallyOpen = false,
    this.dense = false,
  });

  final String label;

  /// Shown next to the label while collapsed. Keep it short: it is the reason to
  /// open, not the content.
  final String? hint;

  /// Colours the row and its chevron. Set it when the content is a problem.
  final Color? tone;
  final IconData? icon;
  final bool initiallyOpen;
  final bool dense;
  final Widget child;

  @override
  State<Disclosure> createState() => _DisclosureState();
}

class _DisclosureState extends State<Disclosure> {
  late bool _open = widget.initiallyOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tone = widget.tone;
    final labelColour = tone ?? theme.colorScheme.onSurfaceVariant;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        MouseRegion(
          cursor: SystemMouseCursors.click,
          child: GestureDetector(
            onTap: () => setState(() => _open = !_open),
            behavior: HitTestBehavior.opaque,
            child: Padding(
              padding: EdgeInsets.symmetric(
                vertical: widget.dense ? 4 : AppSpace.xs,
              ),
              child: Row(
                children: [
                  // Size changes with state, which is the whole affordance: a
                  // rotating chevron animates without saying whether it is open.
                  AnimatedRotation(
                    turns: _open ? 0.25 : 0,
                    duration: AppMotion.resolve(context, AppMotion.fast),
                    curve: AppMotion.settle,
                    child: Icon(
                      Icons.chevron_right,
                      size: 18,
                      color: labelColour,
                    ),
                  ),
                  const SizedBox(width: 6),
                  if (widget.icon != null) ...[
                    Icon(widget.icon, size: 15, color: labelColour),
                    const SizedBox(width: 6),
                  ],
                  Text(
                    widget.label,
                    style: AppText.label.copyWith(
                      color: labelColour,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (widget.hint != null && !_open) ...[
                    const SizedBox(width: AppSpace.sm),
                    Flexible(
                      child: Text(
                        widget.hint!,
                        style: AppText.caption.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
        // Height-animated rather than conditionally built, so opening does not
        // jump the page under the pointer.
        AnimatedSize(
          duration: AppMotion.resolve(context, AppMotion.standard),
          curve: AppMotion.settle,
          alignment: Alignment.topLeft,
          child: _open
              ? Padding(
                  padding: const EdgeInsets.only(top: AppSpace.sm, left: 24),
                  child: widget.child,
                )
              : const SizedBox(width: double.infinity),
        ),
      ],
    );
  }
}
