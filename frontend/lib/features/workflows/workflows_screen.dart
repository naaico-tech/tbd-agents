import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../../core/config/app_links.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/export_import_dialog.dart';
import '../../core/widgets/retro_card.dart';

// ---------------------------------------------------------------------------
// TokensScreen — API key / credential management (live CRUD)
// ---------------------------------------------------------------------------
class TokensScreen extends StatefulWidget {
  const TokensScreen({super.key});

  @override
  State<TokensScreen> createState() => _TokensScreenState();
}

class _TokensScreenState extends State<TokensScreen> {
  http.Client? _ownedClient;
  late Future<List<_TokenRef>> _tokensFuture;

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
      _tokensFuture = _fetchTokens(_client);
    });
  }

  Future<void> _confirmDelete(String id, String name) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => _ConfirmDeleteDialog(
        message: "Delete token '$name'?",
        accentColor: accentAmber,
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      final response = await _client.delete(AppLinks.apiUri('/tokens/$id'));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ?? 'Delete failed (${response.statusCode})',
        );
      }
      if (!mounted) return;
      _reload();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Token '$name' deleted."),
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
    return FutureBuilder<List<_TokenRef>>(
      future: _tokensFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final tokens = snapshot.data ?? [];

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
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentSlate,
                  ),
                  RetroButton(
                    label: 'ADD TOKEN',
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _TokenDialog(
                        client: _client,
                        onSaved: _reload,
                        isEdit: false,
                      ),
                    ),
                    icon: Icons.add,
                    color: accentAmber,
                    textColor: textPrimary,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _WfErrorBanner(
                  message: 'Failed to load tokens: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Stored Credentials',
                accentColor: accentAmber,
                minHeight: tokens.isEmpty ? 300 : 0,
                child: tokens.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: _EmptyState(
                          icon: Icons.key_outlined,
                          message:
                              loading ? 'Loading…' : 'No tokens stored.',
                          hint: 'Tokens are encrypted at rest.',
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final t in tokens)
                              _TokenCard(
                                token: t,
                                client: _client,
                                onSaved: _reload,
                                onDelete: () =>
                                    _confirmDelete(t.id, t.name),
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

// ---------------------------------------------------------------------------
// ProvidersScreen — LLM / embedding provider configuration (live CRUD)
// ---------------------------------------------------------------------------
class ProvidersScreen extends StatefulWidget {
  const ProvidersScreen({super.key});

  @override
  State<ProvidersScreen> createState() => _ProvidersScreenState();
}

class _ProvidersScreenState extends State<ProvidersScreen> {
  http.Client? _ownedClient;
  late Future<List<_Provider>> _providersFuture;

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
      _providersFuture = _fetchProviders(_client);
    });
  }

  Future<void> _confirmDelete(String id, String name) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => _ConfirmDeleteDialog(
        message: "Delete provider '$name'?",
        accentColor: accentSlate,
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      final response =
          await _client.delete(AppLinks.apiUri('/providers/$id'));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ?? 'Delete failed (${response.statusCode})',
        );
      }
      if (!mounted) return;
      _reload();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Provider '$name' deleted."),
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
    return FutureBuilder<List<_Provider>>(
      future: _providersFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final providers = snapshot.data ?? [];

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
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentTeal,
                  ),
                  RetroButton(
                    label: 'ADD PROVIDER',
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _ProviderDialog(
                        client: _client,
                        onSaved: _reload,
                      ),
                    ),
                    icon: Icons.add,
                    color: accentSlate,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _WfErrorBanner(
                  message: 'Failed to load providers: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Configured Providers',
                accentColor: accentSlate,
                minHeight: providers.isEmpty ? 300 : 0,
                child: providers.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: _EmptyState(
                          icon: Icons.business_outlined,
                          message: loading
                              ? 'Loading…'
                              : 'No providers configured.',
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final p in providers)
                              _ProviderCard(
                                provider: p,
                                client: _client,
                                onSaved: _reload,
                                onDelete: () =>
                                    _confirmDelete(p.id, p.name),
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

// ---------------------------------------------------------------------------
// Workflow data models
// ---------------------------------------------------------------------------

class _Workflow {
  _Workflow({
    required this.id,
    required this.title,
    required this.agentId,
    required this.model,
    required this.status,
    required this.maxTurns,
    required this.credentialOverrides,
    this.skillIds = const [],
    this.skillTags = const [],
    this.guardrailIds = const [],
    this.guardrailTags = const [],
    this.outputFormat = 'json',
    this.infiniteSession = true,
    this.bypassMemory = false,
    this.autoMemory = false,
    this.reasoningEffort,
    this.repoUrl,
    this.repoBranch,
    this.repoTokenName,
    this.webhookUrl,
  });

  final String id;
  final String title;
  final String agentId;
  final String model;
  final String status;
  final int maxTurns;
  final Map<String, String> credentialOverrides;
  final List<String> skillIds;
  final List<String> skillTags;
  final List<String> guardrailIds;
  final List<String> guardrailTags;
  final String outputFormat;
  final bool infiniteSession;
  final bool bypassMemory;
  final bool autoMemory;
  final String? reasoningEffort;
  final String? repoUrl;
  final String? repoBranch;
  final String? repoTokenName;
  final String? webhookUrl;

  factory _Workflow.fromJson(Map<String, dynamic> json) => _Workflow(
    id: json['id']?.toString() ?? '',
    title: json['title']?.toString() ?? '',
    agentId: json['agent_id']?.toString() ?? '',
    model: json['model']?.toString() ?? '',
    status: json['status']?.toString() ?? 'idle',
    maxTurns: (json['max_turns'] as num?)?.toInt() ?? 10,
    credentialOverrides: Map<String, String>.from(
      (json['credential_overrides'] as Map<String, dynamic>?) ?? {},
    ),
    skillIds: (json['skill_ids'] as List<dynamic>? ?? []).map((e) => e.toString()).toList(),
    skillTags: (json['skill_tags'] as List<dynamic>? ?? []).map((e) => e.toString()).toList(),
    guardrailIds: (json['guardrail_ids'] as List<dynamic>? ?? []).map((e) => e.toString()).toList(),
    guardrailTags: (json['guardrail_tags'] as List<dynamic>? ?? []).map((e) => e.toString()).toList(),
    outputFormat: json['output_format']?.toString() ?? 'json',
    infiniteSession: json['infinite_session'] as bool? ?? true,
    bypassMemory: json['bypass_memory'] as bool? ?? false,
    autoMemory: json['auto_memory'] as bool? ?? false,
    reasoningEffort: json['reasoning_effort']?.toString(),
    repoUrl: json['repo_url']?.toString(),
    repoBranch: json['repo_branch']?.toString(),
    repoTokenName: json['repo_token_name']?.toString(),
    webhookUrl: json['webhook_url']?.toString(),
  );
}

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

class _CredOverride {
  _CredOverride({required this.envVar, required this.tokenName});
  String envVar;
  String tokenName;
}

// ---------------------------------------------------------------------------
// Workflow API helpers
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

Future<List<_TokenRef>> _fetchTokens(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/tokens'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load tokens (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_TokenRef.fromJson)
      .toList();
}

Future<List<String>> _fetchEnvVarKeys(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/custom-tools'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load custom tools (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) return [];
  final keys = <String>{};
  for (final tool in decoded.whereType<Map<String, dynamic>>()) {
    final envConfig = tool['env_config'] as Map<String, dynamic>?;
    if (envConfig != null) keys.addAll(envConfig.keys);
  }
  return keys.toList()..sort();
}

// ---------------------------------------------------------------------------
// Provider data model
// ---------------------------------------------------------------------------

class _Provider {
  const _Provider({
    required this.id,
    required this.name,
    required this.providerType,
    required this.apiKeyTokenName,
    this.baseUrl,
    this.description = '',
  });

  final String id;
  final String name;
  final String providerType;
  final String apiKeyTokenName;
  final String? baseUrl;
  final String description;

  factory _Provider.fromJson(Map<String, dynamic> j) => _Provider(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? '',
    providerType: j['provider_type']?.toString() ?? '',
    apiKeyTokenName: j['api_key_token_name']?.toString() ?? '',
    baseUrl: j['base_url']?.toString(),
    description: j['description']?.toString() ?? '',
  );
}

// ---------------------------------------------------------------------------
// Provider API helpers
// ---------------------------------------------------------------------------

Future<List<_Provider>> _fetchProviders(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/providers'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load providers (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_Provider.fromJson)
      .toList();
}

// ---------------------------------------------------------------------------
// WorkflowsScreen — workflow definitions list (live data)
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
                  RetroButton(
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentSlate,
                  ),
                  RetroButton(
                    label: '+ NEW WORKFLOW',
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _WorkflowDialog(
                        client: _client,
                        onSaved: _reload,
                      ),
                    ),
                    icon: Icons.add,
                    color: accentLavender,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _WfErrorBanner(
                  message: 'Failed to load workflows: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Workflow Definitions',
                accentColor: accentLavender,
                minHeight: workflows.isEmpty ? 300 : 0,
                child: workflows.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: _EmptyState(
                          icon: Icons.account_tree_outlined,
                          message: loading
                              ? 'Loading…'
                              : 'No workflows defined.',
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final wf in workflows)
                              _WorkflowCard(
                                workflow: wf,
                                client: _client,
                                onSaved: _reload,
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

// ---------------------------------------------------------------------------
// _WorkflowCard — displays a single workflow with credential override action
// ---------------------------------------------------------------------------

class _WorkflowCard extends StatelessWidget {
  const _WorkflowCard({
    required this.workflow,
    required this.client,
    required this.onSaved,
  });

  final _Workflow workflow;
  final http.Client client;
  final VoidCallback onSaved;

  String get _displayTitle =>
      workflow.title.isNotEmpty ? workflow.title : workflow.agentId;

  Color get _statusColor {
    switch (workflow.status.toLowerCase()) {
      case 'active':
      case 'running':
        return accentTeal;
      case 'error':
      case 'failed':
        return accentPrimary;
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
              // ── Header row ──────────────────────────────────────────────
              Row(
                children: [
                  Expanded(
                    child: Text(
                      _displayTitle,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontFamily: fontBody,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  RetroChip(
                    label: workflow.status.toUpperCase(),
                    color: _statusColor,
                    textColor: cardBg,
                  ),
                  if (workflow.credentialOverrides.isNotEmpty) ...[
                    const SizedBox(width: sp8),
                    const RetroChip(
                      label: 'CREDENTIALS',
                      color: accentAmber,
                      textColor: textPrimary,
                    ),
                  ],
                ],
              ),
              // ── Meta row ────────────────────────────────────────────────
              const SizedBox(height: sp8),
              Wrap(
                spacing: sp12,
                runSpacing: sp4,
                children: [
                  if (workflow.model.isNotEmpty)
                    _WfMetaItem(
                      icon: Icons.model_training_outlined,
                      label: workflow.model,
                    ),
                  _WfMetaItem(
                    icon: Icons.repeat_outlined,
                    label: 'max ${workflow.maxTurns} turns',
                  ),
                  if (workflow.credentialOverrides.isNotEmpty)
                    _WfMetaItem(
                      icon: Icons.key_outlined,
                      label:
                          '${workflow.credentialOverrides.length} override(s)',
                    ),
                  if (workflow.webhookUrl != null && workflow.webhookUrl!.isNotEmpty)
                    const _WfMetaItem(
                      icon: Icons.http_outlined,
                      label: 'Webhook configured',
                    ),
                ],
              ),
              // ── Action buttons ─────────────────────────────────────────
              const SizedBox(height: sp12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'EDIT',
                    icon: Icons.edit_outlined,
                    color: accentLavender,
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _WorkflowDialog(
                        client: client,
                        onSaved: onSaved,
                        existing: workflow,
                      ),
                    ),
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: 'CREDENTIALS',
                    icon: Icons.key_outlined,
                    color: accentAmber,
                    textColor: textPrimary,
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _CredentialOverridesDialog(
                        workflow: workflow,
                        client: client,
                        onSaved: onSaved,
                      ),
                    ),
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
// _CredentialOverridesDialog — manage credential overrides for a workflow
// ---------------------------------------------------------------------------

class _CredentialOverridesDialog extends StatefulWidget {
  const _CredentialOverridesDialog({
    required this.workflow,
    required this.client,
    required this.onSaved,
  });

  final _Workflow workflow;
  final http.Client client;
  final VoidCallback onSaved;

  @override
  State<_CredentialOverridesDialog> createState() =>
      _CredentialOverridesDialogState();
}

class _CredentialOverridesDialogState
    extends State<_CredentialOverridesDialog> {
  List<_TokenRef> _tokens = [];
  List<String> _envVarKeys = [];
  List<_CredOverride> _overrides = [];
  bool _loading = true;
  bool _saving = false;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final tokens = await _fetchTokens(widget.client);
      final envVarKeys = await _fetchEnvVarKeys(widget.client);
      if (!mounted) return;
      // Merge known keys with any existing override keys (in case tool removed)
      final allKeys = <String>{
        ...envVarKeys,
        ...widget.workflow.credentialOverrides.keys,
      }.toList()
        ..sort();
      setState(() {
        _tokens = tokens;
        _envVarKeys = allKeys;
        _overrides = widget.workflow.credentialOverrides.entries
            .map((e) => _CredOverride(envVar: e.key, tokenName: e.value))
            .toList();
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  void _addOverride() {
    final firstEnvVar = _envVarKeys.isNotEmpty ? _envVarKeys.first : '';
    final firstToken = _tokens.isNotEmpty ? _tokens.first.name : '';
    setState(() {
      _overrides.add(
        _CredOverride(envVar: firstEnvVar, tokenName: firstToken),
      );
    });
  }

  void _removeOverride(int index) {
    setState(() => _overrides.removeAt(index));
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final response = await widget.client.put(
        AppLinks.apiUri('/workflows/${widget.workflow.id}'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'credential_overrides': {
            for (final o in _overrides) o.envVar: o.tokenName,
          },
        }),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ?? 'Save failed (${response.statusCode})',
        );
      }
      if (!mounted) return;
      widget.onSaved();
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Credential overrides saved.'),
          backgroundColor: accentTeal,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Save failed: $e'),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final displayTitle = widget.workflow.title.isNotEmpty
        ? widget.workflow.title
        : widget.workflow.agentId;

    return Dialog(
      backgroundColor: cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: const BorderSide(color: accentAmber, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 580, minWidth: 340),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header ────────────────────────────────────────────────────
              Row(
                children: [
                  const Icon(
                    Icons.key_outlined,
                    color: accentAmber,
                    size: 20,
                  ),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: Text(
                      'MAP CREDENTIALS — $displayTitle',
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
                    icon: const Icon(Icons.close, color: textMuted, size: 18),
                    onPressed: () => Navigator.of(context).pop(),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
                ],
              ),
              const SizedBox(height: sp4),
              const Text(
                'Override which token each plugin credential uses for this workflow.',
                style: TextStyle(
                  fontFamily: fontBody,
                  fontSize: 11,
                  color: textMuted,
                ),
              ),
              const SizedBox(height: sp16),
              // Body ───────────────────────────────────────────────────────
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
              else ...[
                if (_overrides.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: sp12),
                    child: Text(
                      'No overrides configured. Add one below.',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: 12,
                        color: textMuted,
                      ),
                    ),
                  )
                else
                  ...List.generate(_overrides.length, (i) {
                    final override = _overrides[i];
                    return _OverrideRow(
                      credOverride: override,
                      envVarKeys: _envVarKeys,
                      tokens: _tokens,
                      onEnvVarChanged: (val) {
                        if (val != null) setState(() => override.envVar = val);
                      },
                      onTokenChanged: (val) {
                        if (val != null) {
                          setState(() => override.tokenName = val);
                        }
                      },
                      onRemove: () => _removeOverride(i),
                    );
                  }),
                const SizedBox(height: sp8),
                RetroButton(
                  label: '+ ADD OVERRIDE',
                  icon: Icons.add,
                  color: accentSlate,
                  onPressed: (_envVarKeys.isEmpty || _tokens.isEmpty)
                      ? null
                      : _addOverride,
                ),
              ],
              const SizedBox(height: sp24),
              // Actions ────────────────────────────────────────────────────
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
                    onPressed: (_saving || _loading || _error != null)
                        ? null
                        : _save,
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
// _OverrideRow — one env-var → token mapping row with remove button
// ---------------------------------------------------------------------------

class _OverrideRow extends StatelessWidget {
  const _OverrideRow({
    required this.credOverride,
    required this.envVarKeys,
    required this.tokens,
    required this.onEnvVarChanged,
    required this.onTokenChanged,
    required this.onRemove,
  });

  final _CredOverride credOverride;
  final List<String> envVarKeys;
  final List<_TokenRef> tokens;
  final ValueChanged<String?> onEnvVarChanged;
  final ValueChanged<String?> onTokenChanged;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    // Ensure current values are valid dropdown entries
    final effectiveEnvVar = envVarKeys.contains(credOverride.envVar)
        ? credOverride.envVar
        : (envVarKeys.isNotEmpty ? envVarKeys.first : null);
    final effectiveToken =
        tokens.any((t) => t.name == credOverride.tokenName)
            ? credOverride.tokenName
            : (tokens.isNotEmpty ? tokens.first.name : null);
    final maskedValue = tokens
        .cast<_TokenRef?>()
        .firstWhere(
          (t) => t?.name == credOverride.tokenName,
          orElse: () => null,
        )
        ?.maskedValue;

    return Padding(
      padding: const EdgeInsets.only(bottom: sp12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Env var dropdown ──────────────────────────────────────────
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'ENV VAR',
                  style: TextStyle(
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
                  padding: const EdgeInsets.symmetric(horizontal: sp8),
                  child: DropdownButton<String>(
                    value: effectiveEnvVar,
                    isExpanded: true,
                    underline: const SizedBox(),
                    dropdownColor: cardBg,
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: 11,
                      color: accentAmber,
                    ),
                    hint: Text(
                      credOverride.envVar.isNotEmpty
                          ? credOverride.envVar
                          : '— select env var —',
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: 11,
                        color: textMuted,
                      ),
                    ),
                    items: envVarKeys
                        .map(
                          (k) => DropdownMenuItem<String>(
                            value: k,
                            child: Text(
                              k,
                              style: const TextStyle(
                                fontFamily: fontBody,
                                fontSize: 11,
                                color: accentAmber,
                              ),
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: onEnvVarChanged,
                  ),
                ),
              ],
            ),
          ),
          // ── Arrow ──────────────────────────────────────────────────────
          const Padding(
            padding: EdgeInsets.only(top: 22, left: sp8, right: sp8),
            child: Text(
              '→',
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: 14,
                color: textMuted,
              ),
            ),
          ),
          // ── Token dropdown ────────────────────────────────────────────
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'TOKEN',
                  style: TextStyle(
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
                  padding: const EdgeInsets.symmetric(horizontal: sp8),
                  child: DropdownButton<String>(
                    value: effectiveToken,
                    isExpanded: true,
                    underline: const SizedBox(),
                    dropdownColor: cardBg,
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: 11,
                      color: textPrimary,
                    ),
                    hint: Text(
                      credOverride.tokenName.isNotEmpty
                          ? credOverride.tokenName
                          : '— select token —',
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: 11,
                        color: textMuted,
                      ),
                    ),
                    items: tokens
                        .map(
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
                                    fontSize: 11,
                                    color: textPrimary,
                                  ),
                                ),
                                if (t.maskedValue.isNotEmpty)
                                  Text(
                                    t.maskedValue,
                                    style: const TextStyle(
                                      fontFamily: fontBody,
                                      fontSize: 9,
                                      color: textMuted,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: onTokenChanged,
                  ),
                ),
                if (maskedValue != null && maskedValue.isNotEmpty) ...[
                  const SizedBox(height: sp4),
                  Text(
                    'Value: $maskedValue',
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: 10,
                      color: textMuted,
                    ),
                  ),
                ],
              ],
            ),
          ),
          // ── Remove button ─────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.only(top: 18, left: sp8),
            child: IconButton(
              icon: const Icon(Icons.close, color: textMuted, size: 16),
              onPressed: onRemove,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _Skill model + fetch helper
// ---------------------------------------------------------------------------
class _Skill {
  const _Skill({required this.id, required this.name});
  final String id;
  final String name;
  factory _Skill.fromJson(Map<String, dynamic> j) => _Skill(
    id: j['id']?.toString() ?? '', name: j['name']?.toString() ?? '');
}

Future<List<_Skill>> _fetchSkills(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/skills'));
  if (response.statusCode < 200 || response.statusCode >= 300) return [];
  final decoded = jsonDecode(response.body);
  if (decoded is! List) return [];
  return decoded.whereType<Map<String, dynamic>>().map(_Skill.fromJson).toList();
}

// ---------------------------------------------------------------------------
// _Guardrail model + fetch helper
// ---------------------------------------------------------------------------
class _Guardrail {
  const _Guardrail({required this.id, required this.name});
  final String id;
  final String name;
  factory _Guardrail.fromJson(Map<String, dynamic> j) => _Guardrail(
    id: j['id']?.toString() ?? '', name: j['name']?.toString() ?? '');
}

Future<List<_Guardrail>> _fetchGuardrails(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/guardrails'));
  if (response.statusCode < 200 || response.statusCode >= 300) return [];
  final decoded = jsonDecode(response.body);
  if (decoded is! List) return [];
  return decoded.whereType<Map<String, dynamic>>().map(_Guardrail.fromJson).toList();
}

// ---------------------------------------------------------------------------
// Agent option model (lightweight, for dropdown in _WorkflowDialog)
// ---------------------------------------------------------------------------

class _AgentOption {
  const _AgentOption({required this.id, required this.name});

  final String id;
  final String name;

  factory _AgentOption.fromJson(Map<String, dynamic> j) => _AgentOption(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? '',
  );
}

// ---------------------------------------------------------------------------
// _WorkflowDialog — create a new workflow
// ---------------------------------------------------------------------------

class _WorkflowDialog extends StatefulWidget {
  const _WorkflowDialog({
    required this.client,
    required this.onSaved,
    this.existing,
  });

  final http.Client client;
  final VoidCallback onSaved;
  final _Workflow? existing;

  @override
  State<_WorkflowDialog> createState() => _WorkflowDialogState();
}

class _WorkflowDialogState extends State<_WorkflowDialog> {
  late final TextEditingController _titleCtrl;
  late final TextEditingController _modelCtrl;
  late final TextEditingController _maxTurnsCtrl;
  bool _saving = false;

  bool get _isEdit => widget.existing != null;

  // Agent dropdown state
  late Future<List<_AgentOption>> _agentsFuture;
  String? _selectedAgentId;

  // New fields
  late List<String> _selectedSkillIds;
  late List<String> _selectedGuardrailIds;
  late String _outputFormat;
  late bool _isActive;
  late bool _infiniteSession;
  late bool _bypassMemory;
  late bool _autoMemory;
  late String? _reasoningEffort;
  final _skillTagsCtrl = TextEditingController();
  final _guardrailTagsCtrl = TextEditingController();
  final _repoUrlCtrl = TextEditingController();
  final _repoBranchCtrl = TextEditingController();
  final _repoTokenCtrl = TextEditingController();
  final _webhookUrlCtrl = TextEditingController();
  late Future<List<_Skill>> _skillsFuture;
  late Future<List<_Guardrail>> _wfGuardrailsFuture;

  // Credential overrides
  final List<_CredOverride> _credOverrides = [];
  List<_TokenRef> _credTokens = [];
  List<String> _credEnvVarKeys = [];

  @override
  void initState() {
    super.initState();
    final w = widget.existing;
    _titleCtrl = TextEditingController(text: w?.title ?? '');
    _modelCtrl = TextEditingController(text: w?.model ?? '');
    _maxTurnsCtrl = TextEditingController(text: (w?.maxTurns ?? 10).toString());
    _selectedAgentId = w?.agentId;
    _selectedSkillIds = List.from(w?.skillIds ?? []);
    _selectedGuardrailIds = List.from(w?.guardrailIds ?? []);
    _outputFormat = w?.outputFormat ?? 'json';
    _isActive = (w?.status ?? 'active').toLowerCase() == 'active';
    _infiniteSession = w?.infiniteSession ?? true;
    _bypassMemory = w?.bypassMemory ?? false;
    _autoMemory = w?.autoMemory ?? false;
    _reasoningEffort = w?.reasoningEffort;
    _skillTagsCtrl.text = (w?.skillTags ?? []).join(', ');
    _guardrailTagsCtrl.text = (w?.guardrailTags ?? []).join(', ');
    _repoUrlCtrl.text = w?.repoUrl ?? '';
    _repoBranchCtrl.text = w?.repoBranch ?? '';
    _repoTokenCtrl.text = w?.repoTokenName ?? '';
    _webhookUrlCtrl.text = w?.webhookUrl ?? '';
    // Pre-populate credential overrides from existing workflow
    if (w != null) {
      _credOverrides.addAll(
        w.credentialOverrides.entries.map(
          (e) => _CredOverride(envVar: e.key, tokenName: e.value),
        ),
      );
    }
    _agentsFuture = _fetchAgentOptions(widget.client);
    _skillsFuture = _fetchSkills(widget.client);
    _wfGuardrailsFuture = _fetchGuardrails(widget.client);
    _loadCredentialData();
  }

  Future<void> _loadCredentialData() async {
    try {
      final results = await Future.wait([
        _fetchTokens(widget.client),
        _fetchEnvVarKeys(widget.client),
      ]);
      if (!mounted) return;
      setState(() {
        _credTokens = results[0] as List<_TokenRef>;
        _credEnvVarKeys = results[1] as List<String>;
      });
    } catch (_) {
      // Best-effort; overrides section will show empty dropdowns
    }
  }

  Future<List<_AgentOption>> _fetchAgentOptions(http.Client client) async {
    final response = await client.get(AppLinks.apiUri('/agents'));
    if (response.statusCode < 200 || response.statusCode >= 300) return [];
    final decoded = jsonDecode(response.body);
    if (decoded is! List) return [];
    return decoded.whereType<Map<String, dynamic>>().map(_AgentOption.fromJson).toList();
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _modelCtrl.dispose();
    _maxTurnsCtrl.dispose();
    _skillTagsCtrl.dispose();
    _guardrailTagsCtrl.dispose();
    _repoUrlCtrl.dispose();
    _repoBranchCtrl.dispose();
    _repoTokenCtrl.dispose();
    _webhookUrlCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_selectedAgentId == null || _selectedAgentId!.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please select an agent.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final body = <String, dynamic>{
        'title': _titleCtrl.text.trim(),
        'agent_id': _selectedAgentId!,
        if (_modelCtrl.text.trim().isNotEmpty) 'model': _modelCtrl.text.trim(),
        'max_turns': int.tryParse(_maxTurnsCtrl.text.trim()) ?? 10,
        'credential_overrides': {
          for (final o in _credOverrides) o.envVar: o.tokenName,
        },
        'skill_ids': _selectedSkillIds,
        if (_skillTagsCtrl.text.trim().isNotEmpty)
          'skill_tags': _skillTagsCtrl.text.trim().split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
        'guardrail_ids': _selectedGuardrailIds,
        if (_guardrailTagsCtrl.text.trim().isNotEmpty)
          'guardrail_tags': _guardrailTagsCtrl.text.trim().split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
        'output_format': _outputFormat,
        'infinite_session': _infiniteSession,
        'bypass_memory': _bypassMemory,
        'auto_memory': _autoMemory,
        if (_isEdit) 'status': _isActive ? 'active' : 'inactive',
        if (_reasoningEffort != null) 'reasoning_effort': _reasoningEffort,
        if (_repoUrlCtrl.text.trim().isNotEmpty) 'repo_url': _repoUrlCtrl.text.trim(),
        if (_repoBranchCtrl.text.trim().isNotEmpty) 'repo_branch': _repoBranchCtrl.text.trim(),
        if (_repoTokenCtrl.text.trim().isNotEmpty) 'repo_token_name': _repoTokenCtrl.text.trim(),
        if (_webhookUrlCtrl.text.trim().isNotEmpty) 'webhook_url': _webhookUrlCtrl.text.trim(),
      };
      final response = _isEdit
          ? await widget.client.put(
              AppLinks.apiUri('/workflows/${widget.existing!.id}'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(body),
            )
          : await widget.client.post(
              AppLinks.apiUri('/workflows'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(body),
            );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ??
              '${_isEdit ? 'Update' : 'Create'} failed (${response.statusCode})',
        );
      }
      if (!mounted) return;
      widget.onSaved();
      Navigator.of(context).pop();
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
        side: const BorderSide(color: accentLavender, width: 1),
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
                      Icons.account_tree_outlined,
                      color: accentLavender,
                      size: 20,
                    ),
                    const SizedBox(width: sp8),
                    Expanded(
                      child: Text(
                        _isEdit ? 'EDIT WORKFLOW' : 'NEW WORKFLOW',
                        style: const TextStyle(
                          fontFamily: fontBody,
                          fontSize: 13,
                          color: accentLavender,
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
                const SizedBox(height: sp16),
                _WfDialogField(
                  label: 'TITLE',
                  controller: _titleCtrl,
                  hint: 'My workflow',
                ),
                const SizedBox(height: sp12),
                // Agent dropdown ──────────────────────────────────────────
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'AGENT *',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: 10,
                        color: accentLavender,
                        letterSpacing: 1.2,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: sp4),
                    FutureBuilder<List<_AgentOption>>(
                      future: _agentsFuture,
                      builder: (context, snap) {
                        final agents = snap.data ?? [];
                        return Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: sp12,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: pageBg,
                            border: Border.all(
                              color: accentLavender.withAlpha(80),
                            ),
                            borderRadius: BorderRadius.circular(2),
                          ),
                          child: DropdownButton<String?>(
                            value: _selectedAgentId,
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
                                  ? 'Loading agents…'
                                  : 'Select an agent',
                              style: const TextStyle(
                                fontFamily: fontBody,
                                fontSize: 12,
                                color: textMuted,
                              ),
                            ),
                            items: [
                              for (final a in agents)
                                DropdownMenuItem<String?>(
                                  value: a.id,
                                  child: Text(
                                    a.name,
                                    style: const TextStyle(
                                      fontFamily: fontBody,
                                      fontSize: 12,
                                      color: textPrimary,
                                    ),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                            ],
                            onChanged: (v) =>
                                setState(() => _selectedAgentId = v),
                          ),
                        );
                      },
                    ),
                  ],
                ),
                const SizedBox(height: sp12),
                _WfDialogField(
                  label: 'MODEL',
                  controller: _modelCtrl,
                  hint: 'gpt-4o (optional)',
                ),
                const SizedBox(height: sp12),
                _WfDialogField(
                  label: 'MAX TURNS',
                  controller: _maxTurnsCtrl,
                  hint: '10',
                  keyboardType: TextInputType.number,
                ),
                const SizedBox(height: sp12),
                // SKILLS ───────────────────────────────────────────────
                FutureBuilder<List<_Skill>>(
                  future: _skillsFuture,
                  builder: (context, snap) {
                    final items = (snap.data ?? []).map((s) => (id: s.id, name: s.name)).toList();
                    return _MultiSelectChipField(
                      label: 'SKILLS',
                      selected: _selectedSkillIds,
                      items: items,
                      accentColor: accentTeal,
                      loading: snap.connectionState == ConnectionState.waiting,
                      onChanged: (v) => setState(() => _selectedSkillIds = v),
                    );
                  },
                ),
                const SizedBox(height: sp12),
                // SKILL TAGS ───────────────────────────────────────────
                _WfDialogField(
                  label: 'SKILL TAGS (comma-separated)',
                  controller: _skillTagsCtrl,
                  hint: 'tag1, tag2',
                ),
                const SizedBox(height: sp12),
                // GUARDRAILS ───────────────────────────────────────────
                FutureBuilder<List<_Guardrail>>(
                  future: _wfGuardrailsFuture,
                  builder: (context, snap) {
                    final items = (snap.data ?? []).map((g) => (id: g.id, name: g.name)).toList();
                    return _MultiSelectChipField(
                      label: 'GUARDRAILS',
                      selected: _selectedGuardrailIds,
                      items: items,
                      accentColor: accentSlate,
                      loading: snap.connectionState == ConnectionState.waiting,
                      onChanged: (v) => setState(() => _selectedGuardrailIds = v),
                    );
                  },
                ),
                const SizedBox(height: sp12),
                // GUARDRAIL TAGS ───────────────────────────────────────
                _WfDialogField(
                  label: 'GUARDRAIL TAGS (comma-separated)',
                  controller: _guardrailTagsCtrl,
                  hint: 'tag1, tag2',
                ),
                const SizedBox(height: sp12),
                // OUTPUT FORMAT ────────────────────────────────────────
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('OUTPUT FORMAT', style: TextStyle(fontFamily: fontBody, fontSize: 10, color: accentLavender, letterSpacing: 1.2, fontWeight: FontWeight.bold)),
                    const SizedBox(height: sp4),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: sp12, vertical: 2),
                      decoration: BoxDecoration(
                        color: pageBg,
                        border: Border.all(color: accentLavender.withAlpha(80)),
                        borderRadius: BorderRadius.circular(2),
                      ),
                      child: DropdownButton<String>(
                        value: _outputFormat,
                        isExpanded: true,
                        underline: const SizedBox(),
                        dropdownColor: cardBg,
                        style: const TextStyle(fontFamily: fontBody, fontSize: 12, color: textPrimary),
                        items: const [
                          DropdownMenuItem(value: 'json', child: Text('json', style: TextStyle(fontFamily: fontBody, fontSize: 12, color: textPrimary))),
                          DropdownMenuItem(value: 'markdown', child: Text('markdown', style: TextStyle(fontFamily: fontBody, fontSize: 12, color: textPrimary))),
                        ],
                        onChanged: (v) => setState(() => _outputFormat = v ?? 'json'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: sp12),
                // REASONING EFFORT ────────────────────────────────────
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('REASONING EFFORT', style: TextStyle(fontFamily: fontBody, fontSize: 10, color: accentLavender, letterSpacing: 1.2, fontWeight: FontWeight.bold)),
                    const SizedBox(height: sp4),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: sp12, vertical: 2),
                      decoration: BoxDecoration(
                        color: pageBg,
                        border: Border.all(color: accentLavender.withAlpha(80)),
                        borderRadius: BorderRadius.circular(2),
                      ),
                      child: DropdownButton<String?>(
                        value: _reasoningEffort,
                        isExpanded: true,
                        underline: const SizedBox(),
                        dropdownColor: cardBg,
                        style: const TextStyle(fontFamily: fontBody, fontSize: 12, color: textPrimary),
                        hint: const Text('None (default)', style: TextStyle(fontFamily: fontBody, fontSize: 12, color: textMuted)),
                        items: const [
                          DropdownMenuItem<String?>(value: null, child: Text('None (default)', style: TextStyle(fontFamily: fontBody, fontSize: 12, color: textMuted))),
                          DropdownMenuItem(value: 'low', child: Text('low', style: TextStyle(fontFamily: fontBody, fontSize: 12, color: textPrimary))),
                          DropdownMenuItem(value: 'medium', child: Text('medium', style: TextStyle(fontFamily: fontBody, fontSize: 12, color: textPrimary))),
                          DropdownMenuItem(value: 'high', child: Text('high', style: TextStyle(fontFamily: fontBody, fontSize: 12, color: textPrimary))),
                        ],
                        onChanged: (v) => setState(() => _reasoningEffort = v),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: sp8),
                // TOGGLES ──────────────────────────────────────────────
                SwitchListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Row(
                    children: [
                      const Text('STATUS', style: TextStyle(fontFamily: fontBody, fontSize: 11, color: textPrimary)),
                      const SizedBox(width: sp8),
                      RetroChip(
                        label: _isActive ? 'ACTIVE' : 'INACTIVE',
                        color: _isActive ? const Color(0xFF4CAF50) : accentPrimary,
                      ),
                    ],
                  ),
                  value: _isActive,
                  activeThumbColor: const Color(0xFF4CAF50),
                  onChanged: (v) => setState(() => _isActive = v),
                ),
                SwitchListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: const Text('INFINITE SESSION', style: TextStyle(fontFamily: fontBody, fontSize: 11, color: textPrimary)),
                  value: _infiniteSession,
                  activeThumbColor: accentLavender,
                  onChanged: (v) => setState(() => _infiniteSession = v),
                ),
                SwitchListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: const Text('BYPASS MEMORY', style: TextStyle(fontFamily: fontBody, fontSize: 11, color: textPrimary)),
                  value: _bypassMemory,
                  activeThumbColor: accentLavender,
                  onChanged: (v) => setState(() => _bypassMemory = v),
                ),
                SwitchListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: const Text('AUTO MEMORY', style: TextStyle(fontFamily: fontBody, fontSize: 11, color: textPrimary)),
                  value: _autoMemory,
                  activeThumbColor: accentLavender,
                  onChanged: (v) => setState(() => _autoMemory = v),
                ),
                const SizedBox(height: sp12),
                const SizedBox(height: sp12),
                // CREDENTIAL OVERRIDES ────────────────────────────────────
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'CREDENTIAL OVERRIDES',
                          style: TextStyle(
                            fontFamily: fontBody,
                            fontSize: 10,
                            color: accentAmber,
                            letterSpacing: 1.2,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const Spacer(),
                        TextButton.icon(
                          onPressed: (_credEnvVarKeys.isEmpty || _credTokens.isEmpty)
                              ? null
                              : () {
                                  setState(() {
                                    _credOverrides.add(_CredOverride(
                                      envVar: _credEnvVarKeys.first,
                                      tokenName: _credTokens.first.name,
                                    ));
                                  });
                                },
                          icon: const Icon(Icons.add, size: 14, color: accentAmber),
                          label: const Text(
                            'ADD',
                            style: TextStyle(
                              fontFamily: fontBody,
                              fontSize: 10,
                              color: accentAmber,
                            ),
                          ),
                          style: TextButton.styleFrom(
                            padding: const EdgeInsets.symmetric(
                              horizontal: sp4,
                              vertical: 2,
                            ),
                            minimumSize: Size.zero,
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: sp4),
                    if (_credOverrides.isEmpty)
                      Text(
                        _credEnvVarKeys.isEmpty
                            ? 'No custom tool credentials found.'
                            : 'None — plugin uses default env vars.',
                        style: const TextStyle(
                          fontFamily: fontBody,
                          fontSize: 11,
                          color: textMuted,
                        ),
                      )
                    else
                      ...List.generate(_credOverrides.length, (i) {
                        final override = _credOverrides[i];
                        return _OverrideRow(
                          credOverride: override,
                          envVarKeys: _credEnvVarKeys,
                          tokens: _credTokens,
                          onEnvVarChanged: (val) {
                            if (val != null) setState(() => override.envVar = val);
                          },
                          onTokenChanged: (val) {
                            if (val != null) setState(() => override.tokenName = val);
                          },
                          onRemove: () => setState(() => _credOverrides.removeAt(i)),
                        );
                      }),
                  ],
                ),
                // REPO ─────────────────────────────────────────────────
                _WfDialogField(
                  label: 'REPO URL (optional)',
                  controller: _repoUrlCtrl,
                  hint: 'https://github.com/org/repo',
                ),
                const SizedBox(height: sp12),
                _WfDialogField(
                  label: 'REPO BRANCH (optional)',
                  controller: _repoBranchCtrl,
                  hint: 'main',
                ),
                const SizedBox(height: sp12),
                _WfDialogField(
                  label: 'REPO TOKEN NAME (optional)',
                  controller: _repoTokenCtrl,
                  hint: 'GITHUB_TOKEN',
                ),
                const SizedBox(height: sp12),
                _WfDialogField(
                  label: 'WEBHOOK URL (optional)',
                  controller: _webhookUrlCtrl,
                  hint: 'https://your-server.com/webhook',
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
                      label: _saving ? 'SAVING…' : (_isEdit ? 'SAVE' : 'CREATE'),
                      onPressed: _saving ? null : _save,
                      color: accentLavender,
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
// _WfDialogField — labelled text input for workflow dialogs
// ---------------------------------------------------------------------------

class _WfDialogField extends StatelessWidget {
  const _WfDialogField({
    required this.label,
    required this.controller,
    this.hint = '',
    this.keyboardType = TextInputType.text,
  });

  final String label;
  final TextEditingController controller;
  final String hint;
  final TextInputType keyboardType;

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
            border: Border.all(color: accentLavender.withAlpha(80)),
            borderRadius: BorderRadius.circular(2),
          ),
          padding: const EdgeInsets.symmetric(horizontal: sp8),
          child: TextField(
            controller: controller,
            keyboardType: keyboardType,
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
// _WfMetaItem — small icon + label meta info chip (workflows-scoped)
// ---------------------------------------------------------------------------

class _WfMetaItem extends StatelessWidget {
  const _WfMetaItem({required this.icon, required this.label});

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

// ---------------------------------------------------------------------------
// _WfErrorBanner — error banner with retry (workflows-scoped)
// ---------------------------------------------------------------------------

class _WfErrorBanner extends StatelessWidget {
  const _WfErrorBanner({required this.message, required this.onRetry});

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
// _Task — data model (mirrors TaskExecutionSummary)
// ---------------------------------------------------------------------------

class _Task {
  const _Task({
    required this.id,
    required this.workflowId,
    required this.status,
    required this.prompt,
    required this.createdAt,
    required this.updatedAt,
    this.error,
    this.workflowTitle,
    this.agentName,
    this.model,
    this.reasoningEffort,
    this.toolCalls = 0,
    this.startedAt,
    this.finishedAt,
    this.elapsedSeconds,
    this.worker,
  });

  final String id;
  final String workflowId;
  final String status;
  final String prompt;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? error;

  // enriched fields from TaskExecutionSummary
  final String? workflowTitle;
  final String? agentName;
  final String? model;
  final String? reasoningEffort;
  final int toolCalls;
  final DateTime? startedAt;
  final DateTime? finishedAt;
  final double? elapsedSeconds;
  final String? worker;

  factory _Task.fromJson(Map<String, dynamic> j) => _Task(
    id: j['id']?.toString() ?? '',
    workflowId: j['workflow_id']?.toString() ?? '',
    status: j['status']?.toString() ?? 'pending',
    prompt: j['prompt']?.toString() ?? '',
    createdAt:
        DateTime.tryParse(j['created_at']?.toString() ?? '') ?? DateTime.now(),
    updatedAt:
        DateTime.tryParse(j['updated_at']?.toString() ?? '') ??
        DateTime.tryParse(j['created_at']?.toString() ?? '') ??
        DateTime.now(),
    error: j['error']?.toString(),
    workflowTitle: j['workflow_title']?.toString(),
    agentName: j['agent_name']?.toString(),
    model: j['model']?.toString(),
    reasoningEffort: j['reasoning_effort']?.toString(),
    toolCalls: (j['tool_calls'] as num?)?.toInt() ?? 0,
    startedAt: DateTime.tryParse(j['started_at']?.toString() ?? ''),
    finishedAt: DateTime.tryParse(j['finished_at']?.toString() ?? ''),
    elapsedSeconds: (j['elapsed_seconds'] as num?)?.toDouble(),
    worker: j['worker']?.toString(),
  );
}

// ---------------------------------------------------------------------------
// Tasks API helper
// ---------------------------------------------------------------------------

Future<List<_Task>> _fetchTasks(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/tasks'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception('Failed to load tasks (${response.statusCode})');
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded.whereType<Map<String, dynamic>>().map(_Task.fromJson).toList();
}

// ---------------------------------------------------------------------------
// TasksScreen — task execution log (live list)
// ---------------------------------------------------------------------------
class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key});

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  http.Client? _ownedClient;
  late Future<List<_Task>> _tasksFuture;
  Timer? _pollTimer;

  http.Client get _client => _ownedClient ??= http.Client();

  @override
  void initState() {
    super.initState();
    _reload();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _ownedClient?.close();
    super.dispose();
  }

  void _reload() {
    _pollTimer?.cancel();
    _pollTimer = null;
    final future = _fetchTasks(_client);
    setState(() {
      _tasksFuture = future;
    });
    future.then((tasks) {
      if (!mounted) return;
      final hasActive = tasks.any(
        (t) => t.status == 'running' || t.status == 'pending',
      );
      if (hasActive) {
        _pollTimer = Timer.periodic(
          const Duration(seconds: 5),
          (_) {
            if (!mounted) {
              _pollTimer?.cancel();
              return;
            }
            _reloadSilent();
          },
        );
      }
    }).catchError((_) {});
  }

  void _reloadSilent() {
    final future = _fetchTasks(_client);
    setState(() {
      _tasksFuture = future;
    });
    future.then((tasks) {
      if (!mounted) return;
      final hasActive = tasks.any(
        (t) => t.status == 'running' || t.status == 'pending',
      );
      if (!hasActive) {
        _pollTimer?.cancel();
        _pollTimer = null;
      }
    }).catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_Task>>(
      future: _tasksFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final tasks = snapshot.data ?? [];

        return SingleChildScrollView(
          padding: const EdgeInsets.all(sp24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _ScreenHeader(
                title: 'TASK EXECUTIONS',
                subtitle: 'History of all agent task runs',
                actions: [
                  RetroButton(
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentAmber,
                    textColor: textPrimary,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _WfErrorBanner(
                  message: 'Failed to load tasks: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Execution History',
                accentColor: accentAmber,
                minHeight: tasks.isEmpty ? 400 : 0,
                child: tasks.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: _EmptyState(
                          icon: Icons.list_alt_outlined,
                          message:
                              loading ? 'Loading…' : 'No task executions yet.',
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final t in tasks)
                              _TaskCard(task: t, client: _client),
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

// ---------------------------------------------------------------------------
// _TaskCard — read-only card for a single task execution
// ---------------------------------------------------------------------------

class _TaskCard extends StatelessWidget {
  const _TaskCard({required this.task, required this.client});

  final _Task task;
  final http.Client client;

  Color get _statusColor {
    switch (task.status.toLowerCase()) {
      case 'completed':
        return const Color(0xFF4CAF50);
      case 'running':
        return accentTeal;
      case 'failed':
        return accentPrimary;
      case 'pending':
      default:
        return accentAmber;
    }
  }

  Color get _statusTextColor {
    switch (task.status.toLowerCase()) {
      case 'pending':
        return textPrimary;
      default:
        return cardBg;
    }
  }

  String _formatDate(DateTime dt) {
    final s = dt.toIso8601String();
    return s.length > 16 ? s.substring(0, 16).replaceAll('T', ' ') : s;
  }

  @override
  Widget build(BuildContext context) {
    final wfLabel =
        (task.workflowTitle != null && task.workflowTitle!.isNotEmpty)
            ? task.workflowTitle!
            : (task.workflowId.length > 14
                ? '${task.workflowId.substring(0, 14)}…'
                : task.workflowId);
    return Padding(
      padding: const EdgeInsets.only(bottom: sp12),
      child: RetroCard(
        child: Padding(
          padding: const EdgeInsets.all(sp16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Header row ──────────────────────────────────────────────
              Row(
                children: [
                  RetroChip(
                    label: wfLabel.length > 22
                        ? '${wfLabel.substring(0, 22)}…'
                        : wfLabel,
                    color: accentSlate,
                  ),
                  const Spacer(),
                  RetroChip(
                    label: task.status,
                    color: _statusColor,
                    textColor: _statusTextColor,
                  ),
                ],
              ),
              const SizedBox(height: sp8),
              // ── Prompt ──────────────────────────────────────────────────
              Text(
                task.prompt,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: fontSizeBody,
                  color: textPrimary,
                  letterSpacing: 0.5,
                ),
              ),
              const SizedBox(height: sp8),
              // ── Meta row ────────────────────────────────────────────────
              Wrap(
                spacing: sp12,
                runSpacing: 4,
                children: [
                  _WfMetaItem(
                    icon: Icons.access_time_outlined,
                    label: _formatDate(task.createdAt),
                  ),
                  if (task.agentName != null && task.agentName!.isNotEmpty)
                    _WfMetaItem(
                      icon: Icons.smart_toy_outlined,
                      label: task.agentName!,
                    ),
                  if (task.model != null && task.model!.isNotEmpty)
                    _WfMetaItem(
                      icon: Icons.memory_outlined,
                      label: task.model!,
                    ),
                  if (task.toolCalls > 0)
                    _WfMetaItem(
                      icon: Icons.build_outlined,
                      label: '${task.toolCalls} tools',
                    ),
                  if (task.elapsedSeconds != null)
                    _WfMetaItem(
                      icon: Icons.timer_outlined,
                      label: '${task.elapsedSeconds!.toStringAsFixed(1)}s',
                    ),
                ],
              ),
              // ── Error ───────────────────────────────────────────────────
              if (task.status.toLowerCase() == 'failed' &&
                  task.error != null &&
                  task.error!.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Text(
                  task.error!,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeSmall,
                    color: accentPrimary,
                    letterSpacing: 0.25,
                  ),
                ),
              ],
              const SizedBox(height: sp8),
              // ── VIEW DETAILS button ──────────────────────────────────────
              Align(
                alignment: Alignment.centerRight,
                child: RetroButton(
                  label: 'VIEW DETAILS',
                  icon: Icons.open_in_new_outlined,
                  color: accentSlate,
                  onPressed: () => showDialog<void>(
                    context: context,
                    builder: (_) => _TaskDetailDialog(
                      taskId: task.id,
                      client: client,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _TaskDetailDialog — full task execution detail with logs, messages, usage
// ---------------------------------------------------------------------------

class _TaskDetailDialog extends StatefulWidget {
  const _TaskDetailDialog({required this.taskId, required this.client});

  final String taskId;
  final http.Client client;

  @override
  State<_TaskDetailDialog> createState() => _TaskDetailDialogState();
}

class _TaskDetailDialogState extends State<_TaskDetailDialog> {
  Map<String, dynamic>? _data;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final resp = await widget.client.get(
        AppLinks.apiUri('/tasks/${widget.taskId}'),
      );
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        throw Exception('Failed (${resp.statusCode})');
      }
      if (!mounted) return;
      setState(() {
        _data = jsonDecode(resp.body) as Map<String, dynamic>;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  String _fmt(String? raw) {
    if (raw == null) return '—';
    final dt = DateTime.tryParse(raw);
    if (dt == null) return raw;
    final s = dt.toIso8601String();
    return s.length > 19 ? s.substring(0, 19).replaceAll('T', ' ') : s;
  }

  Color _todoColor(String status) {
    switch (status.toLowerCase()) {
      case 'completed':
        return const Color(0xFF4CAF50);
      case 'in-progress':
        return accentTeal;
      default:
        return accentAmber;
    }
  }

  Color _statusColor(String status) {
    switch (status.toLowerCase()) {
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

  Color _statusTextColor(String status) {
    return status.toLowerCase() == 'pending' ? textPrimary : cardBg;
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 800, maxHeight: 680),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── Dialog header ────────────────────────────────────────────
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: sp16,
                vertical: sp12,
              ),
              decoration: const BoxDecoration(
                color: accentSlate,
                border: Border(
                  bottom: BorderSide(color: borderColor, width: 2),
                ),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.assignment_outlined,
                    color: cardBg,
                    size: 16,
                  ),
                  const SizedBox(width: sp8),
                  const Expanded(
                    child: Text(
                      'TASK DETAILS',
                      style: TextStyle(
                        fontFamily: fontDisplay,
                        fontSize: 9,
                        color: cardBg,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: cardBg, size: 18),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
            ),
            // ── Body ────────────────────────────────────────────────────
            Expanded(
              child: _loading
                  ? const Center(
                      child: CircularProgressIndicator(color: accentSlate),
                    )
                  : _error != null
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(sp24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.error_outline,
                              color: accentPrimary,
                              size: 32,
                            ),
                            const SizedBox(height: sp8),
                            Text(
                              _error!,
                              style: const TextStyle(
                                fontFamily: fontBody,
                                fontSize: fontSizeSmall,
                                color: accentPrimary,
                              ),
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: sp12),
                            RetroButton(
                              label: 'RETRY',
                              onPressed: _load,
                              color: accentSlate,
                            ),
                          ],
                        ),
                      ),
                    )
                  : _buildContent(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildContent() {
    final d = _data!;
    final status = d['status']?.toString() ?? '';
    final response = d['response']?.toString();
    final prompt = d['prompt']?.toString() ?? '';
    final model = d['model']?.toString();
    final reasoningEffort = d['reasoning_effort']?.toString();
    final toolCalls = (d['tool_calls'] as num?)?.toInt() ?? 0;
    final elapsedSeconds = (d['elapsed_seconds'] as num?)?.toDouble();
    final worker = d['worker']?.toString();
    final workflowTitle = d['workflow_title']?.toString();
    final agentName = d['agent_name']?.toString();

    final logs = (d['logs'] as List<dynamic>? ?? [])
        .whereType<Map<String, dynamic>>()
        .toList();
    final messages = (d['messages'] as List<dynamic>? ?? [])
        .whereType<Map<String, dynamic>>()
        .toList();
    final usage = d['usage'] as Map<String, dynamic>?;
    final progress = d['progress'] as Map<String, dynamic>?;
    final todos = progress != null
        ? (progress['todos'] as List<dynamic>? ?? [])
            .whereType<Map<String, dynamic>>()
            .toList()
        : <Map<String, dynamic>>[];

    // Compute total tokens
    final inputTokens = (usage?['total_input_tokens'] as num?)?.toInt() ?? 0;
    final outputTokens = (usage?['total_output_tokens'] as num?)?.toInt() ?? 0;
    final totalTokens = inputTokens + outputTokens;

    final sc = _statusColor(status);
    final stc = _statusTextColor(status);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Status + title row ──────────────────────────────────────
          Row(
            children: [
              if (workflowTitle != null && workflowTitle.isNotEmpty)
                Expanded(
                  child: Text(
                    workflowTitle,
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: fontSizeBody,
                      color: textPrimary,
                      letterSpacing: 0.5,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                )
              else
                const Spacer(),
              RetroChip(label: status, color: sc, textColor: stc),
            ],
          ),
          const SizedBox(height: sp8),
          // ── Meta chips ──────────────────────────────────────────────
          Wrap(
            spacing: sp12,
            runSpacing: 4,
            children: [
              if (agentName != null && agentName.isNotEmpty)
                _WfMetaItem(
                  icon: Icons.smart_toy_outlined,
                  label: agentName,
                ),
              if (model != null && model.isNotEmpty)
                _WfMetaItem(icon: Icons.memory_outlined, label: model),
              if (reasoningEffort != null && reasoningEffort.isNotEmpty)
                _WfMetaItem(
                  icon: Icons.psychology_outlined,
                  label: 'effort: $reasoningEffort',
                ),
              if (toolCalls > 0)
                _WfMetaItem(
                  icon: Icons.build_outlined,
                  label: '$toolCalls tools',
                ),
              if (elapsedSeconds != null)
                _WfMetaItem(
                  icon: Icons.timer_outlined,
                  label: '${elapsedSeconds.toStringAsFixed(1)}s',
                ),
              if (worker != null && worker.isNotEmpty)
                _WfMetaItem(icon: Icons.dns_outlined, label: worker),
              _WfMetaItem(
                icon: Icons.play_arrow_outlined,
                label: _fmt(d['started_at']?.toString()),
              ),
              _WfMetaItem(
                icon: Icons.stop_outlined,
                label: _fmt(d['finished_at']?.toString()),
              ),
            ],
          ),
          const SizedBox(height: sp16),
          // ── Prompt ──────────────────────────────────────────────────
          SectionFrame(
            title: 'Prompt',
            accentColor: accentSlate,
            child: Padding(
              padding: const EdgeInsets.all(sp12),
              child: SelectableText(
                prompt,
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: fontSizeSmall,
                  color: textPrimary,
                ),
              ),
            ),
          ),
          const SizedBox(height: sp12),
          // ── Response ────────────────────────────────────────────────
          if (response != null && response.isNotEmpty) ...[
            SectionFrame(
              title: 'Response',
              accentColor: const Color(0xFF4CAF50),
              child: Padding(
                padding: const EdgeInsets.all(sp12),
                child: SelectableText(
                  response,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeSmall,
                    color: textPrimary,
                  ),
                ),
              ),
            ),
            const SizedBox(height: sp12),
          ],
          // ── Progress / Todos ─────────────────────────────────────────
          if (todos.isNotEmpty) ...[
            SectionFrame(
              title:
                  'Progress  (${(progress?['percent_complete'] ?? 0.0).toStringAsFixed(0)}%)',
              accentColor: accentTeal,
              child: Padding(
                padding: const EdgeInsets.all(sp12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final todo in todos)
                      Padding(
                        padding: const EdgeInsets.only(bottom: sp4),
                        child: Row(
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              color: _todoColor(
                                todo['status']?.toString() ?? '',
                              ),
                            ),
                            const SizedBox(width: sp8),
                            Expanded(
                              child: Text(
                                todo['title']?.toString() ?? '',
                                style: const TextStyle(
                                  fontFamily: fontBody,
                                  fontSize: fontSizeSmall,
                                  color: textPrimary,
                                ),
                              ),
                            ),
                            const SizedBox(width: sp8),
                            Text(
                              todo['status']?.toString() ?? '',
                              style: const TextStyle(
                                fontFamily: fontBody,
                                fontSize: fontSizeSmall,
                                color: textMuted,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: sp12),
          ],
          // ── Usage stats ─────────────────────────────────────────────
          if (usage != null) ...[
            SectionFrame(
              title: 'Usage',
              accentColor: accentLavender,
              child: Padding(
                padding: const EdgeInsets.all(sp12),
                child: Wrap(
                  spacing: sp16,
                  runSpacing: 4,
                  children: [
                    _WfMetaItem(
                      icon: Icons.input_outlined,
                      label: 'in: $inputTokens',
                    ),
                    _WfMetaItem(
                      icon: Icons.output_outlined,
                      label: 'out: $outputTokens',
                    ),
                    _WfMetaItem(
                      icon: Icons.token_outlined,
                      label: 'total: $totalTokens',
                    ),
                    if ((usage['total_cost'] as num?)?.toDouble() != null)
                      _WfMetaItem(
                        icon: Icons.attach_money_outlined,
                        label:
                            '\$${(usage['total_cost'] as num).toStringAsFixed(4)}',
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: sp12),
          ],
          // ── Conversation messages (assistant turns) ──────────────────
          if (messages.where((m) => m['role'] == 'assistant').isNotEmpty) ...[
            SectionFrame(
              title: 'Conversation',
              accentColor: accentTeal,
              child: Padding(
                padding: const EdgeInsets.all(sp12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final msg in messages)
                      if (msg['role']?.toString() == 'assistant' &&
                          msg['content'] != null &&
                          (msg['content'] as String).isNotEmpty) ...[
                        _TaskMessageBubble(
                          content: msg['content']?.toString() ?? '',
                        ),
                        const SizedBox(height: sp8),
                      ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: sp12),
          ],
          // ── Logs (expandable) ────────────────────────────────────────
          if (logs.isNotEmpty)
            _TaskLogsExpansion(logs: logs, formatDate: _fmt),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _TaskMessageBubble — assistant message display in task detail
// ---------------------------------------------------------------------------

class _TaskMessageBubble extends StatelessWidget {
  const _TaskMessageBubble({required this.content});
  final String content;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(sp8),
      decoration: BoxDecoration(
        color: pageBg,
        border: Border.all(color: borderColor.withAlpha(60)),
      ),
      child: SelectableText(
        content,
        style: const TextStyle(
          fontFamily: fontBody,
          fontSize: fontSizeSmall,
          color: textPrimary,
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _TaskLogsExpansion — expandable log list in task detail
// ---------------------------------------------------------------------------

class _TaskLogsExpansion extends StatefulWidget {
  const _TaskLogsExpansion({
    required this.logs,
    required this.formatDate,
  });
  final List<Map<String, dynamic>> logs;
  final String Function(String?) formatDate;

  @override
  State<_TaskLogsExpansion> createState() => _TaskLogsExpansionState();
}

class _TaskLogsExpansionState extends State<_TaskLogsExpansion> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GestureDetector(
          onTap: () => setState(() => _expanded = !_expanded),
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: sp12,
              vertical: sp8,
            ),
            decoration: BoxDecoration(
              color: pageBg,
              border: Border.all(color: borderColor.withAlpha(80)),
            ),
            child: Row(
              children: [
                Icon(
                  _expanded ? Icons.expand_less : Icons.expand_more,
                  size: 14,
                  color: textMuted,
                ),
                const SizedBox(width: sp8),
                Text(
                  'LOGS (${widget.logs.length})',
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeSmall,
                    color: textMuted,
                    letterSpacing: 1,
                  ),
                ),
              ],
            ),
          ),
        ),
        if (_expanded)
          Container(
            padding: const EdgeInsets.all(sp8),
            decoration: BoxDecoration(
              color: pageBg,
              border: Border.all(color: borderColor.withAlpha(60)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final log in widget.logs)
                  Padding(
                    padding: const EdgeInsets.only(bottom: sp4),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.formatDate(log['timestamp']?.toString()),
                          style: const TextStyle(
                            fontFamily: fontBody,
                            fontSize: 9,
                            color: textMuted,
                          ),
                        ),
                        const SizedBox(width: sp8),
                        Flexible(
                          child: RichText(
                            text: TextSpan(
                              children: [
                                TextSpan(
                                  text:
                                      '${log['event']?.toString() ?? ''}: ',
                                  style: const TextStyle(
                                    fontFamily: fontBody,
                                    fontSize: 9,
                                    color: accentTeal,
                                  ),
                                ),
                                TextSpan(
                                  text: log['detail']?.toString() ?? '',
                                  style: const TextStyle(
                                    fontFamily: fontBody,
                                    fontSize: 9,
                                    color: textPrimary,
                                  ),
                                ),
                              ],
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
    );
  }
}

// ---------------------------------------------------------------------------
// _ScheduledAgent — data model
// ---------------------------------------------------------------------------

class _ScheduledAgent {
  const _ScheduledAgent({
    required this.id,
    required this.name,
    required this.workflowId,
    required this.prompt,
    required this.intervalUnit,
    required this.intervalValue,
    required this.enabled,
    this.lastRunAt,
    this.nextRunAt,
  });

  final String id;
  final String name;
  final String workflowId;
  final String prompt;
  final String intervalUnit;
  final int intervalValue;
  final bool enabled;
  final String? lastRunAt;
  final String? nextRunAt;

  factory _ScheduledAgent.fromJson(Map<String, dynamic> j) => _ScheduledAgent(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? '',
    workflowId: j['workflow_id']?.toString() ?? '',
    prompt: j['prompt']?.toString() ?? '',
    intervalUnit: j['interval_unit']?.toString() ?? 'hours',
    intervalValue: (j['interval_value'] as num?)?.toInt() ?? 1,
    enabled: j['enabled'] as bool? ?? true,
    lastRunAt: j['last_run_at']?.toString(),
    nextRunAt: j['next_run_at']?.toString(),
  );
}

// ---------------------------------------------------------------------------
// ScheduledAgents API helper
// ---------------------------------------------------------------------------

Future<List<_ScheduledAgent>> _fetchScheduledAgents(http.Client client) async {
  final response = await client.get(AppLinks.apiUri('/scheduled-agents'));
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception(
      'Failed to load scheduled agents (${response.statusCode})',
    );
  }
  final decoded = jsonDecode(response.body);
  if (decoded is! List) throw Exception('Unexpected response format');
  return decoded
      .whereType<Map<String, dynamic>>()
      .map(_ScheduledAgent.fromJson)
      .toList();
}

// ---------------------------------------------------------------------------
// ScheduledAgentsScreen — cron / scheduled agent runs (live CRUD)
// ---------------------------------------------------------------------------
class ScheduledAgentsScreen extends StatefulWidget {
  const ScheduledAgentsScreen({super.key});

  @override
  State<ScheduledAgentsScreen> createState() => _ScheduledAgentsScreenState();
}

class _ScheduledAgentsScreenState extends State<ScheduledAgentsScreen> {
  http.Client? _ownedClient;
  late Future<List<_ScheduledAgent>> _schedulesFuture;

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
      _schedulesFuture = _fetchScheduledAgents(_client);
    });
  }

  Future<void> _confirmDelete(String id, String name) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => _ConfirmDeleteDialog(
        message: "Delete schedule '$name'?",
        accentColor: accentTeal,
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      final response =
          await _client.delete(AppLinks.apiUri('/scheduled-agents/$id'));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ?? 'Delete failed (${response.statusCode})',
        );
      }
      if (!mounted) return;
      _reload();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Schedule '$name' deleted."),
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

  Future<void> _toggleEnabled(_ScheduledAgent schedule) async {
    final endpoint = schedule.enabled ? 'disable' : 'enable';
    try {
      final response = await _client.patch(
        AppLinks.apiUri('/scheduled-agents/${schedule.id}/$endpoint'),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ?? 'Toggle failed (${response.statusCode})',
        );
      }
      if (!mounted) return;
      _reload();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Toggle failed: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<_ScheduledAgent>>(
      future: _schedulesFuture,
      builder: (context, snapshot) {
        final loading = snapshot.connectionState == ConnectionState.waiting;
        final schedules = snapshot.data ?? [];

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
                    label: loading ? 'LOADING…' : 'REFRESH',
                    onPressed: loading ? null : _reload,
                    icon: Icons.refresh,
                    color: accentSlate,
                  ),
                  RetroButton(
                    label: 'ADD SCHEDULE',
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _ScheduledAgentDialog(
                        client: _client,
                        onSaved: _reload,
                      ),
                    ),
                    icon: Icons.add,
                    color: accentTeal,
                  ),
                ],
              ),
              const SizedBox(height: sp24),
              if (snapshot.hasError)
                _WfErrorBanner(
                  message: 'Failed to load schedules: ${snapshot.error}',
                  onRetry: _reload,
                ),
              SectionFrame(
                title: 'Active Schedules',
                accentColor: accentTeal,
                minHeight: schedules.isEmpty ? 300 : 0,
                child: schedules.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: _EmptyState(
                          icon: Icons.schedule_outlined,
                          message: loading
                              ? 'Loading…'
                              : 'No schedules configured.',
                        ),
                      )
                    : Padding(
                        padding: const EdgeInsets.all(sp16),
                        child: Column(
                          children: [
                            for (final s in schedules)
                              _ScheduledAgentCard(
                                schedule: s,
                                client: _client,
                                onSaved: _reload,
                                onToggleEnabled: () => _toggleEnabled(s),
                                onDelete: () => _confirmDelete(s.id, s.name),
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

// ---------------------------------------------------------------------------
// _ScheduledAgentCard — displays a single schedule with enable toggle + CRUD
// ---------------------------------------------------------------------------

class _ScheduledAgentCard extends StatelessWidget {
  const _ScheduledAgentCard({
    required this.schedule,
    required this.client,
    required this.onSaved,
    required this.onToggleEnabled,
    required this.onDelete,
  });

  final _ScheduledAgent schedule;
  final http.Client client;
  final VoidCallback onSaved;
  final VoidCallback onToggleEnabled;
  final VoidCallback onDelete;

  String _shortDate(String? iso) {
    if (iso == null || iso.isEmpty) return '';
    final trimmed = iso.length > 16 ? iso.substring(0, 16) : iso;
    return trimmed.replaceAll('T', ' ');
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
              // ── Header row ──────────────────────────────────────────────
              Row(
                children: [
                  const Icon(
                    Icons.schedule_outlined,
                    size: 14,
                    color: accentTeal,
                  ),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: Text(
                      schedule.name,
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: fontSizeBody,
                        color: accentTeal,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  Transform.scale(
                    scale: 0.75,
                    child: Switch(
                      value: schedule.enabled,
                      onChanged: (_) => onToggleEnabled(),
                      activeThumbColor: accentTeal,
                    ),
                  ),
                ],
              ),
              // ── Interval subtitle ────────────────────────────────────────
              const SizedBox(height: sp4),
              Text(
                'Every ${schedule.intervalValue} ${schedule.intervalUnit}',
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: fontSizeSmall,
                  color: textMuted,
                  letterSpacing: 0.5,
                ),
              ),
              const SizedBox(height: sp8),
              // ── Chips ────────────────────────────────────────────────────
              Wrap(
                spacing: sp8,
                runSpacing: sp4,
                children: [
                  RetroChip(label: schedule.workflowId, color: accentSlate),
                  if (!schedule.enabled)
                    const RetroChip(
                      label: 'DISABLED',
                      color: textMuted,
                      textColor: cardBg,
                    ),
                ],
              ),
              // ── Run timestamps ───────────────────────────────────────────
              if (schedule.nextRunAt != null &&
                  schedule.nextRunAt!.isNotEmpty) ...[
                const SizedBox(height: sp8),
                _WfMetaItem(
                  icon: Icons.arrow_forward_outlined,
                  label: 'Next: ${_shortDate(schedule.nextRunAt)}',
                ),
              ],
              if (schedule.lastRunAt != null &&
                  schedule.lastRunAt!.isNotEmpty) ...[
                const SizedBox(height: sp4),
                _WfMetaItem(
                  icon: Icons.history_outlined,
                  label: 'Last: ${_shortDate(schedule.lastRunAt)}',
                ),
              ],
              // ── Actions ──────────────────────────────────────────────────
              const SizedBox(height: sp12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'EDIT',
                    icon: Icons.edit_outlined,
                    color: accentTeal,
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _ScheduledAgentDialog(
                        client: client,
                        onSaved: onSaved,
                        schedule: schedule,
                      ),
                    ),
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

// ---------------------------------------------------------------------------
// _ScheduledAgentDialog — create / edit a scheduled agent
// ---------------------------------------------------------------------------

const _kIntervalUnits = <String>['minutes', 'hours', 'days'];

class _ScheduledAgentDialog extends StatefulWidget {
  const _ScheduledAgentDialog({
    required this.client,
    required this.onSaved,
    this.schedule,
  });

  final http.Client client;
  final VoidCallback onSaved;
  final _ScheduledAgent? schedule;

  bool get isEdit => schedule != null;

  @override
  State<_ScheduledAgentDialog> createState() => _ScheduledAgentDialogState();
}

class _ScheduledAgentDialogState extends State<_ScheduledAgentDialog> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _workflowIdCtrl;
  late final TextEditingController _promptCtrl;
  late final TextEditingController _intervalValueCtrl;
  late final TextEditingController _startAtCtrl;
  late final TextEditingController _endAtCtrl;
  late String _intervalUnit;
  String? _startAtError;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final s = widget.schedule;
    _nameCtrl = TextEditingController(text: s?.name ?? '');
    _workflowIdCtrl = TextEditingController(text: s?.workflowId ?? '');
    _promptCtrl = TextEditingController(text: s?.prompt ?? '');
    _intervalValueCtrl = TextEditingController(
      text: s?.intervalValue.toString() ?? '1',
    );
    _startAtCtrl = TextEditingController();
    _endAtCtrl = TextEditingController();
    final unit = s?.intervalUnit ?? 'hours';
    _intervalUnit = _kIntervalUnits.contains(unit) ? unit : 'hours';
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _workflowIdCtrl.dispose();
    _promptCtrl.dispose();
    _intervalValueCtrl.dispose();
    _startAtCtrl.dispose();
    _endAtCtrl.dispose();
    super.dispose();
  }

  void _showValidationError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: Colors.orange),
    );
  }

  Future<void> _save() async {
    if (_nameCtrl.text.trim().isEmpty) {
      _showValidationError('Name is required.');
      return;
    }
    if (!widget.isEdit && _workflowIdCtrl.text.trim().isEmpty) {
      _showValidationError('Workflow ID is required.');
      return;
    }
    if (_promptCtrl.text.trim().isEmpty) {
      _showValidationError('Prompt is required.');
      return;
    }
    final intervalValue = int.tryParse(_intervalValueCtrl.text.trim());
    if (intervalValue == null || intervalValue < 1) {
      _showValidationError('Interval value must be a positive integer.');
      return;
    }

    // Validate start_at
    final startAtText = _startAtCtrl.text.trim();
    DateTime? startAt;
    if (!widget.isEdit) {
      if (startAtText.isEmpty) {
        _showValidationError('Start date/time is required.');
        return;
      }
      startAt = DateTime.tryParse(startAtText);
      if (startAt == null) {
        setState(() => _startAtError = 'Invalid ISO datetime format');
        return;
      }
    } else if (startAtText.isNotEmpty) {
      startAt = DateTime.tryParse(startAtText);
      if (startAt == null) {
        setState(() => _startAtError = 'Invalid ISO datetime format');
        return;
      }
    }
    setState(() => _startAtError = null);

    // Validate end_at (optional)
    final endAtText = _endAtCtrl.text.trim();
    DateTime? endAt;
    if (endAtText.isNotEmpty) {
      endAt = DateTime.tryParse(endAtText);
      if (endAt == null) {
        _showValidationError('Invalid end date/time format.');
        return;
      }
    }

    setState(() => _saving = true);
    try {
      final body = <String, dynamic>{
        'name': _nameCtrl.text.trim(),
        if (!widget.isEdit) 'workflow_id': _workflowIdCtrl.text.trim(),
        'prompt': _promptCtrl.text.trim(),
        'interval_value': intervalValue,
        'interval_unit': _intervalUnit,
        if (startAt != null) 'start_at': startAt.toIso8601String(),
        if (endAt != null) 'end_at': endAt.toIso8601String(),
      };
      final http.Response response;
      if (widget.isEdit) {
        response = await widget.client.patch(
          AppLinks.apiUri('/scheduled-agents/${widget.schedule!.id}'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        );
      } else {
        response = await widget.client.post(
          AppLinks.apiUri('/scheduled-agents'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ?? 'Save failed (${response.statusCode})',
        );
      }
      if (!mounted) return;
      widget.onSaved();
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            widget.isEdit ? 'Schedule updated.' : 'Schedule created.',
          ),
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
        side: const BorderSide(color: accentTeal, width: 1),
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
                // ── Header ───────────────────────────────────────────────
                Row(
                  children: [
                    const Icon(
                      Icons.schedule_outlined,
                      color: accentTeal,
                      size: 20,
                    ),
                    const SizedBox(width: sp8),
                    Expanded(
                      child: Text(
                        widget.isEdit ? 'EDIT SCHEDULE' : 'NEW SCHEDULE',
                        style: const TextStyle(
                          fontFamily: fontBody,
                          fontSize: 13,
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
                      onPressed: () => Navigator.of(context).pop(),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                    ),
                  ],
                ),
                const SizedBox(height: sp16),
                // ── Name ─────────────────────────────────────────────────
                _TealDialogField(
                  label: 'NAME *',
                  controller: _nameCtrl,
                  hint: 'My daily agent',
                ),
                const SizedBox(height: sp12),
                // ── Workflow ID (read-only in edit) ───────────────────────
                if (widget.isEdit) ...[
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'WORKFLOW ID (read-only)',
                        style: TextStyle(
                          fontFamily: fontBody,
                          fontSize: 9,
                          color: textMuted,
                          letterSpacing: 0.8,
                        ),
                      ),
                      const SizedBox(height: sp4),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: sp8,
                          vertical: sp8,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.black12,
                          border:
                              Border.all(color: textMuted.withAlpha(40)),
                          borderRadius: BorderRadius.circular(2),
                        ),
                        child: Text(
                          widget.schedule!.workflowId,
                          style: const TextStyle(
                            fontFamily: fontBody,
                            fontSize: 12,
                            color: textMuted,
                          ),
                        ),
                      ),
                    ],
                  ),
                ] else ...[
                  _TealDialogField(
                    label: 'WORKFLOW ID *',
                    controller: _workflowIdCtrl,
                    hint: 'Workflow ID',
                  ),
                ],
                const SizedBox(height: sp12),
                // ── Prompt ───────────────────────────────────────────────
                _TealDialogField(
                  label: 'PROMPT *',
                  controller: _promptCtrl,
                  hint: 'What should the agent do?',
                  maxLines: 3,
                ),
                const SizedBox(height: sp12),
                // ── Interval value + unit ─────────────────────────────────
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    SizedBox(
                      width: 100,
                      child: _TealDialogField(
                        label: 'INTERVAL *',
                        controller: _intervalValueCtrl,
                        hint: '1',
                        keyboardType: TextInputType.number,
                      ),
                    ),
                    const SizedBox(width: sp8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'UNIT',
                            style: TextStyle(
                              fontFamily: fontBody,
                              fontSize: 9,
                              color: textMuted,
                              letterSpacing: 0.8,
                            ),
                          ),
                          const SizedBox(height: sp4),
                          Container(
                            decoration: BoxDecoration(
                              border: Border.all(
                                color: accentTeal.withAlpha(80),
                              ),
                              borderRadius: BorderRadius.circular(2),
                            ),
                            padding: const EdgeInsets.symmetric(
                              horizontal: sp8,
                            ),
                            child: DropdownButton<String>(
                              value: _intervalUnit,
                              isExpanded: true,
                              underline: const SizedBox(),
                              dropdownColor: cardBg,
                              style: const TextStyle(
                                fontFamily: fontBody,
                                fontSize: 11,
                                color: textPrimary,
                              ),
                              items: _kIntervalUnits
                                  .map(
                                    (u) => DropdownMenuItem<String>(
                                      value: u,
                                      child: Text(
                                        u,
                                        style: const TextStyle(
                                          fontFamily: fontBody,
                                          fontSize: 11,
                                          color: textPrimary,
                                        ),
                                      ),
                                    ),
                                  )
                                  .toList(),
                              onChanged: (val) {
                                if (val != null) {
                                  setState(() => _intervalUnit = val);
                                }
                              },
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: sp12),
                // ── Start at ─────────────────────────────────────────────
                _TealDialogField(
                  label: widget.isEdit
                      ? 'START AT (optional, ISO datetime)'
                      : 'START AT *',
                  controller: _startAtCtrl,
                  hint: 'e.g. 2025-01-01T00:00:00Z',
                ),
                if (_startAtError != null) ...[
                  const SizedBox(height: sp4),
                  Text(
                    _startAtError!,
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: 10,
                      color: Colors.redAccent,
                    ),
                  ),
                ],
                const SizedBox(height: sp12),
                // ── End at (optional) ────────────────────────────────────
                _TealDialogField(
                  label: 'END AT (optional, ISO datetime)',
                  controller: _endAtCtrl,
                  hint: 'e.g. 2025-12-31T23:59:59Z',
                ),
                const SizedBox(height: sp24),
                // ── Actions ──────────────────────────────────────────────
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
                          : (widget.isEdit ? 'UPDATE' : 'CREATE'),
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

// ---------------------------------------------------------------------------
// _TealDialogField — labelled text input with teal accent (for scheduled agents)
// ---------------------------------------------------------------------------

class _TealDialogField extends StatelessWidget {
  const _TealDialogField({
    required this.label,
    required this.controller,
    this.hint = '',
    this.maxLines = 1,
    this.keyboardType = TextInputType.text,
  });

  final String label;
  final TextEditingController controller;
  final String hint;
  final int maxLines;
  final TextInputType keyboardType;

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
            border: Border.all(color: accentTeal.withAlpha(80)),
            borderRadius: BorderRadius.circular(2),
          ),
          padding: const EdgeInsets.symmetric(horizontal: sp8),
          child: TextField(
            controller: controller,
            keyboardType:
                maxLines > 1 ? TextInputType.multiline : keyboardType,
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
            ),
          ),
        ),
      ],
    );
  }
}

// Shared helpers --------------------------------------------------------

// ---------------------------------------------------------------------------
// _ConfirmDeleteDialog — reusable delete confirmation
// ---------------------------------------------------------------------------

class _ConfirmDeleteDialog extends StatelessWidget {
  const _ConfirmDeleteDialog({
    required this.message,
    this.accentColor = accentPrimary,
  });

  final String message;
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
          constraints: const BoxConstraints(maxWidth: 360, minWidth: 260),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    Icons.warning_amber_outlined,
                    color: accentColor,
                    size: 20,
                  ),
                  const SizedBox(width: sp8),
                  const Expanded(
                    child: Text(
                      'CONFIRM DELETE',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: 13,
                        color: accentPrimary,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: sp16),
              Text(
                message,
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
                    color: accentPrimary,
                    onPressed: () => Navigator.of(context).pop(true),
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
// _AmberDialogField — labelled text input with amber accent (for tokens)
// ---------------------------------------------------------------------------

class _AmberDialogField extends StatelessWidget {
  const _AmberDialogField({
    required this.label,
    required this.controller,
    this.hint = '',
    this.readOnly = false,
  });

  final String label;
  final TextEditingController controller;
  final String hint;
  final bool readOnly;

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
            color: readOnly ? Colors.black12 : null,
            border: Border.all(
              color: readOnly
                  ? textMuted.withAlpha(40)
                  : accentAmber.withAlpha(80),
            ),
            borderRadius: BorderRadius.circular(2),
          ),
          padding: const EdgeInsets.symmetric(horizontal: sp8),
          child: TextField(
            controller: controller,
            readOnly: readOnly,
            style: TextStyle(
              fontFamily: fontBody,
              fontSize: 12,
              color: readOnly ? textMuted : textPrimary,
            ),
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: const TextStyle(
                fontFamily: fontBody,
                fontSize: 12,
                color: textMuted,
              ),
              border: InputBorder.none,
            ),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _SlateDialogField — labelled text input with slate accent (for providers)
// ---------------------------------------------------------------------------

class _SlateDialogField extends StatelessWidget {
  const _SlateDialogField({
    required this.label,
    required this.controller,
    this.hint = '',
  });

  final String label;
  final TextEditingController controller;
  final String hint;

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
            border: Border.all(color: accentSlate.withAlpha(120)),
            borderRadius: BorderRadius.circular(2),
          ),
          padding: const EdgeInsets.symmetric(horizontal: sp8),
          child: TextField(
            controller: controller,
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
            ),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _TokenCard — displays a single token with edit / delete actions
// ---------------------------------------------------------------------------

class _TokenCard extends StatelessWidget {
  const _TokenCard({
    required this.token,
    required this.client,
    required this.onSaved,
    required this.onDelete,
  });

  final _TokenRef token;
  final http.Client client;
  final VoidCallback onSaved;
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
              // ── Header row ─────────────────────────────────────────────
              Row(
                children: [
                  const Icon(
                    Icons.key_outlined,
                    size: 14,
                    color: accentAmber,
                  ),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: Text(
                      token.name,
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: fontSizeBody,
                        color: textPrimary,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  RetroButton(
                    label: 'EDIT',
                    icon: Icons.edit_outlined,
                    color: accentAmber,
                    textColor: textPrimary,
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _TokenDialog(
                        client: client,
                        onSaved: onSaved,
                        isEdit: true,
                        token: token,
                      ),
                    ),
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
              // ── Masked value ────────────────────────────────────────────
              if (token.maskedValue.isNotEmpty) ...[
                const SizedBox(height: sp8),
                Text(
                  token.maskedValue,
                  style: const TextStyle(
                    fontFamily: fontFallback,
                    fontSize: fontSizeSmall,
                    color: textMuted,
                    letterSpacing: 2,
                  ),
                ),
              ],
              // ── Description ─────────────────────────────────────────────
              if (token.description.isNotEmpty) ...[
                const SizedBox(height: sp4),
                Text(
                  token.description,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeSmall,
                    color: textMuted,
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
// _TokenDialog — create / edit a token
// ---------------------------------------------------------------------------

class _TokenDialog extends StatefulWidget {
  const _TokenDialog({
    required this.client,
    required this.onSaved,
    required this.isEdit,
    this.token,
  });

  final http.Client client;
  final VoidCallback onSaved;
  final bool isEdit;
  final _TokenRef? token;

  @override
  State<_TokenDialog> createState() => _TokenDialogState();
}

class _TokenDialogState extends State<_TokenDialog> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _valueCtrl;
  late final TextEditingController _descCtrl;
  bool _saving = false;
  bool _obscureValue = true;

  @override
  void initState() {
    super.initState();
    _nameCtrl = TextEditingController(text: widget.token?.name ?? '');
    _valueCtrl = TextEditingController();
    _descCtrl = TextEditingController(
      text: widget.token?.description ?? '',
    );
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _valueCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!widget.isEdit && _nameCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Name is required.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    if (!widget.isEdit && _valueCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Value is required.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final http.Response response;
      if (widget.isEdit) {
        response = await widget.client.put(
          AppLinks.apiUri('/tokens/${widget.token!.id}'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            if (_valueCtrl.text.trim().isNotEmpty)
              'value': _valueCtrl.text.trim(),
            'description': _descCtrl.text.trim(),
          }),
        );
      } else {
        response = await widget.client.post(
          AppLinks.apiUri('/tokens'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'name': _nameCtrl.text.trim(),
            'value': _valueCtrl.text.trim(),
            'description': _descCtrl.text.trim(),
          }),
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ?? 'Save failed (${response.statusCode})',
        );
      }
      if (!mounted) return;
      widget.onSaved();
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            widget.isEdit ? 'Token updated.' : 'Token created.',
          ),
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
          constraints: const BoxConstraints(maxWidth: 480, minWidth: 320),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Header ─────────────────────────────────────────────────
              Row(
                children: [
                  const Icon(
                    Icons.key_outlined,
                    color: accentAmber,
                    size: 20,
                  ),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: Text(
                      widget.isEdit ? 'EDIT TOKEN' : 'NEW TOKEN',
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
              // ── Name ───────────────────────────────────────────────────
              _AmberDialogField(
                label: widget.isEdit ? 'NAME (read-only)' : 'NAME *',
                controller: _nameCtrl,
                hint: 'my-api-key',
                readOnly: widget.isEdit,
              ),
              const SizedBox(height: sp12),
              // ── Value (obscured) ───────────────────────────────────────
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    widget.isEdit
                        ? 'NEW VALUE (leave blank to keep existing)'
                        : 'VALUE *',
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
                    padding: const EdgeInsets.symmetric(horizontal: sp8),
                    child: Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _valueCtrl,
                            obscureText: _obscureValue,
                            style: const TextStyle(
                              fontFamily: fontBody,
                              fontSize: 12,
                              color: textPrimary,
                            ),
                            decoration: const InputDecoration(
                              hintText: '••••••••',
                              hintStyle: TextStyle(
                                fontFamily: fontBody,
                                fontSize: 12,
                                color: textMuted,
                              ),
                              border: InputBorder.none,
                            ),
                          ),
                        ),
                        IconButton(
                          icon: Icon(
                            _obscureValue
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                            size: 16,
                            color: textMuted,
                          ),
                          onPressed: () =>
                              setState(() => _obscureValue = !_obscureValue),
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: sp12),
              // ── Description ────────────────────────────────────────────
              _AmberDialogField(
                label: 'DESCRIPTION',
                controller: _descCtrl,
                hint: 'Optional description',
              ),
              const SizedBox(height: sp24),
              // ── Actions ────────────────────────────────────────────────
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
                        : (widget.isEdit ? 'UPDATE' : 'CREATE'),
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
    );
  }
}

// ---------------------------------------------------------------------------
// _ProviderCard — displays a single provider with edit / delete actions
// ---------------------------------------------------------------------------

const _kProviderTypes = <String>[
  'github_copilot',
  'openai',
  'anthropic',
  'azure_openai',
  'custom',
];

class _ProviderCard extends StatelessWidget {
  const _ProviderCard({
    required this.provider,
    required this.client,
    required this.onSaved,
    required this.onDelete,
  });

  final _Provider provider;
  final http.Client client;
  final VoidCallback onSaved;
  final VoidCallback onDelete;

  Color get _chipColor {
    switch (provider.providerType) {
      case 'openai':
        return accentTeal;
      case 'anthropic':
        return accentLavender;
      case 'azure_openai':
        return accentSlate;
      case 'github_copilot':
        return accentAmber;
      default:
        return textMuted;
    }
  }

  Color get _chipTextColor {
    switch (provider.providerType) {
      case 'github_copilot':
        return textPrimary;
      default:
        return cardBg;
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
              // ── Header row ─────────────────────────────────────────────
              Row(
                children: [
                  const Icon(
                    Icons.business_outlined,
                    size: 14,
                    color: accentSlate,
                  ),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: Text(
                      provider.name,
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: fontSizeBody,
                        color: textPrimary,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  RetroChip(
                    label: provider.providerType,
                    color: _chipColor,
                    textColor: _chipTextColor,
                  ),
                ],
              ),
              // ── Meta row ───────────────────────────────────────────────
              const SizedBox(height: sp8),
              Wrap(
                spacing: sp12,
                runSpacing: sp4,
                children: [
                  _WfMetaItem(
                    icon: Icons.key_outlined,
                    label: provider.apiKeyTokenName,
                  ),
                  if (provider.baseUrl != null &&
                      provider.baseUrl!.isNotEmpty)
                    _WfMetaItem(
                      icon: Icons.link_outlined,
                      label: provider.baseUrl!,
                    ),
                  if (provider.description.isNotEmpty)
                    _WfMetaItem(
                      icon: Icons.info_outline,
                      label: provider.description,
                    ),
                ],
              ),
              // ── Actions ────────────────────────────────────────────────
              const SizedBox(height: sp12),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'EDIT',
                    icon: Icons.edit_outlined,
                    color: accentSlate,
                    onPressed: () => showDialog<void>(
                      context: context,
                      builder: (_) => _ProviderDialog(
                        client: client,
                        onSaved: onSaved,
                        provider: provider,
                      ),
                    ),
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

// ---------------------------------------------------------------------------
// _ProviderDialog — create / edit a provider
// ---------------------------------------------------------------------------

class _ProviderDialog extends StatefulWidget {
  const _ProviderDialog({
    required this.client,
    required this.onSaved,
    this.provider,
  });

  final http.Client client;
  final VoidCallback onSaved;
  final _Provider? provider;

  bool get isEdit => provider != null;

  @override
  State<_ProviderDialog> createState() => _ProviderDialogState();
}

class _ProviderDialogState extends State<_ProviderDialog> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _apiKeyTokenNameCtrl;
  late final TextEditingController _baseUrlCtrl;
  late final TextEditingController _descCtrl;
  late String _providerType;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _nameCtrl = TextEditingController(text: widget.provider?.name ?? '');
    _apiKeyTokenNameCtrl = TextEditingController(
      text: widget.provider?.apiKeyTokenName ?? '',
    );
    _baseUrlCtrl = TextEditingController(
      text: widget.provider?.baseUrl ?? '',
    );
    _descCtrl = TextEditingController(
      text: widget.provider?.description ?? '',
    );
    final stored = widget.provider?.providerType ?? _kProviderTypes.first;
    _providerType =
        _kProviderTypes.contains(stored) ? stored : _kProviderTypes.first;
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _apiKeyTokenNameCtrl.dispose();
    _baseUrlCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_nameCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Name is required.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    if (_apiKeyTokenNameCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('API Key Token Name is required.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final body = <String, dynamic>{
        'name': _nameCtrl.text.trim(),
        'provider_type': _providerType,
        'api_key_token_name': _apiKeyTokenNameCtrl.text.trim(),
        if (_baseUrlCtrl.text.trim().isNotEmpty)
          'base_url': _baseUrlCtrl.text.trim(),
        'description': _descCtrl.text.trim(),
      };
      final http.Response response;
      if (widget.isEdit) {
        response = await widget.client.put(
          AppLinks.apiUri('/providers/${widget.provider!.id}'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        );
      } else {
        response = await widget.client.post(
          AppLinks.apiUri('/providers'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ?? 'Save failed (${response.statusCode})',
        );
      }
      if (!mounted) return;
      widget.onSaved();
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            widget.isEdit ? 'Provider updated.' : 'Provider created.',
          ),
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
        side: const BorderSide(color: accentSlate, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480, minWidth: 320),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // ── Header ───────────────────────────────────────────────
                Row(
                  children: [
                    const Icon(
                      Icons.business_outlined,
                      color: accentSlate,
                      size: 20,
                    ),
                    const SizedBox(width: sp8),
                    Expanded(
                      child: Text(
                        widget.isEdit ? 'EDIT PROVIDER' : 'NEW PROVIDER',
                        style: const TextStyle(
                          fontFamily: fontBody,
                          fontSize: 13,
                          color: accentSlate,
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
                // ── Name ─────────────────────────────────────────────────
                _SlateDialogField(
                  label: 'NAME *',
                  controller: _nameCtrl,
                  hint: 'my-openai-provider',
                ),
                const SizedBox(height: sp12),
                // ── Provider type dropdown ────────────────────────────────
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'PROVIDER TYPE *',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: 9,
                        color: textMuted,
                        letterSpacing: 0.8,
                      ),
                    ),
                    const SizedBox(height: sp4),
                    Container(
                      decoration: BoxDecoration(
                        border:
                            Border.all(color: accentSlate.withAlpha(120)),
                        borderRadius: BorderRadius.circular(2),
                      ),
                      padding:
                          const EdgeInsets.symmetric(horizontal: sp8),
                      child: DropdownButton<String>(
                        value: _providerType,
                        isExpanded: true,
                        underline: const SizedBox(),
                        dropdownColor: cardBg,
                        style: const TextStyle(
                          fontFamily: fontBody,
                          fontSize: 11,
                          color: textPrimary,
                        ),
                        items: _kProviderTypes
                            .map(
                              (t) => DropdownMenuItem<String>(
                                value: t,
                                child: Text(
                                  t,
                                  style: const TextStyle(
                                    fontFamily: fontBody,
                                    fontSize: 11,
                                    color: textPrimary,
                                  ),
                                ),
                              ),
                            )
                            .toList(),
                        onChanged: (val) {
                          if (val != null) {
                            setState(() => _providerType = val);
                          }
                        },
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: sp12),
                // ── API key token name ────────────────────────────────────
                _SlateDialogField(
                  label: 'API KEY TOKEN NAME *',
                  controller: _apiKeyTokenNameCtrl,
                  hint: 'my-openai-key',
                ),
                const SizedBox(height: sp4),
                const Text(
                  'The name of the stored token holding the API key.',
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: 9,
                    color: textMuted,
                  ),
                ),
                const SizedBox(height: sp12),
                // ── Base URL ─────────────────────────────────────────────
                _SlateDialogField(
                  label: 'BASE URL (optional)',
                  controller: _baseUrlCtrl,
                  hint: 'https://api.openai.com/v1',
                ),
                if (_providerType == 'anthropic') ...[
                  const SizedBox(height: sp4),
                  const Text(
                    'Uses the Anthropic Claude Agent SDK — leave blank for the default '
                    'Anthropic endpoint. For a self-hosted LiteLLM proxy that implements '
                    'the full Anthropic beta APIs, set base_url to your proxy '
                    '(e.g. http://localhost:4000).\n'
                    'NOTE: OpenRouter is NOT compatible with this provider type — it only '
                    'supports the OpenAI-compatible API. To use OpenRouter, choose '
                    "'custom' type with base_url 'https://openrouter.ai/api/v1'.",
                    style: TextStyle(
                      fontFamily: fontBody,
                      fontSize: 9,
                      color: textMuted,
                    ),
                  ),
                ],
                const SizedBox(height: sp12),
                // ── Description ──────────────────────────────────────────
                _SlateDialogField(
                  label: 'DESCRIPTION',
                  controller: _descCtrl,
                  hint: 'Optional description',
                ),
                const SizedBox(height: sp24),
                // ── Actions ──────────────────────────────────────────────
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    RetroButton(
                      label: 'CANCEL',
                      onPressed: () => Navigator.of(context).pop(),
                      color: accentTeal,
                    ),
                    const SizedBox(width: sp8),
                    RetroButton(
                      label: _saving
                          ? 'SAVING…'
                          : (widget.isEdit ? 'UPDATE' : 'CREATE'),
                      onPressed: _saving ? null : _save,
                      color: accentSlate,
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
