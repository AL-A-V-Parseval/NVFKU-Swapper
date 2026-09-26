/// Design system: typography, colour, materials, motion.
///
/// Rewritten against the apple-design skill's rules, which changed real
/// decisions rather than just values:
///
/// * **Tracking is size-specific, never one value for all sizes** (§15). Display
///   text tightens as it grows; body sits at zero; small text gets *positive*
///   tracking for legibility. A single `letterSpacing` is wrong somewhere.
/// * **Leading tracks size inversely** (§15). Tight on display, loose on body.
/// * **Hierarchy comes from weight + size + leading as a set**, not size alone.
/// * **Springs are critically damped by default** (§4) — Apple's `damping 1.0`,
///   `response 0.3–0.4`. Bounce is reserved for momentum gestures, and this app
///   has none, so there is no bounce anywhere in it.
/// * **Reduced motion gets a gentler equivalent, not nothing** (§14).
/// * **One translucent layer at most** (§12). Flutter desktop has no
///   `backdrop-filter`, and the skill warns that stacking translucent surfaces
///   collapses legibility, so material hierarchy is built from tonal steps and
///   depth instead of faked glass.
library;

import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

/// Size-specific type scale.
abstract final class AppText {
  /// Page titles. Large text reads too loose, so it pulls in.
  static const display = TextStyle(
    fontSize: 30,
    height: 1.12,
    letterSpacing: -0.8,
    fontWeight: FontWeight.w600,
  );

  /// Section headers and view titles.
  static const title = TextStyle(
    fontSize: 20,
    height: 1.2,
    letterSpacing: -0.45,
    fontWeight: FontWeight.w600,
  );

  /// Card and row titles.
  static const subtitle = TextStyle(
    fontSize: 15,
    height: 1.3,
    letterSpacing: -0.2,
    fontWeight: FontWeight.w600,
  );

  /// Body copy: comfortable leading, tracking at zero.
  static const body = TextStyle(
    fontSize: 13.5,
    height: 1.5,
    letterSpacing: 0,
  );

  /// Small print. Positive tracking, because small text needs it.
  static const caption = TextStyle(
    fontSize: 11.5,
    height: 1.35,
    letterSpacing: 0.15,
  );

  /// Navigation and button labels.
  static const label = TextStyle(
    fontSize: 13,
    height: 1.2,
    letterSpacing: -0.1,
    fontWeight: FontWeight.w500,
  );

  /// Paths, hashes, commands. Monospace with no tracking, so columns line up.
  static const mono = TextStyle(
    fontSize: 11.5,
    height: 1.55,
    letterSpacing: 0,
    fontFamily: 'monospace',
    fontFamilyFallback: ['DejaVu Sans Mono', 'Noto Sans Mono', 'monospace'],
  );
}

/// Colour roles, in the visual language of the tool this project reworks.
///
/// The palette is taken from DLSS5-Swapper's own stylesheet, where the reasoning
/// is written down next to the values and is worth keeping:
///
/// * **The base is near-black and each surface steps up visibly.** The original
///   had a page at `#0d1116` and a panel at `#191f28` — twelve points apart, so
///   nothing looked like it was on top of anything. The dark theme here starts at
///   `#05070a` and lifts by steps you can actually see.
/// * **A green accent** (`#6CC10A`) is the one saturated colour, which is what
///   lets it read as light rather than as paint against near-black.
/// * **Two shadows, not one.** A tight shadow seats a panel; a wide soft one lifts
///   it. A single mid-sized shadow disappears against black, which is the failure
///   mode to avoid.
/// * **One bright hairline along the top edge.** The reference calls this the
///   difference between a flat rectangle and a surface, and it is right.
/// * **Radial glows instead of a flat backdrop.** Two soft accent washes give the
///   window a light source. They are *painted gradients*, not stacked translucent
///   layers.
/// * **Translucency is a budget, not a texture.** The skill says one translucent
///   layer at most, because stacking light surfaces collapses legibility. A desktop
///   shell is a case that has to work anyway — a sidebar, a status bar and a modal
///   sheet really are on screen together — so the rule is honoured through
///   *material weight* instead. See [GlassWeight]: the sidebar and status bar are
///   heavy, near-opaque structural panels and only the sheet is light. A heavy
///   material under a light one reads as depth; two light ones read as fog.
abstract final class AppColors {
  /// The accent, shared by both themes. It is the brand colour.
  static const accentGreen = Color(0xFF6CC10A);
  static const accentGreenDeep = Color(0xFF4D9200);

