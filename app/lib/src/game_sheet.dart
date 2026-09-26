/// The game sheet: a modal panel over the library.
///
/// This replaces a full-page detail view. Two things improve, and both come from
/// the tool this project reworks:
///
/// * **You keep your place.** The library, its filter and its scroll position stay
///   behind the panel, so closing it returns you exactly where you were. A
///   full-page view threw that away on every click.
/// * **The install decision has a home.** The panel carries the hero, the facts,
///   the routes, the plan and the Steam launch options in one column, in the order
///   a person asks about them, instead of splitting them across a page and a
///   modal.
///
/// The backdrop is a flat scrim, not a blur. Flutter desktop has no
/// `backdrop-filter`, and the apple-design skill warns that stacking translucent
/// surfaces collapses legibility — so depth comes from the scrim's opacity and the
/// panel's shadow, honestly, rather than from faking glass.
library;

import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:flutter/services.dart';

import 'cover.dart';
import 'design.dart';
import 'engine.dart';
import 'game_detail.dart';
import 'l10n.dart';
import 'models.dart';

class GameSheet extends StatefulWidget {
  const GameSheet({
    super.key,
    required this.game,
    required this.engine,
    required this.onClose,
    required this.onChanged,
    this.coverPath,
    this.startAtInstall = false,
    this.onLoaded,
    this.component,
    this.onOpenInstall,
    this.onComponentDone,
  });

  final Game game;

  /// Cached cover image for this game, if one was found.
  final String? coverPath;
  final Engine engine;
  final VoidCallback onClose;
  final Future<void> Function() onChanged;

  /// Scrolls to the install panel on open, for a card's install button.
  final bool startAtInstall;
  final VoidCallback? onLoaded;

  /// A component that asked to be installed, and the callbacks that drive it.
  final String? component;
  final void Function(String route)? onOpenInstall;
  final VoidCallback? onComponentDone;

  @override
  State<GameSheet> createState() => _GameSheetState();
}

class _GameSheetState extends State<GameSheet> {
  final ScrollController _scroll = ScrollController();
  final FocusNode _focus = FocusNode(debugLabel: 'game-sheet');

  @override
  void initState() {
    super.initState();
    _focus.requestFocus();
    if (widget.startAtInstall) {
      // The panel is not laid out yet, so jump after the first frame rather than
      // guessing an offset.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.jumpTo(_scroll.position.maxScrollExtent * 0.5);
        }
      });
    }
  }

  @override
  void dispose() {
    _scroll.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;

    return Focus(
      focusNode: _focus,
      onKeyEvent: (node, event) {
        if (event is KeyDownEvent &&
            event.logicalKey == LogicalKeyboardKey.escape) {
          widget.onClose();
          return KeyEventResult.handled;
        }
        return KeyEventResult.ignored;
      },
      child: Stack(
        children: [
          // Scrim. Also the click target that closes the panel.
          Positioned.fill(
            child: GestureDetector(
              onTap: widget.onClose,
              behavior: HitTestBehavior.opaque,
              child: ColoredBox(
                color: Colors.black.withValues(alpha: dark ? 0.66 : 0.38),
              ),
            ),
          ),
          Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: AppSpace.xl),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 720),
                child: Material(
                  // Transparent on purpose: this Material exists only to be an
                  // ancestor for the dialogs and popup menus the sheet hosts. The
                  // surface itself is the glass below.
                  type: MaterialType.transparency,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(
                        GlassMaterial.radiusFor(GlassWeight.sheet),
                      ),
                      border: Border.all(color: AppColors.stroke(context)),
                      boxShadow: dark
                          ? const [
                              BoxShadow(
                                color: Color(0x8C000000),
                                blurRadius: 5,
                                offset: Offset(0, 2),
                              ),
                              BoxShadow(
                                color: Color(0xB3000000),
                                blurRadius: 70,
                                offset: Offset(0, 30),
                              ),
                            ]
                          : const [
                              BoxShadow(
                                color: Color(0x2614202D),
                                blurRadius: 50,
                                offset: Offset(0, 20),
                              ),
                            ],
                    ),
                    child: GlassContainer(
                      // Sheet weight: the lightest material of the three, because
                      // the scrim behind it is doing the separating. Radius,
                      // stroke and the two shadows come from the weight, so this
                      // panel cannot drift from the sidebar's.
                      quality: GlassQuality.standard,
                      shape: LiquidRoundedSuperellipse(
                        borderRadius: GlassMaterial.radiusFor(GlassWeight.sheet),
                      ),
                      settings: GlassMaterial.settings(
                        context,
                        GlassWeight.sheet,
                      ),
                      // The sheet animates in, so its own compositing layer keeps
                      // that motion off the raster thread.
                      useOwnLayer: true,
                      clipBehavior: Clip.antiAlias,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                      children: [
                        _Hero(
                          game: widget.game,
                          coverPath: widget.coverPath,
                          onClose: widget.onClose,
                        ),
                        Flexible(
                          child: GameDetailView(
                            game: widget.game,
                            engine: widget.engine,
                            onBack: widget.onClose,
                            onChanged: widget.onChanged,
                            onLoaded: widget.onLoaded,
                            scrollController: _scroll,
                            embedded: true,
                            component: widget.component,
                            onOpenInstall: widget.onOpenInstall,
                            onComponentDone: widget.onComponentDone,
                          ),
                        ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The banner, the cover and the title.
///
/// A game with no wide artwork gets a tinted band of the same height rather than a
/// shorter header, so the panel does not change shape depending on whether a cover
/// was ever published.
class _Hero extends StatelessWidget {
  const _Hero({
    required this.game,
    required this.coverPath,
    required this.onClose,
  });

  final Game game;
  final String? coverPath;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    const height = 168.0;

    return SizedBox(
      height: height,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: dark
                      ? const [Color(0xFF1C2A10), Color(0xFF12171F)]
                      : const [Color(0xFFDDF3BC), Color(0xFFF1F5F8)],
                ),
              ),
            ),
          ),
          Positioned(
            left: AppSpace.xl,
            bottom: -34,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Container(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(AppSpace.radius),
                    boxShadow: const [
                      BoxShadow(
                        color: Color(0x66000000),
                        blurRadius: 18,
                        offset: Offset(0, 6),
                      ),
                    ],
                  ),
                  child: CoverThumb(
                    path: coverPath,
                    name: game.name,
                    width: 92,
                    height: 138,
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            right: AppSpace.md,
            top: AppSpace.md,
            child: _RoundButton(
              icon: Icons.close,
              tooltip: context.t('common.close'),
              onPressed: onClose,
            ),
          ),
        ],
      ),
    );
  }
}

class _RoundButton extends StatelessWidget {
  const _RoundButton({
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Tooltip(
      message: tooltip,
      child: Material(
        color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.7),
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          child: SizedBox(
            width: 32,
            height: 32,
            child: Icon(icon, size: 17, color: theme.colorScheme.onSurface),
          ),
        ),
      ),
    );
  }
}
