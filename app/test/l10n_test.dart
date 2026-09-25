/// Localisation integrity.
///
/// A missing key silently falls back to English, which is exactly the kind of
/// bug nobody notices until a user reports a half-translated screen. These tests
/// make the two tables prove they agree.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nvfku_ui/src/l10n.dart';

void main() {
  group('string tables', () {
    test('English and Chinese define exactly the same keys', () {
      final en = englishStrings.keys.toSet();
      final zh = chineseStrings.keys.toSet();
      final missingInZh = (en.difference(zh)).toList()..sort();
      final extraInZh = (zh.difference(en)).toList()..sort();
      expect(missingInZh, isEmpty, reason: 'untranslated keys: $missingInZh');
      expect(extraInZh, isEmpty, reason: 'keys with no English original: $extraInZh');
    });

    test('no Chinese entry is left as the English text', () {
      // A handful of keys are legitimately identical because they are proper
      // nouns or identifiers. Everything else must actually differ.
      // A product name is not translated: "NVFKU-Swapper" is the same string in
      // both languages by intent, not by omission.
      const allowedIdentical = {
        'app.title',
        'app.windowTitle',
        'plan.appid',
        'plan.reshade',
      };
      final identical = <String>[];
      for (final entry in englishStrings.entries) {
        if (allowedIdentical.contains(entry.key)) continue;
        if (chineseStrings[entry.key] == entry.value) identical.add(entry.key);
      }
      expect(identical, isEmpty, reason: 'identical in both languages: $identical');
    });

    test('placeholders agree between the two languages', () {
      // A translation that drops `{n}` loses information; one that invents a
      // placeholder renders it literally.
      //
      // The pattern avoids `\w` on purpose: this test previously used a raw
      // string, `r'\{(\w+)\}'`, in which the backslash is literal, so it matched
      // a literal "w" and reported every key as mismatched. A character class
      // makes the intent unambiguous.
      final placeholder = RegExp('[{]([A-Za-z0-9_]+)[}]');
      final mismatches = <String>[];
      for (final entry in englishStrings.entries) {
        final zh = chineseStrings[entry.key] ?? '';
        // Sorted lists, not Sets: `Set ==` is identity in Dart, so two sets with
        // the same members compare unequal and every key would be reported as a
        // mismatch. That mistake cost three debugging rounds, which is why the
        // comparison is by value and spelled out.
        final enNames =
            (placeholder.allMatches(entry.value).map((m) => m.group(1)).toList()
              ..sort());
        final zhNames =
            (placeholder.allMatches(zh).map((m) => m.group(1)).toList()..sort());
        if (enNames.join(',') != zhNames.join(',')) {
          mismatches.add('${entry.key}: $enNames vs $zhNames');
        }
      }
      expect(mismatches, isEmpty, reason: mismatches.join('; '));
    });

    test('no key is empty in either language', () {
      for (final entry in englishStrings.entries) {
        expect(entry.value.trim(), isNotEmpty, reason: '${entry.key} is empty in English');
      }
      for (final entry in chineseStrings.entries) {
        expect(entry.value.trim(), isNotEmpty, reason: '${entry.key} is empty in Chinese');
      }
    });
  });

  group('translate', () {
    test('substitutes every placeholder', () {
      // Deliberately a key unrelated to any screen: this test is about the
      // substitution mechanism, and it was previously pinned to
      // `plan.wouldChangeMany`, which belonged to a widget that no longer exists.
      // A fixture that dies with a feature is a test that dies with it too.
      final text = translate(
        const Locale('en'),
        'home.minAgo',
        {'n': 7},
      );
      expect(text, contains('7'));
      expect(text, isNot(contains('{n}')));
    });

    test('uses Chinese for a zh locale', () {
      final text = translate(const Locale('zh'), 'nav.games');
      expect(text, '游戏');
    });

    test('an unknown key renders as itself rather than throwing', () {
      // A missing string should be an obvious placeholder, not a crash.
      expect(translate(const Locale('en'), 'no.such.key'), 'no.such.key');
      expect(translate(const Locale('zh'), 'no.such.key'), 'no.such.key');
    });
  });

  group('language choice', () {
    test('system follows the platform language', () {
      expect(effectiveLocale(AppLanguage.system, const Locale('zh')), const Locale('zh'));
      expect(effectiveLocale(AppLanguage.system, const Locale('en')), const Locale('en'));
      // Anything else falls back to English rather than guessing.
      expect(effectiveLocale(AppLanguage.system, const Locale('de')), const Locale('en'));
      expect(effectiveLocale(AppLanguage.system, null), const Locale('en'));
    });

    test('an explicit choice overrides the platform', () {
      expect(effectiveLocale(AppLanguage.chinese, const Locale('en')), const Locale('zh'));
      expect(effectiveLocale(AppLanguage.english, const Locale('zh')), const Locale('en'));
    });

    test('codes round-trip', () {
      for (final language in AppLanguage.values) {
        expect(AppLanguageX.fromCode(language.code), language);
      }
      expect(AppLanguageX.fromCode(null), AppLanguage.system);
      expect(AppLanguageX.fromCode('nonsense'), AppLanguage.system);
    });
  });
}
