import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../../core/config/app_links.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/export_import_dialog.dart';
import '../../core/widgets/retro_card.dart';

// ---------------------------------------------------------------------------
// Agent data model
// ---------------------------------------------------------------------------

class _Agent {
  const _Agent({
    required this.id,
    required this.name,
    required this.description,
    required this.systemPrompt,
    this.model,
    this.providerId,
    required this.mcpServerIds,
    required this.customToolIds,
    required this.knowledgeSourceIds,
    required this.builtinTools,
    required this.createdAt,
  });

  final String id;
  final String name;
  final String description;
  final String systemPrompt;
  final String? model;
  final String? providerId;
  final List<String> mcpServerIds;
  final List<String> customToolIds;
  final List<String> knowledgeSourceIds;
  final List<String> builtinTools;
  final DateTime createdAt;

  factory _Agent.fromJson(Map<String, dynamic> j) => _Agent(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? '',
    description: j['description']?.toString() ?? '',
    systemPrompt: j['system_prompt']?.toString() ?? '',
    model: (j['model'] as String?)?.isNotEmpty == true
        ? j['model'] as String
        : null,
    providerId: (j['provider_id'] as String?)?.isNotEmpty == true
        ? j['provider_id'] as String
        : null,
    mcpServerIds: (j['mcp_server_ids'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList(),
    customToolIds: (j['custom_tool_ids'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList(),
    knowledgeSourceIds: (j['knowledge_source_ids'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList(),
    builtinTools: (j['builtin_tools'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList(),
    createdAt:
        DateTime.tryParse(j['created_at']?.toString() ?? '') ?? DateTime.now(),
  );
}

// ---------------------------------------------------------------------------
// Provider option model (lightweight, for dropdown in _AgentDialog)
// ---------------------------------------------------------------------------

class _ProviderOption {
  const _ProviderOption({
    required this.id,
    required this.name,
    required this.providerType,
  });

  final String id;
  final String name;
  final String providerType;

  factory _ProviderOption.fromJson(Map<String, dynamic> j) => _ProviderOption(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? '',
    providerType: j['provider_type']?.toString() ?? '',
  );
}

// ---------------------------------------------------------------------------
// Agent API helpers
// ---------------------------------------------------------------------------

Future<List<_Agent>> _fetchAgents(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/agents'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load agents (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_Agent.fromJson)
      .toList();
}

Future<void> _createAgent(
  http.Client client,
  Map<String, dynamic> body,
) async {
  final response = await client.post(
    AppLinks.apiUri('/agents'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(body),
  );
  if (response.statusCode < 200 || response.statusCode >= 300) {
    final decoded = jsonDecode(response.body);
    throw Exception(
      decoded['detail'] ?? 'Create failed (${response.statusCode})',
    );
  }
}

Future<void> _updateAgent(
  http.Client client,
  String id,
  Map<String, dynamic> body,
) async {
  final response = await client.put(
    AppLinks.apiUri('/agents/$id'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(body),
  );
  if (response.statusCode < 200 || response.statusCode >= 300) {
    final decoded = jsonDecode(response.body);
    throw Exception(
      decoded['detail'] ?? 'Update failed (${response.statusCode})',
    );
  }
}

Future<void> _deleteAgent(http.Client client, String id) async {
  final response = await client.delete(AppLinks.apiUri('/agents/$id'));
  if (response.statusCode != 204 &&
      (response.statusCode < 200 || response.statusCode >= 300)) {
    throw Exception('Delete failed (${response.statusCode})');
  }
}

// ---------------------------------------------------------------------------
// AgentsScreen — live StatefulWidget with full CRUD
// ---------------------------------------------------------------------------

class AgentsScreen extends StatefulWidget {
  const AgentsScreen({super.key});

  @override
  State<AgentsScreen> createState() => _AgentsScreenState();
}

class _AgentsScreenState extends State<AgentsScreen> {
  http.Client? _ownedClient;
  late Future<List<_Agent>> _agentsFuture;

  http.Client get _client => _ownedClient ??= http.Client();

  @override
  void initState() {
    super.initState();
    _reload();
  }

  @override
  void dispose() {
    _ownedClient?.close();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _agentsFuture = _fetchAgents(_client);
    });
  }

  Future<void> _confirmDelete(_Agent agent) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: cardBg,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(4),
          side: const BorderSide(color: accentPrimary, width: 1),
        ),
        title: const Text(
          'DELETE AGENT',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: 13,
            color: accentPrimary,
            letterSpacing: 1.5,
          ),
        ),
        content: Text(
          "Delete agent '${agent.name}'? This action cannot be undone.",
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 12,
            color: textMuted,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text(
              'CANCEL',
              style: TextStyle(fontFamily: fontBody, color: textMuted),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text(
              'DELETE',
              style: TextStyle(fontFamily: fontBody, color: accentPrimary),
            ),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await _deleteAgent(_client, agent.id);
      _reload();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Agent '${agent.name}' deleted."),
          backgroundColor: accentTeal,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Delete failed: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_Agent>>(
      future: _agentsFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final agents = snapshot.data ?? [];

        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ScreenHeader(
                title: 'AGENTS',
                subtitle: 'Configured AI agents',
                actions: [
                  RetroButton(
                    label: 'EXPORT',
                    onPressed: () => showExportDialog(
                      context,
                      apiPath: '/agents/export',
                      resourceLabel: 'AGENTS',
                    ),
                    icon: Icons.download_outlined,
                    color: accentSlate,
                  ),
                  RetroButton(
                    label: 'IMPORT',
                    onPressed: () => showImportDialog(
                      context,
                      apiPath: '/agents/import',
                      resourceLabel: 'AGENTS',
                    ),
                    icon: Icons.upload_outlined,
                    color: accentSlate,
                  ),
                  RetroButton(
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentSlate,
                  ),
                  RetroButton(
                    label: 'NEW AGENT',
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _AgentDialog(
                        client: _client,
                        onSaved: _reload,
                      ),
                    ),
                    icon: Icons.add,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _AgentErrorBanner(
                  message: 'Failed to load agents: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Agent Registry',
                accentColor: accentTeal,
                minHeight: agents.isEmpty ? 300 : 0,
                child: agents.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Center(
                          child: _EmptyState(
                            icon: Icons.smart_toy_outlined,
                            message: loading
                                ? 'Loading…'
                                : 'No agents configured yet.',
                            hint: loading
                                ? null
                                : 'Create an agent to get started.',
                          ),
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final agent in agents)
                              _AgentCard(
                                agent: agent,
                                onEdit: () => showDialog<void>(
                                  context: context,
                                  builder: (_) => _AgentDialog(
                                    client: _client,
                                    onSaved: _reload,
                                    existing: agent,
                                  ),
                                ),
                                onDelete: () => _confirmDelete(agent),
                              ),
                          ],
                        ),
                      ),
              ),
              const SizedBox(height: sp24),
              SectionFrame(title: 'Agent Memory', accentColor: accentAmber),
            ],
          ),
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------
// _AgentCard — displays one agent with edit / delete actions
// ---------------------------------------------------------------------------

class _AgentCard extends StatelessWidget {
  const _AgentCard({
    required this.agent,
    required this.onEdit,
    required this.onDelete,
  });

  final _Agent agent;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: sp12),
      child: RetroCard(
        child: Padding(
          padding: const EdgeInsets.all(sp16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Header row ────────────────────────────────────────────
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      agent.name,
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: fontSizeBody,
                        color: accentAmber,
                        letterSpacing: 1,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const SizedBox(width: sp8),
                  if (agent.model != null && agent.model!.isNotEmpty)
                    RetroChip(
                      label: agent.model!,
                      color: accentTeal,
                    )
                  else
                    const RetroChip(
                      label: 'DEFAULT MODEL',
                      color: textMuted,
                    ),
                ],
              ),
              // ── Description ───────────────────────────────────────────
              if (agent.description.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Text(
                  agent.description,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeCaption,
                    color: textMuted,
                    height: fontHeightBody,
                  ),
                ),
              ],
              // ── Count badges ──────────────────────────────────────────
              const SizedBox(height: sp8),
              Wrap(
                spacing: sp8,
                runSpacing: sp4,
                children: [
                  RetroChip(
                    label: '${agent.mcpServerIds.length} MCPs',
                    color: accentSlate,
                  ),
                  RetroChip(
                    label: '${agent.customToolIds.length} TOOLS',
                    color: accentSlate,
                  ),
                  RetroChip(
                    label: '${agent.knowledgeSourceIds.length} KNOWLEDGE',
                    color: accentSlate,
                  ),
                ],
              ),
              // ── Action buttons ────────────────────────────────────────
              const SizedBox(height: sp12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'EDIT',
                    icon: Icons.edit_outlined,
                    color: accentTeal,
                    onPressed: onEdit,
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: 'DELETE',
                    icon: Icons.delete_outline,
                    color: const Color(0xFF8B2E2E),
                    onPressed: onDelete,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _AgentDialog — create / edit an agent
// ---------------------------------------------------------------------------

class _AgentDialog extends StatefulWidget {
  const _AgentDialog({
    required this.client,
    required this.onSaved,
    this.existing,
  });

  final http.Client client;
  final VoidCallback onSaved;
  final _Agent? existing;

  @override
  State<_AgentDialog> createState() => _AgentDialogState();
}

class _AgentDialogState extends State<_AgentDialog> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _descCtrl;
  late final TextEditingController _systemPromptCtrl;
  late final TextEditingController _modelCtrl;
  bool _saving = false;

  // Provider dropdown state
  late Future<List<_ProviderOption>> _providersFuture;
  String? _selectedProviderId;

  List<String> _selectedMcpIds = [];
  List<String> _selectedCustomToolIds = [];
  List<String> _selectedKnowledgeIds = [];
  List<String> _selectedBuiltinTools = [];
  final _mcpTagsCtrl = TextEditingController();
  final _knowledgeTagsCtrl = TextEditingController();
  late Future<List<_McpServer>> _mcpsFuture;
  late Future<List<_CustomTool>> _customToolsFuture;
  late Future<List<_KnowledgeSource>> _knowledgeFuture;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final a = widget.existing;
    _nameCtrl = TextEditingController(text: a?.name ?? '');
    _descCtrl = TextEditingController(text: a?.description ?? '');
    _systemPromptCtrl = TextEditingController(
      text: a?.systemPrompt ?? 'You are a helpful assistant.',
    );
    _modelCtrl = TextEditingController(text: a?.model ?? '');
    _selectedProviderId = a?.providerId;
    _providersFuture = _fetchProviderOptions(widget.client);
    _selectedMcpIds = List.from(a?.mcpServerIds ?? []);
    _selectedCustomToolIds = List.from(a?.customToolIds ?? []);
    _selectedKnowledgeIds = List.from(a?.knowledgeSourceIds ?? []);
    _selectedBuiltinTools = List.from(a?.builtinTools ?? []);
    _mcpsFuture = _fetchMcpServers(widget.client);
    _customToolsFuture = _fetchCustomTools(widget.client);
    _knowledgeFuture = _fetchKnowledgeSources(widget.client);
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _descCtrl.dispose();
    _systemPromptCtrl.dispose();
    _modelCtrl.dispose();
    _mcpTagsCtrl.dispose();
    _knowledgeTagsCtrl.dispose();
    super.dispose();
  }

  Future<List<_ProviderOption>> _fetchProviderOptions(
    http.Client client,
  ) async {
    final response = await client.get(AppLinks.apiUri('/providers'));
    if (response.statusCode < 200 || response.statusCode >= 300) return [];
    final decoded = jsonDecode(response.body);
    if (decoded is! List) return [];
    return decoded.whereType<Map<String, dynamic>>().map(_ProviderOption.fromJson).toList();
  }

  Future<void> _save() async {
    final name = _nameCtrl.text.trim();
    final systemPrompt = _systemPromptCtrl.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Name is required.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    if (systemPrompt.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('System prompt is required.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final body = <String, dynamic>{
        'name': name,
        'description': _descCtrl.text.trim(),
        'system_prompt': systemPrompt,
        if (_modelCtrl.text.trim().isNotEmpty) 'model': _modelCtrl.text.trim(),
        if (_selectedProviderId != null && _selectedProviderId!.isNotEmpty)
          'provider_id': _selectedProviderId,
        'mcp_server_ids': _selectedMcpIds,
        if (_mcpTagsCtrl.text.trim().isNotEmpty)
          'mcp_server_tags': _mcpTagsCtrl.text.trim().split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
        'custom_tool_ids': _selectedCustomToolIds,
        'knowledge_source_ids': _selectedKnowledgeIds,
        if (_knowledgeTagsCtrl.text.trim().isNotEmpty)
          'knowledge_tags': _knowledgeTagsCtrl.text.trim().split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
        'builtin_tools': _selectedBuiltinTools,
      };
      if (_isEdit) {
        await _updateAgent(widget.client, widget.existing!.id, body);
      } else {
        await _createAgent(widget.client, body);
      }
      if (!mounted) return;
      widget.onSaved();
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_isEdit ? 'Agent updated.' : 'Agent created.'),
          backgroundColor: accentTeal,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed: $e'),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: const BorderSide(color: accentAmber, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520, minWidth: 320),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header ──────────────────────────────────────────────────
                Row(
                  children: [
                    const Icon(
                      Icons.smart_toy_outlined,
                      color: accentAmber,
                      size: 20,
                    ),
                    const SizedBox(width: sp8),
                    Expanded(
                      child: Text(
                        _isEdit ? 'EDIT AGENT' : 'NEW AGENT',
                        style: const TextStyle(
                          fontFamily: fontBody,
                          fontSize: 13,
                          color: accentAmber,
                          letterSpacing: 1.5,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(
                        Icons.close,
                        color: textMuted,
                        size: 18,
                      ),
                      onPressed: () => Navigator.of(context).pop(),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                    ),
                  ],
                ),
                const SizedBox(height: sp16),
                _AgentDialogField(
                  label: 'NAME *',
                  controller: _nameCtrl,
                  hint: 'my-agent',
                ),
                const SizedBox(height: sp12),
                _AgentDialogField(
                  label: 'DESCRIPTION',
                  controller: _descCtrl,
                  hint: 'What does this agent do?',
                  maxLines: 2,
                ),
                const SizedBox(height: sp12),
                _AgentDialogField(
                  label: 'SYSTEM PROMPT *',
                  controller: _systemPromptCtrl,
                  hint: 'You are a helpful assistant.',
                  maxLines: 4,
                ),
                const SizedBox(height: sp12),
                _AgentDialogField(
                  label: 'MODEL',
                  controller: _modelCtrl,
                  hint: 'Leave blank for default',
                ),
                const SizedBox(height: sp12),
                // Provider dropdown ─────────────────────────────────────
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'PROVIDER',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: 10,
                        color: accentAmber,
                        letterSpacing: 1.2,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: sp4),
                    FutureBuilder<List<_ProviderOption>>(
                      future: _providersFuture,
                      builder: (context, snap) {
                        final providers = snap.data ?? [];
                        return Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: sp12,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: pageBg,
                            border: Border.all(color: accentAmber.withAlpha(80)),
                            borderRadius: BorderRadius.circular(2),
                          ),
                          child: DropdownButton<String?>(
                            value: _selectedProviderId,
                            isExpanded: true,
                            underline: const SizedBox(),
                            dropdownColor: cardBg,
                            style: const TextStyle(
                              fontFamily: fontBody,
                              fontSize: 12,
                              color: textPrimary,
                            ),
                            hint: Text(
                              snap.connectionState == ConnectionState.waiting
                                  ? 'Loading providers…'
                                  : 'None (use default)',
                              style: const TextStyle(
                                fontFamily: fontBody,
                                fontSize: 12,
                                color: textMuted,
                              ),
                            ),
                            items: [
                              const DropdownMenuItem<String?>(
                                value: null,
                                child: Text(
                                  'None (use default)',
                                  style: TextStyle(
                                    fontFamily: fontBody,
                                    fontSize: 12,
                                    color: textMuted,
                                  ),
                                ),
                              ),
                              for (final p in providers)
                                DropdownMenuItem<String?>(
                                  value: p.id,
                                  child: Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          p.name,
                                          style: const TextStyle(
                                            fontFamily: fontBody,
                                            fontSize: 12,
                                            color: textPrimary,
                                          ),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                      const SizedBox(width: sp8),
                                      Text(
                                        p.providerType,
                                        style: const TextStyle(
                                          fontFamily: fontBody,
                                          fontSize: 10,
                                          color: textMuted,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                            ],
                            onChanged: (v) => setState(() => _selectedProviderId = v),
                          ),
                        );
                      },
                    ),
                  ],
                ),
                const SizedBox(height: sp12),
                // MCP SERVERS ──────────────────────────────────────────
                FutureBuilder<List<_McpServer>>(
                  future: _mcpsFuture,
                  builder: (context, snap) {
                    final items = (snap.data ?? []).map((s) => (id: s.id, name: s.name)).toList();
                    return _MultiSelectChipField(
                      label: 'MCP SERVERS',
                      selected: _selectedMcpIds,
                      items: items,
                      accentColor: accentSlate,
                      loading: snap.connectionState == ConnectionState.waiting,
                      onChanged: (v) => setState(() => _selectedMcpIds = v),
                    );
                  },
                ),
                const SizedBox(height: sp12),
                // CUSTOM TOOLS ─────────────────────────────────────────
                FutureBuilder<List<_CustomTool>>(
                  future: _customToolsFuture,
                  builder: (context, snap) {
                    final items = (snap.data ?? []).map((t) => (id: t.id, name: t.name)).toList();
                    return _MultiSelectChipField(
                      label: 'CUSTOM TOOLS',
                      selected: _selectedCustomToolIds,
                      items: items,
                      accentColor: accentTeal,
                      loading: snap.connectionState == ConnectionState.waiting,
                      onChanged: (v) => setState(() => _selectedCustomToolIds = v),
                    );
                  },
                ),
                const SizedBox(height: sp12),
                // KNOWLEDGE SOURCES ────────────────────────────────────
                FutureBuilder<List<_KnowledgeSource>>(
                  future: _knowledgeFuture,
                  builder: (context, snap) {
                    final items = (snap.data ?? []).map((k) => (id: k.id, name: k.name)).toList();
                    return _MultiSelectChipField(
                      label: 'KNOWLEDGE SOURCES',
                      selected: _selectedKnowledgeIds,
                      items: items,
                      accentColor: accentLavender,
                      loading: snap.connectionState == ConnectionState.waiting,
                      onChanged: (v) => setState(() => _selectedKnowledgeIds = v),
                    );
                  },
                ),
                const SizedBox(height: sp12),
                // BUILTIN TOOLS ────────────────────────────────────────
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('BUILTIN TOOLS', style: TextStyle(fontFamily: fontBody, fontSize: 10, color: accentAmber, letterSpacing: 1.2, fontWeight: FontWeight.bold)),
                    const SizedBox(height: sp4),
                    Wrap(
                      spacing: sp4,
                      runSpacing: sp4,
                      children: [
                        for (final tool in ['bash', 'read', 'write', 'edit', 'glob', 'grep', 'web_fetch', 'web_search'])
                          FilterChip(
                            label: Text(tool, style: TextStyle(fontFamily: fontBody, fontSize: 11, color: _selectedBuiltinTools.contains(tool) ? Colors.white : textPrimary)),
                            selected: _selectedBuiltinTools.contains(tool),
                            onSelected: (v) => setState(() {
                              if (v) { _selectedBuiltinTools.add(tool); } else { _selectedBuiltinTools.remove(tool); }
                            }),
                            selectedColor: accentAmber,
                            backgroundColor: pageBg,
                            side: BorderSide(color: accentAmber.withAlpha(80)),
                            padding: const EdgeInsets.symmetric(horizontal: sp4),
                            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: sp12),
                // MCP TAGS ─────────────────────────────────────────────
                _AgentDialogField(
                  label: 'MCP TAGS (comma-separated)',
                  controller: _mcpTagsCtrl,
                  hint: 'tag1, tag2',
                ),
                const SizedBox(height: sp12),
                // KNOWLEDGE TAGS ───────────────────────────────────────
                _AgentDialogField(
                  label: 'KNOWLEDGE TAGS (comma-separated)',
                  controller: _knowledgeTagsCtrl,
                  hint: 'tag1, tag2',
                ),
                const SizedBox(height: sp24),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    RetroButton(
                      label: 'CANCEL',
                      onPressed: () => Navigator.of(context).pop(),
                      color: accentSlate,
                    ),
                    const SizedBox(width: sp8),
                    RetroButton(
                      label: _saving
                          ? 'SAVING…'
                          : (_isEdit ? 'SAVE' : 'CREATE'),
                      onPressed: _saving ? null : _save,
                      color: accentAmber,
                      textColor: textPrimary,
                      icon: _saving ? null : Icons.check,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _AgentDialogField — labelled text input for agent dialogs
// ---------------------------------------------------------------------------

class _AgentDialogField extends StatelessWidget {
  const _AgentDialogField({
    required this.label,
    required this.controller,
    this.hint = '',
    this.maxLines = 1,
  });

  final String label;
  final TextEditingController controller;
  final String hint;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 9,
            color: textMuted,
            letterSpacing: 0.8,
          ),
        ),
        const SizedBox(height: sp4),
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: accentAmber.withAlpha(80)),
            borderRadius: BorderRadius.circular(2),
          ),
          padding: const EdgeInsets.symmetric(horizontal: sp8, vertical: sp4),
          child: TextField(
            controller: controller,
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
              border: InputBorder.none,
              isDense: true,
            ),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _MultiSelectChipField — reusable chip-based multi-select input
// ---------------------------------------------------------------------------
typedef _IdName = ({String id, String name});

class _MultiSelectChipField extends StatelessWidget {
  const _MultiSelectChipField({
    required this.label,
    required this.selected,
    required this.items,
    required this.onChanged,
    required this.accentColor,
    this.loading = false,
  });

  final String label;
  final List<String> selected;
  final List<_IdName> items;
  final ValueChanged<List<String>> onChanged;
  final Color accentColor;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(label, style: TextStyle(fontFamily: fontBody, fontSize: 10, color: accentColor, letterSpacing: 1.2, fontWeight: FontWeight.bold)),
            const Spacer(),
            TextButton.icon(
              onPressed: loading ? null : () => _showPicker(context),
              icon: Icon(Icons.add, size: 14, color: accentColor),
              label: Text('ADD', style: TextStyle(fontFamily: fontBody, fontSize: 10, color: accentColor)),
              style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: sp4, vertical: 2), minimumSize: Size.zero, tapTargetSize: MaterialTapTargetSize.shrinkWrap),
            ),
          ],
        ),
        const SizedBox(height: sp4),
        if (selected.isEmpty)
          Text('None selected', style: const TextStyle(fontFamily: fontBody, fontSize: 11, color: textMuted))
        else
          Wrap(
            spacing: sp4,
            runSpacing: sp4,
            children: [
              for (final id in selected)
                Chip(
                  label: Text(items.firstWhere((e) => e.id == id, orElse: () => (id: id, name: id)).name, style: const TextStyle(fontFamily: fontBody, fontSize: 11, color: textPrimary)),
                  backgroundColor: pageBg,
                  side: BorderSide(color: accentColor.withAlpha(120)),
                  deleteIcon: const Icon(Icons.close, size: 14),
                  onDeleted: () => onChanged(selected.where((e) => e != id).toList()),
                  padding: const EdgeInsets.symmetric(horizontal: sp4),
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
            ],
          ),
      ],
    );
  }

  Future<void> _showPicker(BuildContext context) async {
    final current = List<String>.from(selected);
    await showDialog<void>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(builder: (ctx, setS) {
          return AlertDialog(
            backgroundColor: cardBg,
            title: Text(label, style: const TextStyle(fontFamily: fontBody, fontSize: 13, color: textPrimary)),
            content: SizedBox(
              width: 360,
              child: items.isEmpty
                  ? const Text('No items available.', style: TextStyle(fontFamily: fontBody, color: textMuted))
                  : ListView(
                      shrinkWrap: true,
                      children: [
                        for (final item in items)
                          CheckboxListTile(
                            value: current.contains(item.id),
                            title: Text(item.name, style: const TextStyle(fontFamily: fontBody, fontSize: 12, color: textPrimary)),
                            activeColor: accentColor,
                            dense: true,
                            onChanged: (v) => setS(() { if (v == true) { current.add(item.id); } else { current.remove(item.id); } }),
                          ),
                      ],
                    ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('CANCEL', style: TextStyle(fontFamily: fontBody, color: textMuted))),
              TextButton(
                onPressed: () { onChanged(current); Navigator.of(ctx).pop(); },
                child: Text('APPLY', style: TextStyle(fontFamily: fontBody, color: accentColor)),
              ),
            ],
          );
        });
      },
    );
  }
}

