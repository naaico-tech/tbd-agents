import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../../core/config/app_links.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/export_import_dialog.dart';
import '../../core/widgets/retro_card.dart';

// ---------------------------------------------------------------------------
// AgentsScreen — lists agents; shell-ready for /api/agents data.
// ---------------------------------------------------------------------------
class AgentsScreen extends StatelessWidget {
  const AgentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
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
                label: 'NEW AGENT',
                onPressed: () {},
                icon: Icons.add,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Agent Registry',
            accentColor: accentTeal,
            minHeight: 300,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: Center(
                child: _EmptyState(
                  icon: Icons.smart_toy_outlined,
                  message: 'No agents configured yet.',
                  hint: 'Create an agent to get started.',
                ),
              ),
            ),
          ),
          const SizedBox(height: sp24),
          SectionFrame(title: 'Agent Memory', accentColor: accentAmber),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// McpServersScreen
// ---------------------------------------------------------------------------
class McpServersScreen extends StatelessWidget {
  const McpServersScreen({super.key});

  @override
  Widget build(BuildContext context) {
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
                label: 'ADD SERVER',
                onPressed: () {},
                icon: Icons.add,
                color: accentAmber,
                textColor: textPrimary,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Connected Servers',
            accentColor: accentAmber,
            minHeight: 300,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.power_outlined,
                message: 'No MCP servers connected.',
                hint: 'Add a server endpoint to enable tool access.',
              ),
            ),
          ),
        ],
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
                              _ToolCard(tool: tool),
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
                              _ToolCard(tool: tool),
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
  const _ToolCard({required this.tool});

  final _CustomTool tool;

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
            ],
          ),
        ),
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
// SkillsScreen
// ---------------------------------------------------------------------------
class SkillsScreen extends StatelessWidget {
  const SkillsScreen({super.key});

  @override
  Widget build(BuildContext context) {
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
                label: 'INSTALL SKILL',
                onPressed: () {},
                icon: Icons.bolt,
                color: accentLavender,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Installed Skills',
            accentColor: accentLavender,
            minHeight: 280,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.bolt_outlined,
                message: 'No skills installed.',
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// KnowledgeScreen
// ---------------------------------------------------------------------------
class KnowledgeScreen extends StatelessWidget {
  const KnowledgeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ScreenHeader(
            title: 'KNOWLEDGE',
            subtitle: 'Knowledge bases and document stores',
            actions: [
              RetroButton(
                label: 'EXPORT',
                onPressed: () => showExportDialog(
                  context,
                  apiPath: '/knowledge-sources/export',
                  resourceLabel: 'KNOWLEDGE',
                ),
                icon: Icons.download_outlined,
                color: accentTeal,
              ),
              RetroButton(
                label: 'IMPORT',
                onPressed: () => showImportDialog(
                  context,
                  apiPath: '/knowledge-sources/import',
                  resourceLabel: 'KNOWLEDGE',
                ),
                icon: Icons.upload_outlined,
                color: accentTeal,
              ),
              RetroButton(
                label: 'ADD SOURCE',
                onPressed: () {},
                icon: Icons.add,
                color: accentTeal,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Knowledge Sources',
            accentColor: accentTeal,
            minHeight: 280,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.library_books_outlined,
                message: 'No knowledge sources configured.',
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// GuardrailsScreen
// ---------------------------------------------------------------------------
class GuardrailsScreen extends StatelessWidget {
  const GuardrailsScreen({super.key});

  @override
  Widget build(BuildContext context) {
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
                label: 'ADD RULE',
                onPressed: () {},
                icon: Icons.add,
                color: accentPrimary,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Active Guardrails',
            accentColor: accentPrimary,
            minHeight: 280,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.shield_outlined,
                message: 'No guardrails configured.',
              ),
            ),
          ),
        ],
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
