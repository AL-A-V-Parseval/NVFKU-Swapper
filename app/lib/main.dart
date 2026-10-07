import 'package:flutter/material.dart';

import 'src/app.dart';
import 'src/engine.dart';
import 'src/l10n.dart';

/// The stored appearance is applied before the first frame.
///
/// Loading it from an `initState` instead would paint one frame in the default theme
/// and then switch, which reads as the app ignoring the setting for a moment.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final engine = Engine();
  await loadStoredPreferences(engine);
  runApp(Dlss5CtlApp(engine: engine));
}
