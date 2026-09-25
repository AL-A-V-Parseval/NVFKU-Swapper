/// Renders the real views to verify what they actually contain.
///
/// This exists because the screenshot harness produced a file it *called*
/// `01-games.png` whose contents were the Add-ons page — a mistake that image
/// review only catches by luck. A widget test asserts on the rendered text, so
/// "the wrong screen was captured" becomes a test failure, and the localisation is
/// verified where it matters: in the laid-out tree, not in the string table.
library;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nvfku_ui/src/app.dart';
import 'package:nvfku_ui/src/engine.dart';
import 'package:nvfku_ui/src/game_detail.dart';
import 'package:nvfku_ui/src/games_view.dart';
import 'package:nvfku_ui/src/models.dart';

Game _game({
  String appid = '805550',
  String name = 'Assetto Corsa Competizione',
  String source = 'steam',
  String? api = 'DirectX 12',
  List<String> nativeDlss = const ['nvngx_dll.dll'],
}) =>
    Game(
      appid: appid,
      name: name,
      installDir: '/games/$name',
      launchExe: 'Game.exe',
      bitness: 64,
      renderingApi: api,
      nativeDlss: nativeDlss,
      source: source,
    );

RoutePlan _plan({
  String route = 'a1',
  String title = 'A1',
  String detail = '',
  bool viable = true,
  List<EngineCheck> checks = const [],
  RoutePlan? prerequisite,
}) =>
    RoutePlan(
      route: route,
      title: title,
      detail: detail,
      gameName: 'X',
      gameDir: '/x',
      summary: 'summary for $route',
      viable: viable,
      readOnly: false,
      checks: checks,
      actions: const [],
      missing: const [],
      manualSteps: const [],
      prerequisite: prerequisite,
    );

/// Pumps at a realistic desktop size.
///
/// The default test viewport is 800x600, at which the games header legitimately
/// overflows and every test then fails for a reason unrelated to its assertion.
Future<void> _pumpAt(
  WidgetTester tester,
  Widget child, {
  Locale locale = const Locale('zh'),
}) async {
  tester.view.physicalSize = const Size(1440, 1000);
  tester.view.devicePixelRatio = 1.0;
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
      theme: Dlss5CtlApp.buildTheme(Brightness.dark),
      home: Scaffold(body: child),
    ),
  );
  await tester.pumpAndSettle();
}

Widget _gamesView({
  required List<Game> games,
  String filter = '',
  Map<String, String?> artwork = const {},
}) =>
    GamesView(
      games: games,
      filter: filter,
      onFilter: (_) {},
      onOpen: (_, {install = false}) {},
      onOpenFolder: (_) async {},
      onRescan: () async {},
      engine: _StubEngine(),
      busy: false,
      artwork: artwork,
    );

