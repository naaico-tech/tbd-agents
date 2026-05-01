// Hand-rolled Dart models mirroring the backend `IndexJob*` Pydantic schemas
// in `app/schemas/code_repository.py`. Kept dependency-free (no freezed /
// json_serializable) to match the rest of `lib/features/...`.

/// Lifecycle states for an [IndexJob]. Order matches the backend enum.
enum JobState {
  queued,
  discovering,
  hashing,
  embedding,
  upserting,
  committed,
  done,
  failed,
  cancelled;

  static JobState parse(String? raw) {
    for (final s in JobState.values) {
      if (s.name == raw) return s;
    }
    return JobState.queued;
  }

  bool get isTerminal =>
      this == JobState.done ||
      this == JobState.failed ||
      this == JobState.cancelled;
}

enum JobKind {
  full,
  incremental;

  static JobKind parse(String? raw) =>
      raw == 'incremental' ? JobKind.incremental : JobKind.full;
}

class IndexJobCounters {
  const IndexJobCounters({
    this.filesTotal = 0,
    this.filesDone = 0,
    this.filesFailed = 0,
    this.chunksTotal = 0,
    this.chunksDone = 0,
    this.bytesDone = 0,
    this.filesAdded = 0,
    this.filesModified = 0,
    this.filesDeleted = 0,
  });

  final int filesTotal;
  final int filesDone;
  final int filesFailed;
  final int chunksTotal;
  final int chunksDone;
  final int bytesDone;
  final int filesAdded;
  final int filesModified;
  final int filesDeleted;

  static int _i(Map<String, dynamic> m, String k) {
    final v = m[k];
    if (v is int) return v;
    if (v is num) return v.toInt();
    if (v is String) return int.tryParse(v) ?? 0;
    return 0;
  }

  factory IndexJobCounters.fromJson(Map<String, dynamic> json) =>
      IndexJobCounters(
        filesTotal: _i(json, 'files_total'),
        filesDone: _i(json, 'files_done'),
        filesFailed: _i(json, 'files_failed'),
        chunksTotal: _i(json, 'chunks_total'),
        chunksDone: _i(json, 'chunks_done'),
        bytesDone: _i(json, 'bytes_done'),
        filesAdded: _i(json, 'files_added'),
        filesModified: _i(json, 'files_modified'),
        filesDeleted: _i(json, 'files_deleted'),
      );
}

class IndexJobError {
  const IndexJobError({required this.message, this.traceback});

  final String message;
  final String? traceback;

  factory IndexJobError.fromJson(Map<String, dynamic> json) => IndexJobError(
        message: (json['message'] ?? '').toString(),
        traceback: json['traceback']?.toString(),
      );
}

class IndexJob {
  const IndexJob({
    required this.id,
    required this.repoId,
    required this.kind,
    required this.state,
    required this.currentPhase,
    this.currentFile,
    required this.counters,
    this.headCommitSha,
    this.baseCommitSha,
    this.startedAt,
    this.finishedAt,
    this.etaSeconds,
    this.error,
    this.shardCount = 1,
    this.shardsDone = 0,
    required this.createdAt,
    required this.updatedAt,
    required this.isTerminal,
    this.progressPct,
  });

  final String id;
  final String repoId;
  final JobKind kind;
  final JobState state;
  final String currentPhase;
  final String? currentFile;
  final IndexJobCounters counters;
  final String? headCommitSha;
  final String? baseCommitSha;
  final DateTime? startedAt;
  final DateTime? finishedAt;
  final double? etaSeconds;
  final IndexJobError? error;
  final int shardCount;
  final int shardsDone;
  final DateTime createdAt;
  final DateTime updatedAt;
  final bool isTerminal;
  final double? progressPct;

  static DateTime? _dt(Object? v) {
    if (v == null) return null;
    return DateTime.tryParse(v.toString());
  }

  static double? _d(Object? v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }

  factory IndexJob.fromJson(Map<String, dynamic> json) {
    final state = JobState.parse(json['state']?.toString());
    return IndexJob(
      id: (json['id'] ?? '').toString(),
      repoId: (json['repo_id'] ?? '').toString(),
      kind: JobKind.parse(json['kind']?.toString()),
      state: state,
      currentPhase: (json['current_phase'] ?? '').toString(),
      currentFile: json['current_file']?.toString(),
      counters: IndexJobCounters.fromJson(
        (json['counters'] as Map?)?.cast<String, dynamic>() ?? const {},
      ),
      headCommitSha: json['head_commit_sha']?.toString(),
      baseCommitSha: json['base_commit_sha']?.toString(),
      startedAt: _dt(json['started_at']),
      finishedAt: _dt(json['finished_at']),
      etaSeconds: _d(json['eta_seconds']),
      error: json['error'] is Map
          ? IndexJobError.fromJson((json['error'] as Map).cast<String, dynamic>())
          : null,
      shardCount: (json['shard_count'] as num?)?.toInt() ?? 1,
      shardsDone: (json['shards_done'] as num?)?.toInt() ?? 0,
      createdAt: _dt(json['created_at']) ?? DateTime.now(),
      updatedAt: _dt(json['updated_at']) ?? DateTime.now(),
      isTerminal: (json['is_terminal'] as bool?) ?? state.isTerminal,
      progressPct: _d(json['progress_pct']),
    );
  }

  /// Best-effort progress in [0, 1]. Falls back to chunks_done / chunks_total
  /// when the server didn't compute progress_pct yet.
  double? get progressFraction {
    if (progressPct != null) return (progressPct! / 100.0).clamp(0.0, 1.0);
    if (counters.chunksTotal > 0) {
      return (counters.chunksDone / counters.chunksTotal).clamp(0.0, 1.0);
    }
    if (isTerminal && state == JobState.done) return 1.0;
    return null;
  }
}

class IndexJobEnqueueResponse {
  const IndexJobEnqueueResponse({
    required this.jobId,
    required this.state,
    required this.idempotent,
  });

  final String jobId;
  final String state;
  final bool idempotent;

  factory IndexJobEnqueueResponse.fromJson(Map<String, dynamic> json) =>
      IndexJobEnqueueResponse(
        jobId: (json['job_id'] ?? '').toString(),
        state: (json['state'] ?? 'queued').toString(),
        idempotent: (json['idempotent'] as bool?) ?? false,
      );
}
