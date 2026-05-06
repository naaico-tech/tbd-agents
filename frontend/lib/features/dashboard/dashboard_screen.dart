import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../../core/config/app_links.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/retro_card.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, this.snapshotFuture});

  final Future<DashboardSnapshot>? snapshotFuture;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  http.Client? _ownedClient;
  late Future<DashboardSnapshot> _snapshotFuture;
  Timer? _autoRefreshTimer;

  http.Client get _client => _ownedClient ??= http.Client();

  @override
  void initState() {
    super.initState();
    _snapshotFuture = widget.snapshotFuture ?? fetchDashboardSnapshot(_client);
    if (widget.snapshotFuture == null) {
      _autoRefreshTimer = Timer.periodic(
        const Duration(seconds: 30),
        (_) => _reload(),
      );
    }
  }

  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    _ownedClient?.close();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _snapshotFuture = fetchDashboardSnapshot(_client);
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<DashboardSnapshot>(
      future: _snapshotFuture,
      builder: (context, snapshot) {
        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _DashboardHeader(
                loading: snapshot.connectionState == ConnectionState.waiting,
                onReload: _reload,
              ),
              const SizedBox(height: sp24),
              if (snapshot.connectionState == ConnectionState.waiting)
                const _LoadingDashboard()
              else if (snapshot.hasError)
                _DashboardError(error: snapshot.error, onRetry: _reload)
              else if (snapshot.hasData)
                _DashboardContent(snapshot: snapshot.requireData),
            ],
          ),
        );
      },
    );
  }
}

class DashboardSnapshot {
  const DashboardSnapshot({
    required this.agentsCount,
    required this.mcpServersCount,
    required this.skillsCount,
    required this.tokensCount,
    required this.providersCount,
    required this.knowledgeSourcesCount,
    required this.workflowsCount,
    required this.scheduledAgentsCount,
    required this.taskExecutionsCount,
    required this.recentWorkflows,
    required this.recentTasks,
  });

  final int agentsCount;
  final int mcpServersCount;
  final int skillsCount;
  final int tokensCount;
  final int providersCount;
  final int knowledgeSourcesCount;
  final int workflowsCount;
  final int scheduledAgentsCount;
  final int taskExecutionsCount;
  final List<WorkflowSummary> recentWorkflows;
  final List<TaskExecutionSummary> recentTasks;
}

class TaskExecutionSummary {
  const TaskExecutionSummary({
    required this.id,
    required this.workflowTitle,
    required this.status,
    required this.model,
    required this.createdAt,
  });

  final String id;
  final String workflowTitle;
  final String status;
  final String model;
  final DateTime? createdAt;
}

class WorkflowSummary {
  const WorkflowSummary({
    required this.id,
    required this.title,
    required this.agentName,
    required this.taskCount,
    required this.lastTaskStatus,
    required this.model,
    required this.createdAt,
  });

  final String id;
  final String title;
  final String agentName;
  final int taskCount;
  final String? lastTaskStatus;
  final String model;
  final DateTime? createdAt;
}

