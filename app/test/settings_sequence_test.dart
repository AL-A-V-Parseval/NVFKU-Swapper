import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nvfku_ui/src/app.dart';
import 'package:nvfku_ui/src/engine.dart';
import 'package:nvfku_ui/src/l10n.dart';
import 'package:nvfku_ui/src/settings_view.dart';

class ControlledSettingsEngine extends Engine {
  final writes = <Map<String, dynamic>>[];
  final completions = <Completer<Map<String, dynamic>>>[];
  int reads = 0;
  @override
  Future<Map<String, dynamic>> readSettings() async {
    reads++;
    return {'theme': 'system', 'language': 'en', 'version': 1};
  }

  @override
  Future<Map<String, dynamic>> writeSettings({
    String? pythonPath,
    String? steamRoot,
    String? downloadCache,
    String? proxyMode,
    bool? verifyUpstream,
    String? routePreference,
    String? theme,
    String? language,
  }) {
    writes.add({'theme': theme, 'language': language, 'steam_root': steamRoot});
    final completion = Completer<Map<String, dynamic>>();
    completions.add(completion);
    return completion.future;
  }
}

Future<void> pumpSettings(
  WidgetTester tester,
  ControlledSettingsEngine engine,
) async {
  tester.view.physicalSize = const Size(1000, 1600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: Dlss5CtlApp.buildTheme(Brightness.light),
      home: Scaffold(
        body: SettingsView(engine: engine, onChanged: () async {}),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  tearDown(() {
    appTheme.value = AppTheme.system;
    appLanguage.value = AppLanguage.system;
  });
  testWidgets(
    'returning to Settings waits for pending intents before reloading',
    (tester) async {
      final engine = ControlledSettingsEngine();
      await pumpSettings(tester, engine);
      await tester.tap(find.text('Dark'));
      await tester.pump();
      await tester.tap(find.text('Light'));
      await tester.pump();
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SettingsView(engine: engine, onChanged: () async {}),
          ),
        ),
      );
      await tester.pump();
      expect(
        engine.reads,
        1,
        reason:
            'do not load an old appearance snapshot while writes are pending',
      );
      engine.completions[0].complete({});
      await tester.pump();
      expect(engine.writes, hasLength(2));
      engine.completions[1].complete({});
      await tester.pumpAndSettle();
      expect(engine.reads, 2);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('a failed appearance write retains fields and can be retried', (
    tester,
  ) async {
    final engine = ControlledSettingsEngine();
    await pumpSettings(tester, engine);
    await tester.enterText(find.byType(TextField).at(1), '/unsaved-steam');
    await tester.tap(find.text('Dark'));
    await tester.pump();
    engine.completions[0].completeError(EngineException('fixture disk full'));
    await tester.pumpAndSettle();
    expect(find.text('fixture disk full'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(3));
    expect(
      tester.widget<TextField>(find.byType(TextField).at(1)).controller!.text,
      '/unsaved-steam',
    );
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(engine.writes, hasLength(2));
    engine.completions[1].complete({});
    await tester.pumpAndSettle();
    expect(find.text('fixture disk full'), findsNothing);
    expect(find.text('Settings saved.'), findsOneWidget);
  });

  testWidgets(
    'latest appearance intent and ordinary Save share one write sequence',
    (tester) async {
      final engine = ControlledSettingsEngine();
      await pumpSettings(tester, engine);
      await tester.tap(find.text('Dark'));
      await tester.pump();
      await tester.tap(find.text('Light'));
      await tester.pump();
      await tester.tap(find.text('简体中文'));
      await tester.pump();
      await tester.enterText(find.byType(TextField).at(1), '/fixture-steam');
      await tester.tap(find.text('Save'));
      await tester.pump();
      await tester.tap(find.text('English'));
      await tester.pump();
      expect(
        engine.writes,
        hasLength(1),
        reason: 'no concurrent read-modify-write subprocesses',
      );
      expect(find.text('Saving…'), findsOneWidget);
      engine.completions[0].complete({});
      await tester.pump();
      expect(engine.writes, hasLength(2));
      expect(engine.writes[1]['theme'], 'light');
      engine.completions[1].complete({});
      await tester.pump();
      expect(engine.writes, hasLength(3));
      expect(engine.writes[2]['language'], 'zh');
      engine.completions[2].complete({});
      await tester.pump();
      expect(engine.writes, hasLength(4));
      expect(engine.writes[3]['steam_root'], '/fixture-steam');
      expect(engine.writes[3]['language'], 'zh');
      engine.completions[3].complete({});
      await tester.pump();
      expect(engine.writes, hasLength(5));
      expect(engine.writes[4]['theme'], 'light');
      expect(engine.writes[4]['language'], 'en');
      engine.completions[4].complete({});
      await tester.pumpAndSettle();
      expect(find.text('Saving…'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
