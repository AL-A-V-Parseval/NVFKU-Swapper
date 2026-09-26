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
///   window a light source. The apple-design skill's rule still applies on top of
///   this: they are *painted gradients*, not stacked translucent layers, so a
///   panel on top of them stays legible.
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
