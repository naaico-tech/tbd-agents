import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../../core/config/app_links.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/retro_card.dart';

// ---------------------------------------------------------------------------
// _WorkflowOption — lightweight model for workflow dropdown
// ---------------------------------------------------------------------------

class _WorkflowOption {
  const _WorkflowOption({required this.id, required this.title});

  final String id;
  final String title;

  factory _WorkflowOption.fromJson(Map<String, dynamic> j) => _WorkflowOption(
    id: j['id']?.toString() ?? '',
    title: j['title']?.toString() ?? j['id']?.toString() ?? '',
  );
}

// ---------------------------------------------------------------------------
// RunTaskScreen — submit a prompt to a workflow and see live results.
// ---------------------------------------------------------------------------
class RunTaskScreen extends StatefulWidget {
  const RunTaskScreen({super.key});

  @override
  State<RunTaskScreen> createState() => _RunTaskScreenState();
}

class _RunTaskScreenState extends State<RunTaskScreen> {
  http.Client? _ownedClient;
  http.Client get _client => _ownedClient ??= http.Client();

  // ── form ──────────────────────────────────────────────────────────────
  final _promptController = TextEditingController();
  List<_WorkflowOption> _workflows = [];
  bool _loadingWorkflows = false;
  String? _workflowsError;
  _WorkflowOption? _selectedWorkflow;
  String? _reasoningEffort; // null = use workflow default

  // ── task state ────────────────────────────────────────────────────────
  bool _isRunning = false;
  String? _taskId;
  String? _workflowId;
  String? _output;
  String? _outputStatus;
  int? _currentTurn;
  int? _maxTurns;
  String? _error;
  Timer? _pollTimer;
  // Live execution logs (event_type + message) shown during run
  final List<Map<String, String>> _liveLogs = [];

  @override
  void initState() {
    super.initState();
    _loadWorkflows();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _promptController.dispose();
    _ownedClient?.close();
    super.dispose();
  }

  // ── workflow loading ───────────────────────────────────────────────────

