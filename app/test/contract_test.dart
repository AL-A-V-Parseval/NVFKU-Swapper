/// Contract tests for the engine's JSON, plus the pure logic the UI layers on
/// top of it.
///
/// These exist because the UI's failure modes are almost all parsing failures:
/// a field the engine renamed, a check severity that arrives as something new,
/// a plan with no viable route at all. Each test pins a shape the engine
/// actually emits (taken from real output on the development machine), so a
/// change on either side shows up here instead of on screen.
library;

import 'dart:convert';

import 'package:nvfku_ui/src/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Game', () {
    // Real output for Cyberpunk 2077, trimmed to the fields the UI reads.
    final json = jsonDecode('''
    {
      "appid": "1091500",
      "name": "Cyberpunk 2077",
      "install_dir": "/run/media/jackyji/Amusement_Photography/SteamLibrary/steamapps/common/Cyberpunk 2077",
      "proton_prefix": "/home/jackyji/.local/share/Steam/steamapps/compatdata/1091500/pfx",
      "proton_tool": "CachyOS-10.1000-200",
      "launch_exe": "/run/media/jackyji/Amusement_Photography/SteamLibrary/steamapps/common/Cyberpunk 2077/bin/x64/Cyberpunk2077.exe",
      "bitness": 64,
      "rendering_api": "DirectX 12",
      "api_evidence": ["indirect-import:ffx_backend_dx12", "indirect-import:libxess.dll"],
      "native_dlss": ["/games/cp/bin/x64/nvngx_dlss.dll"],
      "nvngx_dlssnr": ["/games/cp/bin/x64/nvngx_dlssnr.dll"],
      "reshade_files": ["/games/cp/bin/x64/ReShade.ini", "/games/cp/bin/x64/dxgi.dll"]
    }
    ''') as Map<String, dynamic>;

    test('parses every field the UI displays', () {
      final game = Game.fromJson(json);
      expect(game.appid, '1091500');
      expect(game.name, 'Cyberpunk 2077');
      expect(game.bitness, 64);
      expect(game.renderingApi, 'DirectX 12');
      expect(game.protonTool, 'CachyOS-10.1000-200');
      expect(game.apiEvidence, hasLength(2));
      expect(game.hasNativeDlss, isTrue);
      expect(game.hasNrModel, isTrue);
    });

    test('exeName is the basename, not the whole path', () {
      expect(Game.fromJson(json).exeName, 'Cyberpunk2077.exe');
    });

    test('hasReshade needs a DLL and an ini in the same directory', () {
      final both = Game.fromJson(json);
      expect(both.hasReshade, isTrue);

      // An ini alone is residue from another tool's install, and reporting it
      // as installed would tell the user to skip a step they still owe.
      final iniOnly = Game.fromJson({
        ...json,
        'reshade_files': ['/games/cp/bin/x64/ReShade.ini'],
      });
      expect(iniOnly.hasReshade, isFalse);

      final dllOnly = Game.fromJson({
        ...json,
        'reshade_files': ['/games/cp/bin/x64/dxgi.dll'],
      });
      expect(dllOnly.hasReshade, isFalse);
    });

    test('hasReshade is false when the exe directory disagrees', () {
      // dll in one place, ini in another: not a working installation.
      final split = Game.fromJson({
        ...json,
        'reshade_files': [
          '/games/cp/bin/x64/ReShade.ini',
          '/games/cp/other/dxgi.dll',
        ],
      });
      expect(split.hasReshade, isFalse);
    });

    test('a missing exe falls back to the game name rather than an empty cell', () {
      final noExe = Game.fromJson({...json, 'launch_exe': null});
      expect(noExe.exeName, 'Cyberpunk 2077');
    });

    test('unknown fields and absent lists do not throw', () {
      final minimal = Game.fromJson({'appid': '1', 'name': 'x', 'install_dir': '/x'});
      expect(minimal.renderingApi, isNull);
      expect(minimal.nativeDlss, isEmpty);
      expect(minimal.hasReshade, isFalse);
    });
  });

  group('RoutePlan', () {
    Map<String, dynamic> planJson({
      bool viable = true,
      bool readOnly = false,
      List<Map<String, dynamic>> checks = const [],
    }) =>
        {
          'route': 'a1',
          'title': 'A1 - ReShade chain',
          'game': 'Cyberpunk 2077',
          'game_dir': '/games/cp',
          'summary': 'Install the chain.',
          'viable': viable,
          'read_only': readOnly,
          'checks': checks,
          'actions': [
            {'kind': 'copy', 'destination': '/games/cp/dlss5-bridge.addon64', 'source': 'bridge', 'reason': 'r', 'optional': false},
          ],
          'missing': [
            {'what': 'nvngx_dlssnr.dll', 'why': 'the model', 'how_to_get': 'from Magpie', 'blocking': true},
          ],
          'manual_steps': ['Launch the game'],
          'launch_options': 'PROTON_FORCE_NVAPI=1 WINEDLLOVERRIDES="dxgi=n,b" %command%',
        };

    test('separates blockers from warnings', () {
      final plan = RoutePlan.fromJson(planJson(viable: false, checks: [
        {'name': 'api', 'severity': 'ok', 'detail': 'D3D12'},
        {'name': 'model', 'severity': 'blocker', 'detail': 'missing', 'fix': 'place it'},
        {'name': 'model-build', 'severity': 'warning', 'detail': 'untested'},
      ]));
      expect(plan.blockers, hasLength(1));
      expect(plan.blockers.first.name, 'model');
      expect(plan.blockers.first.fix, 'place it');
      expect(plan.warnings, hasLength(1));
      expect(plan.viable, isFalse);
    });

    test('an unrecognised severity is not silently treated as fine', () {
      final plan = RoutePlan.fromJson(planJson(checks: [
        {'name': 'x', 'severity': 'advisory', 'detail': 'something new'},
      ]));
      final check = plan.checks.single;
      expect(check.isOk, isFalse);
      expect(check.isBlocker, isFalse);
      expect(check.isWarning, isFalse);
      expect(check.severity, 'advisory');
    });

    test('read-only routes parse and stay distinguishable', () {
      final probe = RoutePlan.fromJson(planJson(readOnly: true));
      expect(probe.readOnly, isTrue);
      expect(probe.viable, isTrue);
    });

    test('missing files keep their blocking flag and instructions', () {
      final plan = RoutePlan.fromJson(planJson());
      final missing = plan.missing.single;
      expect(missing.blocking, isTrue);
      expect(missing.howToGet, 'from Magpie');
    });

    test('launch options survive as one pasteable string', () {
      final plan = RoutePlan.fromJson(planJson());
      expect(plan.launchOptions, contains('PROTON_FORCE_NVAPI=1'));
      expect(plan.launchOptions, endsWith('%command%'));
    });
  });

  group('InstallEvent', () {
    test('terminal phases are recognised', () {
      expect(const InstallEvent(phase: 'done', message: '').isTerminal, isTrue);
      expect(const InstallEvent(phase: 'failed', message: '').isTerminal, isTrue);
      expect(const InstallEvent(phase: 'log', message: '').isTerminal, isFalse);
      expect(const InstallEvent(phase: 'start', message: '').isTerminal, isFalse);
    });
  });

  group('InstallResult', () {
    test('parses the four feedback kinds the design spec defines', () {
      final result = InstallResult.fromJson({
        'route': 'a1',
        'game': 'Cyberpunk 2077',
        'game_dir': '/games/cp',
        'journal_id': '20260924-224630-e090e4',
        'verified': ['dlss5-bridge matches upstream'],
        'warnings': ['not the measured-stable model'],
        'notes': ['state written'],
        'manual_steps': ['Launch the game'],
        'launch_options': 'x %command%',
      });
      expect(result.journalId, '20260924-224630-e090e4');
      expect(result.verified, hasLength(1));
      expect(result.warnings, hasLength(1));
      expect(result.notes, hasLength(1));
      expect(result.manualSteps, hasLength(1));
    });

    test('an install with no journal id is representable', () {
      // ReShade installs can report no journal when only a partial result came
      // back, so the shape has to stay decodable.
      final result = InstallResult.fromJson({
        'route': 'reshade',
        'game': 'x',
        'game_dir': '/x',
      });
      expect(result.journalId, isNull);
    });
  });

  group('the install document', () {
    // The engine's `--json install` emits one object, which the panel decodes.
    // These two shapes are what every failure path has to look like.
    test('a success document carries the result under "result"', () {
      final document = jsonDecode('''
      {
        "ok": true,
        "plan": {"route": "a1", "viable": true},
        "result": {
          "route": "a1",
          "game": "Test Game",
          "game_dir": "/games/test",
          "journal_id": "20260924-224630-e090e4",
          "verified": ["bridge matches upstream"],
          "warnings": ["not the measured-stable model"],
          "notes": ["state written"],
          "manual_steps": ["Launch the game"],
          "launch_options": "PROTON_FORCE_NVAPI=1 %command%"
        }
      }
      ''') as Map<String, dynamic>;

      expect(document['ok'], isTrue);
      final result = InstallResult.fromJson(document['result'] as Map<String, dynamic>);
      expect(result.journalId, '20260924-224630-e090e4');
      expect(result.verified, hasLength(1));
      expect(result.warnings, hasLength(1));
      expect(result.refusal, isNull);
    });

    test('a refusal document has ok=false and a reason', () {
      final document = jsonDecode('''
      {"ok": false, "refused": "A1 cannot install: no usable nvngx_dlssnr.dll found"}
      ''') as Map<String, dynamic>;
      expect(document['ok'], isFalse);
      expect(document['refused'], contains('nvngx_dlssnr.dll'));
    });

    test('a blocked plan document lists blockers', () {
      final document = jsonDecode('''
      {
        "ok": false,
        "refused": "the route is blocked",
        "blockers": [{"name": "rendering API", "detail": "Vulkan game", "fix": "use D3D11"}]
      }
      ''') as Map<String, dynamic>;
      final blockers = document['blockers'] as List<dynamic>;
      expect(blockers, hasLength(1));
      expect((blockers.first as Map<String, dynamic>)['detail'], 'Vulkan game');
    });

    test('a needs-confirmation document is distinguishable', () {
      final document = jsonDecode('''
      {"ok": false, "needs_confirmation": true, "plan": {"route": "a1"}}
      ''') as Map<String, dynamic>;
      expect(document['needs_confirmation'], isTrue);
      expect(document.containsKey('refused'), isFalse);
    });
  });

  group('launch options', () {
    test('state reports whether Steam is running, and blocks writes when it is', () {
      final blocked = LaunchOptionsState.fromJson({
        'appid': '1091500',
        'game': 'Cyberpunk 2077',
        'config': '/home/u/.local/share/Steam/userdata/1/config/localconfig.vdf',
        'launch_options': 'PROTON_FORCE_NVAPI=1 %command%',
        'steam_running': true,
      });
      expect(blocked.steamRunning, isTrue);
      expect(blocked.canWrite, isFalse, reason: 'Steam would revert the write');
      expect(blocked.hasValue, isTrue);
    });

    test('a game with no key is distinguishable from an empty one', () {
      final none = LaunchOptionsState.fromJson({
        'appid': '805550',
        'game': 'ACC',
        'config': '/x/localconfig.vdf',
        'launch_options': null,
        'steam_running': false,
      });
      expect(none.hasValue, isFalse);
      expect(none.canWrite, isTrue);
    });

    test('a written result carries backup and notes', () {
      final write = LaunchOptionsWrite.fromJson({
        'value': 'A=1 %command%',
        'config': '/x/localconfig.vdf',
        'backup': '/state/steam-config-backups/localconfig.vdf.20260925.bak',
        'created_key': true,
        'verified': true,
        'previous': null,
        'notes': ['Start Steam again for the change to be adopted.'],
      });
      expect(write.createdKey, isTrue);
      expect(write.verified, isTrue);
      expect(write.previous, isNull);
      expect(write.notes.single, contains('Start Steam again'));
    });
  });

  group('JournalEntry', () {
    test('states are mutually informative', () {
      final rolled = JournalEntry.fromJson({
        'id': 'j1',
        'route': 'a1',
        'game_dir': '/x',
        'operations': 5,
        'finished': true,
        'rolled_back': true,
      });
      expect(rolled.operations, 5);
      expect(rolled.rolledBack, isTrue);
      expect(rolled.finished, isTrue);
    });
  });

  group('ProviderRow', () {
    test('a resolution error is carried, not swallowed', () {
      final row = ProviderRow.fromJson({
        'key': 'optiscaler',
        'version': '(resolved at install)',
        'pinned': false,
        'error': 'network unreachable',
      });
      expect(row.error, 'network unreachable');
      expect(row.pinned, isFalse);
    });
  });
}