Future<DashboardSnapshot> fetchDashboardSnapshot(http.Client client) async {
  final coreResponses = await Future.wait([
    _fetchList(client, '/agents'),
    _fetchList(client, '/mcps'),
    _fetchList(client, '/skills'),
    _fetchList(client, '/tokens'),
    _fetchList(client, '/providers'),
    _fetchList(client, '/workflows'),
    _fetchList(client, '/tasks'),
  ]);

  final knowledgeSources = await _fetchListOrEmpty(
    client,
    '/knowledge-sources',
  );
  final scheduledAgents = await _fetchListOrEmpty(client, '/scheduled-agents');

  final agents = coreResponses[0];
  final mcps = coreResponses[1];
  final skills = coreResponses[2];
  final tokens = coreResponses[3];
  final providers = coreResponses[4];
  final workflows = coreResponses[5];
  final tasks = coreResponses[6];

  final agentNames = <String, String>{
    for (final item in agents)
      if (item is Map<String, dynamic> &&
          item['id'] is String &&
          item['name'] is String)
        item['id'] as String: item['name'] as String,
  };

  final workflowTitles = <String, String>{
    for (final item in workflows)
      if (item is Map<String, dynamic> && item['id'] is String)
        item['id'] as String:
            (item['title']?.toString().trim().isNotEmpty ?? false)
                ? item['title'].toString().trim()
                : item['id'].toString().substring(0, 8),
  };

  final recentWorkflows =
      workflows
          .whereType<Map<String, dynamic>>()
          .map((workflow) => _toWorkflowSummary(workflow, agentNames))
          .toList()
        ..sort((a, b) {
          final left = a.createdAt?.millisecondsSinceEpoch ?? 0;
          final right = b.createdAt?.millisecondsSinceEpoch ?? 0;
          return right.compareTo(left);
        });

  final recentTasks =
      tasks
          .whereType<Map<String, dynamic>>()
          .map((t) => _toTaskSummary(t, workflowTitles))
          .toList()
        ..sort((a, b) {
          final left = a.createdAt?.millisecondsSinceEpoch ?? 0;
          final right = b.createdAt?.millisecondsSinceEpoch ?? 0;
          return right.compareTo(left);
        });

  return DashboardSnapshot(
    agentsCount: agents.length,
    mcpServersCount: mcps.length,
    skillsCount: skills.length,
    tokensCount: tokens.length,
    providersCount: providers.length,
    knowledgeSourcesCount: knowledgeSources.length,
    workflowsCount: workflows.length,
    scheduledAgentsCount: scheduledAgents.length,
    taskExecutionsCount: tasks.length,
    recentWorkflows: recentWorkflows.take(5).toList(),
    recentTasks: recentTasks.take(10).toList(),
  );
}

Future<List<dynamic>> _fetchList(http.Client client, String path) async {
  final response = await client.get(AppLinks.apiUri(path));
  if (response.statusCode == 204 || response.body.trim().isEmpty) {
    return const [];
  }
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load $path (${response.statusCode})');
  }

  final decoded = jsonDecode(response.body);
  if (decoded is List<dynamic>) {
    return decoded;
  }
  throw Exception('Unexpected response for $path');
}

Future<List<dynamic>> _fetchListOrEmpty(http.Client client, String path) async {
  try {
    return await _fetchList(client, path);
  } catch (_) {
    return const [];
  }
}

WorkflowSummary _toWorkflowSummary(
  Map<String, dynamic> workflow,
  Map<String, String> agentNames,
) {
  final id = workflow['id']?.toString() ?? 'unknown';
  final title = (workflow['title']?.toString().trim().isNotEmpty ?? false)
      ? workflow['title'].toString().trim()
      : id;
  final agentId = workflow['agent_id']?.toString();
  return WorkflowSummary(
    id: id,
    title: title,
    agentName: agentId == null ? '—' : (agentNames[agentId] ?? agentId),
    taskCount: _toInt(workflow['task_count']),
    lastTaskStatus: workflow['last_task_status']?.toString(),
    model: workflow['model']?.toString() ?? '—',
    createdAt: DateTime.tryParse(workflow['created_at']?.toString() ?? ''),
  );
}

int _toInt(Object? value) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

TaskExecutionSummary _toTaskSummary(
  Map<String, dynamic> task,
  Map<String, String> workflowTitles,
) {
  final id = task['id']?.toString() ?? 'unknown';
  final workflowId = task['workflow_id']?.toString();
  return TaskExecutionSummary(
    id: id,
    workflowTitle: workflowId == null
        ? '—'
        : (workflowTitles[workflowId] ?? workflowId.substring(0, 8)),
    status: task['status']?.toString() ?? 'unknown',
    model: task['model']?.toString() ?? '—',
    createdAt: DateTime.tryParse(task['created_at']?.toString() ?? ''),
  );
}

class _DashboardHeader extends StatelessWidget {
  const _DashboardHeader({required this.loading, required this.onReload});

  final bool loading;
  final VoidCallback onReload;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'DASHBOARD',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 4),
              const Text(
                'Live system overview',
                style: TextStyle(
                  fontFamily: fontBody,
                  fontSize: 16,
                  color: textMuted,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
        ),
        RetroButton(
          label: loading ? 'LOADING' : 'REFRESH',
          icon: Icons.refresh,
          onPressed: loading ? null : onReload,
          color: accentAmber,
          textColor: textPrimary,
        ),
      ],
    );
  }
}

