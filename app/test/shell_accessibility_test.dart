import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'dart:ui' show Tristate;
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nvfku_ui/src/app.dart';
import 'package:nvfku_ui/src/engine.dart';
import 'package:nvfku_ui/src/models.dart';

class ShellFixtureEngine extends Engine {
  ShellFixtureEngine({
    this.games = const [
      Game(appid: 'fixture', name: 'Fixture game', installDir: '/fixture'),
    ],
  });
  final List<Game> games;
  @override
  Future<String> version() async => 'fixture 1';
  @override
  Future<List<Game>> scan() async => games;
  @override
  Future<Map<String, String?>> cachedArtwork() async => {};
  @override
  Future<Map<String, dynamic>> readSettings() async => {'version': 1};
  @override
  Future<List<JournalEntry>> backups({String? gameKey}) async => [];
  @override
  Future<List<ProviderRow>> providers({bool resolve = true}) async => [];
}

Future<void> pumpShell(
  WidgetTester tester, {
  Engine? engine,
  AppView view = AppView.games,
  Size size = const Size(1200, 900),
  Locale locale = const Locale('en'),
  Brightness brightness = Brightness.light,
  double scale = 1,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      locale: locale,
      supportedLocales: const [Locale('en'), Locale('zh')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      theme: Dlss5CtlApp.buildTheme(brightness),
      builder:
          (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(
              textScaler: TextScaler.linear(scale),
              disableAnimations: true,
            ),
            child: child!,
          ),
      home: Shell(engine: engine ?? ShellFixtureEngine(), initialView: view),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  for (final locale in [const Locale('en'), const Locale('zh')]) {
    testWidgets(
      'partial scan is visibly uncertain in whole Shell ${locale.languageCode}',
      (tester) async {
        final game = Game.fromJson({
          'appid': 'fixture',
          'name': 'Fixture game',
          'install_dir': '/fixture',
          'detection_complete': false,
          'detection_warnings': ['fixture directory budget exceeded'],
        });
        await pumpShell(
          tester,
          engine: ShellFixtureEngine(games: [game]),
          locale: locale,
          size: const Size(480, 700),
        );
        expect(
          find.text(
            locale.languageCode == 'zh' ? '检测不完整' : 'Detection incomplete',
          ),
          findsWidgets,
        );
        expect(
          find.textContaining('fixture directory budget exceeded'),
          findsOneWidget,
        );
        expect(tester.takeException(), isNull);
      },
    );
  }
  for (final size in [const Size(480, 700), const Size(700, 400)]) {
    for (final locale in [const Locale('en'), const Locale('zh')]) {
      for (final brightness in Brightness.values) {
        for (final scale in [1.3, 2.0]) {
          for (final view in AppView.values) {
            testWidgets(
              'whole Shell $view $size ${locale.languageCode} $brightness ${scale}x',
              (tester) async {
                await pumpShell(
                  tester,
                  view: view,
                  size: size,
                  locale: locale,
                  brightness: brightness,
                  scale: scale,
                );
                expect(tester.takeException(), isNull);
                if (view == AppView.games) {
                  final game = find.text('Fixture game');
                  await tester.scrollUntilVisible(
                    game,
                    150,
                    scrollable: find.descendant(
                      of: find.byType(CustomScrollView),
                      matching: find.byType(Scrollable),
                    ).first,
                  );
                  await tester.pumpAndSettle();
                  expect(game.hitTestable(), findsOneWidget);
                }
                if (view == AppView.settings) {
                  final save = find.text(
                    locale.languageCode == 'zh' ? '保存' : 'Save',
                  );
                  await tester.ensureVisible(save);
                  expect(save.hitTestable(), findsOneWidget);
                }
                await tester.tap(
                  find.byTooltip(
                    locale.languageCode == 'zh'
                        ? '打开导航菜单'
                        : 'Open navigation menu',
                  ),
                );
                await tester.pumpAndSettle();
                final about =
                    find
                        .text(locale.languageCode == 'zh' ? '关于' : 'About')
                        .first;
                await tester.ensureVisible(about);
                expect(about.hitTestable(), findsOneWidget);
                await tester.tap(about);
                await tester.pumpAndSettle();
                expect(tester.takeException(), isNull);
              },
            );
          }
        }
      }
    }
  }
  testWidgets(
    'full Shell navigation supports Tab Enter Space and selected semantics',
    (tester) async {
      final semantics = tester.ensureSemantics();
      await pumpShell(tester, view: AppView.home);
      expect(
        tester
                .getSemantics(find.text('Home'))
                .getSemanticsData()
                .flagsCollection
                .isSelected ==
            Tristate.isTrue,
        isTrue,
      );
      for (var tab = 0; tab < 12; tab++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pump();
        if (tester
                .getSemantics(find.text('Games').first)
                .getSemanticsData()
                .flagsCollection
                .isFocused ==
            Tristate.isTrue) {
          break;
        }
      }
      expect(
        tester
                .getSemantics(find.text('Games').first)
                .getSemanticsData()
                .flagsCollection
                .isFocused ==
            Tristate.isTrue,
        isTrue,
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsOneWidget);
      expect(
        tester
                .getSemantics(find.text('Games').first)
                .getSemanticsData()
                .flagsCollection
                .isSelected ==
            Tristate.isTrue,
        isTrue,
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.sendKeyEvent(LogicalKeyboardKey.space);
      await tester.pumpAndSettle();
      expect(
        tester
                .getSemantics(find.text('Add-ons').first)
                .getSemanticsData()
                .flagsCollection
                .isSelected ==
            Tristate.isTrue,
        isTrue,
      );
      semantics.dispose();
    },
  );

  testWidgets(
    'real startup failure shows retry rather than a permanent spinner',
    (tester) async {
      await pumpShell(
        tester,
        engine: Engine(
          projectRoot: Directory.systemTemp.path,
          pythonOverride: '/missing-nvfku-python',
        ),
      );
      expect(find.text('Try again'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
      final semantics = tester.ensureSemantics();
      expect(
        tester
            .getSemantics(find.text('Games'))
            .getSemanticsData()
            .flagsCollection
            .isEnabled,
        Tristate.isFalse,
      );
      semantics.dispose();
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.text('Try again'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'complete compact Shell keeps Settings and navigation reachable at 2x',
    (tester) async {
      await pumpShell(
        tester,
        view: AppView.settings,
        size: const Size(480, 700),
        scale: 2,
      );
      expect(tester.takeException(), isNull);
      await tester.ensureVisible(find.text('Save'));
      expect(find.text('Save').hitTestable(), findsOneWidget);
    },
  );
}
