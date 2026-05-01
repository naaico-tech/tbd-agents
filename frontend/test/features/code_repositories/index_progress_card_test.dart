import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:naaico_frontend/core/theme/app_theme.dart';
import 'package:naaico_frontend/features/code_repositories/code_repository_api.dart';
import 'package:naaico_frontend/features/code_repositories/index_job_controller.dart';
import 'package:naaico_frontend/features/code_repositories/index_job_models.dart';
import 'package:naaico_frontend/features/code_repositories/index_progress_card.dart';

/// A stub controller that bypasses any network. The widget calls `start()`
/// in its `initState`; we override it to a no-op and let the test feed
/// jobs in directly.
class _PrebakedController extends IndexJobController {
  _PrebakedController(IndexJob initial)
      : _job = initial,
        super(
          api: CodeRepositoryApi(client: _NoopClient()),
          repoId: 'repo1',
          jobId: 'job1',
        );

  IndexJob _job;
  bool cancelled = false;

  @override
  IndexJob? get job => _job;

  @override
  bool get isTerminal => _job.isTerminal;

  @override
  void start() {/* no network */}

  @override
  Future<void> cancel() async {
    cancelled = true;
  }

  void update(IndexJob j) {
    _job = j;
    notifyListeners();
  }
}

class _NoopClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    throw UnimplementedError('not used in widget test');
  }
}

IndexJob _job({
  JobState state = JobState.embedding,
  int chunksDone = 25,
  int chunksTotal = 100,
  String? currentFile,
  double? eta,
  IndexJobError? error,
  bool terminal = false,
}) =>
    IndexJob(
      id: 'job1',
      repoId: 'repo1',
      kind: JobKind.full,
      state: state,
      currentPhase: state.name,
      currentFile: currentFile,
      counters: IndexJobCounters(
        filesTotal: 10,
        filesDone: chunksDone ~/ 10,
        chunksTotal: chunksTotal,
        chunksDone: chunksDone,
      ),
      etaSeconds: eta,
      error: error,
      createdAt: DateTime.utc(2024, 1, 1),
      updatedAt: DateTime.utc(2024, 1, 1),
      isTerminal: terminal,
      progressPct:
          chunksTotal == 0 ? null : 100.0 * chunksDone / chunksTotal,
    );

Widget _wrap(Widget child) => MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('renders counters, ETA and a CANCEL button while running',
      (tester) async {
    final ctrl = _PrebakedController(
      _job(
        state: JobState.embedding,
        chunksDone: 25,
        chunksTotal: 100,
        currentFile: 'lib/very/long/path/to/some/source_file.dart',
        eta: 42,
      ),
    );
    await tester.pumpWidget(
      _wrap(IndexProgressCard(controller: ctrl, repoName: 'tbd-agents')),
    );

    expect(find.textContaining('2/10 files'), findsOneWidget);
    expect(find.textContaining('25/100 chunks'), findsOneWidget);
    expect(find.textContaining('25.0%'), findsWidgets);
    expect(find.textContaining('ETA 42s'), findsOneWidget);
    expect(find.text('CANCEL'), findsOneWidget);
    expect(find.text('DISMISS'), findsNothing);
    ctrl.dispose();
  });

  testWidgets('CANCEL invokes controller.cancel()', (tester) async {
    final ctrl = _PrebakedController(_job(state: JobState.embedding));
    await tester.pumpWidget(
      _wrap(IndexProgressCard(controller: ctrl, repoName: 'r')),
    );
    await tester.tap(find.text('CANCEL'));
    await tester.pump();
    expect(ctrl.cancelled, isTrue);
    ctrl.dispose();
  });

  testWidgets('terminal `done` swaps CANCEL for DISMISS and shows summary',
      (tester) async {
    final ctrl = _PrebakedController(
      _job(
        state: JobState.done,
        chunksDone: 100,
        chunksTotal: 100,
        terminal: true,
      ),
    );
    await tester.pumpWidget(
      _wrap(IndexProgressCard(controller: ctrl, repoName: 'r')),
    );

    expect(find.text('CANCEL'), findsNothing);
    expect(find.text('DISMISS'), findsOneWidget);
    expect(find.textContaining('Indexed'), findsOneWidget);
    ctrl.dispose();
  });

  testWidgets('failed state renders error banner with message', (tester) async {
    final ctrl = _PrebakedController(
      _job(
        state: JobState.failed,
        terminal: true,
        error: const IndexJobError(message: 'boom: kaboom'),
      ),
    );
    await tester.pumpWidget(
      _wrap(IndexProgressCard(controller: ctrl, repoName: 'r')),
    );
    expect(find.textContaining('boom: kaboom'), findsOneWidget);
    ctrl.dispose();
  });
}