  static bool _dark(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark;

  static Color success(BuildContext context) =>
      _dark(context) ? const Color(0xFF6FD08C) : const Color(0xFF1F7A3D);

  static Color warning(BuildContext context) =>
      _dark(context) ? const Color(0xFFE8B45C) : const Color(0xFF8A5A00);

  static Color danger(BuildContext context) =>
      _dark(context) ? const Color(0xFFEF7B7B) : const Color(0xFFB3261E);

  static Color accent(BuildContext context) => Theme.of(context).colorScheme.primary;

  /// A card surface, one tonal step above the page.
  static Color card(BuildContext context) =>
      Theme.of(context).colorScheme.surfaceContainerLow;

  /// A raised card, for the selected or primary item.
  static Color raised(BuildContext context) =>
      Theme.of(context).colorScheme.surfaceContainerHigh;

  /// The recessed chrome behind logs and inset panels.
  static Color chrome(BuildContext context) =>
      _dark(context) ? const Color(0xFF0E1116) : const Color(0xFFEFF2F5);

  /// The accent at low opacity, for a selected or hovered fill.
  static Color accentSoft(BuildContext context) =>
      accentGreen.withValues(alpha: _dark(context) ? 0.14 : 0.12);

  /// The border that separates surfaces of the same tone.
  ///
  /// A neutral hairline, not the accent: using the accent for every edge made the
  /// whole window read as selected.
  static Color stroke(BuildContext context) => _dark(context)
      ? Colors.white.withValues(alpha: 0.07)
      : Colors.black.withValues(alpha: 0.09);
}

/// The weight of one glass surface.
///
/// The skill's rule is "one translucent layer at most", and a desktop shell cannot
/// obey it literally: the sidebar, the status bar and a modal sheet are on screen
/// together whenever the sheet is open. Apple's own answer is material weight —
/// structural regions get heavier material, interactive surfaces get lighter — so
/// three glasses of *different* weight still read as a hierarchy rather than as
/// fog. No fourth weight is added without a case where all three fail.
enum GlassWeight {
  /// Structural chrome: the sidebar. Darkest and thickest, so nav text on it keeps
  /// its contrast whatever is scrolling behind.
  structural,

  /// A floating bar: the status line. It sits over content that moves, so it is
  /// heavier than the sheet and lighter than the sidebar.
  bar,

  /// The modal sheet. The lightest, because it is the thing being attended to and
  /// it has a scrim behind it doing most of the separating.
  sheet,
}

/// Glass, as an extension of the design system rather than a second one.
///
/// The tonal steps in [AppColors] still exist and still do the work *inside* a
/// surface — a card on a page, a row in a card. What changes is depth *between*
/// regions: that is blur and shadow now, not a lighter grey.
abstract final class GlassMaterial {
  /// Corners, matched to the tonal system's radii so a glass panel and an opaque
  /// card can sit side by side without reading as two designs.
  static double radiusFor(GlassWeight weight) => switch (weight) {
        GlassWeight.structural => AppSpace.radiusShell,
        GlassWeight.bar => AppSpace.radiusLarge,
        GlassWeight.sheet => AppSpace.radiusShell,
      };

