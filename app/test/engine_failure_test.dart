import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:nvfku_ui/src/engine.dart';

void main() {
  test(
    'malformed install result ends the task with failure, never a stuck stream',
    () async {
      final dir = await Directory.systemTemp.createTemp('nvfku-install-shape-');
      addTearDown(() => dir.delete(recursive: true));
      final executable = File('${dir.path}/fixture-python');
      await executable.writeAsString(
        '#!/bin/sh\nprintf \'%s\\n\' \'{"ok":true,"result":{"notes":[42]}}\'\n',
      );
      expect((await Process.run('chmod', ['+x', executable.path])).exitCode, 0);
      final engine = Engine(
        projectRoot: dir.path,
        pythonOverride: executable.path,
      );
      final events = await engine
          .install(gameKey: 'fixture', route: 'a1')
          .toList()
          .timeout(const Duration(seconds: 1));
      expect(events.last.phase, 'failed');
      expect(events.last.message, contains('Invalid engine'));
    },
  );
  test('queries expose startup failures as EngineException', () async {
    final engine = Engine(
      projectRoot: Directory.systemTemp.path,
      pythonOverride: '/missing-nvfku-python',
    );
    for (final query in <Future<dynamic> Function()>[
      engine.version,
      engine.scan,
      engine.readSettings,
      () => engine.plan('fixture'),
    ]) {
      await expectLater(query(), throwsA(isA<EngineException>()));
    }
  });

  test('nested JSON type errors are rejected before UI reads lists', () async {
    final dir = await Directory.systemTemp.createTemp('nvfku-nested-json-');
    addTearDown(() => dir.delete(recursive: true));
    final executable = File('${dir.path}/fixture-python');
    await executable.writeAsString(
      '#!/bin/sh\nprintf \'%s\\n\' \'[{"native_dlss":[42]}]\'\n',
    );
    expect((await Process.run('chmod', ['+x', executable.path])).exitCode, 0);
    final engine = Engine(
      projectRoot: dir.path,
      pythonOverride: executable.path,
    );
    await expectLater(engine.scan(), throwsA(isA<EngineException>()));
  });

  test(
    'queries reject malformed document shapes with useful diagnostics',
    () async {
      final dir = await Directory.systemTemp.createTemp('nvfku-json-');
      addTearDown(() => dir.delete(recursive: true));
      final executable = File('${dir.path}/fixture-python');
      await executable.writeAsString(
        '#!/bin/sh\nprintf \'%s\\n\' "\$NVFKU_TEST_UNUSED"\n',
      );
      final result = await Process.run('chmod', ['+x', executable.path]);
      expect(result.exitCode, 0);
      final engine = Engine(
        projectRoot: dir.path,
        pythonOverride: executable.path,
      );
      for (final document in ['null', '42', '"text"', '[42]']) {
        await executable.writeAsString(
          '#!/bin/sh\nprintf \'%s\\n\' \'$document\'\n',
        );
        for (final query in <Future<dynamic> Function()>[
          engine.scan,
          () => engine.plan('fixture'),
          engine.providers,
          engine.backups,
          engine.cachedArtwork,
          engine.readSettings,
          () => engine.writeSettings(theme: 'dark'),
          () => engine.launchOptions('fixture'),
          () => engine.setLaunchOptions('fixture', clear: true),
          () => engine.addGameFolder('/fixture'),
        ]) {
          await expectLater(
            query(),
            throwsA(isA<EngineException>()),
            reason: 'document: $document',
          );
        }
      }
    },
  );
}
