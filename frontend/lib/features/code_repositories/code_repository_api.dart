import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/config/app_links.dart';
import 'index_job_models.dart';
import 'sse_parser.dart';

/// Thin wrapper around the `/api/code-repositories/{id}/...` index-job
/// endpoints introduced in PR1 of the indexing redesign.
///
/// The existing screen issues raw `http` calls inline; this class exists
/// specifically because the new SSE flow needs lifecycle management
/// (long-lived response, retries, cancellation) that doesn't belong inline
/// in the widget. CRUD on repositories themselves continues to live in the
/// screen — we don't churn that.
class CodeRepositoryApi {
  CodeRepositoryApi({http.Client? client})
      : _client = client ?? http.Client(),
        _ownsClient = client == null;

  final http.Client _client;
  final bool _ownsClient;

  void dispose() {
    if (_ownsClient) _client.close();
  }

  // ── Job lifecycle ─────────────────────────────────────────────────────────

  /// `POST /api/code-repositories/{repoId}/index` → 202.
  Future<IndexJobEnqueueResponse> startIndex(String repoId) async {
    final resp = await _client.post(
      AppLinks.apiUri('/code-repositories/$repoId/index'),
      headers: const {'Content-Type': 'application/json'},
    );
    _ensure2xx(resp);
    return IndexJobEnqueueResponse.fromJson(
      (jsonDecode(resp.body) as Map).cast<String, dynamic>(),
    );
  }

  /// `GET /api/code-repositories/{repoId}/jobs` → newest 50 jobs.
  Future<List<IndexJob>> listJobs(String repoId) async {
    final resp = await _client.get(
      AppLinks.apiUri('/code-repositories/$repoId/jobs'),
    );
    _ensure2xx(resp);
    final decoded = jsonDecode(resp.body);
    if (decoded is! List) return const [];
    return decoded
        .whereType<Map>()
        .map((e) => IndexJob.fromJson(e.cast<String, dynamic>()))
        .toList();
  }

  /// `GET /api/code-repositories/{repoId}/jobs/{jobId}` → snapshot.
  Future<IndexJob> getJob(String repoId, String jobId) async {
    final resp = await _client.get(
      AppLinks.apiUri('/code-repositories/$repoId/jobs/$jobId'),
    );
    _ensure2xx(resp);
    return IndexJob.fromJson(
      (jsonDecode(resp.body) as Map).cast<String, dynamic>(),
    );
  }

  /// `POST /api/code-repositories/{repoId}/jobs/{jobId}/cancel`.
  /// 409 (already terminal) is treated as a no-op success.
  Future<void> cancelJob(String repoId, String jobId) async {
    final resp = await _client.post(
      AppLinks.apiUri('/code-repositories/$repoId/jobs/$jobId/cancel'),
    );
    if (resp.statusCode == 409) return;
    _ensure2xx(resp);
  }

  // ── SSE event stream ──────────────────────────────────────────────────────

  /// Live job updates from `GET /jobs/{jobId}/events`.
  ///
  /// Emits an [IndexJob] for every `progress` and `done` SSE event. Closes
  /// when the upstream connection closes (i.e. on the final `done` event).
  /// Auto-reconnects up to [maxRetries] times with exponential backoff
  /// (1s, 2s, 4s) while the last-known state is non-terminal. The stream is
  /// broadcast-safe and cancellation tears down the underlying request.
  Stream<IndexJob> jobEvents(
    String repoId,
    String jobId, {
    int maxRetries = 3,
    Duration baseBackoff = const Duration(seconds: 1),
  }) {
    final controller = StreamController<IndexJob>();
    StreamSubscription<SseEvent>? sub;
    Timer? reconnectTimer;
    var attempt = 0;
    var lastTerminal = false;
    var cancelled = false;

    Future<void> connect() async {
      if (cancelled || controller.isClosed) return;
      final req = http.Request(
        'GET',
        AppLinks.apiUri('/code-repositories/$repoId/jobs/$jobId/events'),
      );
      req.headers['Accept'] = 'text/event-stream';
      req.headers['Cache-Control'] = 'no-cache';

      void scheduleReconnect() {
        if (cancelled || controller.isClosed) return;
        if (attempt >= maxRetries) {
          if (!controller.isClosed) controller.close();
          return;
        }
        final delay = baseBackoff * (1 << attempt);
        attempt += 1;
        reconnectTimer?.cancel();
        reconnectTimer = Timer(delay, () {
          reconnectTimer = null;
          if (cancelled || controller.isClosed) return;
          connect();
        });
      }

      try {
        // Reuse the injected client so tests (and any DI) can stub the
        // transport. Cancelling [sub] tears down the byte-stream subscription,
        // which is what dart:io / browser clients use to abort the request.
        final resp = await _client.send(req);
        if (cancelled || controller.isClosed) return;
        if (resp.statusCode < 200 || resp.statusCode >= 300) {
          throw http.ClientException(
            'SSE stream returned ${resp.statusCode}',
            req.url,
          );
        }
        attempt = 0; // successful (re)connect resets backoff
        sub = decodeSseStream(resp.stream).listen(
          (ev) {
            if (ev.event != 'progress' && ev.event != 'done') return;
            final raw = ev.data.trim();
            if (raw.isEmpty || raw == '{}') return;
            try {
              final job = IndexJob.fromJson(
                (jsonDecode(raw) as Map).cast<String, dynamic>(),
              );
              lastTerminal = job.isTerminal;
              if (!controller.isClosed) controller.add(job);
            } catch (_) {
              // Ignore malformed payloads — heartbeat / partial chunks.
            }
          },
          onError: (Object e, StackTrace st) {
            if (!controller.isClosed) controller.addError(e, st);
          },
          onDone: () {
            if (cancelled || controller.isClosed) return;
            if (lastTerminal) {
              controller.close();
              return;
            }
            scheduleReconnect();
          },
        );
      } catch (e, st) {
        if (cancelled || controller.isClosed) return;
        if (attempt >= maxRetries) {
          controller.addError(e, st);
          if (!controller.isClosed) controller.close();
          return;
        }
        scheduleReconnect();
      }
    }

    controller.onListen = connect;
    controller.onCancel = () async {
      cancelled = true;
      reconnectTimer?.cancel();
      reconnectTimer = null;
      final s = sub;
      sub = null;
      await s?.cancel();
    };
    return controller.stream;
  }

  void _ensure2xx(http.Response resp) {
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      String detail = resp.body;
      try {
        final parsed = jsonDecode(resp.body);
        if (parsed is Map && parsed['detail'] != null) {
          detail = parsed['detail'].toString();
        }
      } catch (_) {}
      throw Exception('${resp.statusCode}: $detail');
    }
  }
}
