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

// Data models ---------------------------------------------------------------

class _AggregatedEntry {
  String providerId;
  String model;
  int priority;
  _AggregatedEntry({required this.providerId, this.model = '', this.priority = 0});
  factory _AggregatedEntry.fromJson(Map<String, dynamic> j) => _AggregatedEntry(
    providerId: j['provider_id'] as String,
    model: j['model'] as String? ?? '',
    priority: (j['priority'] as num?)?.toInt() ?? 0,
  );
  Map<String, dynamic> toJson() => {
    'provider_id': providerId,
    'model': model,
    'priority': priority,
  };
}

class _ProviderItem {
  final String id;
  final String name;
  final String providerType;
  final String? apiKeyTokenName;
  final String? baseUrl;
  final String azureApiVersion;
  final String? azureDeployment;
  final String description;
  final List<_AggregatedEntry> aggregatedProviders;

  const _ProviderItem({
    required this.id,
    required this.name,
    required this.providerType,
    this.apiKeyTokenName,
    this.baseUrl,
    this.azureApiVersion = '2024-12-01-preview',
    this.azureDeployment,
    this.description = '',
    this.aggregatedProviders = const [],
  });

  bool get isAuto => providerType == 'auto';

  factory _ProviderItem.fromJson(Map<String, dynamic> j) => _ProviderItem(
    id: j['id'] as String,
    name: j['name'] as String,
    providerType: j['provider_type'] as String,
    apiKeyTokenName: j['api_key_token_name'] as String?,
    baseUrl: j['base_url'] as String?,
    azureApiVersion: j['azure_api_version'] as String? ?? '2024-12-01-preview',
    azureDeployment: j['azure_deployment'] as String?,
    description: j['description'] as String? ?? '',
    aggregatedProviders: (j['aggregated_providers'] as List<dynamic>? ?? [])
        .map((e) => _AggregatedEntry.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

// ProvidersScreen -----------------------------------------------------------

class ProvidersScreen extends StatefulWidget {
  const ProvidersScreen({super.key});

  @override
  State<ProvidersScreen> createState() => _ProvidersScreenState();
}

class _ProvidersScreenState extends State<ProvidersScreen> {
  final _client = http.Client();
  List<_ProviderItem>? _providers;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await _client.get(AppLinks.apiUri('/providers'));
      if (!mounted) return;
      if (res.statusCode == 200) {
        final list = (jsonDecode(res.body) as List)
            .map((e) => _ProviderItem.fromJson(e as Map<String, dynamic>))
            .toList();
        setState(() {
          _providers = list;
          _loading = false;
        });
      } else {
        setState(() {
          _error = 'Failed to load (${res.statusCode})';
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  Future<void> _delete(_ProviderItem p) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete Provider'),
        content: Text('Delete "${p.name}"?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final res = await _client.delete(AppLinks.apiUri('/providers/${p.id}'));
    if (res.statusCode == 204) {
      _load();
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Delete failed (${res.statusCode})')),
        );
      }
    }
  }

  void _openForm([_ProviderItem? existing]) async {
    final saved = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => _ProviderFormDialog(
        existing: existing,
        allProviders: _providers ?? [],
        client: _client,
      ),
    );
    if (saved == true) _load();
  }

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
                onPressed: () => _openForm(),
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
            child: _buildBody(),
          ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.all(sp24),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null) {
      return Padding(
        padding: const EdgeInsets.all(sp16),
        child: Text(_error!, style: const TextStyle(color: Colors.red)),
      );
    }
    final providers = _providers ?? [];
    if (providers.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(sp16),
        child: _EmptyState(
          icon: Icons.business_outlined,
          message: 'No providers configured.',
          hint: 'Add a provider to route agents through custom LLM endpoints.',
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.all(sp16),
      child: Column(
        children: providers
            .map(
              (p) => _ProviderRow(
                provider: p,
                onEdit: () => _openForm(p),
                onDelete: () => _delete(p),
              ),
            )
            .toList(),
      ),
    );
  }
}

// Provider row widget -------------------------------------------------------

class _ProviderRow extends StatelessWidget {
  const _ProviderRow({
    required this.provider,
    required this.onEdit,
    required this.onDelete,
  });

  final _ProviderItem provider;
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final typeColor = provider.isAuto ? accentAmber : accentSlate;
    return Container(
      margin: const EdgeInsets.only(bottom: sp8),
      padding: const EdgeInsets.symmetric(horizontal: sp16, vertical: sp12),
      decoration: BoxDecoration(
        border: Border.all(color: borderColor),
        color: cardBg,
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  provider.name,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontWeight: FontWeight.bold,
                    color: textPrimary,
                  ),
                ),
                if (provider.description.isNotEmpty)
                  Text(
                    provider.description,
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: 12,
                      color: textMuted,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: sp16),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: sp8, vertical: 2),
            decoration: BoxDecoration(
              color: typeColor.withValues(alpha: 0.15),
              border: Border.all(color: typeColor),
            ),
            child: Text(
              provider.providerType,
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: 11,
                color: typeColor,
              ),
            ),
          ),
          const SizedBox(width: sp16),
          Expanded(
            child: provider.isAuto
                ? Text(
                    '${provider.aggregatedProviders.length} sub-provider(s)',
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: 12,
                      color: textMuted,
                    ),
                  )
                : Text(
                    provider.apiKeyTokenName ?? '—',
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: 12,
                      color: textMuted,
                    ),
                  ),
          ),
          const SizedBox(width: sp8),
          RetroButton(label: 'EDIT', onPressed: onEdit, color: accentSlate),
          const SizedBox(width: sp8),
          RetroButton(
            label: 'DELETE',
            onPressed: onDelete,
            color: const Color(0xFFE8434B),
          ),
        ],
      ),
    );
  }
}