class _LoadingDashboard extends StatelessWidget {
  const _LoadingDashboard();

  @override
  Widget build(BuildContext context) {
    return const SectionFrame(
      title: 'Loading Dashboard',
      accentColor: accentTeal,
      minHeight: 220,
      child: Center(
        child: Text(
          'Loading live dashboard data…',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textMuted,
          ),
        ),
      ),
    );
  }
}

class _DashboardError extends StatelessWidget {
  const _DashboardError({required this.error, required this.onRetry});

  final Object? error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return SectionFrame(
      title: 'Dashboard Error',
      accentColor: accentPrimary,
      minHeight: 220,
      child: Padding(
        padding: const EdgeInsets.all(sp16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'The dashboard could not load live data.',
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: 16,
                color: textPrimary,
              ),
            ),
            const SizedBox(height: sp8),
            Text(
              error.toString(),
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 14,
                color: textMuted,
              ),
            ),
            const SizedBox(height: sp16),
            RetroButton(
              label: 'TRY AGAIN',
              icon: Icons.refresh,
              onPressed: onRetry,
              color: accentPrimary,
            ),
          ],
        ),
      ),
    );
  }
}

class _DashboardContent extends StatelessWidget {
  const _DashboardContent({required this.snapshot});

  final DashboardSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    final stats = [
      _DashboardStat(
        label: 'Agents',
        value: snapshot.agentsCount,
        icon: Icons.smart_toy_outlined,
        accent: accentTeal,
      ),
      _DashboardStat(
        label: 'MCP Servers',
        value: snapshot.mcpServersCount,
        icon: Icons.power_outlined,
        accent: accentAmber,
      ),
      _DashboardStat(
        label: 'Skills',
        value: snapshot.skillsCount,
        icon: Icons.bolt_outlined,
        accent: accentLavender,
      ),
      _DashboardStat(
        label: 'Tokens',
        value: snapshot.tokensCount,
        icon: Icons.key_outlined,
        accent: accentPrimary,
      ),
      _DashboardStat(
        label: 'Providers',
        value: snapshot.providersCount,
        icon: Icons.business_outlined,
        accent: accentAmber,
      ),
      _DashboardStat(
        label: 'Knowledge Sources',
        value: snapshot.knowledgeSourcesCount,
        icon: Icons.library_books_outlined,
        accent: accentTeal,
      ),
      _DashboardStat(
        label: 'Workflows',
        value: snapshot.workflowsCount,
        icon: Icons.account_tree_outlined,
        accent: accentLavender,
      ),
      _DashboardStat(
        label: 'Scheduled Agents',
        value: snapshot.scheduledAgentsCount,
        icon: Icons.schedule_outlined,
        accent: accentTeal,
      ),
      _DashboardStat(
        label: 'Task Executions',
        value: snapshot.taskExecutionsCount,
        icon: Icons.list_alt_outlined,
        accent: accentLavender,
      ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _StatusGrid(stats: stats),
        const SizedBox(height: sp24),
        SectionFrame(
          title: 'Recent Workflows',
          accentColor: accentSlate,
          minHeight: 220,
          child: _RecentWorkflowsTable(workflows: snapshot.recentWorkflows),
        ),
        const SizedBox(height: sp24),
        SectionFrame(
          title: 'Recent Task Executions',
          accentColor: accentLavender,
          minHeight: 220,
          child: _RecentTasksTable(tasks: snapshot.recentTasks),
        ),
      ],
    );
  }
}

class _DashboardStat {
  const _DashboardStat({
    required this.label,
    required this.value,
    required this.icon,
    required this.accent,
  });

  final String label;
  final int value;
  final IconData icon;
  final Color accent;
}

class _StatusGrid extends StatelessWidget {
  const _StatusGrid({required this.stats});

  final List<_DashboardStat> stats;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth >= 1600
            ? 5
            : constraints.maxWidth >= 1200
            ? 4
            : constraints.maxWidth >= 900
            ? 3
            : constraints.maxWidth >= 600
            ? 2
            : 1;
        final itemWidth =
            (constraints.maxWidth - ((columns - 1) * sp16)) / columns;

