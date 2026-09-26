/// One glass surface, in the design system's own vocabulary.
///
/// Three call sites need glass — the sidebar, the status bar and the modal sheet —
/// and none of them should carry its own `GlassContainer` configuration, because
/// then the "material weight" idea lives only in three sets of literal numbers and
/// drifts the first time one of them is tweaked. This is that idea as one widget:
/// pass a [GlassWeight], get the right blur, tint, radius and shadow for it.
///
/// Two things it keeps from the tonal system it replaces:
///
/// * **The bright hairline.** A one-pixel top edge at low opacity reads as light
///   catching a material, and it is what separates a surface from a flat rectangle.
///   It survives the move to blur because it is doing the same job.
/// * **Two shadows, not one.** A tight shadow seats the panel; a wide soft one
///   lifts it. The skill's point stands — a single mid-sized shadow disappears
///   against a near-black page.
library;

import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import 'design.dart';

class GlassSurface extends StatelessWidget {
  const GlassSurface({
    super.key,
    required this.weight,
    required this.child,
    this.width,
    this.height,
    this.padding,
    this.margin,
    this.alignment,
    this.shape,
  });

  final GlassWeight weight;
  final Widget child;
  final double? width;
  final double? height;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final AlignmentGeometry? alignment;

  /// Overrides the weight's default corner. Only the status bar uses this, to take
  /// a smaller radius than its weight would otherwise imply.
  final LiquidShape? shape;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final radius = GlassMaterial.radiusFor(weight);

    final surface = GlassContainer(
      width: width,
      height: height,
      padding: padding,
      alignment: alignment,
      // `standard` everywhere, including on Impeller: the package caps desktop
      // there anyway, and asking for `premium` on a machine that silently falls
      // back would make the two platforms render differently for no gain.
      quality: GlassQuality.standard,
      shape: shape ?? LiquidRoundedSuperellipse(borderRadius: radius),
      settings: GlassMaterial.settings(context, weight),
      // `true` only where the surface moves independently of what is behind it.
      // The sidebar and the status bar are static; the sheet animates in, and its
      // own compositing layer is what keeps that animation off the raster thread.
      useOwnLayer: weight == GlassWeight.sheet,
      child: child,
    );

    // The stroke and shadows are painted *outside* the glass, so they never enter
    // the shader's sampling region and cannot soften the blur behind them.
    return Container(
      margin: margin,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: AppColors.stroke(context)),
        boxShadow: switch ((weight, dark)) {
          // Structural: seated firmly, so the sidebar reads as a fixed region.
          (GlassWeight.structural, true) => const [
              BoxShadow(color: Color(0x8C000000), blurRadius: 5, offset: Offset(0, 2)),
              BoxShadow(color: Color(0x99000000), blurRadius: 60, offset: Offset(0, 26)),
            ],
          (GlassWeight.structural, false) => const [
              BoxShadow(color: Color(0x1A14202D), blurRadius: 40, offset: Offset(0, 18)),
            ],
          // Bar: a lighter lift, because it is a strip and not a region.
          (GlassWeight.bar, true) => const [
              BoxShadow(color: Color(0x66000000), blurRadius: 4, offset: Offset(0, -1)),
              BoxShadow(color: Color(0x73000000), blurRadius: 24, offset: Offset(0, -8)),
            ],
          (GlassWeight.bar, false) => const [
              BoxShadow(color: Color(0x14000000), blurRadius: 20, offset: Offset(0, -6)),
            ],
          // Sheet: the deepest lift, because it is the thing in front of everything.
          (GlassWeight.sheet, true) => const [
              BoxShadow(color: Color(0x99000000), blurRadius: 8, offset: Offset(0, 4)),
              BoxShadow(color: Color(0xB3000000), blurRadius: 80, offset: Offset(0, 34)),
            ],
          (GlassWeight.sheet, false) => const [
              BoxShadow(color: Color(0x2414202D), blurRadius: 60, offset: Offset(0, 24)),
            ],
        },
      ),
      child: surface,
    );
  }
}

/// The bright top edge, as an overlay.
///
/// Separate from [GlassSurface] because it must be painted *after* the glass and
/// only where a surface has content scrolling under its top edge. A `Border` in the
/// decoration above sits outside the shader; this sits inside, and is what the
/// tonal system used to convey "lit from above".
class GlassTopEdge extends StatelessWidget {
  const GlassTopEdge({super.key, required this.radius, required this.child});

  final double radius;
  final Widget child;

  @override
  Widget build(BuildContext context) => Stack(
        children: [
          child,
          Positioned(
            left: radius * 0.6,
            right: radius * 0.6,
            top: 0,
            child: Container(
              height: 1,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    Colors.white.withValues(alpha: 0.0),
                    Colors.white.withValues(alpha: 0.14),
                    Colors.white.withValues(alpha: 0.0),
                  ],
                ),
              ),
            ),
          ),
        ],
      );
}