// Provider form dialog ------------------------------------------------------

class _ProviderFormDialog extends StatefulWidget {
  const _ProviderFormDialog({
    this.existing,
    required this.allProviders,
    required this.client,
  });

  final _ProviderItem? existing;
  final List<_ProviderItem> allProviders;
  final http.Client client;

  @override
  State<_ProviderFormDialog> createState() => _ProviderFormDialogState();
}

class _ProviderFormDialogState extends State<_ProviderFormDialog> {
  final _nameCtrl = TextEditingController();
  final _tokenCtrl = TextEditingController();
  final _baseUrlCtrl = TextEditingController();
  final _azureVersionCtrl = TextEditingController();
  final _azureDeploymentCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  String _providerType = 'openai';
  List<_AggregatedEntry> _aggregatedEntries = [];
  bool _saving = false;
  String? _formError;

  static const _allTypes = [
    'github_copilot',
    'openai',
    'anthropic',
    'azure_openai',
    'custom',
    'auto',
  ];

  // Only BYOK HTTP types are valid sub-providers for AUTO
  static const _byokHttpTypes = ['openai', 'azure_openai', 'custom'];

  List<_ProviderItem> get _byokProviders => widget.allProviders
      .where(
        (p) =>
            _byokHttpTypes.contains(p.providerType) &&
            (widget.existing == null || p.id != widget.existing!.id),
      )
      .toList();

  @override
  void initState() {
    super.initState();
    final p = widget.existing;
    if (p != null) {
      _nameCtrl.text = p.name;
      _tokenCtrl.text = p.apiKeyTokenName ?? '';
      _baseUrlCtrl.text = p.baseUrl ?? '';
      _azureVersionCtrl.text = p.azureApiVersion;
      _azureDeploymentCtrl.text = p.azureDeployment ?? '';
      _descCtrl.text = p.description;
      _providerType = p.providerType;
      _aggregatedEntries = p.aggregatedProviders
          .map(
            (e) => _AggregatedEntry(
              providerId: e.providerId,
              model: e.model,
              priority: e.priority,
            ),
          )
          .toList();
    } else {
      _azureVersionCtrl.text = '2024-12-01-preview';
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _tokenCtrl.dispose();
    _baseUrlCtrl.dispose();
    _azureVersionCtrl.dispose();
    _azureDeploymentCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _formError = null;
    });

