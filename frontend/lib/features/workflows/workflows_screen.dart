import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../../core/config/app_links.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/export_import_dialog.dart';
import '../../core/widgets/retro_card.dart';

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
  });

  final String id;
  final String title;
  final String agentId;
  final String model;
  final String status;
  final int maxTurns;
  final Map<String, String> credentialOverrides;

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
                ],
              ),
              // ── EDIT CREDENTIALS button ─────────────────────────────────
              const SizedBox(height: sp12),
              Align(
                alignment: Alignment.centerRight,
                child: RetroButton(
                  label: 'EDIT CREDENTIALS',
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
      backgroundColor: const Color(0xFF1A1A2E),
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
                    dropdownColor: const Color(0xFF1A1A2E),
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
                    dropdownColor: const Color(0xFF1A1A2E),
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
// _WorkflowDialog — create a new workflow
// ---------------------------------------------------------------------------

class _WorkflowDialog extends StatefulWidget {
  const _WorkflowDialog({required this.client, required this.onSaved});

  final http.Client client;
  final VoidCallback onSaved;

  @override
  State<_WorkflowDialog> createState() => _WorkflowDialogState();
}

class _WorkflowDialogState extends State<_WorkflowDialog> {
  final _titleCtrl = TextEditingController();
  final _agentIdCtrl = TextEditingController();
  final _modelCtrl = TextEditingController();
  final _maxTurnsCtrl = TextEditingController(text: '10');
  bool _saving = false;

  @override
  void dispose() {
    _titleCtrl.dispose();
    _agentIdCtrl.dispose();
    _modelCtrl.dispose();
    _maxTurnsCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_agentIdCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Agent ID is required.'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final response = await widget.client.post(
        AppLinks.apiUri('/workflows'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'title': _titleCtrl.text.trim(),
          'agent_id': _agentIdCtrl.text.trim(),
          if (_modelCtrl.text.trim().isNotEmpty) 'model': _modelCtrl.text.trim(),
          'max_turns': int.tryParse(_maxTurnsCtrl.text.trim()) ?? 10,
          'credential_overrides': <String, String>{},
        }),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = jsonDecode(response.body);
        throw Exception(
          decoded['detail'] ?? 'Create failed (${response.statusCode})',
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
      backgroundColor: const Color(0xFF1A1A2E),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(4),
        side: const BorderSide(color: accentLavender, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(sp24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480, minWidth: 320),
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
                  const Expanded(
                    child: Text(
                      'NEW WORKFLOW',
                      style: TextStyle(
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
              _WfDialogField(
                label: 'AGENT ID *',
                controller: _agentIdCtrl,
                hint: 'my-agent',
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
                    label: _saving ? 'SAVING…' : 'CREATE',
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