void main() {
  group('the shell', () {
    testWidgets('paints Chinese when the locale is zh', (tester) async {
      await _pumpAt(tester, const _ShellHarness(), locale: const Locale('zh'));

      // Twice: the sidebar item and the page heading. Asserting the count keeps
      // the test from passing if only one of them were translated.
      expect(find.text('游戏'), findsNWidgets(2), reason: 'nav item and heading');
      expect(find.text('组件'), findsOneWidget, reason: 'the Add-ons nav item');
      expect(find.text('历史'), findsOneWidget);
      expect(find.text('设置'), findsOneWidget);
      expect(find.text('Games'), findsNothing, reason: 'no English left behind');
    });

    testWidgets('paints English when the locale is en', (tester) async {
      await _pumpAt(tester, const _ShellHarness(), locale: const Locale('en'));

      expect(find.text('Games'), findsNWidgets(2), reason: 'nav item and heading');
      expect(find.text('Add-ons'), findsOneWidget);
      expect(find.text('游戏'), findsNothing);
    });
  });

  group('the games grid', () {
    testWidgets('lists each game and summarises in Chinese', (tester) async {
      await _pumpAt(
        tester,
        _gamesView(
          games: [_game(), _game(appid: '999', name: 'Test Game Two')],
        ),
      );

      // Once each: a poster card carries the name under the cover. The exact count
      // is asserted so a duplicated card would fail rather than pass.
      expect(find.text('Assetto Corsa Competizione'), findsOneWidget);
      expect(find.text('Test Game Two'), findsOneWidget);
      expect(find.textContaining('2 个游戏'), findsOneWidget);
      expect(find.textContaining('2 个自带 DLSS'), findsOneWidget);
      expect(find.text('DX12'), findsNWidgets(2), reason: 'one API badge per card');
    });

    testWidgets('a card shows the name, the API badge and its state',
        (tester) async {
      await _pumpAt(
        tester,
        _gamesView(
          games: [
            _game(
              appid: 'folder-abc',
              name: 'Hand Added',
              source: 'folder',
              api: null,
              nativeDlss: const [],
            ),
          ],
        ),
      );

      // The prefix and bitness moved into the sheet, which is where a card's
      // details belong; the card keeps what you scan for.
      expect(find.text('Hand Added'), findsOneWidget);
      expect(find.text('手动添加'), findsWidgets, reason: 'status line');
      expect(find.text('未知 API'), findsOneWidget, reason: 'API badge');
    });

    testWidgets('the empty state explains what to check', (tester) async {
      await _pumpAt(tester, _gamesView(games: const []));

      expect(find.text('没有找到游戏'), findsWidgets);
      expect(find.text('添加文件夹'), findsOneWidget);
      expect(find.textContaining('libraryfolders.vdf'), findsOneWidget);
    });

    testWidgets('a filter with no matches names the filter', (tester) async {
      await _pumpAt(tester, _gamesView(games: [_game()], filter: 'zzzz'));

      expect(find.text('没有匹配项'), findsOneWidget);
      expect(find.textContaining('zzzz'), findsOneWidget);
    });
  });

  group('cover thumbnails', () {
    testWidgets('a game with no cover still renders its name and initial',
        (tester) async {
      await _pumpAt(tester, _gamesView(games: [_game()]));

      expect(find.text('Assetto Corsa Competizione'), findsOneWidget);
      // The placeholder draws the first character, so the card keeps its shape
      // instead of collapsing.
      expect(find.text('A'), findsOneWidget);
    });

    testWidgets('a missing file degrades to the placeholder, not an error',
        (tester) async {
      await _pumpAt(
        tester,
        _gamesView(
          games: [_game()],
          artwork: const {'805550': '/does/not/exist/cover.jpg'},
        ),
      );

      expect(find.text('Assetto Corsa Competizione'), findsOneWidget);
      expect(find.text('A'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  /// A route's prerequisite is nested under it, not listed as a sibling.
  ///
  /// The plan used to return ReShade as a third route, which made it read as three
  /// options when there are two. This asserts the shape a user actually sees.
  /// The Steam gate: the install button is held while Steam runs.
  ///
  /// A1 cannot work without its launch options, and Steam reverts a write made
  /// while it is up. So the button must be disabled with the reason visible, not
  /// enabled and then fail.
  /// The developer-facing detail is folded away, and a blocker opens it.
  ///
  /// The reason this needs a test: "collapsed by default" and "opened when
  /// something is wrong" are opposite defaults, and getting the second one wrong
  /// turns a blocker into something the user has to go hunting for.
  /// The route names describe the choice; the mechanism is folded away.
  group('route naming', () {
    testWidgets('shows a plain name, not an internal route code',
        (tester) async {
      await _pumpAt(
        tester,
        GameDetailHarness(
          plans: [
            _plan(route: 'a1', title: 'ReShade 叠层'),
            _plan(route: 'a2', title: 'OptiScaler 直连'),
          ],
        ),
      );

      expect(find.text('ReShade 叠层'), findsOneWidget);
      expect(find.text('OptiScaler 直连'), findsOneWidget);
      // The A1/A2 codes and the component list are gone from what a chooser sees.
      expect(find.textContaining('A1 —'), findsNothing);
      expect(find.textContaining('A2 —'), findsNothing);
      expect(find.textContaining('dlss5-bridge'), findsNothing);
    });

    testWidgets('a blocked route explains itself on the card', (tester) async {
      await _pumpAt(
        tester,
        GameDetailHarness(
          plans: [
            _plan(
              viable: false,
              checks: const [
                EngineCheck(
                  name: '反作弊',
                  severity: 'blocker',
                  detail: '检测到 EAC，注入会被拒绝',
                ),
              ],
            ),
          ],
        ),
      );

      // On the card, not behind the disclosure: the pill says "blocked" and that
      // raises a question the card must answer.
      expect(find.textContaining('检测到 EAC'), findsWidgets);
      // The pill itself must not be the only signal.
      expect(find.text('受阻'), findsWidgets);
    });
  });

  group('the developer detail disclosure', () {
    testWidgets('is collapsed when the route is ready', (tester) async {
      await _pumpAt(
        tester,
        GameDetailHarness(
          plans: [
            _plan(
              checks: const [
                // A string that appears nowhere else on the page, so "not found"
                // really means the disclosure is closed rather than that the text
                // happens to match something in the facts table above it.
                EngineCheck(
                  name: 'disclosure-marker',
                  severity: 'ok',
                  detail: 'detail-behind-the-fold',
                ),
              ],
            ),
          ],
        ),
      );

      // The disclosure exists and is labelled...
      expect(find.text('检查项与将执行的动作'), findsOneWidget);
      // ...but its contents are not laid out while it is closed.
      expect(find.text('disclosure-marker'), findsNothing);
      expect(find.text('detail-behind-the-fold'), findsNothing);
    });

    testWidgets('is absent entirely when there is nothing to disclose',
        (tester) async {
      // A route with no checks and no actions should not offer to show them.
      await _pumpAt(tester, GameDetailHarness(plans: [_plan()]));
      expect(find.text('检查项与将执行的动作'), findsNothing);
    });

    testWidgets('is open when the route is blocked, naming the blocker',
        (tester) async {
      await _pumpAt(
        tester,
        GameDetailHarness(
          plans: [
            _plan(
              viable: false,
              checks: const [
                EngineCheck(
                  name: 'rendering API',
                  severity: 'blocker',
                  detail: 'Vulkan cannot load a DLL proxy',
                ),
              ],
            ),
          ],
        ),
      );

      // The blocker is stated on the card itself, without opening anything.
      expect(
        find.textContaining('Vulkan cannot load a DLL proxy'),
        findsWidgets,
        reason: 'a blocked route must say why on the card',
      );
    });

    testWidgets('opens on tap, revealing what it held', (tester) async {
      // Collapsed-by-default is only half the contract; a disclosure that cannot
      // be opened is a worse bug than one that starts open.
      await _pumpAt(
        tester,
        GameDetailHarness(
          plans: [
            _plan(
              checks: const [
                EngineCheck(
                  name: 'disclosure-marker',
                  severity: 'ok',
                  detail: 'detail-behind-the-fold',
                ),
              ],
            ),
          ],
        ),
      );

      expect(find.text('detail-behind-the-fold'), findsNothing);
      await tester.tap(find.text('检查项与将执行的动作'));
      await tester.pumpAndSettle();
      expect(find.text('disclosure-marker'), findsOneWidget);
      expect(find.text('detail-behind-the-fold'), findsOneWidget);
    });

    testWidgets('the mechanism is behind its own disclosure', (tester) async {
      await _pumpAt(
        tester,
        GameDetailHarness(plans: [_plan(detail: 'it hooks NGX and copies bytes')]),
      );

      expect(find.text('它是怎么工作的'), findsOneWidget);
      expect(find.text('it hooks NGX and copies bytes'), findsNothing,
          reason: 'the mechanism starts folded');
    });
  });

  group('the Steam gate', () {
    testWidgets('a running Steam disables the confirm button',
        (tester) async {
      await _pumpAt(
        tester,
        GameDetailHarness(
          plans: [_plan()],
          steamRunning: true,
        ),
      );

      // The blocked label is what the button reads; the confirm label must be gone.
      expect(find.text('等待 Steam 关闭'), findsWidgets);
      expect(find.text('确认并安装'), findsNothing);
      // And the reason is on screen rather than in a tooltip only.
      expect(find.text('请关闭 Steam 后继续'), findsWidgets);
    });

    testWidgets('a closed Steam shows the confirm button', (tester) async {
      await _pumpAt(
        tester,
        GameDetailHarness(plans: [_plan()], steamRunning: false),
      );

      expect(find.text('确认并安装'), findsOneWidget);
      expect(find.text('等待 Steam 关闭'), findsNothing);
    });
  });

  group('a route prerequisite', () {
    testWidgets('is rendered inside the route, labelled', (tester) async {
      final reshade = _plan(route: 'reshade', title: 'ReShade 6.8.0');
      await _pumpAt(
        tester,
        GameDetailHarness(plans: [_plan(prerequisite: reshade)]),
      );

      expect(find.text('A1'), findsOneWidget);
      expect(find.text('ReShade 6.8.0'), findsOneWidget,
          reason: 'the component is named under its route');
      expect(find.text('前置'), findsOneWidget, reason: 'the nesting label');
      expect(find.text('安装'), findsWidgets,
          reason: 'a component keeps its own install action');
    });

    testWidgets('a route without one shows no nesting label', (tester) async {
      await _pumpAt(tester, GameDetailHarness(plans: [_plan(route: 'a2')]));
      expect(find.text('前置'), findsNothing);
    });
  });
}

/// The real shell with an empty library and an engine that does no I/O.
class _ShellHarness extends StatelessWidget {
  const _ShellHarness();

  @override
  Widget build(BuildContext context) => Shell(
        engine: _QuietEngine(),
        initialGames: const [],
        // Stated rather than defaulted: the shell opens on Home, and these
        // assertions are about the Games view.
        initialView: AppView.games,
      );
}

/// Renders [GameDetailView] with plans supplied directly.
///
/// The view loads its own plans through the engine, so this stub returns the given
/// list: the point is to assert what the view draws for a known plan shape, not to
/// exercise the engine again.
class GameDetailHarness extends StatelessWidget {
  const GameDetailHarness({
    super.key,
    required this.plans,
    this.steamRunning = false,
  });

  final List<RoutePlan> plans;
  final bool steamRunning;

  @override
  Widget build(BuildContext context) => GameDetailView(
        game: _game(),
        engine: _PlanEngine(plans, steamRunning: steamRunning),
        onBack: () {},
        onChanged: () async {},
        embedded: true,
      );
}

class _PlanEngine implements Engine {
  _PlanEngine(this.plans, {this.steamRunning = false});

  final List<RoutePlan> plans;

  /// The view re-reads the live Steam state on a timer, so this is what decides
  /// whether the gate is closed.
  final bool steamRunning;

  @override
  Future<List<RoutePlan>> plan(String gameKey, {String? route}) async => plans;

  /// The detail view also renders the Steam launch-option panel, which reads the
  /// current value on mount.
  @override
  Future<LaunchOptionsState> launchOptions(String gameKey) async =>
      LaunchOptionsState(
        appid: '805550',
        game: 'X',
        config: '/x/localconfig.vdf',
        steamRunning: steamRunning,
      );

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('unexpected engine call: ${invocation.memberName}');
}

/// Fails loudly, for views that must render without touching the engine.
class _StubEngine implements Engine {
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('rendering must not call the engine');
}

/// Answers the calls the shell makes while rendering, and nothing else.
///
/// `noSuchMethod` cannot cover these: it returns `Future<dynamic>`, which is not
/// assignable to `Future<String>`, so an untyped stub fails with a type error that
/// looks like a bug in the widget. The methods the shell actually calls are
/// therefore implemented explicitly and the rest still throw.
class _QuietEngine implements Engine {
  @override
  Future<String> version() async => 'nvfku test';

  @override
  Future<List<Game>> scan() async => const [];

  @override
  Future<Map<String, String?>> cachedArtwork() async => const {};

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('unexpected engine call: ${invocation.memberName}');
}
