import 'dart:async';

import 'package:flutter/foundation.dart';

import 'code_repository_api.dart';
import 'index_job_models.dart';

/// Drives a single [IndexJob]'s live state for the progress UI.
///
/// Strategy:
/// 1. On [start], opens the SSE stream from [CodeRepositoryApi.jobEvents].
/// 2. Forwards each [IndexJob] update via [ChangeNotifier].
/// 3. If the SSE stream errors out (after the API client's own retries),
///    falls back to polling [CodeRepositoryApi.getJob] every 5 s until the
///    job reaches a terminal state.
///
/// We use `ChangeNotifier` because `package:provider` is already in pubspec
/// and the rest of `lib/features/...` is plain `StatefulWidget` — adding
/// Riverpod / Bloc just for one screen would be a net negative.
class IndexJobController extends ChangeNotifier {
  IndexJobController({
    required this.api,
    required this.repoId,
    required this.jobId,
    this.pollInterval = const Duration(seconds: 5),
  });

  final CodeRepositoryApi api;
  final String repoId;
  final String jobId;
  final Duration pollInterval;

  IndexJob? _job;
  Object? _error;
  bool _disposed = false;
  StreamSubscription<IndexJob>? _sseSub;
  Timer? _pollTimer;
  bool _useFallbackPolling = false;

  IndexJob? get job => _job;
  Object? get error => _error;
  bool get isTerminal => _job?.isTerminal ?? false;
  bool get isPolling => _useFallbackPolling;

  /// Begin listening. Idempotent — calling twice is a no-op.
  void start() {
    if (_sseSub != null || _pollTimer != null || _disposed) return;
    _sseSub = api.jobEvents(repoId, jobId).listen(
      _onJob,
      onError: (Object e, StackTrace st) {
        // SSE failed after its own retries. Switch to polling.
        _error = e;
        _switchToPolling();
      },
      onDone: () {
        _sseSub = null;
        // If the connection closed without a terminal payload, fall back
        // to polling so we don't leave the UI stuck mid-flight.
        if (!_disposed && !isTerminal) _switchToPolling();
      },
    );
  }

  void _onJob(IndexJob j) {
    _job = j;
    _error = null;
    notifyListeners();
    if (j.isTerminal) _stopAll();
  }

  void _switchToPolling() {
    if (_disposed || isTerminal) return;
    _useFallbackPolling = true;
    notifyListeners();
    _pollTimer ??= Timer.periodic(pollInterval, (_) => _pollOnce());
    // Fire immediately so the UI doesn't wait a full interval after
    // SSE drops.
    _pollOnce();
  }

  Future<void> _pollOnce() async {
    if (_disposed) return;
    try {
      final j = await api.getJob(repoId, jobId);
      _onJob(j);
    } catch (e) {
      _error = e;
      if (!_disposed) notifyListeners();
    }
  }

  void _stopAll() {
    _sseSub?.cancel();
    _sseSub = null;
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  /// Request job cancellation server-side. Local state will reflect the
  /// new terminal state via the next SSE / poll tick.
  Future<void> cancel() async {
    try {
      await api.cancelJob(repoId, jobId);
    } catch (e) {
      _error = e;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _stopAll();
    super.dispose();
  }
}
