/// Cover thumbnails.
///
/// Steam publishes a portrait poster per app, and the engine caches one file per
/// game under its state directory. Rendering is therefore a plain file read, not
/// a network request in the frame loop — which matters, because a library of
/// twenty games would otherwise open twenty sockets while the user scrolls.
///
/// A game added by hand has no appid and no cover. That is normal, not an error,
/// so it gets a drawn placeholder with its initial rather than an empty box or a
/// broken-image glyph.
library;

import 'dart:io';

import 'package:flutter/material.dart';

import 'design.dart';

class CoverThumb extends StatelessWidget {
  const CoverThumb({
    super.key,
    required this.path,
    required this.name,
    this.width = 44,
    this.height = 66,
    this.radius = 4,
  });

  /// Absolute path to a cached image, or null when there is none.
  final String? path;
  final String name;
  final double width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final file = path == null ? null : File(path!);

    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: SizedBox(
        width: width,
        height: height,
        child:
            file != null
                ? LayoutBuilder(
                  builder: (context, constraints) {
                    final dpr = MediaQuery.devicePixelRatioOf(context);
                    final resolvedWidth =
                        constraints.hasBoundedWidth
                            ? constraints.maxWidth
                            : (width.isFinite ? width : 44.0);
                    final resolvedHeight =
                        constraints.hasBoundedHeight
                            ? constraints.maxHeight
                            : (height.isFinite ? height : 66.0);
                    // A finite per-axis budget bounds decode even on very large/high
                    // DPI windows. Fit preserves the source aspect ratio; BoxFit.cover
                    // handles any cropping, rather than distorting the decoded image.
                    final decodeWidth = (resolvedWidth * dpr).ceil().clamp(
                      1,
                      1024,
                    );
                    final decodeHeight = (resolvedHeight * dpr).ceil().clamp(
                      1,
                      1024,
                    );
                    return Image(
                      image: ResizeImage(
                        FileImage(file),
                        width: decodeWidth,
                        height: decodeHeight,
                        policy: ResizeImagePolicy.fit,
                      ),
                      fit: BoxFit.cover,
                      // A corrupt or half-written image must degrade to the
                      // placeholder, not to a red error box in the middle of a list.
                      errorBuilder:
                          (context, error, stack) => _Placeholder(
                            name: name,
                            width: width,
                            height: height,
                          ),
                      // Fade in on load so a scrolling list does not flash.
                      frameBuilder: (
                        context,
                        child,
                        frame,
                        wasSynchronouslyLoaded,
                      ) {
                        if (wasSynchronouslyLoaded || frame != null) {
                          return child;
                        }
                        return _Placeholder(
                          name: name,
                          width: width,
                          height: height,
                        );
                      },
                    );
                  },
                )
                : _Placeholder(name: name, width: width, height: height),
      ),
    );
  }
}

class _Placeholder extends StatelessWidget {
  const _Placeholder({
    required this.name,
    required this.width,
    required this.height,
  });

  final String name;
  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // The first character of the name. `substring` rather than the `characters`
    // package: for a CJK title this yields one code point, which is the initial;
    // pulling in a dependency to handle grapheme clusters would be overkill for
    // a placeholder.
    final trimmed = name.trim();
    final initial = trimmed.isEmpty ? '?' : trimmed.substring(0, 1);

    return LayoutBuilder(
      builder: (context, constraints) {
        // Grid covers request infinite dimensions to fill their slot. Use the
        // resolved height, never that request, when sizing the placeholder glyph.
        final resolvedHeight =
            constraints.hasBoundedHeight
                ? constraints.maxHeight
                : (height.isFinite ? height : 66.0);
        return Container(
          width: width,
          height: height,
          alignment: Alignment.center,
          color: theme.colorScheme.primary.withValues(alpha: 0.14),
          child: Text(
            initial,
            style: AppText.subtitle.copyWith(
              color: theme.colorScheme.primary,
              fontSize: (resolvedHeight * 0.34).clamp(12.0, 96.0),
            ),
          ),
        );
      },
    );
  }
}
