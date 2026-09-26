import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import 'src/app.dart';

/// The glass shaders are loaded before the first frame.
///
/// `LiquidGlassWidgets.initialize()` only reads shader bytecode from disk into
/// memory — no GPU work — and without it the first painted frames show the
/// un-shaded fallback while the programs compile, which on a launch screen looks
/// like a rendering bug rather than a warm-up.
///
/// `warmUpMode` is left at its `auto` default on purpose: the package skips the
/// multi-pass shaders on Linux and web, which are capped at `GlassQuality.standard`
/// there, so forcing them would load bytecode this platform never draws with.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await LiquidGlassWidgets.initialize();
  runApp(const Dlss5CtlApp());
}