  Future<void> _loadWorkflows() async {
    setState(() {
      _loadingWorkflows = true;
      _workflowsError = null;
    });
    try {
      final resp = await _client.get(AppLinks.apiUri('/workflows'));
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        throw Exception('Failed to load workflows (${resp.statusCode})');
      }
      final decoded = jsonDecode(resp.body);
      if (decoded is! List) throw Exception('Unexpected format');
      final list = decoded
          .whereType<Map<String, dynamic>>()
          .map(_WorkflowOption.fromJson)
          .where((w) => w.id.isNotEmpty)
          .toList();
      if (!mounted) return;
      setState(() {
        _workflows = list;
        _loadingWorkflows = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _workflowsError = e.toString();
        _loadingWorkflows = false;
      });
    }
  }

  // ── task submission ────────────────────────────────────────────────────

  Future<void> _submitTask() async {
    final prompt = _promptController.text.trim();
    if (prompt.isEmpty || _selectedWorkflow == null) return;

    _pollTimer?.cancel();
    _pollTimer = null;

    setState(() {
      _isRunning = true;
      _error = null;
      _output = null;
      _outputStatus = null;
      _taskId = null;
      _workflowId = null;
      _currentTurn = null;
      _maxTurns = null;
      _liveLogs.clear();
    });

    try {
      final body = <String, dynamic>{'prompt': prompt};
      if (_reasoningEffort != null) {
        body['reasoning_effort'] = _reasoningEffort;
      }
      final resp = await _client.post(
        AppLinks.apiUri('/workflows/${_selectedWorkflow!.id}/prompt'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        final decoded = jsonDecode(resp.body);
        throw Exception(
          decoded['detail'] ?? 'Submit failed (${resp.statusCode})',
        );
      }
      final decoded = jsonDecode(resp.body) as Map<String, dynamic>;
      final workflowId =
          decoded['workflow_id']?.toString() ?? _selectedWorkflow!.id;
      if (!mounted) return;
      setState(() {
        _outputStatus = decoded['status']?.toString() ?? 'running';
        _currentTurn = (decoded['current_turn'] as num?)?.toInt();
        _maxTurns = (decoded['max_turns'] as num?)?.toInt();
        _output = decoded['response']?.toString();
        _taskId = decoded['task_id']?.toString();
        _workflowId = decoded['workflow_id']?.toString() ?? _selectedWorkflow!.id;
      });

      // Fall back to discovery only when the prompt response omitted task_id
      if (_taskId == null) {
        await _discoverTaskId(workflowId);
      }
      _startPolling(workflowId);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isRunning = false;
        _error = e.toString();
      });
    }
  }

  // ── polling helpers ────────────────────────────────────────────────────

  Future<void> _discoverTaskId(String workflowId) async {
    try {
      final resp = await _client.get(
        AppLinks.apiUri('/tasks/workflow/$workflowId'),
      );
      if (resp.statusCode >= 200 && resp.statusCode < 300) {
        final decoded = jsonDecode(resp.body);
        if (decoded is List && decoded.isNotEmpty) {
          final latest = decoded.first as Map<String, dynamic>;
          if (mounted) {
            setState(() => _taskId = latest['id']?.toString());
          }
        }
      }
    } catch (_) {}
  }

  void _startPolling(String workflowId) {
    _pollTimer = Timer.periodic(
      const Duration(seconds: 3),
      (_) async {
        if (!mounted) {
          _pollTimer?.cancel();
          return;
        }
        // If we still don't have a task ID, try discovering again
        if (_taskId == null) {
          await _discoverTaskId(workflowId);
          return;
        }
        await _pollTask();
      },
    );
  }

  Future<void> _pollTask() async {
    if (_taskId == null) return;
    try {
      final resp = await _client.get(AppLinks.apiUri('/tasks/$_taskId'));
      if (!mounted) return;
      if (resp.statusCode < 200 || resp.statusCode >= 300) return;
      final decoded = jsonDecode(resp.body) as Map<String, dynamic>;
      final status = decoded['status']?.toString() ?? '';
      setState(() {
        _outputStatus = status;
        final newResponse = decoded['response']?.toString();
        if (newResponse != null && newResponse.isNotEmpty) {
          _output = newResponse;
        }
        // Update live logs
        final rawLogs = decoded['logs'];
        if (rawLogs is List) {
          _liveLogs
            ..clear()
            ..addAll(
              rawLogs
                  .whereType<Map<String, dynamic>>()
                  .map(
                    (l) => {
                      'type': l['event']?.toString() ?? 'log',
                      'msg': l['detail']?.toString() ?? '',
                    },
                  )
                  .toList(),
            );
        }
      });
      // Stop polling when task is terminal
      if (status == 'completed' || status == 'failed' ||
          status == 'halted' || status == 'max_turns_reached') {
        _pollTimer?.cancel();
        _pollTimer = null;
        if (mounted) setState(() => _isRunning = false);
      }
    } catch (_) {}
  }

  Future<void> _stopTask() async {
    if (_workflowId == null) return;
    try {
      final resp = await _client.post(
        AppLinks.apiUri('/workflows/$_workflowId/halt'),
        headers: {'Content-Type': 'application/json'},
      );
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        String detail = 'Stop failed (${resp.statusCode})';
        try {
          final body = jsonDecode(resp.body) as Map<String, dynamic>?;
          detail = body?['detail'] as String? ?? detail;
        } catch (_) {}
        throw Exception(detail);
      }
      if (mounted) setState(() => _outputStatus = 'halted');
    } catch (e) {
      if (mounted) setState(() => _error = 'Stop failed: $e');
    }
  }

  // ── helpers ────────────────────────────────────────────────────────────

  Color get _outputAccentColor {
    switch (_outputStatus?.toLowerCase()) {
      case 'completed':
        return const Color(0xFF4CAF50);
      case 'running':
        return accentTeal;
      case 'failed':
        return accentPrimary;
      case 'pending':
        return accentAmber;
      default:
        return accentTeal;
    }
  }

  Color get _statusChipColor {
    switch (_outputStatus?.toLowerCase()) {
      case 'completed':
        return const Color(0xFF4CAF50);
      case 'running':
        return accentTeal;
      case 'failed':
        return accentPrimary;
      default:
        return accentAmber;
    }
  }

  Color get _statusChipTextColor =>
      _outputStatus?.toLowerCase() == 'pending' ? textPrimary : cardBg;

  // ── build ─────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Page header ──────────────────────────────────────────────
          Text('RUN TASK', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 4),
          const Text(
            'Execute a task with a selected workflow.',
            style: TextStyle(
              fontFamily: fontBody,
              fontSize: 16,
              color: textMuted,
            ),
          ),
          const SizedBox(height: sp24),

          // ── Error banner ─────────────────────────────────────────────
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: sp16),
              child: RetroCard(
                child: Padding(
                  padding: const EdgeInsets.all(sp12),
                  child: Row(
                    children: [
                      const Icon(
                        Icons.error_outline,
                        color: accentPrimary,
                        size: 16,
                      ),
                      const SizedBox(width: sp8),
                      Expanded(
                        child: Text(
                          _error!,
                          style: const TextStyle(
                            fontFamily: fontBody,
                            fontSize: fontSizeSmall,
                            color: accentPrimary,
                          ),
                        ),
                      ),
                      GestureDetector(
                        onTap: () => setState(() => _error = null),
                        child: const Icon(
                          Icons.close,
                          size: 14,
                          color: textMuted,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),

          // ── Form card ────────────────────────────────────────────────
          RetroCard(
            header: const Text(
              'TASK PROMPT',
              style: TextStyle(
                fontFamily: fontDisplay,
                fontSize: 9,
                color: textPrimary,
                letterSpacing: 1,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Workflow selector
                const Text(
                  'WORKFLOW',
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeSmall,
                    color: textMuted,
                    letterSpacing: 0.8,
                  ),
                ),
                const SizedBox(height: sp4),
                Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: borderColor, width: 1),
                    color: pageBg,
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: sp12),
                  child: _buildWorkflowDropdown(),
                ),
                const SizedBox(height: sp12),

                // Prompt text field
                const Text(
                  'PROMPT',
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeSmall,
                    color: textMuted,
                    letterSpacing: 0.8,
                  ),
                ),
                const SizedBox(height: sp4),
                Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: borderColor, width: 1),
                    color: pageBg,
                  ),
                  child: TextField(
                    controller: _promptController,
                    minLines: 4,
                    maxLines: 8,
                    enabled: !_isRunning,
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: fontSizeSmall,
                      color: textPrimary,
                    ),
                    decoration: const InputDecoration(
                      contentPadding: EdgeInsets.all(sp12),
                      border: InputBorder.none,
                      hintText: 'Describe the task…',
                      hintStyle: TextStyle(
                        fontFamily: fontBody,
                        fontSize: fontSizeSmall,
                        color: textMuted,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: sp12),

                // Reasoning effort override
                const Text(
                  'REASONING EFFORT  (optional override)',
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeSmall,
                    color: textMuted,
                    letterSpacing: 0.8,
                  ),
                ),
                const SizedBox(height: sp4),
                Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: borderColor, width: 1),
                    color: pageBg,
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: sp12),
                  child: DropdownButton<String?>(
                    value: _reasoningEffort,
                    isExpanded: true,
                    underline: const SizedBox(),
                    dropdownColor: cardBg,
                    hint: const Text(
                      'None (use workflow default)',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: fontSizeSmall,
                        color: textMuted,
                      ),
                    ),
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: fontSizeSmall,
                      color: textPrimary,
                    ),
                    items: const [
                      DropdownMenuItem<String?>(
                        value: null,
                        child: Text(
                          'None (use workflow default)',
                          style: TextStyle(
                            fontFamily: fontBody,
                            fontSize: fontSizeSmall,
                            color: textMuted,
                          ),
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'low',
                        child: Text(
                          'low',
                          style: TextStyle(
                            fontFamily: fontBody,
                            fontSize: fontSizeSmall,
                            color: textPrimary,
                          ),
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'medium',
                        child: Text(
                          'medium',
                          style: TextStyle(
                            fontFamily: fontBody,
                            fontSize: fontSizeSmall,
                            color: textPrimary,
                          ),
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'high',
                        child: Text(
                          'high',
                          style: TextStyle(
                            fontFamily: fontBody,
                            fontSize: fontSizeSmall,
                            color: textPrimary,
                          ),
                        ),
                      ),
                    ],
                    onChanged:
                        _isRunning ? null : (v) => setState(() => _reasoningEffort = v),
                  ),
                ),
                const SizedBox(height: sp16),

                // Submit button
                Align(
                  alignment: Alignment.centerRight,
                  child: RetroButton(
                    label: _isRunning ? 'RUNNING…' : 'RUN TASK',
                    icon: _isRunning ? null : Icons.play_circle_outline,
                    onPressed: _isRunning ? null : _submitTask,
                    color: accentTeal,
                  ),
                ),
              ],
            ),
          ),

          // ── Output section ───────────────────────────────────────────
          if (_output != null || _outputStatus != null || _isRunning) ...[
            const SizedBox(height: sp24),
            SectionFrame(
              title: 'Output',
              accentColor: _outputAccentColor,
              child: Padding(
                padding: const EdgeInsets.all(sp12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Status row
                    Row(
                      children: [
                        if (_outputStatus != null)
                          RetroChip(
                            label: _outputStatus!,
                            color: _statusChipColor,
                            textColor: _statusChipTextColor,
                          ),
                        if (_currentTurn != null && _maxTurns != null) ...[
                          const SizedBox(width: sp8),
                          Text(
                            'turn $_currentTurn / $_maxTurns',
                            style: const TextStyle(
                              fontFamily: fontBody,
                              fontSize: fontSizeSmall,
                              color: textMuted,
                            ),
                          ),
                        ],
                        if (_isRunning) ...[
                          const Spacer(),
                          const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: accentTeal,
                            ),
                          ),
                          if (_workflowId != null) ...[
                            const SizedBox(width: sp8),
                            _StopButton(onStop: _stopTask),
                          ],
                        ],
                        if (_taskId != null && !_isRunning) ...[
                          const Spacer(),
                          Text(
                            'id: ${_taskId!.length > 12 ? '${_taskId!.substring(0, 12)}…' : _taskId!}',
                            style: const TextStyle(
                              fontFamily: fontBody,
                              fontSize: fontSizeSmall,
                              color: textMuted,
                            ),
                          ),
                        ],
                      ],
                    ),
                    // Response text
                    if (_output != null && _output!.isNotEmpty) ...[
                      const SizedBox(height: sp12),
                      SelectableText(
                        _output!,
                        style: const TextStyle(
                          fontFamily: fontBody,
                          fontSize: fontSizeSmall,
                          color: textPrimary,
                        ),
                      ),
                    ] else if (_isRunning) ...[
                      const SizedBox(height: sp12),
                      const Text(
                        '[ waiting for response… ]',
                        style: TextStyle(
                          fontFamily: fontBody,
                          fontSize: fontSizeSmall,
                          color: textMuted,
                        ),
                      ),
                    ],
                    // Live execution logs
                    if (_liveLogs.isNotEmpty) ...[
                      const SizedBox(height: sp16),
                      const Text(
                        'EXECUTION LOG',
                        style: TextStyle(
                          fontFamily: fontBody,
                          fontSize: fontSizeSmall,
                          color: textMuted,
                          letterSpacing: 0.8,
                        ),
                      ),
                      const SizedBox(height: sp8),
                      Container(
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: pageBg,
                          border: Border.all(color: borderColor),
                        ),
                        padding: const EdgeInsets.all(sp8),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            for (final log in _liveLogs)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 2),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      '[${log['type'] ?? 'log'}]',
                                      style: const TextStyle(
                                        fontFamily: fontBody,
                                        fontSize: 10,
                                        color: accentTeal,
                                        letterSpacing: 0.4,
                                      ),
                                    ),
                                    const SizedBox(width: sp4),
                                    Expanded(
                                      child: Text(
                                        log['msg'] ?? '',
                                        style: const TextStyle(
                                          fontFamily: fontBody,
                                          fontSize: 11,
                                          color: textPrimary,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildWorkflowDropdown() {
    if (_loadingWorkflows) {
      return const Padding(
        padding: EdgeInsets.all(sp8),
        child: SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(strokeWidth: 2, color: accentSlate),
        ),
      );
    }
    if (_workflowsError != null) {
      return Row(
        children: [
          Expanded(
            child: Text(
              'Error: $_workflowsError',
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeSmall,
                color: accentPrimary,
              ),
            ),
          ),
          TextButton(
            onPressed: _loadWorkflows,
            child: const Text(
              'Retry',
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeSmall,
                color: accentTeal,
              ),
            ),
          ),
        ],
      );
    }
    return DropdownButton<_WorkflowOption>(
      value: _selectedWorkflow,
      isExpanded: true,
      underline: const SizedBox(),
      dropdownColor: cardBg,
      hint: Text(
        _workflows.isEmpty ? 'No workflows available' : 'Select a workflow…',
        style: const TextStyle(
          fontFamily: fontBody,
          fontSize: fontSizeSmall,
          color: textMuted,
        ),
      ),
      style: const TextStyle(
        fontFamily: fontBody,
        fontSize: fontSizeSmall,
        color: textPrimary,
      ),
      items: _workflows
          .map(
            (w) => DropdownMenuItem<_WorkflowOption>(
              value: w,
              child: Text(
                w.title.isNotEmpty ? w.title : w.id,
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: fontSizeSmall,
                  color: textPrimary,
                ),
              ),
            ),
          )
          .toList(),
      onChanged:
          _isRunning ? null : (v) => setState(() => _selectedWorkflow = v),
    );
  }
}

// ---------------------------------------------------------------------------
// _StopButton — compact stop control for an in-progress task
// ---------------------------------------------------------------------------
class _StopButton extends StatefulWidget {
  const _StopButton({required this.onStop});
  final Future<void> Function() onStop;

  @override
  State<_StopButton> createState() => _StopButtonState();
}

class _StopButtonState extends State<_StopButton> {
  bool _stopping = false;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: _stopping
          ? null
          : () async {
              setState(() => _stopping = true);
              try {
                await widget.onStop();
              } finally {
                if (mounted) setState(() => _stopping = false);
              }
            },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: sp8, vertical: 4),
        decoration: BoxDecoration(
          border: Border.all(color: accentPrimary, width: 1),
          color: accentPrimary.withValues(alpha: 0.1),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.stop_circle_outlined, color: accentPrimary, size: 12),
            const SizedBox(width: 4),
            Text(
              _stopping ? 'STOPPING…' : 'STOP',
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 10,
                color: accentPrimary,
                letterSpacing: 0.8,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
