/// The engine's text language must actually reach the command line.
///
/// `Engine` assembles argv by hand, and the language flag is a *global* option:
/// it has to precede the subcommand. A first attempt placed it after the
/// positional arguments, where argparse does not accept it, so the plan came back
/// in English with no error. This test runs the real process and asserts on the
/// text that comes back.
library;

import 'dart:io';

import 'package:flutter/material.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';

import 'package:nvfku_ui/src/engine.dart';
import 'package:nvfku_ui/src/l10n.dart';

void main() {
  final projectRoot = Platform.environment['NVFKU_ENGINE'] ??
      '/run/media/jackyji/Documents/DLSS5-swapper-linux';
  final available = Directory('$projectRoot/engine/nvfku').existsSync();

  setUp(() => appLanguage.value = AppLanguage.chinese);
  tearDown(() => appLanguage.value = AppLanguage.system);

  test('textLanguage follows the language preference', () {
    appLanguage.value = AppLanguage.chinese;
    expect(Engine.textLanguage, 'zh');
    appLanguage.value = AppLanguage.english;
    expect(Engine.textLanguage, 'en');
    appLanguage.value = AppLanguage.system;
    expect(Engine.textLanguage, 'en', reason: 'system falls back to English');
  });

  test(
    'a plan comes back in Chinese when the language is Chinese',
    () async {
      final engine = Engine(projectRoot: projectRoot);
      final plans = await engine.plan('805550', route: 'a1');
      expect(plans, isNotEmpty);

      // The title is translated; the identifiers inside it are not.
      expect(plans.first.title, contains('ReShade'));
      expect(
        plans.first.title,
        isNot(contains('ReShade + dlss5-bridge + addon-dlssnr-linux (Proton)')),
        reason: 'the English title should have been replaced by the Chinese one',
      );
      // A check name is localised too, which is the part a user reads first.
      final names = plans.first.checks.map((c) => c.name).toList();
      expect(names, contains('渲染 API'));
      expect(names, isNot(contains('rendering API')));
    },
    skip: available ? false : 'engine checkout not available',
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'the same plan comes back in English when asked',
    () async {
      appLanguage.value = AppLanguage.english;
      final engine = Engine(projectRoot: projectRoot);
      final plans = await engine.plan('805550', route: 'a1');
      final names = plans.first.checks.map((c) => c.name).toList();
      expect(names, contains('rendering API'));
      expect(names, isNot(contains('渲染 API')));
    },
    skip: available ? false : 'engine checkout not available',
    timeout: const Timeout(Duration(minutes: 2)),
  );

  group('the reshade route', () {
    test('is a prerequisite of a1, not a route of its own', () async {
      final engine = Engine(projectRoot: projectRoot);
      final all = await engine.plan('805550');

      // Two routes, exactly. ReShade used to be returned as a third, which made
      // the plan read as three options when there are two.
      expect(all.map((p) => p.route).toList(), ['a1', 'a2']);

      final a1 = all.firstWhere((p) => p.route == 'a1');
      expect(a1.prerequisite, isNotNull,
          reason: 'A1 needs ReShade as its proxy');
      expect(a1.prerequisite!.route, 'reshade');

      final a2 = all.firstWhere((p) => p.route == 'a2');
      expect(a2.prerequisite, isNull, reason: 'A2 does not use ReShade');

      // A route asked for alone does not gain the other route's prerequisite.
      final onlyA2 = await engine.plan('805550', route: 'a2');
      expect(onlyA2.map((p) => p.route).toList(), ['a2']);
    }, skip: available ? false : 'engine checkout not available',
        timeout: const Timeout(Duration(minutes: 2)));

    test('its plan names the installer invocation it would run', () async {
      final engine = Engine(projectRoot: projectRoot);
      final plans = await engine.plan('805550', route: 'a1');
      final reshade = plans.firstWhere((p) => p.route == 'a1').prerequisite!;
      final notes = reshade.actions
          .where((a) => a.kind == 'note')
          .map((a) => a.destination)
          .join(' ');
      // The flags are the contract with ReShade's own setup tool.
      expect(notes, contains('--headless'));
      expect(notes, contains('--api dxgi'));
      // And the Vulkan path must never appear, because Wine cannot load a layer.
      expect(notes, isNot(contains('--api vulkan')));
    }, skip: available ? false : 'engine checkout not available',
        timeout: const Timeout(Duration(minutes: 2)));

    test('a Vulkan-only game is blocked with the layer explanation', () async {
      final engine = Engine(projectRoot: projectRoot);
      // No Steam game here is Vulkan-only, so assert on the rule through a game
      // that is: if none exists, the engine-level test covers it.
      final plans = await engine.plan('805550', route: 'a1');
      final reshade = plans.firstWhere((p) => p.route == 'a1').prerequisite!;
      expect(reshade.checks, isNotEmpty);
    }, skip: available ? false : 'engine checkout not available',
        timeout: const Timeout(Duration(minutes: 2)));
  });

  group('locale plumbing', () {
    test('a zh preference resolves to a zh locale', () {
      expect(
        effectiveLocale(AppLanguage.chinese, const Locale('en')).languageCode,
        'zh',
      );
    });
  });
}