        return Wrap(
          spacing: sp16,
          runSpacing: sp16,
          children: stats
              .map((stat) => _StatTile(stat: stat, width: itemWidth))
              .toList(),
        );
      },
    );
  }
}

class _StatTile extends StatelessWidget {
  const _StatTile({required this.stat, required this.width});

  final _DashboardStat stat;
  final double width;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      child: RetroCard(
        background: const Color(0xFF13131B),
        shadowOffsetX: 4,
        shadowOffsetY: 4,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(stat.icon, color: stat.accent, size: 18),
                const SizedBox(width: sp8),
                Expanded(
                  child: Text(
                    stat.label.toUpperCase(),
                    style: const TextStyle(
                      fontFamily: fontDisplay,
                      fontSize: 8,
                      color: Color(0xFF8F8AAF),
                      letterSpacing: 0.8,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: sp16),
            Text(
              '${stat.value}',
              style: TextStyle(
                fontFamily: fontDisplay,
                fontSize: 22,
                color: stat.accent,
                height: 1.2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RecentWorkflowsTable extends StatelessWidget {
  const _RecentWorkflowsTable({required this.workflows});

  final List<WorkflowSummary> workflows;

  @override
  Widget build(BuildContext context) {
    if (workflows.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(sp16),
        child: Text(
          'No workflows yet.',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textMuted,
          ),
        ),
      );
    }

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minWidth: 900),
        child: Table(
          defaultVerticalAlignment: TableCellVerticalAlignment.middle,
          columnWidths: const {
            0: FlexColumnWidth(1.8),
            1: FlexColumnWidth(1.8),
            2: FlexColumnWidth(0.9),
            3: FlexColumnWidth(1.2),
            4: FlexColumnWidth(1.4),
            5: FlexColumnWidth(1.2),
          },
          children: [
            _headerRow(),
            for (final workflow in workflows) _workflowRow(workflow),
          ],
        ),
      ),
    );
  }

  TableRow _headerRow() {
    const headerStyle = TextStyle(
      fontFamily: fontDisplay,
      fontSize: 8,
      color: textMuted,
      letterSpacing: 0.6,
    );

    return TableRow(
      children: [
        _cell('ID', style: headerStyle, isHeader: true),
        _cell('AGENT', style: headerStyle, isHeader: true),
        _cell('TASKS', style: headerStyle, isHeader: true),
        _cell('LAST TASK', style: headerStyle, isHeader: true),
        _cell('MODEL', style: headerStyle, isHeader: true),
        _cell('CREATED', style: headerStyle, isHeader: true),
      ],
    );
  }

  TableRow _workflowRow(WorkflowSummary workflow) {
    return TableRow(
      children: [
        _cell(
          workflow.title,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: accentLavender,
          ),
        ),
        _cell(
          workflow.agentName,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textPrimary,
          ),
        ),
        _cell(
          '${workflow.taskCount}',
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textPrimary,
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: sp12, vertical: sp16),
          child: Align(
            alignment: Alignment.centerLeft,
            child: workflow.lastTaskStatus == null
                ? const Text(
                    '—',
                    style: TextStyle(
                      fontFamily: fontBody,
                      fontSize: 16,
                      color: textMuted,
                    ),
                  )
                : RetroChip(
                    label: workflow.lastTaskStatus!,
                    color: _statusColor(workflow.lastTaskStatus),
                    textColor: cardBg,
                  ),
          ),
        ),
        _cell(
          workflow.model,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textPrimary,
          ),
        ),
        _cell(
          _formatDate(workflow.createdAt),
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textPrimary,
          ),
        ),
      ],
    );
  }

  Widget _cell(String text, {required TextStyle style, bool isHeader = false}) {
    return Container(
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(
            color: isHeader ? borderColor : borderColor.withAlpha(90),
            width: 1,
          ),
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: sp12, vertical: sp16),
      child: Text(text, style: style),
    );
  }

  Color _statusColor(String? status) {
    switch (status?.toLowerCase()) {
      case 'completed':
        return accentTeal;
      case 'running':
      case 'active':
        return accentAmber;
      case 'failed':
        return accentPrimary;
      case 'halted':
      case 'max_turns_reached':
        return accentLavender;
      default:
        return accentSlate;
    }
  }

  String _formatDate(DateTime? value) {
    if (value == null) {
      return '—';
    }

    final day = value.day.toString().padLeft(2, '0');
    final month = _monthLabel(value.month);
    final hour = value.hour.toString().padLeft(2, '0');
    final minute = value.minute.toString().padLeft(2, '0');
    return '$day $month, $hour:$minute';
  }

  String _monthLabel(int month) {
    const months = [
      'Jan',
      'Feb',
      'Mar',
      'Apr',
      'May',
      'Jun',
      'Jul',
      'Aug',
      'Sep',
      'Oct',
      'Nov',
      'Dec',
    ];
    return months[month - 1];
  }
}

