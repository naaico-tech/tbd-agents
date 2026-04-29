import 'dart:convert';

import 'package:flutter/material.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/export_import_dialog.dart';
import '../../core/widgets/retro_card.dart';
import 'package:http/http.dart' as http;
import '../../core/config/app_links.dart';

// ---------------------------------------------------------------------------
// TokensScreen — API key / credential management
// ---------------------------------------------------------------------------
class TokensScreen extends StatelessWidget {
  const TokensScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ScreenHeader(
            title: 'TOKENS',
            subtitle: 'API keys and credentials',
            actions: [
              RetroButton(
                label: 'ADD TOKEN',
                onPressed: () {},
                icon: Icons.add,
                color: accentAmber,
                textColor: textPrimary,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Stored Credentials',
            accentColor: accentAmber,
            minHeight: 300,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.key_outlined,
                message: 'No tokens stored.',
                hint: 'Tokens are encrypted at rest.',
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// ProvidersScreen — LLM / embedding provider configuration
// ---------------------------------------------------------------------------
class ProvidersScreen extends StatelessWidget {
  const ProvidersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ScreenHeader(
            title: 'PROVIDERS',
            subtitle: 'LLM and embedding provider settings',
            actions: [
              RetroButton(
                label: 'ADD PROVIDER',
                onPressed: () {},
                icon: Icons.add,
                color: accentSlate,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Configured Providers',
            accentColor: accentSlate,
            minHeight: 300,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.business_outlined,
                message: 'No providers configured.',
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Data models
// ---------------------------------------------------------------------------

class _OutputMcpConfig {
  _OutputMcpConfig({
    required this.mcpServerId,
    this.toolName,
    Map<String, dynamic>? metadata,
  }) : metadata = metadata ?? {};

  String mcpServerId;
  String? toolName;
  Map<String, dynamic> metadata;

  factory _OutputMcpConfig.fromJson(Map<String, dynamic> json) =>
      _OutputMcpConfig(
        mcpServerId: json['mcp_server_id']?.toString() ?? '',
        toolName: json['tool_name']?.toString(),
        metadata: (json['metadata'] as Map<String, dynamic>?) ?? {},
      );

  Map<String, dynamic> toJson() => {
    'mcp_server_id': mcpServerId,
    if (toolName != null && toolName!.isNotEmpty) 'tool_name': toolName,
    'metadata': metadata,
  };
}

class _McpServer {
  const _McpServer({required this.id, required this.name});
  final String id;
  final String name;

  factory _McpServer.fromJson(Map<String, dynamic> json) => _McpServer(
    id: json['id']?.toString() ?? '',
    name: json['name']?.toString() ?? '',
  );
}

class _Workflow {
  _Workflow({
    required this.id,
    required this.title,
    required this.agentId,
    required this.model,
    required this.status,
    required this.outputMcps,
  });

  final String id;
  final String title;
  final String agentId;
  final String model;
  final String status;
  List<_OutputMcpConfig> outputMcps;

  factory _Workflow.fromJson(Map<String, dynamic> json) => _Workflow(
    id: json['id']?.toString() ?? '',
    title: json['title']?.toString() ?? '(untitled)',
    agentId: json['agent_id']?.toString() ?? '',
    model: json['model']?.toString() ?? '',
    status: json['status']?.toString() ?? '',
    outputMcps: (json['output_mcps'] as List<dynamic>? ?? [])
        .whereType<Map<String, dynamic>>()
        .map(_OutputMcpConfig.fromJson)
        .toList(),
  );
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

Future<List<_Workflow>> _fetchWorkflows(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/workflows'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load workflows (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_Workflow.fromJson)
      .toList();
}

Future<List<_McpServer>> _fetchMcpServers(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/mcps'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load MCP servers (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_McpServer.fromJson)
      .toList();
}

Future<void> _saveOutputMcps(
  http.Client client,
  String workflowId,
  List<_OutputMcpConfig> outputMcps,
) async {
  final body = jsonEncode({
    'output_mcps': outputMcps.map((omc) => omc.toJson()).toList(),
  });
  final response = await client.put(
    AppLinks.apiUri('/workflows/$workflowId'),
    headers: {'Content-Type': 'application/json'},
    body: body,
  );
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to save output MCPs (${response.statusCode})');
  }
}

// ---------------------------------------------------------------------------
// WorkflowsScreen — workflow definitions list with Output MCP configuration
// ---------------------------------------------------------------------------
class WorkflowsScreen extends StatefulWidget {
  const WorkflowsScreen({super.key});

  @override
  State<WorkflowsScreen> createState() => _WorkflowsScreenState();
}

class _WorkflowsScreenState extends State<WorkflowsScreen> {
  http.Client? _ownedClient;
  late Future<List<_Workflow>> _workflowsFuture;

  http.Client get _client => _ownedClient ??= http.Client();

  @override
  void initState() {
    super.initState();
    _workflowsFuture = _fetchWorkflows(_client);
  }

  @override
  void dispose() {
    _ownedClient?.close();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _workflowsFuture = _fetchWorkflows(_client);
    });
  }

  Future<void> _openOutputMcpDialog(_Workflow workflow) async {
    List<_McpServer> servers;
    try {
      servers = await _fetchMcpServers(_client);
    } catch (_) {
      servers = [];
    }

    if (!mounted) return;
    final updated = await showDialog<List<_OutputMcpConfig>>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => _OutputMcpDialog(
        workflow: workflow,
        servers: servers,
        httpClient: _client,
      ),
    );

    if (updated != null) {
      setState(() {
        workflow.outputMcps = updated;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_Workflow>>(
      future: _workflowsFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final workflows = snapshot.data ?? [];

        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ScreenHeader(
                title: 'WORKFLOWS',
                subtitle: 'Multi-step agent workflows',
                actions: [
                  RetroButton(
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentLavender,
                  ),
                  RetroButton(
                    label: 'EXPORT',
                    onPressed: () => showExportDialog(
                      context,
                      apiPath: '/workflows/export',
                      resourceLabel: 'WORKFLOWS',
                    ),
                    icon: Icons.download_outlined,
                    color: accentLavender,
                  ),
                  RetroButton(
                    label: 'IMPORT',
                    onPressed: () => showImportDialog(
                      context,
                      apiPath: '/workflows/import',
                      resourceLabel: 'WORKFLOWS',
                    ),
                    icon: Icons.upload_outlined,
                    color: accentLavender,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _ErrorBanner(
                  message: 'Failed to load workflows: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Workflow Definitions',
                accentColor: accentLavender,
                minHeight: workflows.isEmpty ? 200 : 0,
                child: loading
                    ? const Padding(
                        padding: EdgeInsets.all(sp48),
                        child: Center(
                          child: SizedBox(
                            width: 24,
                            height: 24,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        ),
                      )
                    : workflows.isEmpty
                        ? const Padding(
                            padding: EdgeInsets.all(sp16),
                            child: _EmptyState(
                              icon: Icons.account_tree_outlined,
                              message: 'No workflows defined.',
                            ),
                          )
                        : Column(
                            children: workflows
                                .map((wf) => _WorkflowRow(
                                      workflow: wf,
                                      onConfigureOutputMcps: () =>
                                          _openOutputMcpDialog(wf),
                                    ))
                                .toList(),
                          ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------
// _WorkflowRow — one workflow in the list with an Output MCPs config button
// ---------------------------------------------------------------------------
class _WorkflowRow extends StatelessWidget {
  const _WorkflowRow({
    required this.workflow,
    required this.onConfigureOutputMcps,
  });

  final _Workflow workflow;
  final VoidCallback onConfigureOutputMcps;

  @override
  Widget build(BuildContext context) {
    final mcpCount = workflow.outputMcps.length;
    return Container(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: borderColor, width: 1)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: sp16, vertical: sp12),
      child: Row(
        children: [
          Icon(
            Icons.account_tree_outlined,
            size: 18,
            color: workflow.status == 'active' ? accentTeal : textMuted,
          ),
          const SizedBox(width: sp12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  workflow.title,
                  style: const TextStyle(
                    fontFamily: fontDisplay,
                    fontSize: 9,
                    color: textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${workflow.model}  ·  ${workflow.status}',
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 11,
                    color: textMuted,
                  ),
                ),
              ],
            ),
          ),
          // Output MCP badge
          GestureDetector(
            onTap: onConfigureOutputMcps,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: sp8, vertical: 4),
              decoration: BoxDecoration(
                border: Border.all(
                  color: mcpCount > 0 ? accentLavender : borderColor,
                  width: 1,
                ),
                color: mcpCount > 0
                    ? accentLavender.withAlpha(20)
                    : Colors.transparent,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.output,
                    size: 12,
                    color: mcpCount > 0 ? accentLavender : textMuted,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    mcpCount > 0
                        ? '$mcpCount OUTPUT MCP${mcpCount > 1 ? 'S' : ''}'
                        : 'OUTPUT MCPs',
                    style: TextStyle(
                      fontFamily: fontBody,
                      fontSize: 10,
                      color: mcpCount > 0 ? accentLavender : textMuted,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _OutputMcpDialog — configure output MCPs for a workflow
// ---------------------------------------------------------------------------
class _OutputMcpDialog extends StatefulWidget {
  const _OutputMcpDialog({
    required this.workflow,
    required this.servers,
    required this.httpClient,
  });

  final _Workflow workflow;
  final List<_McpServer> servers;
  final http.Client httpClient;

  @override
  State<_OutputMcpDialog> createState() => _OutputMcpDialogState();
}

class _OutputMcpDialogState extends State<_OutputMcpDialog> {
  late List<_OutputMcpConfig> _configs;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    // Deep-copy the configs so edits don't mutate the original until saved
    _configs = widget.workflow.outputMcps
        .map((c) => _OutputMcpConfig(
              mcpServerId: c.mcpServerId,
              toolName: c.toolName,
              metadata: Map<String, dynamic>.from(c.metadata),
            ))
        .toList();
  }

  void _addConfig() {
    final firstServerId =
        widget.servers.isNotEmpty ? widget.servers.first.id : '';
    setState(() {
      _configs.add(_OutputMcpConfig(mcpServerId: firstServerId));
    });
  }

  void _removeConfig(int index) {
    setState(() {
      _configs.removeAt(index);
    });
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await _saveOutputMcps(
        widget.httpClient,
        widget.workflow.id,
        _configs,
      );
      if (mounted) Navigator.of(context).pop(_configs);
    } catch (e) {
      setState(() {
        _saving = false;
        _error = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: pageBg,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640, maxHeight: 640),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header
            Container(
              padding: const EdgeInsets.all(sp16),
              decoration: const BoxDecoration(
                border: Border(bottom: BorderSide(color: borderColor, width: 2)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.output, size: 16, color: accentLavender),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: Text(
                      'OUTPUT MCPs — ${widget.workflow.title}',
                      style: const TextStyle(
                        fontFamily: fontDisplay,
                        fontSize: 9,
                        color: textPrimary,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => Navigator.of(context).pop(null),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
                ],
              ),
            ),

            // Body
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(sp16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Select MCP servers to receive the final agent output. '
                      'Optionally specify a tool name and metadata.',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: 12,
                        color: textMuted,
                      ),
                    ),
                    const SizedBox(height: sp16),

                    if (_configs.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: sp16),
                        child: Center(
                          child: Text(
                            'No output MCPs configured.',
                            style: TextStyle(
                              fontFamily: fontBody,
                              fontSize: 12,
                              color: textMuted,
                            ),
                          ),
                        ),
                      ),

                    ..._configs.asMap().entries.map((entry) {
                      final idx = entry.key;
                      final cfg = entry.value;
                      return _OutputMcpConfigRow(
                        key: ValueKey(idx),
                        config: cfg,
                        servers: widget.servers,
                        index: idx,
                        onRemove: () => _removeConfig(idx),
                        onChanged: () => setState(() {}),
                      );
                    }),

                    const SizedBox(height: sp12),
                    RetroButton(
                      label: 'ADD OUTPUT MCP',
                      icon: Icons.add,
                      color: accentLavender,
                      onPressed: widget.servers.isEmpty ? null : _addConfig,
                    ),

                    if (widget.servers.isEmpty)
                      const Padding(
                        padding: EdgeInsets.only(top: sp8),
                        child: Text(
                          'No MCP servers available. Register an MCP server first.',
                          style: TextStyle(
                            fontFamily: fontBody,
                            fontSize: 11,
                            color: textMuted,
                          ),
                        ),
                      ),

                    if (_error != null) ...[
                      const SizedBox(height: sp12),
                      Container(
                        padding: const EdgeInsets.all(sp8),
                        decoration: BoxDecoration(
                          border: Border.all(color: accentPrimary),
                          color: accentPrimary.withAlpha(20),
                        ),
                        child: Text(
                          _error!,
                          style: const TextStyle(
                            fontFamily: fontBody,
                            fontSize: 11,
                            color: accentPrimary,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),

            // Footer
            Container(
              padding: const EdgeInsets.all(sp16),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: borderColor, width: 1)),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'CANCEL',
                    onPressed: () => Navigator.of(context).pop(null),
                    color: cardBg,
                    textColor: textPrimary,
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: _saving ? 'SAVING…' : 'SAVE',
                    icon: Icons.save_outlined,
                    onPressed: _saving ? null : _save,
                    color: accentTeal,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _OutputMcpConfigRow — one row in the Output MCP dialog
// ---------------------------------------------------------------------------
class _OutputMcpConfigRow extends StatefulWidget {
  const _OutputMcpConfigRow({
    super.key,
    required this.config,
    required this.servers,
    required this.index,
    required this.onRemove,
    required this.onChanged,
  });

  final _OutputMcpConfig config;
  final List<_McpServer> servers;
  final int index;
  final VoidCallback onRemove;
  final VoidCallback onChanged;

  @override
  State<_OutputMcpConfigRow> createState() => _OutputMcpConfigRowState();
}

class _OutputMcpConfigRowState extends State<_OutputMcpConfigRow> {
  late TextEditingController _toolCtrl;
  late TextEditingController _metaCtrl;
  String? _metaError;

  @override
  void initState() {
    super.initState();
    _toolCtrl = TextEditingController(text: widget.config.toolName ?? '');
    _metaCtrl = TextEditingController(
      text: widget.config.metadata.isEmpty
          ? ''
          : const JsonEncoder.withIndent('  ')
              .convert(widget.config.metadata),
    );
    _toolCtrl.addListener(_onToolChanged);
    _metaCtrl.addListener(_onMetaChanged);
  }

  @override
  void dispose() {
    _toolCtrl.dispose();
    _metaCtrl.dispose();
    super.dispose();
  }

  void _onToolChanged() {
    final t = _toolCtrl.text.trim();
    widget.config.toolName = t.isEmpty ? null : t;
    widget.onChanged();
  }

  void _onMetaChanged() {
    final text = _metaCtrl.text.trim();
    if (text.isEmpty) {
      setState(() => _metaError = null);
      widget.config.metadata = {};
      widget.onChanged();
      return;
    }
    try {
      final parsed = jsonDecode(text);
      if (parsed is Map<String, dynamic>) {
        setState(() => _metaError = null);
        widget.config.metadata = parsed;
        widget.onChanged();
      } else {
        setState(() => _metaError = 'Must be a JSON object {}');
      }
    } catch (_) {
      setState(() => _metaError = 'Invalid JSON');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: sp12),
      decoration: BoxDecoration(
        border: Border.all(color: borderColor, width: 1),
        color: cardBg,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Row header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: sp12, vertical: sp8),
            decoration: const BoxDecoration(
              border: Border(
                bottom: BorderSide(color: borderColor, width: 1),
                left: BorderSide(color: accentLavender, width: 4),
              ),
              color: pageBg,
            ),
            child: Row(
              children: [
                Text(
                  'OUTPUT MCP ${widget.index + 1}',
                  style: const TextStyle(
                    fontFamily: fontDisplay,
                    fontSize: 8,
                    color: textPrimary,
                  ),
                ),
                const Spacer(),
                InkWell(
                  onTap: widget.onRemove,
                  child: const Icon(Icons.delete_outline,
                      size: 16, color: accentPrimary),
                ),
              ],
            ),
          ),

          Padding(
            padding: const EdgeInsets.all(sp12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // MCP Server selector
                _FieldLabel('MCP SERVER'),
                const SizedBox(height: sp4),
                Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: borderColor, width: 1),
                    color: pageBg,
                  ),
                  padding:
                      const EdgeInsets.symmetric(horizontal: sp8, vertical: 2),
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String>(
                      value: widget.servers
                              .any((s) => s.id == widget.config.mcpServerId)
                          ? widget.config.mcpServerId
                          : (widget.servers.isNotEmpty
                              ? widget.servers.first.id
                              : null),
                      isExpanded: true,
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: 12,
                        color: textPrimary,
                      ),
                      items: widget.servers
                          .map((s) => DropdownMenuItem(
                                value: s.id,
                                child: Text(s.name),
                              ))
                          .toList(),
                      onChanged: (val) {
                        if (val != null) {
                          setState(() {
                            widget.config.mcpServerId = val;
                          });
                          widget.onChanged();
                        }
                      },
                    ),
                  ),
                ),

                const SizedBox(height: sp12),

                // Tool name (optional)
                _FieldLabel('TOOL NAME (optional — uses first tool if blank)'),
                const SizedBox(height: sp4),
                _RetroTextField(
                  controller: _toolCtrl,
                  hint: 'e.g. send_message',
                ),

                const SizedBox(height: sp12),

                // Metadata JSON
                _FieldLabel('METADATA JSON (optional)'),
                const SizedBox(height: sp4),
                _RetroTextField(
                  controller: _metaCtrl,
                  hint: '{\n  "destination": "...",\n  "title": "..."\n}',
                  minLines: 3,
                  maxLines: 6,
                  error: _metaError,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Small reusable field helpers
// ---------------------------------------------------------------------------

class _FieldLabel extends StatelessWidget {
  const _FieldLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Text(
        text,
        style: const TextStyle(
          fontFamily: fontDisplay,
          fontSize: 7,
          color: textMuted,
          letterSpacing: 0.5,
        ),
      );
}

class _RetroTextField extends StatelessWidget {
  const _RetroTextField({
    required this.controller,
    this.hint,
    this.minLines = 1,
    this.maxLines = 1,
    this.error,
  });

  final TextEditingController controller;
  final String? hint;
  final int minLines;
  final int maxLines;
  final String? error;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          decoration: BoxDecoration(
            border: Border.all(
              color: error != null ? accentPrimary : borderColor,
              width: 1,
            ),
            color: pageBg,
          ),
          child: TextField(
            controller: controller,
            minLines: minLines,
            maxLines: maxLines,
            style: const TextStyle(
              fontFamily: fontBody,
              fontSize: 12,
              color: textPrimary,
            ),
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: const TextStyle(
                fontFamily: fontBody,
                fontSize: 12,
                color: textMuted,
              ),
              contentPadding: const EdgeInsets.all(sp8),
              border: InputBorder.none,
            ),
          ),
        ),
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              error!,
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 10,
                color: accentPrimary,
              ),
            ),
          ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _ErrorBanner
// ---------------------------------------------------------------------------
class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: sp12),
      padding: const EdgeInsets.all(sp12),
      decoration: BoxDecoration(
        border: Border.all(color: accentPrimary),
        color: accentPrimary.withAlpha(20),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, size: 16, color: accentPrimary),
          const SizedBox(width: sp8),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 11,
                color: accentPrimary,
              ),
            ),
          ),
          TextButton(
            onPressed: onRetry,
            child: const Text(
              'RETRY',
              style: TextStyle(fontFamily: fontBody, fontSize: 11),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// TasksScreen — task execution log
// ---------------------------------------------------------------------------
class TasksScreen extends StatelessWidget {
  const TasksScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _ScreenHeader(
            title: 'TASK EXECUTIONS',
            subtitle: 'History of all agent task runs',
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Execution History',
            accentColor: accentAmber,
            minHeight: 400,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.list_alt_outlined,
                message: 'No task executions yet.',
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// ScheduledAgentsScreen — cron / scheduled agent runs
// ---------------------------------------------------------------------------
class ScheduledAgentsScreen extends StatelessWidget {
  const ScheduledAgentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ScreenHeader(
            title: 'SCHEDULED AGENTS',
            subtitle: 'Cron-triggered agent executions',
            actions: [
              RetroButton(
                label: 'ADD SCHEDULE',
                onPressed: () {},
                icon: Icons.add,
                color: accentTeal,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Active Schedules',
            accentColor: accentTeal,
            minHeight: 300,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.schedule_outlined,
                message: 'No schedules configured.',
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// Shared helpers --------------------------------------------------------

class _ScreenHeader extends StatelessWidget {
  const _ScreenHeader({
    required this.title,
    required this.subtitle,
    this.actions = const [],
  });

  final String title;
  final String subtitle;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 4),
              Text(
                subtitle,
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: 16,
                  color: textMuted,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
        ),
        ...actions.map(
          (a) => Padding(
            padding: const EdgeInsets.only(left: sp8),
            child: a,
          ),
        ),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.icon, required this.message, this.hint});

  final IconData icon;
  final String message;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 40, color: textMuted.withAlpha(100)),
          const SizedBox(height: sp12),
          Text(
            message,
            style: const TextStyle(
              fontFamily: fontBody,
              fontSize: 16,
              color: textMuted,
            ),
            textAlign: TextAlign.center,
          ),
          if (hint != null) ...[
            const SizedBox(height: sp4),
            Text(
              hint!,
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 14,
                color: textMuted,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ],
      ),
    );
  }
}
