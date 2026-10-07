/// The appearance preference must survive a restart, and must reach the engine.
///
/// This runs the real engine process rather than a fake, because the failure that
/// motivated it was a real one: the language picker wrote to an in-memory notifier
/// and nothing else, so the docstring's claim that the choice was stored was false
/// and every launch came back as "system". A fake would have reproduced the same
/// cheerful success.
library;

import 'dart:io';

import 'package:flutter/material.dart' show ThemeMode;
import 'package:flutter_test/flutter_test.dart';

import 'package:nvfku_ui/src/engine.dart';
import 'package:nvfku_ui/src/l10n.dart';

import 'support/engine_fixture.dart';

void main() {
  final projectRoot = engineCheckoutRoot();

  late Directory state;
  late Engine engine;

  setUp(() {
    state = Directory.systemTemp.createTempSync('nvfku-appearance-');
    engine = Engine(projectRoot: projectRoot, stateDir: state.path);
  });

  tearDown(() => state.deleteSync(recursive: true));

  group('AppTheme', () {
    test('every value maps to a ThemeMode', () {
      expect(AppTheme.system.mode, ThemeMode.system);
      expect(AppTheme.light.mode, ThemeMode.light);
      expect(AppTheme.dark.mode, ThemeMode.dark);
    });

    test('the codes match what the engine accepts', () {
      // These strings are the contract with `Settings.THEMES` in
      // engine/nvfku/settings.py. A mismatch would surface as a rejected write.
      expect(AppTheme.system.code, 'system');
      expect(AppTheme.light.code, 'light');
      expect(AppTheme.dark.code, 'dark');
    });

    test('an unknown code falls back to system rather than throwing', () {
      expect(AppThemeX.fromCode('nonsense'), AppTheme.system);
      expect(AppThemeX.fromCode(null), AppTheme.system);
    });

    test('round trips through its code', () {
      for (final value in AppTheme.values) {
        expect(AppThemeX.fromCode(value.code), value);
      }
    });
  });

  group('persistence', () {
    test('a theme write is read back by a second engine instance', () async {
      // A second instance is the point: it proves the value left the process.
      await engine.writeSettings(theme: 'dark', language: 'zh');

      final second = Engine(projectRoot: projectRoot, stateDir: state.path);
      final stored = await second.readSettings();
      expect(stored['theme'], 'dark');
      expect(stored['language'], 'zh');
    });

    test('loadStoredPreferences applies both to the notifiers', () async {
      await engine.writeSettings(theme: 'light', language: 'en');
      appTheme.value = AppTheme.system;
      appLanguage.value = AppLanguage.system;

      await loadStoredPreferences(engine);

      expect(appTheme.value, AppTheme.light);
      expect(appLanguage.value, AppLanguage.english);
    });

    test('a fresh state directory yields the defaults, not an error', () async {
      // Nothing has been written here, so `loadStoredPreferences` must leave the
      // notifiers alone rather than throw — a first launch has no settings file.
      appTheme.value = AppTheme.dark;
      appLanguage.value = AppLanguage.chinese;
      final fresh = Directory.systemTemp.createTempSync('nvfku-fresh-');
      addTearDown(() => fresh.deleteSync(recursive: true));

      await loadStoredPreferences(
        Engine(projectRoot: projectRoot, stateDir: fresh.path),
      );

      expect(appTheme.value, AppTheme.dark);
      expect(appLanguage.value, AppLanguage.chinese);
    });

    test(
      'an invalid theme is refused by the engine, not silently stored',
      () async {
        // The engine validates too, so a bad code is a failed write rather than a
        // setting that appears to save and does nothing.
        await expectLater(
          engine.writeSettings(theme: 'ligth'),
          throwsA(isA<EngineException>()),
        );
      },
    );
  });
}
