import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nvfku_ui/src/home_view.dart';
import 'package:nvfku_ui/src/app.dart';
import 'package:nvfku_ui/src/settings_view.dart';

import 'shell_accessibility_test.dart' show pumpShell;

void main() {
  for (final width in [760.0, 844.0]) {
    for (final locale in [const Locale('en'), const Locale('zh')]) {
      for (final brightness in Brightness.values) {
        for (final view in AppView.values) {
          testWidgets('desktop tile $width $locale $brightness $view 2x', (
            tester,
          ) async {
            await pumpShell(
              tester,
              size: Size(width, 700),
              locale: locale,
              brightness: brightness,
              scale: 2,
              view: view,
            );
            expect(tester.takeException(), isNull);
            expect(find.byType(Drawer), findsNothing);
          });
        }
      }
    }
  }
  testWidgets('typical 844px Wayland tile keeps navigation visible', (
    tester,
  ) async {
    await pumpShell(tester, size: const Size(844, 1011), view: AppView.home);
    expect(find.text('Games').hitTestable(), findsOneWidget);
    expect(find.text('Settings').hitTestable(), findsOneWidget);
    expect(find.byType(Drawer), findsNothing);
  });

  testWidgets('wide sidebar starts at top and fills the window height', (
    tester,
  ) async {
    await pumpShell(tester, size: const Size(1200, 1000));
    final sidebarScroll = find.byType(SingleChildScrollView).first;
    final rect = tester.getRect(sidebarScroll);
    expect(rect.top, lessThanOrEqualTo(16));
    expect(rect.bottom, greaterThanOrEqualTo(980));
  });

  testWidgets(
    'home drop panel fills content width instead of shrink wrapping',
    (tester) async {
      await pumpShell(tester, size: const Size(1200, 900), view: AppView.home);
      final rect = tester.getRect(find.byType(DropZone));
      expect(rect.width, greaterThan(850));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('narrow navigation has an explicit bundled menu icon and opens', (
    tester,
  ) async {
    await pumpShell(tester, size: const Size(480, 700));
    // An explicit constant Icon is also required by release font tree shaking.
    expect(find.byIcon(Icons.menu).hitTestable(), findsOneWidget);
    await tester.tap(find.byIcon(Icons.menu));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Settings').first);
    await tester.pumpAndSettle();
    expect(find.byType(Drawer).hitTestable(), findsNothing);
    expect(find.byType(SettingsView), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