// ── Recent Task Executions Table ─────────────────────────────────────────────

class _RecentTasksTable extends StatelessWidget {
  const _RecentTasksTable({required this.tasks});

  final List<TaskExecutionSummary> tasks;

  @override
  Widget build(BuildContext context) {
    if (tasks.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(sp16),
        child: Text(
          'No task executions yet. Run a task to see results here.',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textMuted,
          ),
        ),
      );
    }

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minWidth: 800),
        child: Table(
          defaultVerticalAlignment: TableCellVerticalAlignment.middle,
          columnWidths: const {
            0: FlexColumnWidth(1.6),
            1: FlexColumnWidth(2.0),
            2: FlexColumnWidth(1.2),
            3: FlexColumnWidth(1.4),
            4: FlexColumnWidth(1.2),
          },
          children: [
            _headerRow(),
            for (final task in tasks) _taskRow(task),
          ],
        ),
      ),
    );
  }

  TableRow _headerRow() {
    const headerStyle = TextStyle(
      fontFamily: fontDisplay,
      fontSize: 8,
      color: textMuted,
      letterSpacing: 0.6,
    );
    return TableRow(
      children: [
        _cell('TASK ID', style: headerStyle, isHeader: true),
        _cell('WORKFLOW', style: headerStyle, isHeader: true),
        _cell('STATUS', style: headerStyle, isHeader: true),
        _cell('MODEL', style: headerStyle, isHeader: true),
        _cell('CREATED', style: headerStyle, isHeader: true),
      ],
    );
  }

  TableRow _taskRow(TaskExecutionSummary task) {
    final shortId = task.id.length > 8 ? task.id.substring(0, 8) : task.id;
    return TableRow(
      children: [
        _cell(
          shortId,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 14,
            color: accentTeal,
          ),
        ),
        _cell(
          task.workflowTitle,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textPrimary,
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: sp12, vertical: sp16),
          child: Align(
            alignment: Alignment.centerLeft,
            child: RetroChip(
              label: task.status,
              color: _statusColor(task.status),
              textColor: cardBg,
            ),
          ),
        ),
        _cell(
          task.model,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textPrimary,
          ),
        ),
        _cell(
          _formatDate(task.createdAt),
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textPrimary,
          ),
        ),
      ],
    );
  }

  Widget _cell(String text, {required TextStyle style, bool isHeader = false}) {
    return Container(
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(
            color: isHeader ? borderColor : borderColor.withAlpha(90),
            width: 1,
          ),
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: sp12, vertical: sp16),
      child: Text(text, style: style),
    );
  }

  Color _statusColor(String? status) {
    switch (status?.toLowerCase()) {
      case 'completed':
        return accentTeal;
      case 'running':
        return accentAmber;
      case 'failed':
        return accentPrimary;
      case 'pending':
        return accentSlate;
      case 'halted':
      case 'max_turns_reached':
        return accentLavender;
      default:
        return accentSlate;
    }
  }

  String _formatDate(DateTime? value) {
    if (value == null) return '—';
    final day = value.day.toString().padLeft(2, '0');
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    final month = months[value.month - 1];
    final hour = value.hour.toString().padLeft(2, '0');
    final minute = value.minute.toString().padLeft(2, '0');
    return '$day $month, $hour:$minute';
  }
}
