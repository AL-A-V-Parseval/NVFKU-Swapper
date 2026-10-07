import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:nvfku_ui/src/install_task.dart';
import 'package:nvfku_ui/src/engine.dart';
import 'package:nvfku_ui/src/models.dart';

class _EventEngine extends Engine {
  _EventEngine(this.events, {String? root, String? command})
      : super(projectRoot: root ?? '/nonexistent', pythonOverride: command);
  final StreamController<InstallEvent> events;

  @override
  Stream<InstallEvent> install({
    required String gameKey,
    required String route,
    int? workingScale,
    bool yes = true,
    bool skipDownload = false,
    bool verifyUpstream = true,
  }) => events.stream;
}

Future<Engine> _rollbackRetryEngine() async {
  final root = await Directory.systemTemp.createTemp('nvfku-ui-retry-');
  addTearDown(() => root.delete(recursive: true));
  final command = File('${root.path}/mock-engine');
  await command.writeAsString('''#!/bin/sh
case "\$*" in
  *install*other*) printf '%s\\n' '{"ok":true,"result":{"route":"a1","game":"Other","game_dir":"/other","journal_id":"txn-2"}}' ;;
  *install*)
    if [ -f rollback-attempted ]; then
      printf '%s\\n' '{"ok":false,"error":"new install refused"}'; exit 1
    fi
    printf '%s\\n' '{"ok":true,"result":{"route":"a1","game":"Test","game_dir":"/test","journal_id":"txn-1"}}' ;;
  *rollback*)
    if [ ! -f rollback-attempted ]; then
      touch rollback-attempted
      printf '%s\\n' '{"ok":false,"report":["restored first.dll"],"failed":["second.dll: permission denied"]}'; exit 1
    fi
    printf '%s\\n' '{"ok":true,"report":["restored second.dll"],"failed":[]}' ;;
esac
''');
  final chmod = await Process.run('chmod', ['+x', command.path]);
  expect(chmod.exitCode, 0);
  return Engine(projectRoot: root.path, pythonOverride: command.path,
      stateDir: '${root.path}/state');
}

Future<void> _installAndWait(Engine engine, String gameKey) async {
  engine.startInstallation(gameKey: gameKey, route: 'a1');
  final task = engine.installationFor(gameKey, 'a1');
  final completed = Completer<void>();
  void observe() {
    if (!task.running && !completed.isCompleted) completed.complete();
  }
  task.addListener(observe);
  try {
    await completed.future.timeout(const Duration(seconds: 10));
  } finally {
    task.removeListener(observe);
  }
}

