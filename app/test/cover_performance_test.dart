import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nvfku_ui/src/cover.dart';

class ObservedCoverFile extends Fake implements File {
  ObservedCoverFile(this.path);
  @override
  final String path;
  int synchronousStats = 0;
  @override
  bool existsSync() {
    synchronousStats++;
    return false;
  }

  @override
  Future<int> length() async => 0;
}

class EncodedCoverFile extends ObservedCoverFile {
  EncodedCoverFile(super.path, this.bytes);
  final Uint8List bytes;
  @override
  Future<int> length() async => bytes.length;
  @override
  Future<Uint8List> readAsBytes() async => bytes;
}

void main() {
  testWidgets(
    'high resolution artwork actually decodes within the thumbnail pixel budget',
    (tester) async {
      final bytes = await tester.runAsync(() async {
        final recorder = ui.PictureRecorder();
        final canvas = Canvas(recorder);
        canvas.drawRect(
          const Rect.fromLTWH(0, 0, 2048, 3072),
          Paint()..color = Colors.green,
        );
        final picture = recorder.endRecording();
        final source = await picture.toImage(2048, 3072);
        final data = await source.toByteData(format: ui.ImageByteFormat.png);
        source.dispose();
        picture.dispose();
        return data!.buffer.asUint8List();
      });
      final file = EncodedCoverFile('/high-resolution-fixture-cover', bytes!);
      await IOOverrides.runZoned(() async {
        await tester.pumpWidget(
          MaterialApp(
            home: MediaQuery(
              data: const MediaQueryData(devicePixelRatio: 2),
              child: Center(
                child: CoverThumb(
                  path: file.path,
                  name: 'Fixture',
                  width: 100,
                  height: 150,
                ),
              ),
            ),
          ),
        );
        final provider = tester.widget<Image>(find.byType(Image)).image;
        final watch = Stopwatch()..start();
        final decoded = await tester.runAsync(() async {
          final ready = Completer<ImageInfo>();
          final stream = provider.resolve(const ImageConfiguration());
          late ImageStreamListener listener;
          listener = ImageStreamListener(
            (info, _) {
              if (!ready.isCompleted) ready.complete(info.clone());
            },
            onError:
                (Object error, StackTrace? stack) =>
                    ready.completeError(error, stack),
          );
          stream.addListener(listener);
          try {
            return await ready.future;
          } finally {
            stream.removeListener(listener);
          }
        });
        watch.stop();
        expect(decoded!.image.width, 200);
        expect(decoded.image.height, 300);
        // Debug test-codec probe, not a native desktop frame-time benchmark.
        debugPrint(
          'cover decode probe: 2048x3072 -> ${decoded.image.width}x${decoded.image.height}, '
          '${watch.elapsedMicroseconds}us; decoded RGBA budget 240000 bytes',
        );
        decoded.dispose();
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      }, createFile: (_) => file);
    },
  );
  testWidgets('Cover limits decode to resolved finite layout times DPR', (
    tester,
  ) async {
    final file = ObservedCoverFile('/decode-budget-cover');
    await IOOverrides.runZoned(() async {
      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(devicePixelRatio: 2),
            child: Center(
              child: SizedBox(
                width: 100,
                height: 150,
                child: CoverThumb(
                  path: file.path,
                  name: 'Fixture',
                  width: double.infinity,
                  height: double.infinity,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final image = tester.widget<Image>(find.byType(Image));
      expect(image.image, isA<ResizeImage>());
      final resize = image.image as ResizeImage;
      expect(resize.width, 200);
      expect(resize.height, 300);
      expect(resize.policy, ResizeImagePolicy.fit);
      expect(tester.takeException(), isNull);
    }, createFile: (_) => file);
  });
  testWidgets('Cover builds and rebuilds without synchronous filesystem stat', (
    tester,
  ) async {
    final file = ObservedCoverFile('/missing-cover');
    await IOOverrides.runZoned(() async {
      for (var frame = 0; frame < 3; frame++) {
        await tester.pumpWidget(
          MaterialApp(
            home: Center(
              child: CoverThumb(path: file.path, name: 'Fixture $frame'),
            ),
          ),
        );
        await tester.pumpAndSettle();
      }
      expect(file.synchronousStats, 0);
      expect(find.text('F'), findsOneWidget);
      expect(tester.takeException(), isNull);
    }, createFile: (_) => file);
  });
}