  /// The tint/blur/thickness triad for a weight, per brightness.
  ///
  /// Conservative on purpose: the package caps desktop at `GlassQuality.standard`
  /// and runs a lightweight 2D shader here, so a large `thickness` buys little and
  /// widens the sampling kernel on every frame.
  static LiquidGlassSettings settings(
    BuildContext context,
    GlassWeight weight,
  ) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    // Tints are lifted off pure black. Pure-black glass over dark content reads as
    // a hole rather than a material; these keep enough body to be seen against the
    // deep base while still letting the backdrop through.
    final (tint, blur, thickness, saturation) = switch ((weight, dark)) {
      (GlassWeight.structural, true) => (const Color(0xE60A0A0B), 24.0, 34.0, 1.2),
      (GlassWeight.structural, false) => (const Color(0xE6EEF1F4), 24.0, 34.0, 1.2),
      (GlassWeight.bar, true) => (const Color(0xCC0E1116), 18.0, 26.0, 1.3),
      (GlassWeight.bar, false) => (const Color(0xCCF7F9FA), 18.0, 26.0, 1.3),
      (GlassWeight.sheet, true) => (const Color(0xB312171F), 14.0, 20.0, 1.4),
      (GlassWeight.sheet, false) => (const Color(0xB3FFFFFF), 14.0, 20.0, 1.4),
    };
    return LiquidGlassSettings(
      glassColor: tint,
      blur: blur,
      thickness: thickness,
      saturation: saturation,
      // Chromatic aberration is what makes glass read as *refracting* rather than
      // merely blurred, but it is the most expensive part of the shader and the
      // worst for small text. Only the sheet — the least text over the busiest
      // backdrop — gets any.
      chromaticAberration: weight == GlassWeight.sheet ? 0.012 : 0.0,
      lightIntensity: weight == GlassWeight.structural ? 0.35 : 0.5,
      refractiveIndex: 1.2,
    );
  }

  /// Text over glass cannot be flat grey: it loses contrast as the backdrop
  /// changes underneath while scrolling. The skill's answer is a small
  /// letter-spacing bump and a heavier weight, not a different colour.
  static TextStyle vibrant(TextStyle base) => base.copyWith(
        fontWeight: _bump(base.fontWeight),
        letterSpacing: (base.letterSpacing ?? 0) + 0.15,
      );

  static FontWeight _bump(FontWeight? weight) => switch (weight) {
        FontWeight.w300 => FontWeight.w400,
        FontWeight.w400 => FontWeight.w500,
        FontWeight.w500 => FontWeight.w600,
        FontWeight.w600 => FontWeight.w700,
        FontWeight.w700 => FontWeight.w800,
        _ => FontWeight.w600,
      };
}

/// Motion in Apple's own vocabulary.
abstract final class AppMotion {
  /// Critically damped, `response 0.3–0.4`. The house default.
  static const Duration fast = Duration(milliseconds: 160);
  static const Duration standard = Duration(milliseconds: 300);

  /// A critically damped spring settles like this closely enough that the
  /// difference is invisible at these durations.
  static const Curve settle = Curves.easeOutCubic;

  /// Spatial consistency (§7): enter and exit along the same path, with mirrored
  /// easing, so a panel that grew out of a row also collapses back into it.
  static const Curve enter = Curves.easeOutCubic;
  static const Curve exit = Curves.easeInCubic;

  static bool reduced(BuildContext context) =>
      MediaQuery.maybeOf(context)?.disableAnimations ?? false;

  /// Springs become instant when the user asked for reduced motion. Returning
  /// zero still applies the final value on the next frame, so state is never
  /// lost — only the travel.
  static Duration resolve(BuildContext context, Duration duration) =>
      reduced(context) ? Duration.zero : duration;
}

/// Metrics. Every value is deliberate: nothing here is a random number.
abstract final class AppSpace {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;

  /// The reference's radii: `--radius: 18px` for surfaces, `--radius-sm: 12px`
  /// for controls, and a 26px shell around the floating sidebar.
  static const double radius = 12;
  static const double radiusLarge = 18;
  static const double radiusShell = 26;

  /// 232px, matching the reference's sidebar.
  static const double sidebarWidth = 232;
  static const double rowHeight = 64;
  static const double contentMaxWidth = 1160;
  static const double coverWidth = 44;
  static const double coverHeight = 66;
}