    final name = _nameCtrl.text.trim();
    if (name.isEmpty) {
      setState(() {
        _saving = false;
        _formError = 'Name is required';
      });
      return;
    }

    final Map<String, dynamic> body = {
      'name': name,
      'provider_type': _providerType,
      'description': _descCtrl.text.trim(),
    };

    if (_providerType == 'auto') {
      if (_aggregatedEntries.isEmpty) {
        setState(() {
          _saving = false;
          _formError = 'Add at least one sub-provider';
        });
        return;
      }
      for (final e in _aggregatedEntries) {
        if (e.providerId.isEmpty || e.model.isEmpty) {
          setState(() {
            _saving = false;
            _formError = 'Each sub-provider needs a provider and model';
          });
          return;
        }
      }
      body['aggregated_providers'] =
          _aggregatedEntries.map((e) => e.toJson()).toList();
    } else {
      final token = _tokenCtrl.text.trim();
      if (token.isEmpty) {
        setState(() {
          _saving = false;
          _formError = 'API Key Token Name is required';
        });
        return;
      }
      body['api_key_token_name'] = token;
      if (_baseUrlCtrl.text.trim().isNotEmpty) {
        body['base_url'] = _baseUrlCtrl.text.trim();
      }
      if (_providerType == 'azure_openai') {
        body['azure_api_version'] = _azureVersionCtrl.text.trim().isNotEmpty
            ? _azureVersionCtrl.text.trim()
            : '2024-12-01-preview';
        if (_azureDeploymentCtrl.text.trim().isNotEmpty) {
          body['azure_deployment'] = _azureDeploymentCtrl.text.trim();
        }
      }
    }

    final id = widget.existing?.id;
    final uri = id != null
        ? AppLinks.apiUri('/providers/$id')
        : AppLinks.apiUri('/providers');
    final res = id != null
        ? await widget.client.put(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
        : await widget.client.post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          );

    if (!mounted) return;
    if (res.statusCode == 200 || res.statusCode == 201) {
      Navigator.of(context).pop(true);
    } else {
      String msg = 'Save failed (${res.statusCode})';
      try {
        msg = (jsonDecode(res.body) as Map)['detail']?.toString() ?? msg;
      } catch (_) {}
      setState(() {
        _saving = false;
        _formError = msg;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.existing != null ? 'Edit Provider' : 'Add Provider'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_formError != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: sp8),
                  child: Text(
                    _formError!,
                    style: const TextStyle(color: Colors.red, fontSize: 13),
                  ),
                ),
              _field('Name', _nameCtrl, hint: 'e.g. my-openai'),
              const SizedBox(height: sp12),
              const Text(
                'Provider Type',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: sp4),
              DropdownButtonFormField<String>(
                initialValue: _providerType,
                items: _allTypes
                    .map((t) => DropdownMenuItem(value: t, child: Text(t)))
                    .toList(),
                onChanged: (v) {
                  if (v != null) setState(() => _providerType = v);
                },
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
              ),
              const SizedBox(height: sp12),
              if (_providerType != 'auto') ...[
                _field(
                  'API Key Token Name',
                  _tokenCtrl,
                  hint: 'Name of token in Token Store',
                ),
                const SizedBox(height: sp12),
                _field(
                  'Base URL',
                  _baseUrlCtrl,
                  hint: 'Optional; required for azure_openai/custom',
                ),
                if (_providerType == 'azure_openai') ...[
                  const SizedBox(height: sp12),
                  _field(
                    'Azure API Version',
                    _azureVersionCtrl,
                    hint: '2024-12-01-preview',
                  ),
                  const SizedBox(height: sp12),
                  _field(
                    'Azure Deployment',
                    _azureDeploymentCtrl,
                    hint: 'Optional; defaults to model name',
                  ),
                ],
              ],
              if (_providerType == 'auto') ...[
                const SizedBox(height: sp8),
                const Text(
                  'Sub-Providers',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
                ),
                const SizedBox(height: sp4),
                const Text(
                  'Tried in ascending priority order (0 = highest).',
                  style: TextStyle(fontSize: 12, color: textMuted),
                ),
                const SizedBox(height: sp8),
                ..._aggregatedEntries.asMap().entries.map(
                  (e) => _SubProviderRow(
                    key: ValueKey(e.key),
                    entry: e.value,
                    availableProviders: _byokProviders,
                    onRemove: () =>
                        setState(() => _aggregatedEntries.removeAt(e.key)),
                    onChanged: () => setState(() {}),
                  ),
                ),
                TextButton.icon(
                  onPressed: _byokProviders.isEmpty
                      ? null
                      : () {
                          setState(
                            () => _aggregatedEntries.add(
                              _AggregatedEntry(
                                providerId: _byokProviders.first.id,
                              ),
                            ),
                          );
                        },
                  icon: const Icon(Icons.add),
                  label: Text(
                    _byokProviders.isEmpty
                        ? 'No BYOK providers available'
                        : 'Add Sub-Provider',
                  ),
                ),
              ],
              const SizedBox(height: sp12),
              _field('Description', _descCtrl, hint: 'Optional description'),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: _saving ? null : _save,
          child: _saving
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(widget.existing != null ? 'Update' : 'Create'),
        ),
      ],
    );
  }

  Widget _field(
    String label,
    TextEditingController ctrl, {
    String? hint,
  }) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
          ),
          const SizedBox(height: sp4),
          TextField(
            controller: ctrl,
            decoration: InputDecoration(
              hintText: hint,
              border: const OutlineInputBorder(),
              isDense: true,
              contentPadding: const EdgeInsets.all(sp8),
            ),
          ),
        ],
      );
}

