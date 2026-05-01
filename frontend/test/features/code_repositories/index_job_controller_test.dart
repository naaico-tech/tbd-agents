import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:naaico_frontend/features/code_repositories/code_repository_api.dart';
import 'package:naaico_frontend/features/code_repositories/index_job_controller.dart';
import 'package:naaico_frontend/features/code_repositories/index_job_models.dart';

class _FakeClient extends http.BaseClient {
  _FakeClient({this.sseBytes, this.snapshots = const []});

  final Stream<List<int>>? sseBytes;
  final List<Map<String, dynamic>> snapshots;
  int _snapIdx = 0;

  int sendCalls = 0;
  int snapshotCalls = 0;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (request.url.path.endsWith('/events')) {
      sendCalls += 1;
      final body = sseBytes;
      if (body == null) {
        return http.StreamedResponse(const Stream<List<int>>.empty(), 500);
      }
      return http.StreamedResponse(
        body,
        200,
        headers: const {'content-type': 'text/event-stream'},
      );
    }
    snapshotCalls += 1;
    final json = snapshots[_snapIdx.clamp(0, snapshots.length - 1)];
    _snapIdx += 1;
    return http.StreamedResponse(
      Stream.value(utf8.encode(jsonEncode(json))),
      200,
      headers: const {'content-type': 'application/json'},
    );
  }
}

Map<String, dynamic> _jobJson({
  required String state,
  int chunksDone = 0,
  int chunksTotal = 100,
  bool terminal = false,
}) =>
    {
      'id': 'job1',
      'repo_id': 'repo1',
      'kind': 'full',
      'state': state,
      'current_phase': state,
      'current_file': null,
      'counters': {
        'files_total': 10,
        'files_done': chunksDone ~/ 10,
        'files_failed': 0,
        'chunks_total': chunksTotal,
        'chunks_done': chunksDone,
        'bytes_done': 0,
        'files_added': 0,
        'files_modified': 0,
        'files_deleted': 0,
      },
      'shard_count': 1,
      'shards_done': 0,
      'created_at': '2024-01-01T00:00:00Z',
      'updated_at': '2024-01-01T00:00:00Z',
      'is_terminal': terminal,
      'progress_pct':
          chunksTotal == 0 ? null : 100.0 * chunksDone / chunksTotal,
    };

void main() {
  test('IndexJob.fromJson parses backend payload', () {
    final j = IndexJob.fromJson(_jobJson(state: 'embedding', chunksDone: 25));
    expect(j.state, equals(JobState.embedding));
    expect(j.counters.chunksDone, equals(25));
    expect(j.progressFraction, closeTo(0.25, 1e-6));
    expect(j.isTerminal, isFalse);
  });

  test('JobState.isTerminal flags done/failed/cancelled', () {
    expect(JobState.done.isTerminal, isTrue);
    expect(JobState.failed.isTerminal, isTrue);
    expect(JobState.cancelled.isTerminal, isTrue);
    expect(JobState.embedding.isTerminal, isFalse);
  });

  test('IndexJobController transitions queued → embedding → done via SSE',
      () async {
    final controller = StreamController<List<int>>();
    final fake = _FakeClient(sseBytes: controller.stream);
    final api = CodeRepositoryApi(client: fake);
    final ctrl = IndexJobController(api: api, repoId: 'repo1', jobId: 'job1');

    final received = <JobState>[];
    ctrl.addListener(() {
      final s = ctrl.job?.state;
      if (s != null && (received.isEmpty || received.last != s)) {
        received.add(s);
      }
    });
    ctrl.start();

    Future<void> push(Map<String, dynamic> j, String evt) async {
      controller.add(utf8.encode('event: $evt\ndata: ${jsonEncode(j)}\n\n'));
      // Yield so the stream subscription delivers before the next push.
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }

    await push(_jobJson(state: 'queued'), 'progress');
    await push(_jobJson(state: 'embedding', chunksDone: 50), 'progress');
    await push(
      _jobJson(state: 'done', chunksDone: 100, terminal: true),
      'done',
    );
    await controller.close();
    await Future<void>.delayed(const Duration(milliseconds: 20));

    expect(received,
        equals([JobState.queued, JobState.embedding, JobState.done]));
    expect(ctrl.isTerminal, isTrue);
    ctrl.dispose();
  });
}
