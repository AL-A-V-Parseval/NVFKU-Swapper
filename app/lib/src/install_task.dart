import 'dart:async';

import 'package:flutter/foundation.dart';

import 'models.dart';

/// An installation belongs to the application, not the sheet displaying it.
/// Removing a listener never cancels the engine's file operations. Terminal
/// results remain available when the user reopens the same game and route.
class InstallTask extends ChangeNotifier {
  bool running = false;
  InstallResult? result;
  String? error;
  String? _invalidatedJournalId;
  final List<String> _progress = [];
  List<String> get progress => List.unmodifiable(_progress);
  int completion = 0;

  void start(Stream<InstallEvent> Function() events) {
    if (running) throw StateError('This installation is already running.');
    running = true;
    result = null;
    error = null;
    _invalidatedJournalId = null;
    _progress.clear();
    notifyListeners();
    try {
      events().listen(
        (event) {
          if (!running) return;
          switch (event.phase) {
            case 'log':
              _progress.add(event.message);
              // Retain a useful tail without unbounded growth during a long run.
              if (_progress.length > 2000) _progress.removeAt(0);
              notifyListeners();
            case 'done':
              if (event.result == null) {
                _finish(error: 'The engine returned no installation result.');
              } else {
                _finish(result: event.result);
              }
            case 'failed':
              _finish(error: event.message);
          }
        },
        onError: (Object failure) => _finish(error: failure.toString()),
        onDone: () {
          if (running) {
            _finish(error: 'The engine stopped without a final installation result.');
          }
        },
      );
    } catch (failure) {
      _finish(error: failure.toString());
    }
  }

  /// A rollback attempt makes this receipt obsolete or uncertain. Keep a
  /// failure visible when reopening the sheet instead of showing green success.
  void clearRolledBackResult(String journalId, {String? error}) {
    if (result?.journalId != journalId && _invalidatedJournalId != journalId) return;
    result = null;
    _invalidatedJournalId = error == null ? null : journalId;
    this.error = error;
    notifyListeners();
  }

  void _finish({InstallResult? result, String? error}) {
    if (!running) return;
    this.result = result;
    this.error = error;
    running = false;
    completion++;
    notifyListeners();
  }
}