// Sub-provider row (inside AUTO form) ---------------------------------------

class _SubProviderRow extends StatelessWidget {
  const _SubProviderRow({
    super.key,
    required this.entry,
    required this.availableProviders,
    required this.onRemove,
    required this.onChanged,
  });

  final _AggregatedEntry entry;
  final List<_ProviderItem> availableProviders;
  final VoidCallback onRemove;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final modelCtrl = TextEditingController(text: entry.model);
    final priorityCtrl = TextEditingController(text: entry.priority.toString());
    return Padding(
      padding: const EdgeInsets.only(bottom: sp8),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: DropdownButtonFormField<String>(
              initialValue: availableProviders.any((p) => p.id == entry.providerId)
                  ? entry.providerId
                  : (availableProviders.isNotEmpty
                      ? availableProviders.first.id
                      : null),
              items: availableProviders
                  .map(
                    (p) => DropdownMenuItem(
                      value: p.id,
                      child: Text(
                        '${p.name} (${p.providerType})',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  )
                  .toList(),
              onChanged: (v) {
                if (v != null) {
                  entry.providerId = v;
                  onChanged();
                }
              },
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                isDense: true,
                labelText: 'Provider',
              ),
            ),
          ),
          const SizedBox(width: sp8),
          Expanded(
            flex: 2,
            child: TextField(
              controller: modelCtrl,
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                isDense: true,
                labelText: 'Model',
              ),
              onChanged: (v) => entry.model = v,
            ),
          ),
          const SizedBox(width: sp8),
          SizedBox(
            width: 72,
            child: TextField(
              controller: priorityCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                isDense: true,
                labelText: 'Priority',
              ),
              onChanged: (v) => entry.priority = int.tryParse(v) ?? 0,
            ),
          ),
          IconButton(
            icon: const Icon(Icons.remove_circle_outline, color: Colors.red),
            onPressed: onRemove,
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// WorkflowsScreen — workflow definitions list
// ---------------------------------------------------------------------------
class WorkflowsScreen extends StatelessWidget {
  const WorkflowsScreen({super.key});

  @override
  Widget build(BuildContext context) {
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
                label: 'NEW WORKFLOW',
                onPressed: () {},
                icon: Icons.add,
                color: accentLavender,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Workflow Definitions',
            accentColor: accentLavender,
            minHeight: 300,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.account_tree_outlined,
                message: 'No workflows defined.',
              ),
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