void main() {
  test('only a completed unrolled journal is live; incomplete is restorable', () {
    JournalEntry entry({required bool finished, required bool rolledBack}) =>
        JournalEntry(id: 'a', route: 'a1', gameDir: '/test', operations: 1,
            finished: finished, rolledBack: rolledBack);
    expect(entry(finished: false, rolledBack: false).live, isFalse);
    expect(entry(finished: false, rolledBack: false).restorable, isTrue);
    expect(entry(finished: true, rolledBack: false).live, isTrue);
    expect(entry(finished: true, rolledBack: true).restorable, isFalse);
  });
  test('a successful install notifies the owner after the sheet is gone', () async {
    final events = StreamController<InstallEvent>();
    final engine = _EventEngine(events);
    var changes = 0;
    engine.revision.addListener(() => changes++);
    engine.startInstallation(gameKey: 'test', route: 'a1');
    events.add(const InstallEvent(phase: 'log', message: 'copying'));
    await Future<void>.delayed(Duration.zero);
    expect(changes, 0);
    events.add(const InstallEvent(
      phase: 'done', message: '',
      result: InstallResult(route: 'a1', game: 'Test', gameDir: '/test'),
    ));
    await events.close();
    expect(changes, 1);
    expect(engine.installationFor('test', 'a1').result?.game, 'Test');
  });

  test('successful rollback clears the matching retained install result', () async {
    final root = await Directory.systemTemp.createTemp('nvfku-ui-state-');
    addTearDown(() => root.delete(recursive: true));
    final command = File('${root.path}/mock-engine');
    await command.writeAsString('''#!/bin/sh
printf '%s\\n' '{"ok":true,"report":[],"failed":[]}'
''');
    await Process.run('chmod', ['+x', command.path]);
    final events = StreamController<InstallEvent>();
    final engine = _EventEngine(events, root: root.path, command: command.path);
    engine.startInstallation(gameKey: 'test', route: 'a1');
    events.add(const InstallEvent(
      phase: 'done', message: '',
      result: InstallResult(route: 'a1', game: 'Test', gameDir: '/test', journalId: 'txn-1'),
    ));
    await events.close();
    expect(engine.installationFor('test', 'a1').result?.journalId, 'txn-1');
    await engine.rollback('txn-1');
    expect(engine.installationFor('test', 'a1').result, isNull);
    expect(engine.revision.value, 2);
  });

  test('partial rollback invalidates its receipt and refreshes observers', () async {
    final root = await Directory.systemTemp.createTemp('nvfku-ui-rollback-');
    addTearDown(() => root.delete(recursive: true));
    final command = File('${root.path}/mock-engine');
    await command.writeAsString('''#!/bin/sh
case "\$*" in
  *install*) printf '%s\\n' '{"ok":true,"result":{"route":"a1","game":"Test","game_dir":"/test","journal_id":"txn-1"}}' ;;
  *rollback*) printf '%s\\n' '{"ok":false,"report":["restored first.dll"],"failed":["second.dll: permission denied"]}'; exit 1 ;;
esac
''');
    final chmod = await Process.run('chmod', ['+x', command.path]);
    expect(chmod.exitCode, 0);
    final engine = Engine(projectRoot: root.path, pythonOverride: command.path,
        stateDir: '${root.path}/state');
    engine.startInstallation(gameKey: 'test', route: 'a1');
    final task = engine.installationFor('test', 'a1');
    final installed = Completer<void>();
    task.addListener(() {
      if (!task.running && !installed.isCompleted) installed.complete();
    });
    await installed.future.timeout(const Duration(seconds: 10));
    expect(task.result?.journalId, 'txn-1');
    var refreshed = 0;
    engine.revision.addListener(() => refreshed++);

    await expectLater(engine.rollback('txn-1'), throwsA(isA<EngineException>()
        .having((error) => error.message, 'message', 'second.dll: permission denied')));

    expect(task.result, isNull);
    expect(task.error, 'second.dll: permission denied');
    expect(refreshed, 1);
    expect(engine.revision.value, 2);
  });

  test('backups marks interrupted rollback recoverable, not live', () async {
    final root = await Directory.systemTemp.createTemp('nvfku-ui-backups-');
    addTearDown(() => root.delete(recursive: true));
    final command = File('${root.path}/mock-engine');
    await command.writeAsString('''#!/bin/sh
printf '%s\\n' '[{"id":"txn-1","route":"a1","game_dir":"/test","operations":2,"finished":true,"rolled_back":false,"rollback_started":true}]'
''');
    final chmod = await Process.run('chmod', ['+x', command.path]);
    expect(chmod.exitCode, 0);
    final engine = Engine(projectRoot: root.path, pythonOverride: command.path,
        stateDir: '${root.path}/state');
    final entries = await engine.backups();
    expect(entries.single.live, isFalse);
    expect(entries.single.restorable, isTrue);
    expect(entries.single.finished, isTrue);
  });

  for (final scenario in [
    (name: 'no-op refusal', output: '{"ok":false,"report":[],"failed":[],"error":"Steam is running"}', message: 'Steam is running'),
    (name: 'malformed document', output: 'not JSON', message: 'transport interrupted'),
    (name: 'invalid report', output: '{"ok":true,"report":[42]}', message: 'the engine returned an invalid rollback report'),
  ]) {
    test('${scenario.name} conservatively invalidates without claiming restore', () async {
      final root = await Directory.systemTemp.createTemp('nvfku-ui-failure-');
      addTearDown(() => root.delete(recursive: true));
      final command = File('${root.path}/mock-engine');
      await command.writeAsString('''#!/bin/sh
case "\$*" in
  *install*) printf '%s\\n' '{"ok":true,"result":{"route":"a1","game":"Test","game_dir":"/test","journal_id":"txn-1"}}' ;;
  *rollback*) printf '%s\\n' '${scenario.output}'; printf '%s\\n' 'transport interrupted' >&2; exit 1 ;;
esac
''');
      final chmod = await Process.run('chmod', ['+x', command.path]);
      expect(chmod.exitCode, 0);
      final engine = Engine(projectRoot: root.path, pythonOverride: command.path,
          stateDir: '${root.path}/state');
      engine.startInstallation(gameKey: 'test', route: 'a1');
      final task = engine.installationFor('test', 'a1');
      final installed = Completer<void>();
      task.addListener(() {
        if (!task.running && !installed.isCompleted) installed.complete();
      });
      await installed.future.timeout(const Duration(seconds: 10));
      expect(task.result?.journalId, 'txn-1');
      await expectLater(engine.rollback('txn-1'), throwsA(isA<EngineException>()
          .having((error) => error.message, 'message', scenario.message)));
      expect(task.result, isNull);
      expect(task.error, scenario.message);
      expect(engine.revision.value, 2);
    });
  }

  test('successful rollback retry clears its old failure, not unrelated receipts', () async {
    final engine = await _rollbackRetryEngine();
    await _installAndWait(engine, 'test');
    await _installAndWait(engine, 'other');
    final task = engine.installationFor('test', 'a1');
    final other = engine.installationFor('other', 'a1');
    expect(task.result?.journalId, 'txn-1');
    expect(other.result?.journalId, 'txn-2');
    await expectLater(engine.rollback('txn-1'), throwsA(isA<EngineException>()));
    expect(task.result, isNull);
    expect(task.error, 'second.dll: permission denied');

    expect(await engine.rollback('txn-1'), 'restored second.dll');
    expect(task.result, isNull);
    expect(task.error, isNull);
    expect(other.result?.journalId, 'txn-2');
    expect(other.error, isNull);
    expect(engine.revision.value, 4);
  });

  test('old rollback retry does not erase a newer installation failure', () async {
    final engine = await _rollbackRetryEngine();
    await _installAndWait(engine, 'test');
    final task = engine.installationFor('test', 'a1');
    await expectLater(engine.rollback('txn-1'), throwsA(isA<EngineException>()));
    expect(task.error, 'second.dll: permission denied');
    await _installAndWait(engine, 'test');
    expect(task.error, 'new install refused');
    expect(await engine.rollback('txn-1'), 'restored second.dll');
    expect(task.result, isNull);
    expect(task.error, 'new install refused');
  });

  test('rollback process startup error remains a visible engine failure', () async {
    final root = await Directory.systemTemp.createTemp('nvfku-ui-startup-');
    addTearDown(() => root.delete(recursive: true));
    final engine = Engine(projectRoot: root.path,
        pythonOverride: '${root.path}/missing-engine', stateDir: '${root.path}/state');
    await expectLater(engine.rollback('txn-1'), throwsA(isA<EngineException>()));
    expect(engine.revision.value, 1);
  });

  test('a failed install does not signal a new game state', () async {
    final events = StreamController<InstallEvent>();
    final engine = _EventEngine(events);
    engine.startInstallation(gameKey: 'test', route: 'a1');
    events.add(const InstallEvent(phase: 'failed', message: 'refused'));
    await events.close();
    expect(engine.revision.value, 0);
  });
  test('installation continues without a view listener and retains its result', () async {
    final task = InstallTask();
    final events = StreamController<InstallEvent>();
    var observations = 0;
    void observe() => observations++;
    task.addListener(observe);
    task.start(() => events.stream);
    expect(task.running, isTrue);
    task.removeListener(observe); // The sheet is closed while Python is working.
    events.add(const InstallEvent(phase: 'log', message: 'copying'));
    events.add(const InstallEvent(
      phase: 'done', message: '',
      result: InstallResult(route: 'a1', game: 'Test', gameDir: '/test'),
    ));
    await events.close();
    expect(task.running, isFalse);
    expect(task.result?.route, 'a1');
    expect(task.progress, contains('copying'));
    expect(task.completion, 1);
    task.addListener(observe); // Reopen the sheet and read the retained result.
    expect(task.result?.game, 'Test');
    expect(observations, greaterThan(0));
  });

  test('a terminal failure stays visible after the listener is detached', () async {
    final task = InstallTask();
    final events = StreamController<InstallEvent>();
    void observe() {}
    task.addListener(observe);
    task.start(() => events.stream);
    task.removeListener(observe);
    events.add(const InstallEvent(phase: 'failed', message: 'rollback incomplete'));
    await events.close();
    expect(task.running, isFalse);
    expect(task.error, 'rollback incomplete');
    expect(task.result, isNull);
    expect(task.completion, 1);
  });
}