// ---------------------------------------------------------------------------
// _AgentErrorBanner — error banner with retry for AgentsScreen
// ---------------------------------------------------------------------------

class _AgentErrorBanner extends StatelessWidget {
  const _AgentErrorBanner({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: sp16),
      child: RetroCard(
        child: Padding(
          padding: const EdgeInsets.all(sp16),
          child: Row(
            children: [
              const Icon(
                Icons.warning_amber_outlined,
                color: accentAmber,
                size: 20,
              ),
              const SizedBox(width: sp8),
              Expanded(
                child: Text(
                  message,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: textMuted,
                  ),
                ),
              ),
              RetroButton(
                label: 'RETRY',
                onPressed: onRetry,
                color: accentAmber,
                textColor: textPrimary,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// McpServersScreen — model + full CRUD
// ---------------------------------------------------------------------------
class _McpServer {
  const _McpServer({
    required this.id,
    required this.name,
    required this.transportType,
    required this.connectionConfig,
    required this.allowedTools,
    required this.tags,
    required this.status,
    this.lastError,
  });

  final String id;
  final String name;
  final String transportType;
  final Map<String, dynamic> connectionConfig;
  final List<String> allowedTools;
  final List<String> tags;
  final String status;
  final String? lastError;

  factory _McpServer.fromJson(Map<String, dynamic> j) => _McpServer(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? '',
    transportType: j['transport_type']?.toString() ?? 'stdio',
    connectionConfig: (j['connection_config'] as Map<String, dynamic>?) ?? {},
    allowedTools: (j['allowed_tools'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList(),
    tags: (j['tags'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList(),
    status: j['status']?.toString() ?? 'unknown',
    lastError: j['last_error']?.toString(),
  );
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

class McpServersScreen extends StatefulWidget {
  const McpServersScreen({super.key});

  @override
  State<McpServersScreen> createState() => _McpServersScreenState();
}

class _McpServersScreenState extends State<McpServersScreen> {
  final _client = http.Client();
  late Future<List<_McpServer>> _serversFuture;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _serversFuture = _fetchMcpServers(_client);
    });
  }

  Future<void> _deleteServer(String id) async {
    final response = await _client.delete(AppLinks.apiUri('/mcps/$id'));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Delete failed (${response.statusCode})');
    }
  }

  void _confirmDelete(BuildContext context, _McpServer server) {
    final messenger = ScaffoldMessenger.of(context);
    showDialog<bool>(
      context: context,
      builder: (_) => _ConfirmDeleteDialog(
        name: server.name,
        accentColor: accentPrimary,
      ),
    ).then((confirmed) async {
      if (confirmed != true) return;
      try {
        await _deleteServer(server.id);
        if (!mounted) return;
        _reload();
      } catch (e) {
        if (!mounted) return;
        messenger.showSnackBar(
          SnackBar(
            content: Text('Delete failed: $e'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    });
  }

  void _showForm({_McpServer? existing}) {
    showDialog<bool>(
      context: context,
      builder: (_) => _McpServerDialog(client: _client, existing: existing),
    ).then((saved) {
      if (saved == true) _reload();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_McpServer>>(
      future: _serversFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final servers = snapshot.data ?? [];
        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ScreenHeader(
                title: 'MCP SERVERS',
                subtitle: 'Model Context Protocol server connections',
                actions: [
                  RetroButton(
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentSlate,
                  ),
                  RetroButton(
                    label: 'ADD SERVER',
                    onPressed: () => _showForm(),
                    icon: Icons.add,
                    color: accentAmber,
                    textColor: textPrimary,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _ErrorBanner(
                  message: 'Failed to load MCP servers: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Connected Servers',
                accentColor: accentAmber,
                minHeight: servers.isEmpty ? 300.0 : 0.0,
                child: servers.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Center(
                          child: _EmptyState(
                            icon: Icons.power_outlined,
                            message: loading
                                ? 'Loading…'
                                : 'No MCP servers connected.',
                            hint: 'Add a server endpoint to enable tool access.',
                          ),
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final server in servers)
                              _McpServerCard(
                                server: server,
                                client: _client,
                                onEdit: () => _showForm(existing: server),
                                onDelete: () =>
                                    _confirmDelete(context, server),
                              ),
                          ],
                        ),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _McpServerCard extends StatelessWidget {
  const _McpServerCard({
    required this.server,
    required this.client,
    required this.onEdit,
    required this.onDelete,
  });

  final _McpServer server;
  final http.Client client;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  Color get _statusColor {
    switch (server.status) {
      case 'connected':
        return accentTeal;
      case 'error':
        return accentPrimary;
      default:
        return textMuted;
    }
  }

  Future<void> _testConnection(BuildContext context) async {
    try {
      final response = await client.post(
        AppLinks.apiUri('/mcps/${server.id}/test'),
        headers: {'Content-Type': 'application/json'},
        body: '{}',
      );
      if (!context.mounted) return;
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final success = data['success'] == true;
        final toolCount = (data['tools'] as List?)?.length ?? 0;
        final error = data['error']?.toString();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              success
                  ? 'Connected — $toolCount tools available'
                  : 'Error: ${error ?? 'unknown error'}',
            ),
            backgroundColor: success ? accentTeal : Colors.red.shade700,
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Test failed (${response.statusCode})'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Test error: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: sp12),
      child: RetroCard(
        child: Padding(
          padding: const EdgeInsets.all(sp16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      server.name,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontFamily: fontBody,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  RetroChip(
                    label: server.transportType,
                    color: accentAmber,
                    textColor: textPrimary,
                  ),
                  const SizedBox(width: sp8),
                  RetroChip(label: server.status, color: _statusColor),
                ],
              ),
              if (server.lastError != null && server.lastError!.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Text(
                  'Error: ${server.lastError}',
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 11,
                    color: accentPrimary,
                    height: 1.4,
                  ),
                ),
              ],
              if (server.tags.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Wrap(
                  spacing: sp4,
                  runSpacing: sp4,
                  children: [
                    for (final tag in server.tags)
                      RetroChip(label: tag, color: accentSlate),
                  ],
                ),
              ],
              const SizedBox(height: sp12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'TEST',
                    icon: Icons.network_check,
                    color: accentTeal,
                    onPressed: () => _testConnection(context),
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: 'EDIT',
                    icon: Icons.edit_outlined,
                    color: accentSlate,
                    onPressed: onEdit,
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: 'DELETE',
                    icon: Icons.delete_outline,
                    color: accentPrimary,
                    onPressed: onDelete,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _McpServerDialog extends StatefulWidget {
  const _McpServerDialog({required this.client, this.existing});
  final http.Client client;
  final _McpServer? existing;

  @override
  State<_McpServerDialog> createState() => _McpServerDialogState();
}

class _McpServerDialogState extends State<_McpServerDialog> {
  static const _stdioTemplate =
      '{\n  "command": "npx",\n  "args": ["-y", "@some/mcp-server"],\n  "env": {}\n}';
  static const _sseTemplate = '{\n  "url": "https://example.com/sse"\n}';

  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _configCtrl = TextEditingController();
  final _tagsCtrl = TextEditingController();
  String _transportType = 'stdio';
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final s = widget.existing;
    if (s != null) {
      _nameCtrl.text = s.name;
      _transportType = s.transportType;
      _configCtrl.text =
          const JsonEncoder.withIndent('  ').convert(s.connectionConfig);
      _tagsCtrl.text = s.tags.join(', ');
    } else {
      _configCtrl.text = _stdioTemplate;
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _configCtrl.dispose();
    _tagsCtrl.dispose();
    super.dispose();
  }

  void _onTransportChanged(String? val) {
    if (val == null) return;
    setState(() {
      _transportType = val;
      if (widget.existing == null) {
        _configCtrl.text = val == 'stdio' ? _stdioTemplate : _sseTemplate;
      }
    });
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    Map<String, dynamic> configJson;
    try {
      configJson = jsonDecode(_configCtrl.text) as Map<String, dynamic>;
    } catch (_) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Connection config is not valid JSON.'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final body = jsonEncode({
        'name': _nameCtrl.text.trim(),
        'transport_type': _transportType,
        'connection_config': configJson,
        'tags': _tagsCtrl.text
            .split(',')
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty)
            .toList(),
      });
      final http.Response response;
      if (widget.existing != null) {
        response = await widget.client.put(
          AppLinks.apiUri('/mcps/${widget.existing!.id}'),
          headers: {'Content-Type': 'application/json'},
          body: body,
        );
      } else {
        response = await widget.client.post(
          AppLinks.apiUri('/mcps'),
          headers: {'Content-Type': 'application/json'},
          body: body,
        );
      }
      if (!mounted) return;
      if (response.statusCode >= 200 && response.statusCode < 300) {
        Navigator.of(context).pop(true);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(_extractDetail(response.body)),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Save failed: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: const BorderSide(color: accentAmber, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560, minWidth: 320),
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _DialogHeader(
                    title: widget.existing != null
                        ? 'EDIT MCP SERVER'
                        : 'ADD MCP SERVER',
                    color: accentAmber,
                    icon: Icons.power_outlined,
                    onClose: () => Navigator.of(context).pop(false),
                  ),
                  const SizedBox(height: sp16),
                  _DialogField(
                    label: 'NAME',
                    child: TextFormField(
                      controller: _nameCtrl,
                      style: _kDialogInputStyle,
                      decoration: _dialogInputDeco('e.g. My MCP Server'),
                      validator: (v) => (v == null || v.trim().isEmpty)
                          ? 'Name is required'
                          : null,
                    ),
                  ),
                  const SizedBox(height: sp12),
                  _DialogField(
                    label: 'TRANSPORT TYPE',
                    child: _RetroDropdown<String>(
                      value: _transportType,
                      items: const ['stdio', 'sse'],
                      onChanged: _onTransportChanged,
                    ),
                  ),
                  const SizedBox(height: sp12),
                  _DialogField(
                    label: 'CONNECTION CONFIG (JSON)',
                    child: TextFormField(
                      controller: _configCtrl,
                      style: _kDialogInputStyle,
                      decoration: _dialogInputDeco('{}'),
                      maxLines: 6,
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) {
                          return 'Config is required';
                        }
                        try {
                          jsonDecode(v);
                        } catch (_) {
                          return 'Must be valid JSON';
                        }
                        return null;
                      },
                    ),
                  ),
                  const SizedBox(height: sp12),
                  _DialogField(
                    label: 'TAGS (comma-separated)',
                    child: TextFormField(
                      controller: _tagsCtrl,
                      style: _kDialogInputStyle,
                      decoration: _dialogInputDeco('e.g. production, tools'),
                    ),
                  ),
                  const SizedBox(height: sp24),
                  _DialogActions(
                    saving: _saving,
                    onCancel: () => Navigator.of(context).pop(false),
                    onSave: _saving ? null : _save,
                    saveColor: accentAmber,
                    saveTextColor: textPrimary,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// CustomToolsScreen — fetches and displays all custom tools from the API.
// ---------------------------------------------------------------------------

class _CustomTool {
  const _CustomTool({
    required this.id,
    required this.name,
    required this.description,
    required this.tags,
    required this.isEnabled,
    required this.isPlugin,
    required this.envConfig,
    required this.parametersSchema,
  });

  final String id;
  final String name;
  final String description;
  final List<String> tags;
  final bool isEnabled;
  final bool isPlugin;
  final Map<String, dynamic> envConfig;
  final Map<String, dynamic> parametersSchema;

  factory _CustomTool.fromJson(Map<String, dynamic> json) => _CustomTool(
    id: json['id']?.toString() ?? '',
    name: json['name']?.toString() ?? '',
    description: json['description']?.toString() ?? '',
    tags: (json['tags'] as List<dynamic>? ?? []).map((e) => e.toString()).toList(),
    isEnabled: json['is_enabled'] == true,
    isPlugin: json['is_plugin'] == true,
    envConfig: (json['env_config'] as Map<String, dynamic>?) ?? {},
    parametersSchema: (json['parameters_schema'] as Map<String, dynamic>?) ?? {},
  );
}

// ---------------------------------------------------------------------------
// Token-mapping models
// ---------------------------------------------------------------------------
class _TokenRef {
  const _TokenRef({
    required this.id,
    required this.name,
    required this.description,
    required this.maskedValue,
  });
  final String id;
  final String name;
  final String description;
  final String maskedValue;

  factory _TokenRef.fromJson(Map<String, dynamic> json) => _TokenRef(
    id: json['id']?.toString() ?? '',
    name: json['name']?.toString() ?? '',
    description: json['description']?.toString() ?? '',
    maskedValue: json['masked_value']?.toString() ?? '',
  );
}

class _EnvVarEntry {
  const _EnvVarEntry({
    required this.envVar,
    required this.currentToken,
    required this.template,
  });
  final String envVar;
  final String? currentToken; // null if not mapped to a token
  final String template;

  factory _EnvVarEntry.fromJson(Map<String, dynamic> json) => _EnvVarEntry(
    envVar: json['env_var']?.toString() ?? '',
    currentToken: json['current_token']?.toString(),
    template: json['template']?.toString() ?? '',
  );
}

class _EnvMapping {
  const _EnvMapping({
    required this.toolId,
    required this.toolName,
    required this.envVars,
    required this.availableTokens,
  });
  final String toolId;
  final String toolName;
  final List<_EnvVarEntry> envVars;
  final List<_TokenRef> availableTokens;

  factory _EnvMapping.fromJson(Map<String, dynamic> json) => _EnvMapping(
    toolId: json['tool_id']?.toString() ?? '',
    toolName: json['tool_name']?.toString() ?? '',
    envVars: (json['env_vars'] as List<dynamic>? ?? [])
        .whereType<Map<String, dynamic>>()
        .map(_EnvVarEntry.fromJson)
        .toList(),
    availableTokens: (json['available_tokens'] as List<dynamic>? ?? [])
        .whereType<Map<String, dynamic>>()
        .map(_TokenRef.fromJson)
        .toList(),
  );
}

// ---------------------------------------------------------------------------
// Token-mapping API helpers
// ---------------------------------------------------------------------------
Future<List<_CustomTool>> _fetchCustomTools(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/custom-tools'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load custom tools (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_CustomTool.fromJson)
      .toList();
}

Future<_EnvMapping> _fetchEnvMapping(
  http.Client client,
  String toolId,
) async {
  final response = await client.get(
    AppLinks.apiUri('/custom-tools/$toolId/env-mapping'),
  );
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load env mapping (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! Map<String, dynamic>) {
    throw Exception('Unexpected response format');
  }
  return _EnvMapping.fromJson(decoded);
}

Future<void> _saveEnvMapping(
  http.Client client,
  String toolId,
  Map<String, String> mapping,
) async {
  final response = await client.put(
    AppLinks.apiUri('/custom-tools/$toolId/env-mapping'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'env_var_mapping': mapping}),
  );
  if (response.statusCode < 200 || response.statusCode >= 300) {
    final body = jsonDecode(response.body);
    throw Exception(
      body['detail'] ?? 'Failed to save mapping (${response.statusCode})',
    );
  }
}

class CustomToolsScreen extends StatefulWidget {
  const CustomToolsScreen({super.key});

  @override
  State<CustomToolsScreen> createState() => _CustomToolsScreenState();
}

class _CustomToolsScreenState extends State<CustomToolsScreen> {
  http.Client? _ownedClient;
  late Future<List<_CustomTool>> _toolsFuture;

  http.Client get _client => _ownedClient ??= http.Client();

  @override
  void initState() {
    super.initState();
    _toolsFuture = _fetchCustomTools(_client);
  }

  @override
  void dispose() {
    _ownedClient?.close();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _toolsFuture = _fetchCustomTools(_client);
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_CustomTool>>(
      future: _toolsFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final tools = snapshot.data ?? [];
        final pluginTools = tools.where((t) => t.isPlugin).toList();
        final userTools = tools.where((t) => !t.isPlugin).toList();

        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ScreenHeader(
                title: 'CUSTOM TOOLS',
                subtitle: 'Tools available to agents',
                actions: [
                  RetroButton(
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentSlate,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _ErrorBanner(
                  message: 'Failed to load tools: ${snapshot.error}',
                  onRetry: _reload,
                ),
              // ── Plugin Tools ─────────────────────────────────────────
              SectionFrame(
                title: 'Bundled Plugins',
                accentColor: accentTeal,
                minHeight: pluginTools.isEmpty ? 120.0 : 0.0,
                child: pluginTools.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Center(
                          child: _EmptyState(
                            icon: Icons.extension_outlined,
                            message: loading
                                ? 'Loading…'
                                : 'No plugins registered.',
                            hint:
                                'Add plugins to app/plugins.yaml to install bundled tools.',
                          ),
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final tool in pluginTools)
                              _ToolCard(
                                tool: tool,
                                client: _client,
                                onMappingSaved: _reload,
                              ),
                          ],
                        ),
                      ),
              ),
              const SizedBox(height: sp24),
              // ── User-Created Tools ────────────────────────────────────
              SectionFrame(
                title: 'User-Defined Tools',
                accentColor: accentSlate,
                minHeight: userTools.isEmpty ? 120.0 : 0.0,
                child: userTools.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Center(
                          child: _EmptyState(
                            icon: Icons.build_outlined,
                            message: loading
                                ? 'Loading…'
                                : 'No user-defined tools.',
                            hint: 'Upload or create a Python tool via the API.',
                          ),
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final tool in userTools)
                              _ToolCard(
                                tool: tool,
                                client: _client,
                                onMappingSaved: _reload,
                              ),
                          ],
                        ),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _ToolCard extends StatelessWidget {
  const _ToolCard({
    required this.tool,
    required this.client,
    required this.onMappingSaved,
  });

  final _CustomTool tool;
  final http.Client client;
  final VoidCallback onMappingSaved;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: sp12),
      child: RetroCard(
        child: Padding(
          padding: const EdgeInsets.all(sp16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Header row ──────────────────────────────────────
              Row(
                children: [
                  Expanded(
                    child: Text(
                      tool.name,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontFamily: fontBody,
                            letterSpacing: 1,
                          ),
                    ),
                  ),
                  if (tool.isPlugin)
                    const Padding(
                      padding: EdgeInsets.only(left: sp8),
                      child: RetroChip(
                        label: 'PLUGIN',
                        color: accentTeal,
                      ),
                    ),
                  Padding(
                    padding: const EdgeInsets.only(left: sp8),
                    child: RetroChip(
                      label: tool.isEnabled ? 'ENABLED' : 'DISABLED',
                      color: tool.isEnabled ? accentSlate : textMuted,
                    ),
                  ),
                ],
              ),
              // ── Description ─────────────────────────────────────
              if (tool.description.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Text(
                  tool.description,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: textMuted,
                    height: 1.5,
                  ),
                ),
              ],
              // ── Tags ────────────────────────────────────────────
              if (tool.tags.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Wrap(
                  spacing: sp4,
                  runSpacing: sp4,
                  children: [
                    for (final tag in tool.tags)
                      RetroChip(
                        label: tag,
                        color: accentAmber,
                        textColor: textPrimary,
                      ),
                  ],
                ),
              ],
              // ── Params count + env vars ──────────────────────────
              const SizedBox(height: sp8),
              Row(
                children: [
                  _MetaItem(
                    icon: Icons.input_outlined,
                    label:
                        '${(tool.parametersSchema['properties'] as Map?)?.length ?? 0} params',
                  ),
                  if (tool.envConfig.isNotEmpty) ...[
                    const SizedBox(width: sp12),
                    _MetaItem(
                      icon: Icons.key_outlined,
                      label: '${tool.envConfig.length} env var(s)',
                    ),
                  ],
                  if (tool.isPlugin) ...[
                    const SizedBox(width: sp12),
                    const _MetaItem(
                      icon: Icons.lock_outline,
                      label: 'read-only',
                    ),
                  ],
                ],
              ),
              // ── MAP TOKENS button — only shown when env vars exist ───────
              if (tool.envConfig.isNotEmpty) ...[
                const SizedBox(height: sp12),
                Align(
                  alignment: Alignment.centerRight,
                  child: RetroButton(
                    label: 'MAP TOKENS',
                    icon: Icons.key_outlined,
                    color: accentAmber,
                    textColor: textPrimary,
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _TokenMappingDialog(
                        tool: tool,
                        client: client,
                        onSaved: onMappingSaved,
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _TokenMappingDialog — modal for assigning tokens to env vars
// ---------------------------------------------------------------------------
class _TokenMappingDialog extends StatefulWidget {
  const _TokenMappingDialog({
    required this.tool,
    required this.client,
    required this.onSaved,
  });
  final _CustomTool tool;
  final http.Client client;
  final VoidCallback onSaved;

  @override
  State<_TokenMappingDialog> createState() => _TokenMappingDialogState();
}

class _TokenMappingDialogState extends State<_TokenMappingDialog> {
  _EnvMapping? _mapping;
  Object? _error;
  bool _loading = true;
  bool _saving = false;
  // env_var → selected token name (or null for unset)
  final Map<String, String?> _selections = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final m = await _fetchEnvMapping(widget.client, widget.tool.id);
      if (!mounted) return;
      setState(() {
        _mapping = m;
        _loading = false;
        // Initialise selections from current state
        for (final e in m.envVars) {
          _selections[e.envVar] = e.currentToken;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final payload = <String, String>{
        for (final e in (_mapping?.envVars ?? []))
          e.envVar: _selections[e.envVar] ?? '',
      };
      await _saveEnvMapping(widget.client, widget.tool.id, payload);
      if (!mounted) return;
      widget.onSaved();
      Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Save failed: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: const BorderSide(color: accentAmber, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 540, minWidth: 320),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                children: [
                  const Icon(Icons.key_outlined, color: accentAmber, size: 20),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: Text(
                      'MAP TOKENS — ${widget.tool.name}',
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: 14,
                        color: accentAmber,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: textMuted, size: 18),
                    onPressed: () => Navigator.of(context).pop(),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
                ],
              ),
              const SizedBox(height: sp4),
              const Text(
                'Assign a stored token to each required credential.',
                style: TextStyle(
                  fontFamily: fontBody,
                  fontSize: 12,
                  color: textMuted,
                ),
              ),
              const SizedBox(height: sp16),
              // Body
              if (_loading)
                const Center(
                  child: Padding(
                    padding: EdgeInsets.symmetric(vertical: sp24),
                    child: CircularProgressIndicator(color: accentAmber),
                  ),
                )
              else if (_error != null)
                Text(
                  'Error: $_error',
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: Colors.redAccent,
                  ),
                )
              else if (_mapping != null && _mapping!.envVars.isEmpty)
                const Text(
                  'This tool has no credential requirements.',
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: textMuted,
                  ),
                )
              else if (_mapping != null)
                ..._mapping!.envVars.map(
                  (entry) => _EnvVarRow(
                    entry: entry,
                    availableTokens: _mapping!.availableTokens,
                    selectedToken: _selections[entry.envVar],
                    onChanged: (val) =>
                        setState(() => _selections[entry.envVar] = val),
                  ),
                ),
              const SizedBox(height: sp24),
              // Actions
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'CANCEL',
                    onPressed: () => Navigator.of(context).pop(),
                    color: accentSlate,
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: _saving ? 'SAVING…' : 'SAVE',
                    onPressed:
                        (_saving || _loading || _error != null) ? null : _save,
                    color: accentAmber,
                    textColor: textPrimary,
                    icon: _saving ? null : Icons.check,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _EnvVarRow — a single env-var → token dropdown row
// ---------------------------------------------------------------------------
class _EnvVarRow extends StatelessWidget {
  const _EnvVarRow({
    required this.entry,
    required this.availableTokens,
    required this.selectedToken,
    required this.onChanged,
  });

  final _EnvVarEntry entry;
  final List<_TokenRef> availableTokens;
  final String? selectedToken;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    final maskedValue = availableTokens
        .cast<_TokenRef?>()
        .firstWhere((t) => t?.name == selectedToken, orElse: () => null)
        ?.maskedValue;

    return Padding(
      padding: const EdgeInsets.only(bottom: sp12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            entry.envVar,
            style: const TextStyle(
              fontFamily: fontBody,
              fontSize: 12,
              color: textMuted,
              letterSpacing: 0.8,
            ),
          ),
          const SizedBox(height: sp4),
          Container(
            decoration: BoxDecoration(
              border: Border.all(color: accentAmber.withAlpha(80)),
              borderRadius: BorderRadius.circular(2),
            ),
            padding: const EdgeInsets.symmetric(horizontal: sp8),
            child: DropdownButton<String>(
              value: selectedToken,
              isExpanded: true,
              underline: const SizedBox(),
              dropdownColor: cardBg,
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 12,
                color: textPrimary,
              ),
              hint: const Text(
                '— not mapped —',
                style: TextStyle(
                  fontFamily: fontBody,
                  fontSize: 12,
                  color: textMuted,
                ),
              ),
              items: [
                const DropdownMenuItem<String>(
                  value: null,
                  child: Text(
                    '— not mapped —',
                    style: TextStyle(
                      fontFamily: fontBody,
                      fontSize: 12,
                      color: textMuted,
                    ),
                  ),
                ),
                ...availableTokens.map(
                  (t) => DropdownMenuItem<String>(
                    value: t.name,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          t.name,
                          style: const TextStyle(
                            fontFamily: fontBody,
                            fontSize: 12,
                            color: textPrimary,
                          ),
                        ),
                        if (t.description.isNotEmpty)
                          Text(
                            t.description,
                            style: const TextStyle(
                              fontFamily: fontBody,
                              fontSize: 10,
                              color: textMuted,
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ],
              onChanged: onChanged,
            ),
          ),
          if (selectedToken != null) ...[
            const SizedBox(height: sp4),
            Text(
              'Value: ${maskedValue ?? '****'}',
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 10,
                color: textMuted,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _MetaItem extends StatelessWidget {
  const _MetaItem({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 12, color: textMuted),
        const SizedBox(width: 4),
        Text(
          label,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 11,
            color: textMuted,
            letterSpacing: 0.5,
          ),
        ),
      ],
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: sp16),
      child: RetroCard(
        child: Padding(
          padding: const EdgeInsets.all(sp16),
          child: Row(
            children: [
              const Icon(Icons.warning_amber_outlined,
                  color: accentAmber, size: 20),
              const SizedBox(width: sp8),
              Expanded(
                child: Text(
                  message,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: textMuted,
                  ),
                ),
              ),
              RetroButton(
                label: 'RETRY',
                onPressed: onRetry,
                color: accentAmber,
                textColor: textPrimary,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// SkillsScreen — model + full CRUD
// ---------------------------------------------------------------------------
class _Skill {
  const _Skill({
    required this.id,
    required this.name,
    required this.description,
    required this.instructions,
    required this.tags,
  });

  final String id;
  final String name;
  final String description;
  final String instructions;
  final List<String> tags;

  factory _Skill.fromJson(Map<String, dynamic> j) => _Skill(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? '',
    description: j['description']?.toString() ?? '',
    instructions: j['instructions']?.toString() ?? '',
    tags: (j['tags'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList(),
  );
}

Future<List<_Skill>> _fetchSkills(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/skills'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load skills (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_Skill.fromJson)
      .toList();
}

class SkillsScreen extends StatefulWidget {
  const SkillsScreen({super.key});

  @override
  State<SkillsScreen> createState() => _SkillsScreenState();
}

class _SkillsScreenState extends State<SkillsScreen> {
  final _client = http.Client();
  late Future<List<_Skill>> _skillsFuture;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _skillsFuture = _fetchSkills(_client);
    });
  }

  Future<void> _deleteSkill(String id) async {
    final response = await _client.delete(AppLinks.apiUri('/skills/$id'));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Delete failed (${response.statusCode})');
    }
  }

  void _confirmDelete(BuildContext context, _Skill skill) {
    final messenger = ScaffoldMessenger.of(context);
    showDialog<bool>(
      context: context,
      builder: (_) => _ConfirmDeleteDialog(
        name: skill.name,
        accentColor: accentLavender,
      ),
    ).then((confirmed) async {
      if (confirmed != true) return;
      try {
        await _deleteSkill(skill.id);
        if (!mounted) return;
        _reload();
      } catch (e) {
        if (!mounted) return;
        messenger.showSnackBar(
          SnackBar(
            content: Text('Delete failed: $e'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    });
  }

  void _showForm({_Skill? existing}) {
    showDialog<bool>(
      context: context,
      builder: (_) => _SkillDialog(client: _client, existing: existing),
    ).then((saved) {
      if (saved == true) _reload();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_Skill>>(
      future: _skillsFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final skills = snapshot.data ?? [];
        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ScreenHeader(
                title: 'SKILLS',
                subtitle: 'Reusable skill modules',
                actions: [
                  RetroButton(
                    label: 'EXPORT',
                    onPressed: () => showExportDialog(
                      context,
                      apiPath: '/skills/export',
                      resourceLabel: 'SKILLS',
                    ),
                    icon: Icons.download_outlined,
                    color: accentLavender,
                  ),
                  RetroButton(
                    label: 'IMPORT',
                    onPressed: () => showImportDialog(
                      context,
                      apiPath: '/skills/import',
                      resourceLabel: 'SKILLS',
                    ),
                    icon: Icons.upload_outlined,
                    color: accentLavender,
                  ),
                  RetroButton(
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentSlate,
                  ),
                  RetroButton(
                    label: 'NEW SKILL',
                    onPressed: () => _showForm(),
                    icon: Icons.bolt,
                    color: accentLavender,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _ErrorBanner(
                  message: 'Failed to load skills: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Installed Skills',
                accentColor: accentLavender,
                minHeight: skills.isEmpty ? 280.0 : 0.0,
                child: skills.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Center(
                          child: _EmptyState(
                            icon: Icons.bolt_outlined,
                            message:
                                loading ? 'Loading…' : 'No skills installed.',
                          ),
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final skill in skills)
                              _SkillCard(
                                skill: skill,
                                onEdit: () => _showForm(existing: skill),
                                onDelete: () =>
                                    _confirmDelete(context, skill),
                              ),
                          ],
                        ),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _SkillCard extends StatelessWidget {
  const _SkillCard({
    required this.skill,
    required this.onEdit,
    required this.onDelete,
  });

  final _Skill skill;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: sp12),
      child: RetroCard(
        child: Padding(
          padding: const EdgeInsets.all(sp16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                skill.name,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontFamily: fontBody,
                  letterSpacing: 1,
                ),
              ),
              if (skill.description.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Text(
                  skill.description,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: textMuted,
                    height: 1.5,
                  ),
                ),
              ],
              if (skill.tags.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Wrap(
                  spacing: sp4,
                  runSpacing: sp4,
                  children: [
                    for (final tag in skill.tags)
                      RetroChip(label: tag, color: accentLavender),
                  ],
                ),
              ],
              const SizedBox(height: sp12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'EDIT',
                    icon: Icons.edit_outlined,
                    color: accentSlate,
                    onPressed: onEdit,
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: 'DELETE',
                    icon: Icons.delete_outline,
                    color: accentPrimary,
                    onPressed: onDelete,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SkillDialog extends StatefulWidget {
  const _SkillDialog({required this.client, this.existing});
  final http.Client client;
  final _Skill? existing;

  @override
  State<_SkillDialog> createState() => _SkillDialogState();
}

class _SkillDialogState extends State<_SkillDialog> {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  final _instrCtrl = TextEditingController();
  final _tagsCtrl = TextEditingController();
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final s = widget.existing;
    if (s != null) {
      _nameCtrl.text = s.name;
      _descCtrl.text = s.description;
      _instrCtrl.text = s.instructions;
      _tagsCtrl.text = s.tags.join(', ');
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _descCtrl.dispose();
    _instrCtrl.dispose();
    _tagsCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    try {
      final body = jsonEncode({
        'name': _nameCtrl.text.trim(),
        if (_descCtrl.text.trim().isNotEmpty)
          'description': _descCtrl.text.trim(),
        'instructions': _instrCtrl.text.trim(),
        'tags': _tagsCtrl.text
            .split(',')
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty)
            .toList(),
      });
      final http.Response response;
      if (widget.existing != null) {
        response = await widget.client.put(
          AppLinks.apiUri('/skills/${widget.existing!.id}'),
          headers: {'Content-Type': 'application/json'},
          body: body,
        );
      } else {
        response = await widget.client.post(
          AppLinks.apiUri('/skills'),
          headers: {'Content-Type': 'application/json'},
          body: body,
        );
      }
      if (!mounted) return;
      if (response.statusCode >= 200 && response.statusCode < 300) {
        Navigator.of(context).pop(true);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(_extractDetail(response.body)),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Save failed: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: const BorderSide(color: accentLavender, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560, minWidth: 320),
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _DialogHeader(
                    title: widget.existing != null ? 'EDIT SKILL' : 'NEW SKILL',
                    color: accentLavender,
                    icon: Icons.bolt_outlined,
                    onClose: () => Navigator.of(context).pop(false),
                  ),
                  const SizedBox(height: sp16),
                  _DialogField(
                    label: 'NAME',
                    child: TextFormField(
                      controller: _nameCtrl,
                      style: _kDialogInputStyle,
                      decoration: _dialogInputDeco('Skill name'),
                      validator: (v) => (v == null || v.trim().isEmpty)
                          ? 'Name is required'
                          : null,
                    ),
                  ),
                  const SizedBox(height: sp12),
                  _DialogField(
                    label: 'DESCRIPTION (optional)',
                    child: TextFormField(
                      controller: _descCtrl,
                      style: _kDialogInputStyle,
                      decoration: _dialogInputDeco('Brief description'),
                    ),
                  ),
                  const SizedBox(height: sp12),
                  _DialogField(
                    label: 'INSTRUCTIONS',
                    child: TextFormField(
                      controller: _instrCtrl,
                      style: _kDialogInputStyle,
                      decoration:
                          _dialogInputDeco('Skill prompt / instructions…'),
                      maxLines: 5,
                      validator: (v) => (v == null || v.trim().isEmpty)
                          ? 'Instructions are required'
                          : null,
                    ),
                  ),
                  const SizedBox(height: sp12),
                  _DialogField(
                    label: 'TAGS (comma-separated)',
                    child: TextFormField(
                      controller: _tagsCtrl,
                      style: _kDialogInputStyle,
                      decoration: _dialogInputDeco('e.g. writing, analysis'),
                    ),
                  ),
                  const SizedBox(height: sp24),
                  _DialogActions(
                    saving: _saving,
                    onCancel: () => Navigator.of(context).pop(false),
                    onSave: _saving ? null : _save,
                    saveColor: accentLavender,
                    saveTextColor: cardBg,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// KnowledgeScreen — two-tab live CRUD: Knowledge Sources + Knowledge Items
// ---------------------------------------------------------------------------

// ── Data models ──────────────────────────────────────────────────────────────

class _KnowledgeSource {
  const _KnowledgeSource({
    required this.id,
    required this.name,
    required this.description,
    required this.sourceType,
    required this.tags,
  });

  final String id;
  final String name;
  final String description;
  final String sourceType;
  final List<String> tags;

  factory _KnowledgeSource.fromJson(Map<String, dynamic> j) => _KnowledgeSource(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? '',
    description: j['description']?.toString() ?? '',
    sourceType: j['source_type']?.toString() ?? 'text',
    tags:
        (j['tags'] as List<dynamic>? ?? []).map((t) => t.toString()).toList(),
  );
}

class _KnowledgeItem {
  const _KnowledgeItem({
    required this.id,
    required this.title,
    this.contentPreview,
    this.sourceId,
    required this.tags,
  });

  final String id;
  final String title;
  final String? contentPreview;
  final String? sourceId;
  final List<String> tags;

  factory _KnowledgeItem.fromJson(Map<String, dynamic> j) => _KnowledgeItem(
    id: j['id']?.toString() ?? '',
    title: j['title']?.toString() ?? '',
    contentPreview: j['content_preview']?.toString(),
    sourceId: j['source_id']?.toString(),
    tags:
        (j['tags'] as List<dynamic>? ?? []).map((t) => t.toString()).toList(),
  );
}

// ── API helpers ──────────────────────────────────────────────────────────────

Future<List<_KnowledgeSource>> _fetchKnowledgeSources(
  http.Client client,
) async {
  final response = await client.get(AppLinks.apiUri('/knowledge-sources'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception(
      'Failed to load knowledge sources (${response.statusCode})',
    );
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_KnowledgeSource.fromJson)
      .toList();
}

Future<List<_KnowledgeItem>> _fetchKnowledgeItems(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/knowledge-items'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception(
      'Failed to load knowledge items (${response.statusCode})',
    );
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_KnowledgeItem.fromJson)
      .toList();
}

// ── Main screen ──────────────────────────────────────────────────────────────

class KnowledgeScreen extends StatefulWidget {
  const KnowledgeScreen({super.key});

  @override
  State<KnowledgeScreen> createState() => _KnowledgeScreenState();
}

class _KnowledgeScreenState extends State<KnowledgeScreen> {
  final _client = http.Client();
  late Future<List<_KnowledgeSource>> _sourcesFuture;
  late Future<List<_KnowledgeItem>> _itemsFuture;

  @override
  void initState() {
    super.initState();
    _reloadSources();
    _reloadItems();
  }

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  void _reloadSources() =>
      setState(() => _sourcesFuture = _fetchKnowledgeSources(_client));

  void _reloadItems() =>
      setState(() => _itemsFuture = _fetchKnowledgeItems(_client));

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ── Page header ────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.fromLTRB(sp24, sp24, sp24, 0),
            child: _ScreenHeader(
              title: 'KNOWLEDGE',
              subtitle: 'Knowledge bases and document stores',
            ),
          ),
          const SizedBox(height: sp16),
          // ── Tab bar ────────────────────────────────────────────────
          ColoredBox(
            color: cardBg,
            child: TabBar(
              labelStyle: const TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeCaption,
                letterSpacing: letterSpacingLabel,
              ),
              unselectedLabelStyle: const TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeCaption,
                letterSpacing: letterSpacingLabel,
              ),
              labelColor: accentTeal,
              unselectedLabelColor: textMuted,
              indicatorColor: accentTeal,
              indicatorWeight: borderWidth,
              tabs: const [Tab(text: 'SOURCES'), Tab(text: 'ITEMS')],
            ),
          ),
          const Divider(height: 0, color: borderColor),
          // ── Tab views (each handles its own scrolling) ─────────────
          Expanded(
            child: TabBarView(
              children: [
                _SourcesTabView(
                  client: _client,
                  sourcesFuture: _sourcesFuture,
                  onReload: _reloadSources,
                ),
                _ItemsTabView(
                  client: _client,
                  itemsFuture: _itemsFuture,
                  onReload: _reloadItems,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Sources tab ───────────────────────────────────────────────────────────────

class _SourcesTabView extends StatelessWidget {
  const _SourcesTabView({
    required this.client,
    required this.sourcesFuture,
    required this.onReload,
  });

  final http.Client client;
  final Future<List<_KnowledgeSource>> sourcesFuture;
  final VoidCallback onReload;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_KnowledgeSource>>(
      future: sourcesFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final sources = snapshot.data ?? [];

        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Section header row
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      'KNOWLEDGE SOURCES',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: fontSizeBody,
                        color: textPrimary,
                        letterSpacing: letterSpacingLabel,
                      ),
                    ),
                  ),
                  RetroButton(
                    label: 'ADD SOURCE',
                    icon: Icons.add,
                    color: accentTeal,
                    onPressed: () => showDialog<bool>(
                      context: context,
                      builder: (_) =>
                          _KnowledgeSourceDialog(client: client),
                    ).then((added) {
                      if (added == true) onReload();
                    }),
                  ),
                ],
              ),
              const SizedBox(height: sp16),
              if (snapshot.hasError)
                _ErrorBanner(
                  message: 'Failed to load sources: ${snapshot.error}',
                  onRetry: onReload,
                ),
              if (loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: sp48),
                  child: Center(
                    child: CircularProgressIndicator(color: accentTeal),
                  ),
                )
              else if (sources.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: sp48),
                  child: Center(
                    child: _EmptyState(
                      icon: Icons.library_books_outlined,
                      message: 'No knowledge sources configured.',
                      hint: 'Add a source to get started.',
                    ),
                  ),
                )
              else
                for (final source in sources)
                  Padding(
                    padding: const EdgeInsets.only(bottom: sp12),
                    child: _KnowledgeSourceCard(
                      source: source,
                      client: client,
                      onChanged: onReload,
                    ),
                  ),
            ],
          ),
        );
      },
    );
  }
}

// ── Source card ───────────────────────────────────────────────────────────────

class _KnowledgeSourceCard extends StatelessWidget {
  const _KnowledgeSourceCard({
    required this.source,
    required this.client,
    required this.onChanged,
  });

  final _KnowledgeSource source;
  final http.Client client;
  final VoidCallback onChanged;

  Color _typeColor(String type) {
    switch (type) {
      case 'url':
        return accentTeal;
      case 'file':
        return accentAmber;
      case 'git':
        return accentLavender;
      case 'database':
        return accentPrimary;
      default:
        return accentSlate;
    }
  }

  Future<void> _test(BuildContext context) async {
    try {
      final response = await client.post(
        AppLinks.apiUri('/knowledge-sources/${source.id}/test'),
        headers: {'Content-Type': 'application/json'},
      );
      if (!context.mounted) return;
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final ok = body['success'] == true;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            ok
                ? 'Test passed ✓'
                : 'Test failed: ${body['error'] ?? 'Unknown error'}',
            style: const TextStyle(fontFamily: fontBody, fontSize: 12),
          ),
          backgroundColor: ok ? accentTeal : Colors.red.shade700,
        ),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Test error: $e',
            style: const TextStyle(fontFamily: fontBody, fontSize: 12),
          ),
          backgroundColor: Colors.red.shade700,
        ),
      );
    }
  }

  Future<void> _delete(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: cardBg,
        title: const Text(
          'DELETE SOURCE',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: 13,
            color: textPrimary,
          ),
        ),
        content: Text(
          'Delete "${source.name}"? This cannot be undone.',
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 12,
            color: textMuted,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text(
              'CANCEL',
              style: TextStyle(fontFamily: fontBody, fontSize: 11),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text(
              'DELETE',
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: 11,
                color: accentPrimary,
              ),
            ),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    try {
      final response = await client.delete(
        AppLinks.apiUri('/knowledge-sources/${source.id}'),
      );
      if (response.statusCode == 204 ||
          (response.statusCode >= 200 && response.statusCode < 300)) {
        onChanged();
      } else {
        if (!context.mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Delete failed (${response.statusCode})'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Delete error: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return RetroCard(
      child: Padding(
        padding: const EdgeInsets.all(sp16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Name + type chip
            Row(
              children: [
                Expanded(
                  child: Text(
                    source.name,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontFamily: fontBody,
                      letterSpacing: 1,
                    ),
                  ),
                ),
                const SizedBox(width: sp8),
                RetroChip(
                  label: source.sourceType,
                  color: _typeColor(source.sourceType),
                ),
              ],
            ),
            // Description
            if (source.description.isNotEmpty) ...[
              const SizedBox(height: sp8),
              Text(
                source.description,
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: 12,
                  color: textMuted,
                  height: 1.5,
                ),
              ),
            ],
            // Tags
            if (source.tags.isNotEmpty) ...[
              const SizedBox(height: sp8),
              Wrap(
                spacing: sp4,
                runSpacing: sp4,
                children: [
                  for (final tag in source.tags)
                    RetroChip(
                      label: tag,
                      color: accentAmber,
                      textColor: textPrimary,
                    ),
                ],
              ),
            ],
            // Actions
            const SizedBox(height: sp12),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                RetroButton(
                  label: 'TEST',
                  icon: Icons.bolt_outlined,
                  color: accentSlate,
                  onPressed: () => _test(context),
                ),
                const SizedBox(width: sp8),
                RetroButton(
                  label: 'EDIT',
                  icon: Icons.edit_outlined,
                  color: accentTeal,
                  onPressed: () => showDialog<bool>(
                    context: context,
                    builder: (_) =>
                        _KnowledgeSourceDialog(client: client, existing: source),
                  ).then((saved) {
                    if (saved == true) onChanged();
                  }),
                ),
                const SizedBox(width: sp8),
                RetroButton(
                  label: 'DELETE',
                  icon: Icons.delete_outline,
                  color: accentPrimary,
                  onPressed: () => _delete(context),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ── Items tab ─────────────────────────────────────────────────────────────────

class _ItemsTabView extends StatelessWidget {
  const _ItemsTabView({
    required this.client,
    required this.itemsFuture,
    required this.onReload,
  });

  final http.Client client;
  final Future<List<_KnowledgeItem>> itemsFuture;
  final VoidCallback onReload;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_KnowledgeItem>>(
      future: itemsFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final items = snapshot.data ?? [];

        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Section header row
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      'KNOWLEDGE ITEMS',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: fontSizeBody,
                        color: textPrimary,
                        letterSpacing: letterSpacingLabel,
                      ),
                    ),
                  ),
                  RetroButton(
                    label: 'ADD ITEM',
                    icon: Icons.add,
                    color: accentAmber,
                    textColor: textPrimary,
                    onPressed: () => showDialog<bool>(
                      context: context,
                      builder: (_) => _KnowledgeItemDialog(client: client),
                    ).then((added) {
                      if (added == true) onReload();
                    }),
                  ),
                ],
              ),
              const SizedBox(height: sp16),
              if (snapshot.hasError)
                _ErrorBanner(
                  message: 'Failed to load items: ${snapshot.error}',
                  onRetry: onReload,
                ),
              if (loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: sp48),
                  child: Center(
                    child: CircularProgressIndicator(color: accentAmber),
                  ),
                )
              else if (items.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: sp48),
                  child: Center(
                    child: _EmptyState(
                      icon: Icons.article_outlined,
                      message: 'No knowledge items found.',
                      hint: 'Add items to populate your knowledge base.',
                    ),
                  ),
                )
              else
                for (final item in items)
                  Padding(
                    padding: const EdgeInsets.only(bottom: sp12),
                    child: _KnowledgeItemCard(
                      item: item,
                      client: client,
                      onChanged: onReload,
                    ),
                  ),
            ],
          ),
        );
      },
    );
  }
}

// ── Item card ─────────────────────────────────────────────────────────────────

class _KnowledgeItemCard extends StatelessWidget {
  const _KnowledgeItemCard({
    required this.item,
    required this.client,
    required this.onChanged,
  });

  final _KnowledgeItem item;
  final http.Client client;
  final VoidCallback onChanged;

  Future<void> _delete(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: cardBg,
        title: const Text(
          'DELETE ITEM',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: 13,
            color: textPrimary,
          ),
        ),
        content: Text(
          'Delete "${item.title}"? This cannot be undone.',
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 12,
            color: textMuted,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text(
              'CANCEL',
              style: TextStyle(fontFamily: fontBody, fontSize: 11),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text(
              'DELETE',
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: 11,
                color: accentPrimary,
              ),
            ),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    try {
      final response = await client.delete(
        AppLinks.apiUri('/knowledge-items/${item.id}'),
      );
      if (response.statusCode == 204 ||
          (response.statusCode >= 200 && response.statusCode < 300)) {
        onChanged();
      } else {
        if (!context.mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Delete failed (${response.statusCode})'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Delete error: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return RetroCard(
      child: Padding(
        padding: const EdgeInsets.all(sp16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Title
            Text(
              item.title,
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeBody,
                color: textPrimary,
                fontWeight: FontWeight.bold,
                letterSpacing: 0.5,
              ),
            ),
            // Content preview (max 2 lines)
            if ((item.contentPreview ?? '').isNotEmpty) ...[
              const SizedBox(height: sp8),
              Text(
                item.contentPreview!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: 12,
                  color: textMuted,
                  height: 1.5,
                ),
              ),
            ],
            // Source chip
            if (item.sourceId != null && item.sourceId!.isNotEmpty) ...[
              const SizedBox(height: sp8),
              RetroChip(
                label: 'src: ${item.sourceId!}',
                color: accentSlate,
              ),
            ],
            // Tags
            if (item.tags.isNotEmpty) ...[
              const SizedBox(height: sp8),
              Wrap(
                spacing: sp4,
                runSpacing: sp4,
                children: [
                  for (final tag in item.tags)
                    RetroChip(
                      label: tag,
                      color: accentAmber,
                      textColor: textPrimary,
                    ),
                ],
              ),
            ],
            // Delete button
            const SizedBox(height: sp12),
            Align(
              alignment: Alignment.centerRight,
              child: RetroButton(
                label: 'DELETE',
                icon: Icons.delete_outline,
                color: accentPrimary,
                onPressed: () => _delete(context),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Shared dialog helpers ─────────────────────────────────────────────────────

const _kFieldTextStyle = TextStyle(
  fontFamily: fontBody,
  fontSize: fontSizeBody,
  color: textPrimary,
);

InputDecoration _kFieldDecoration(String hint) => InputDecoration(
  hintText: hint,
  hintStyle: const TextStyle(
    fontFamily: fontBody,
    fontSize: fontSizeBody,
    color: textMuted,
  ),
  border: const OutlineInputBorder(
    borderRadius: BorderRadius.zero,
    borderSide: BorderSide(color: borderColor, width: 1),
  ),
  enabledBorder: const OutlineInputBorder(
    borderRadius: BorderRadius.zero,
    borderSide: BorderSide(color: borderColor, width: 1),
  ),
  focusedBorder: const OutlineInputBorder(
    borderRadius: BorderRadius.zero,
    borderSide: BorderSide(color: accentTeal, width: borderWidth),
  ),
  errorBorder: const OutlineInputBorder(
    borderRadius: BorderRadius.zero,
    borderSide: BorderSide(color: accentPrimary, width: borderWidth),
  ),
  focusedErrorBorder: const OutlineInputBorder(
    borderRadius: BorderRadius.zero,
    borderSide: BorderSide(color: accentPrimary, width: borderWidth),
  ),
  contentPadding: const EdgeInsets.symmetric(
    horizontal: sp12,
    vertical: sp8,
  ),
  isDense: true,
);

// ── Knowledge Source dialog (add / edit) ──────────────────────────────────────

class _KnowledgeSourceDialog extends StatefulWidget {
  const _KnowledgeSourceDialog({required this.client, this.existing});

  final http.Client client;
  final _KnowledgeSource? existing;

  @override
  State<_KnowledgeSourceDialog> createState() => _KnowledgeSourceDialogState();
}

class _KnowledgeSourceDialogState extends State<_KnowledgeSourceDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _nameCtrl;
  late final TextEditingController _descCtrl;
  late final TextEditingController _tagsCtrl;
  late String _sourceType;
  bool _saving = false;

  static const _sourceTypes = ['text', 'url', 'file', 'git', 'database'];

  @override
  void initState() {
    super.initState();
    final ex = widget.existing;
    _nameCtrl = TextEditingController(text: ex?.name ?? '');
    _descCtrl = TextEditingController(text: ex?.description ?? '');
    _tagsCtrl = TextEditingController(text: ex?.tags.join(', ') ?? '');
    _sourceType = ex?.sourceType ?? 'text';
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _descCtrl.dispose();
    _tagsCtrl.dispose();
    super.dispose();
  }

  List<String> get _parsedTags => _tagsCtrl.text
      .split(',')
      .map((t) => t.trim())
      .where((t) => t.isNotEmpty)
      .toList();

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      final payload = jsonEncode({
        'name': _nameCtrl.text.trim(),
        'description': _descCtrl.text.trim(),
        'source_type': _sourceType,
        'tags': _parsedTags,
      });
      final response = widget.existing == null
          ? await widget.client.post(
              AppLinks.apiUri('/knowledge-sources'),
              headers: {'Content-Type': 'application/json'},
              body: payload,
            )
          : await widget.client.put(
              AppLinks.apiUri('/knowledge-sources/${widget.existing!.id}'),
              headers: {'Content-Type': 'application/json'},
              body: payload,
            );
      if (!mounted) return;
      if (response.statusCode >= 200 && response.statusCode < 300) {
        Navigator.of(context).pop(true);
      } else {
        final decoded = jsonDecode(response.body);
        final detail =
            (decoded is Map) ? decoded['detail']?.toString() : null;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              detail ?? 'Save failed (${response.statusCode})',
            ),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.existing != null;
    return Dialog(
      backgroundColor: cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: const BorderSide(color: accentTeal, width: borderWidth),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520, minWidth: 320),
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                Row(
                  children: [
                    const Icon(
                      Icons.library_books_outlined,
                      color: accentTeal,
                      size: 20,
                    ),
                    const SizedBox(width: sp8),
                    Expanded(
                      child: Text(
                        isEdit ? 'EDIT SOURCE' : 'ADD SOURCE',
                        style: const TextStyle(
                          fontFamily: fontBody,
                          fontSize: 14,
                          color: accentTeal,
                          letterSpacing: 1.5,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(
                        Icons.close,
                        color: textMuted,
                        size: 18,
                      ),
                      onPressed: () => Navigator.of(context).pop(false),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                    ),
                  ],
                ),
                const SizedBox(height: sp16),
                // Name
                _DialogField(
                  label: 'NAME *',
                  child: TextFormField(
                    controller: _nameCtrl,
                    style: _kFieldTextStyle,
                    decoration: _kFieldDecoration('Source name'),
                    validator: (v) =>
                        (v == null || v.trim().isEmpty)
                            ? 'Name is required'
                            : null,
                  ),
                ),
                const SizedBox(height: sp12),
                // Description
                _DialogField(
                  label: 'DESCRIPTION',
                  child: TextFormField(
                    controller: _descCtrl,
                    style: _kFieldTextStyle,
                    decoration: _kFieldDecoration('Optional description'),
                    maxLines: 3,
                  ),
                ),
                const SizedBox(height: sp12),
                // Source type
                _DialogField(
                  label: 'SOURCE TYPE',
                  child: Container(
                    decoration: const BoxDecoration(
                      border: Border.fromBorderSide(
                        BorderSide(color: borderColor, width: 1),
                      ),
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: sp8),
                    child: DropdownButton<String>(
                      value: _sourceType,
                      isExpanded: true,
                      underline: const SizedBox(),
                      dropdownColor: cardBg,
                      style: _kFieldTextStyle,
                      items: _sourceTypes
                          .map(
                            (t) => DropdownMenuItem(
                              value: t,
                              child: Text(t, style: _kFieldTextStyle),
                            ),
                          )
                          .toList(),
                      onChanged: (v) {
                        if (v != null) setState(() => _sourceType = v);
                      },
                    ),
                  ),
                ),
                const SizedBox(height: sp12),
                // Tags
                _DialogField(
                  label: 'TAGS',
                  child: TextFormField(
                    controller: _tagsCtrl,
                    style: _kFieldTextStyle,
                    decoration: _kFieldDecoration('Comma-separated tags'),
                  ),
                ),
                const SizedBox(height: sp24),
                // Actions
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    RetroButton(
                      label: 'CANCEL',
                      onPressed: () => Navigator.of(context).pop(false),
                      color: accentSlate,
                    ),
                    const SizedBox(width: sp8),
                    RetroButton(
                      label: _saving
                          ? 'SAVING…'
                          : (isEdit ? 'SAVE' : 'CREATE'),
                      onPressed: _saving ? null : _save,
                      color: accentTeal,
                      icon: _saving ? null : Icons.check,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Knowledge Item dialog (add only) ─────────────────────────────────────────

class _KnowledgeItemDialog extends StatefulWidget {
  const _KnowledgeItemDialog({required this.client});

  final http.Client client;

  @override
  State<_KnowledgeItemDialog> createState() => _KnowledgeItemDialogState();
}

class _KnowledgeItemDialogState extends State<_KnowledgeItemDialog> {
  final _formKey = GlobalKey<FormState>();
  final _titleCtrl = TextEditingController();
  final _contentCtrl = TextEditingController();
  final _sourceIdCtrl = TextEditingController();
  final _tagsCtrl = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _titleCtrl.dispose();
    _contentCtrl.dispose();
    _sourceIdCtrl.dispose();
    _tagsCtrl.dispose();
    super.dispose();
  }

  List<String> get _parsedTags => _tagsCtrl.text
      .split(',')
      .map((t) => t.trim())
      .where((t) => t.isNotEmpty)
      .toList();

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      final sourceId = _sourceIdCtrl.text.trim();
      final payload = <String, dynamic>{
        'title': _titleCtrl.text.trim(),
        'content': _contentCtrl.text.trim(),
        if (sourceId.isNotEmpty) 'source_id': sourceId,
        'tags': _parsedTags,
      };
      final response = await widget.client.post(
        AppLinks.apiUri('/knowledge-items'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(payload),
      );
      if (!mounted) return;
      if (response.statusCode >= 200 && response.statusCode < 300) {
        Navigator.of(context).pop(true);
      } else {
        final decoded = jsonDecode(response.body);
        final detail =
            (decoded is Map) ? decoded['detail']?.toString() : null;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              detail ?? 'Save failed (${response.statusCode})',
            ),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: const BorderSide(color: accentAmber, width: borderWidth),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520, minWidth: 320),
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                Row(
                  children: [
                    const Icon(
                      Icons.article_outlined,
                      color: accentAmber,
                      size: 20,
                    ),
                    const SizedBox(width: sp8),
                    const Expanded(
                      child: Text(
                        'ADD KNOWLEDGE ITEM',
                        style: TextStyle(
                          fontFamily: fontBody,
                          fontSize: 14,
                          color: accentAmber,
                          letterSpacing: 1.5,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(
                        Icons.close,
                        color: textMuted,
                        size: 18,
                      ),
                      onPressed: () => Navigator.of(context).pop(false),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                    ),
                  ],
                ),
                const SizedBox(height: sp16),
                // Title
                _DialogField(
                  label: 'TITLE *',
                  child: TextFormField(
                    controller: _titleCtrl,
                    style: _kFieldTextStyle,
                    decoration: _kFieldDecoration('Item title'),
                    validator: (v) =>
                        (v == null || v.trim().isEmpty)
                            ? 'Title is required'
                            : null,
                  ),
                ),
                const SizedBox(height: sp12),
                // Content
                _DialogField(
                  label: 'CONTENT *',
                  child: TextFormField(
                    controller: _contentCtrl,
                    style: _kFieldTextStyle,
                    decoration: _kFieldDecoration('Item content'),
                    maxLines: 5,
                    validator: (v) =>
                        (v == null || v.trim().isEmpty)
                            ? 'Content is required'
                            : null,
                  ),
                ),
                const SizedBox(height: sp12),
                // Source ID
                _DialogField(
                  label: 'SOURCE ID',
                  child: TextFormField(
                    controller: _sourceIdCtrl,
                    style: _kFieldTextStyle,
                    decoration: _kFieldDecoration(
                      'Knowledge source ID (optional)',
                    ),
                  ),
                ),
                const SizedBox(height: sp12),
                // Tags
                _DialogField(
                  label: 'TAGS',
                  child: TextFormField(
                    controller: _tagsCtrl,
                    style: _kFieldTextStyle,
                    decoration: _kFieldDecoration('Comma-separated tags'),
                  ),
                ),
                const SizedBox(height: sp24),
                // Actions
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    RetroButton(
                      label: 'CANCEL',
                      onPressed: () => Navigator.of(context).pop(false),
                      color: accentSlate,
                    ),
                    const SizedBox(width: sp8),
                    RetroButton(
                      label: _saving ? 'SAVING…' : 'CREATE',
                      onPressed: _saving ? null : _save,
                      color: accentAmber,
                      textColor: textPrimary,
                      icon: _saving ? null : Icons.check,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// GuardrailsScreen — model + full CRUD
// ---------------------------------------------------------------------------
class _Guardrail {
  const _Guardrail({
    required this.id,
    required this.name,
    required this.description,
    required this.guardrailType,
    required this.tags,
    required this.enabled,
  });

  final String id;
  final String name;
  final String description;
  final String guardrailType;
  final List<String> tags;
  final bool enabled;

  factory _Guardrail.fromJson(Map<String, dynamic> j) => _Guardrail(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? '',
    description: j['description']?.toString() ?? '',
    guardrailType: j['guardrail_type']?.toString() ?? 'prompt',
    tags: (j['tags'] as List<dynamic>? ?? [])
        .map((e) => e.toString())
        .toList(),
    enabled: j['enabled'] == true,
  );
}

Future<List<_Guardrail>> _fetchGuardrails(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/guardrails'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load guardrails (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_Guardrail.fromJson)
      .toList();
}

class GuardrailsScreen extends StatefulWidget {
  const GuardrailsScreen({super.key});

  @override
  State<GuardrailsScreen> createState() => _GuardrailsScreenState();
}

class _GuardrailsScreenState extends State<GuardrailsScreen> {
  final _client = http.Client();
  late Future<List<_Guardrail>> _guardrailsFuture;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  void _reload() {
    setState(() {
      _guardrailsFuture = _fetchGuardrails(_client);
    });
  }

  Future<void> _toggleEnabled(
    BuildContext context,
    _Guardrail guardrail,
    bool enabled,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final response = await _client.put(
        AppLinks.apiUri('/guardrails/${guardrail.id}'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'enabled': enabled}),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (!mounted) return;
        _reload();
      } else {
        if (!mounted) return;
        messenger.showSnackBar(
          SnackBar(
            content: Text('Update failed (${response.statusCode})'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      messenger.showSnackBar(
        SnackBar(
          content: Text('Update failed: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    }
  }

  Future<void> _deleteGuardrail(String id) async {
    final response = await _client.delete(AppLinks.apiUri('/guardrails/$id'));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('Delete failed (${response.statusCode})');
    }
  }

  void _confirmDelete(BuildContext context, _Guardrail guardrail) {
    final messenger = ScaffoldMessenger.of(context);
    showDialog<bool>(
      context: context,
      builder: (_) => _ConfirmDeleteDialog(
        name: guardrail.name,
        accentColor: accentPrimary,
      ),
    ).then((confirmed) async {
      if (confirmed != true) return;
      try {
        await _deleteGuardrail(guardrail.id);
        if (!mounted) return;
        _reload();
      } catch (e) {
        if (!mounted) return;
        messenger.showSnackBar(
          SnackBar(
            content: Text('Delete failed: $e'),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    });
  }

  void _showForm({_Guardrail? existing}) {
    showDialog<bool>(
      context: context,
      builder: (_) => _GuardrailDialog(client: _client, existing: existing),
    ).then((saved) {
      if (saved == true) _reload();
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_Guardrail>>(
      future: _guardrailsFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final guardrails = snapshot.data ?? [];
        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ScreenHeader(
                title: 'GUARDRAILS',
                subtitle: 'Safety policies and content filters',
                actions: [
                  RetroButton(
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentSlate,
                  ),
                  RetroButton(
                    label: 'ADD RULE',
                    onPressed: () => _showForm(),
                    icon: Icons.add,
                    color: accentPrimary,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _ErrorBanner(
                  message: 'Failed to load guardrails: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Active Guardrails',
                accentColor: accentPrimary,
                minHeight: guardrails.isEmpty ? 280.0 : 0.0,
                child: guardrails.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Center(
                          child: _EmptyState(
                            icon: Icons.shield_outlined,
                            message: loading
                                ? 'Loading…'
                                : 'No guardrails configured.',
                          ),
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final gr in guardrails)
                              _GuardrailCard(
                                guardrail: gr,
                                onEdit: () => _showForm(existing: gr),
                                onDelete: () => _confirmDelete(context, gr),
                                onToggle: (enabled) =>
                                    _toggleEnabled(context, gr, enabled),
                              ),
                          ],
                        ),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _GuardrailCard extends StatelessWidget {
  const _GuardrailCard({
    required this.guardrail,
    required this.onEdit,
    required this.onDelete,
    required this.onToggle,
  });

  final _Guardrail guardrail;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final ValueChanged<bool> onToggle;

  Color get _typeColor {
    switch (guardrail.guardrailType) {
      case 'prompt':
        return accentAmber;
      case 'request':
        return accentTeal;
      case 'output':
        return accentLavender;
      default:
        return textMuted;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: sp12),
      child: RetroCard(
        child: Padding(
          padding: const EdgeInsets.all(sp16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      guardrail.name,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontFamily: fontBody,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  RetroChip(
                    label: guardrail.guardrailType,
                    color: _typeColor,
                    textColor: guardrail.guardrailType == 'prompt'
                        ? textPrimary
                        : cardBg,
                  ),
                  const SizedBox(width: sp8),
                  Switch(
                    value: guardrail.enabled,
                    onChanged: onToggle,
                    activeThumbColor: accentTeal,
                    inactiveThumbColor: textMuted,
                  ),
                ],
              ),
              if (guardrail.description.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Text(
                  guardrail.description,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: textMuted,
                    height: 1.5,
                  ),
                ),
              ],
              if (guardrail.tags.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Wrap(
                  spacing: sp4,
                  runSpacing: sp4,
                  children: [
                    for (final tag in guardrail.tags)
                      RetroChip(label: tag, color: accentSlate),
                  ],
                ),
              ],
              const SizedBox(height: sp12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'EDIT',
                    icon: Icons.edit_outlined,
                    color: accentSlate,
                    onPressed: onEdit,
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: 'DELETE',
                    icon: Icons.delete_outline,
                    color: accentPrimary,
                    onPressed: onDelete,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GuardrailDialog extends StatefulWidget {
  const _GuardrailDialog({required this.client, this.existing});
  final http.Client client;
  final _Guardrail? existing;

  @override
  State<_GuardrailDialog> createState() => _GuardrailDialogState();
}

class _GuardrailDialogState extends State<_GuardrailDialog> {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  final _tagsCtrl = TextEditingController();
  // shared pattern fields (prompt + output)
  final _forbiddenCtrl = TextEditingController();
  final _requiredCtrl = TextEditingController();
  final _maxLenCtrl = TextEditingController();
  // request-only
  final _jsonSchemaCtrl = TextEditingController();
  // output-only booleans
  bool _piiDetection = false;
  bool _mustBeValidJson = false;
  // common
  String _guardrailType = 'prompt';
  bool _enabled = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final g = widget.existing;
    if (g != null) {
      _nameCtrl.text = g.name;
      _descCtrl.text = g.description;
      _guardrailType = g.guardrailType;
      _enabled = g.enabled;
      _tagsCtrl.text = g.tags.join(', ');
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _descCtrl.dispose();
    _tagsCtrl.dispose();
    _forbiddenCtrl.dispose();
    _requiredCtrl.dispose();
    _maxLenCtrl.dispose();
    _jsonSchemaCtrl.dispose();
    super.dispose();
  }

  /// Returns the type-specific config map, or null if validation fails.
  Map<String, dynamic>? _buildTypeConfig() {
    if (_guardrailType == 'prompt' || _guardrailType == 'output') {
      final config = <String, dynamic>{
        'forbidden_patterns': _forbiddenCtrl.text
            .split('\n')
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty)
            .toList(),
        'required_patterns': _requiredCtrl.text
            .split('\n')
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty)
            .toList(),
      };
      final maxLenStr = _maxLenCtrl.text.trim();
      if (maxLenStr.isNotEmpty) {
        config['max_length'] = int.tryParse(maxLenStr);
      }
      if (_guardrailType == 'output') {
        config['pii_detection'] = _piiDetection;
        config['must_be_valid_json'] = _mustBeValidJson;
      }
      return config;
    }
    if (_guardrailType == 'request') {
      final raw = _jsonSchemaCtrl.text.trim();
      if (raw.isEmpty) return {};
      try {
        return {'json_schema': jsonDecode(raw)};
      } catch (_) {
        return null; // signals invalid JSON
      }
    }
    return {};
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final typeConfig = _buildTypeConfig();
    if (typeConfig == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('JSON schema is not valid JSON.'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final configKey = '${_guardrailType}_config';
      final body = jsonEncode({
        'name': _nameCtrl.text.trim(),
        if (_descCtrl.text.trim().isNotEmpty)
          'description': _descCtrl.text.trim(),
        'guardrail_type': _guardrailType,
        'tags': _tagsCtrl.text
            .split(',')
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty)
            .toList(),
        'enabled': _enabled,
        configKey: typeConfig,
      });
      final http.Response response;
      if (widget.existing != null) {
        response = await widget.client.put(
          AppLinks.apiUri('/guardrails/${widget.existing!.id}'),
          headers: {'Content-Type': 'application/json'},
          body: body,
        );
      } else {
        response = await widget.client.post(
          AppLinks.apiUri('/guardrails'),
          headers: {'Content-Type': 'application/json'},
          body: body,
        );
      }
      if (!mounted) return;
      if (response.statusCode >= 200 && response.statusCode < 300) {
        Navigator.of(context).pop(true);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(_extractDetail(response.body)),
            backgroundColor: Colors.red.shade700,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Save failed: $e'),
          backgroundColor: Colors.red.shade700,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _buildTypeSection() {
    if (_guardrailType == 'prompt' || _guardrailType == 'output') {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _DialogField(
            label: 'FORBIDDEN PATTERNS (one per line)',
            child: TextFormField(
              controller: _forbiddenCtrl,
              style: _kDialogInputStyle,
              decoration: _dialogInputDeco('pattern1\npattern2'),
              maxLines: 3,
            ),
          ),
          const SizedBox(height: sp12),
          _DialogField(
            label: 'REQUIRED PATTERNS (one per line)',
            child: TextFormField(
              controller: _requiredCtrl,
              style: _kDialogInputStyle,
              decoration: _dialogInputDeco('required_term'),
              maxLines: 3,
            ),
          ),
          const SizedBox(height: sp12),
          _DialogField(
            label: 'MAX LENGTH (optional)',
            child: TextFormField(
              controller: _maxLenCtrl,
              style: _kDialogInputStyle,
              decoration: _dialogInputDeco('e.g. 4096'),
              keyboardType: TextInputType.number,
            ),
          ),
          if (_guardrailType == 'output') ...[
            const SizedBox(height: sp12),
            Row(
              children: [
                Checkbox(
                  value: _piiDetection,
                  onChanged: (v) =>
                      setState(() => _piiDetection = v ?? false),
                  activeColor: accentTeal,
                  side: const BorderSide(color: textMuted),
                ),
                const Text(
                  'PII Detection',
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: textMuted,
                  ),
                ),
                const SizedBox(width: sp16),
                Checkbox(
                  value: _mustBeValidJson,
                  onChanged: (v) =>
                      setState(() => _mustBeValidJson = v ?? false),
                  activeColor: accentTeal,
                  side: const BorderSide(color: textMuted),
                ),
                const Text(
                  'Must be valid JSON',
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: textMuted,
                  ),
                ),
              ],
            ),
          ],
        ],
      );
    }
    if (_guardrailType == 'request') {
      return _DialogField(
        label: 'JSON SCHEMA',
        child: TextFormField(
          controller: _jsonSchemaCtrl,
          style: _kDialogInputStyle,
          decoration: _dialogInputDeco('{"type": "object", ...}'),
          maxLines: 6,
        ),
      );
    }
    return const SizedBox.shrink();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: const BorderSide(color: accentPrimary, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560, minWidth: 320),
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _DialogHeader(
                    title: widget.existing != null
                        ? 'EDIT GUARDRAIL'
                        : 'ADD GUARDRAIL',
                    color: accentPrimary,
                    icon: Icons.shield_outlined,
                    onClose: () => Navigator.of(context).pop(false),
                  ),
                  const SizedBox(height: sp16),
                  _DialogField(
                    label: 'NAME',
                    child: TextFormField(
                      controller: _nameCtrl,
                      style: _kDialogInputStyle,
                      decoration: _dialogInputDeco('Guardrail name'),
                      validator: (v) => (v == null || v.trim().isEmpty)
                          ? 'Name is required'
                          : null,
                    ),
                  ),
                  const SizedBox(height: sp12),
                  _DialogField(
                    label: 'DESCRIPTION (optional)',
                    child: TextFormField(
                      controller: _descCtrl,
                      style: _kDialogInputStyle,
                      decoration: _dialogInputDeco('Brief description'),
                    ),
                  ),
                  const SizedBox(height: sp12),
                  _DialogField(
                    label: 'TYPE',
                    child: _RetroDropdown<String>(
                      value: _guardrailType,
                      items: const ['prompt', 'request', 'output'],
                      onChanged: (v) {
                        if (v == null) return;
                        setState(() => _guardrailType = v);
                      },
                    ),
                  ),
                  const SizedBox(height: sp12),
                  _DialogField(
                    label: 'TAGS (comma-separated)',
                    child: TextFormField(
                      controller: _tagsCtrl,
                      style: _kDialogInputStyle,
                      decoration: _dialogInputDeco('e.g. safety, content'),
                    ),
                  ),
                  const SizedBox(height: sp12),
                  Row(
                    children: [
                      Switch(
                        value: _enabled,
                        onChanged: (v) => setState(() => _enabled = v),
                        activeThumbColor: accentTeal,
                        inactiveThumbColor: textMuted,
                      ),
                      const SizedBox(width: sp8),
                      Text(
                        _enabled ? 'ENABLED' : 'DISABLED',
                        style: TextStyle(
                          fontFamily: fontBody,
                          fontSize: 11,
                          color: _enabled ? accentTeal : textMuted,
                          letterSpacing: 0.8,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: sp12),
                  _buildTypeSection(),
                  const SizedBox(height: sp24),
                  _DialogActions(
                    saving: _saving,
                    onCancel: () => Navigator.of(context).pop(false),
                    onSave: _saving ? null : _save,
                    saveColor: accentPrimary,
                    saveTextColor: cardBg,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Shared dialog / form helpers
// ---------------------------------------------------------------------------

/// Immutable input text style reused by all dialogs.
const _kDialogInputStyle = TextStyle(
  fontFamily: fontBody,
  fontSize: 12,
  color: textPrimary,
);

/// Returns an [InputDecoration] used in all dialogs.
InputDecoration _dialogInputDeco(String hint) => InputDecoration(
  hintText: hint,
  hintStyle: const TextStyle(fontFamily: fontBody, fontSize: 12, color: textMuted),
  contentPadding: const EdgeInsets.symmetric(horizontal: sp8, vertical: sp8),
  enabledBorder: OutlineInputBorder(
    borderRadius: BorderRadius.zero,
    borderSide: BorderSide(color: accentSlate.withAlpha(120), width: 1),
  ),
  focusedBorder: const OutlineInputBorder(
    borderRadius: BorderRadius.zero,
    borderSide: BorderSide(color: accentTeal, width: 1.5),
  ),
  errorBorder: const OutlineInputBorder(
    borderRadius: BorderRadius.zero,
    borderSide: BorderSide(color: accentPrimary, width: 1),
  ),
  focusedErrorBorder: const OutlineInputBorder(
    borderRadius: BorderRadius.zero,
    borderSide: BorderSide(color: accentPrimary, width: 1.5),
  ),
  filled: true,
  fillColor: pageBg,
  errorStyle: const TextStyle(fontFamily: fontBody, fontSize: 10),
);

/// Tries to extract a `detail` field from an error JSON body.
String _extractDetail(String body) {
  try {
    final decoded = jsonDecode(body);
    if (decoded is Map && decoded['detail'] != null) {
      return decoded['detail'].toString();
    }
  } catch (_) {}
  return 'Request failed';
}

// ---------------------------------------------------------------------------
// _DialogHeader — icon + title + close button row
// ---------------------------------------------------------------------------
class _DialogHeader extends StatelessWidget {
  const _DialogHeader({
    required this.title,
    required this.color,
    required this.icon,
    required this.onClose,
  });

  final String title;
  final Color color;
  final IconData icon;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: color, size: 20),
        const SizedBox(width: sp8),
        Expanded(
          child: Text(
            title,
            style: TextStyle(
              fontFamily: fontBody,
              fontSize: 14,
              color: color,
              letterSpacing: 1.5,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        IconButton(
          icon: const Icon(Icons.close, color: textMuted, size: 18),
          onPressed: onClose,
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _DialogField — labelled wrapper for form inputs
// ---------------------------------------------------------------------------
class _DialogField extends StatelessWidget {
  const _DialogField({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 10,
            color: textMuted,
            letterSpacing: 1,
          ),
        ),
        const SizedBox(height: sp4),
        child,
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _DialogActions — cancel + save button row
// ---------------------------------------------------------------------------
class _DialogActions extends StatelessWidget {
  const _DialogActions({
    required this.saving,
    required this.onCancel,
    required this.onSave,
    required this.saveColor,
    required this.saveTextColor,
  });

  final bool saving;
  final VoidCallback onCancel;
  final VoidCallback? onSave;
  final Color saveColor;
  final Color saveTextColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        RetroButton(
          label: 'CANCEL',
          onPressed: onCancel,
          color: accentSlate,
        ),
        const SizedBox(width: sp8),
        RetroButton(
          label: saving ? 'SAVING…' : 'SAVE',
          onPressed: onSave,
          color: saveColor,
          textColor: saveTextColor,
          icon: saving ? null : Icons.check,
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _RetroDropdown — themed DropdownButton wrapper
// ---------------------------------------------------------------------------
class _RetroDropdown<T> extends StatelessWidget {
  const _RetroDropdown({
    required this.value,
    required this.items,
    required this.onChanged,
  });

  final T value;
  final List<T> items;
  final ValueChanged<T?> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: pageBg,
        border: Border.all(color: accentSlate.withAlpha(120), width: 1),
      ),
      padding: const EdgeInsets.symmetric(horizontal: sp8),
      child: DropdownButton<T>(
        value: value,
        isExpanded: true,
        underline: const SizedBox(),
        dropdownColor: cardBg,
        style: _kDialogInputStyle,
        items: items
            .map(
              (item) => DropdownMenuItem<T>(
                value: item,
                child: Text(item.toString(), style: _kDialogInputStyle),
              ),
            )
            .toList(),
        onChanged: onChanged,
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _ConfirmDeleteDialog — reusable destructive-action confirmation modal
// ---------------------------------------------------------------------------
class _ConfirmDeleteDialog extends StatelessWidget {
  const _ConfirmDeleteDialog({
    required this.name,
    required this.accentColor,
  });

  final String name;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: BorderSide(color: accentColor, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400, minWidth: 280),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'DELETE',
                style: TextStyle(
                  fontFamily: fontBody,
                  fontSize: 14,
                  color: accentColor,
                  letterSpacing: 1.5,
                ),
              ),
              const SizedBox(height: sp12),
              Text(
                'Delete "$name"? This cannot be undone.',
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: 12,
                  color: textMuted,
                ),
              ),
              const SizedBox(height: sp24),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'CANCEL',
                    onPressed: () => Navigator.of(context).pop(false),
                    color: accentSlate,
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: 'DELETE',
                    icon: Icons.delete_outline,
                    onPressed: () => Navigator.of(context).pop(true),
                    color: accentPrimary,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// Shared helpers used across feature screens --------------------------------

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
        if (actions.isNotEmpty)
          Flexible(
            child: Wrap(
              spacing: sp8,
              runSpacing: sp4,
              alignment: WrapAlignment.end,
              children: actions,
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
              letterSpacing: 0.5,
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
