import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme/design_tokens.dart';
import '../../core/widgets/retro_card.dart';
import 'index_job_controller.dart';
import 'index_job_models.dart';

/// VS Code-style live progress strip for an [IndexJob].
///
/// Lifecycle:
/// - Subscribes to [IndexJobController] in [initState] and listens for
///   notifications.
/// - On a terminal `done` state, schedules an auto-collapse 5 s later.
/// - Disposes the controller via [onDispose] (the parent owns the API
///   client; we only own the controller's lifecycle).
class IndexProgressCard extends StatefulWidget {
  const IndexProgressCard({
    super.key,
    required this.controller,
    required this.repoName,
    this.onDismiss,
  });

  final IndexJobController controller;
  final String repoName;

  /// Called when the card auto-collapses (5 s after terminal `done`)
  /// or when the user explicitly dismisses a finished/failed run.
  final VoidCallback? onDismiss;

  @override
  State<IndexProgressCard> createState() => _IndexProgressCardState();
}

class _IndexProgressCardState extends State<IndexProgressCard> {
  Timer? _autoCollapse;
  bool _tracebackOpen = false;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onChange);
    widget.controller.start();
  }

  @override
  void dispose() {
    _autoCollapse?.cancel();
    widget.controller.removeListener(_onChange);
    super.dispose();
  }

  void _onChange() {
    if (!mounted) return;
    setState(() {});
    final job = widget.controller.job;
    if (job?.state == JobState.done && _autoCollapse == null) {
      _autoCollapse = Timer(const Duration(seconds: 5), () {
        if (mounted) widget.onDismiss?.call();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final job = c.job;

    return RetroCard(
      background: cardBg,
      child: job == null ? _buildBootstrapping(c) : _buildJob(job, c),
    );
  }

  // ── Sub-views ──────────────────────────────────────────────────────────

  Widget _buildBootstrapping(IndexJobController c) {
    return Row(
      children: [
        const SizedBox(
          width: 14,
          height: 14,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        const SizedBox(width: sp12),
        Expanded(
          child: Text(
            c.error == null
                ? 'Connecting to index job…'
                : 'Lost connection — retrying (${c.error})',
            style: const TextStyle(
              fontFamily: fontBody,
              fontSize: 13,
              color: textMuted,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildJob(IndexJob job, IndexJobController c) {
    final pct = job.progressFraction;
    final pctLabel = pct == null ? '—' : '${(pct * 100).toStringAsFixed(1)}%';
    final phaseColor = _phaseColor(job.state);

    final subtitleParts = <String>[
      job.currentPhase.isEmpty ? job.state.name : job.currentPhase,
      if ((job.currentFile ?? '').isNotEmpty) _midEllipsis(job.currentFile!, 60),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Header row: title + state pill + (cancel|dismiss).
        Row(
          children: [
            Expanded(
              child: Text(
                'INDEXING ${widget.repoName.toUpperCase()}',
                style: const TextStyle(
                  fontFamily: fontDisplay,
                  fontSize: 10,
                  color: textPrimary,
                  letterSpacing: 1,
                ),
              ),
            ),
            RetroChip(label: job.state.name, color: phaseColor),
            const SizedBox(width: sp8),
            if (!job.isTerminal)
              RetroButton(
                label: 'CANCEL',
                onPressed: c.cancel,
                color: accentPrimary,
                icon: Icons.stop_circle_outlined,
              )
            else
              RetroButton(
                label: 'DISMISS',
                onPressed: widget.onDismiss ?? () {},
                color: accentSlate,
                icon: Icons.close,
              ),
          ],
        ),
        const SizedBox(height: sp8),

        // Progress bar (semantic).
        Semantics(
          label: 'Indexing ${widget.repoName}: '
              '${job.currentPhase.isEmpty ? job.state.name : job.currentPhase} '
              '— $pctLabel',
          value: pctLabel,
          child: ClipRRect(
            borderRadius: borderRadiusNone,
            child: LinearProgressIndicator(
              value: pct,
              minHeight: 6,
              backgroundColor: pageBg,
              valueColor: AlwaysStoppedAnimation<Color>(phaseColor),
            ),
          ),
        ),
        const SizedBox(height: sp8),

        // Subtitle: phase · current_file
        Text(
          subtitleParts.join(' · '),
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 12,
            color: textMuted,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        const SizedBox(height: 4),

        // Counters line + ETA + percent.
        Wrap(
          spacing: sp16,
          runSpacing: 4,
          children: [
            Text(
              '${job.counters.filesDone}/${job.counters.filesTotal} files · '
              '${job.counters.chunksDone}/${job.counters.chunksTotal} chunks',
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 12,
                color: textPrimary,
              ),
            ),
            Text(
              pctLabel,
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 12,
                color: textMuted,
              ),
            ),
            if (job.etaSeconds != null && !job.isTerminal)
              Text(
                'ETA ${_humanDuration(job.etaSeconds!)}',
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: 12,
                  color: textMuted,
                ),
              ),
            if (c.isPolling)
              const Text(
                '(polling fallback)',
                style: TextStyle(
                  fontFamily: fontBody,
                  fontSize: 12,
                  color: accentAmber,
                ),
              ),
          ],
        ),

        if (job.state == JobState.failed && job.error != null) ...[
          const SizedBox(height: sp8),
          _ErrorBanner(
            error: job.error!,
            expanded: _tracebackOpen,
            onToggle: () => setState(() => _tracebackOpen = !_tracebackOpen),
          ),
        ],

        if (job.state == JobState.done) ...[
          const SizedBox(height: sp8),
          Row(
            children: [
              const Icon(Icons.check_circle, size: 14, color: accentTeal),
              const SizedBox(width: sp4),
              Text(
                'Indexed ${job.counters.filesDone} files · '
                '${job.counters.chunksDone} chunks',
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: 12,
                  color: accentTeal,
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }

  // ── Helpers ────────────────────────────────────────────────────────────

  static Color _phaseColor(JobState s) {
    switch (s) {
      case JobState.done:
        return accentTeal;
      case JobState.failed:
        return accentPrimary;
      case JobState.cancelled:
        return accentSlate;
      case JobState.queued:
        return accentLavender;
      default:
        return accentAmber;
    }
  }

  /// VS Code-style mid-path ellipsis: keep head + tail, drop the middle.
  static String _midEllipsis(String s, int max) {
    if (s.length <= max) return s;
    final keep = max - 1; // 1 char for the ellipsis
    final head = (keep / 2).floor();
    final tail = keep - head;
    return '${s.substring(0, head)}…${s.substring(s.length - tail)}';
  }

  static String _humanDuration(double seconds) {
    if (seconds.isNaN || seconds.isInfinite || seconds < 0) return '—';
    if (seconds < 1) return '<1s';
    if (seconds < 60) return '${seconds.round()}s';
    final m = (seconds / 60).floor();
    final s = (seconds - m * 60).round();
    if (m < 60) return s == 0 ? '${m}m' : '${m}m ${s}s';
    final h = (m / 60).floor();
    final mm = m - h * 60;
    return mm == 0 ? '${h}h' : '${h}h ${mm}m';
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({
    required this.error,
    required this.expanded,
    required this.onToggle,
  });

  final IndexJobError error;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(sp8),
      decoration: BoxDecoration(
        color: accentPrimary.withAlpha(28),
        border: Border.all(color: accentPrimary, width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.error_outline, size: 14, color: accentPrimary),
              const SizedBox(width: sp4),
              Expanded(
                child: Text(
                  error.message,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: accentPrimary,
                  ),
                ),
              ),
              if ((error.traceback ?? '').isNotEmpty)
                TextButton(
                  onPressed: onToggle,
                  child: Text(expanded ? 'HIDE TRACE' : 'SHOW TRACE'),
                ),
            ],
          ),
          if (expanded && (error.traceback ?? '').isNotEmpty) ...[
            const SizedBox(height: sp4),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(sp8),
              color: pageBg,
              child: SelectableText(
                error.traceback!,
                style: const TextStyle(
                  fontFamily: fontFallback,
                  fontSize: 11,
                  color: textPrimary,
                  height: 1.3,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
