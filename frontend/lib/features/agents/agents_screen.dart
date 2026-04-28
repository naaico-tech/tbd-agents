import 'package:flutter/material.dart';
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
// CustomToolsScreen
// ---------------------------------------------------------------------------
class CustomToolsScreen extends StatelessWidget {
  const CustomToolsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ScreenHeader(
            title: 'CUSTOM TOOLS',
            subtitle: 'User-defined tools available to agents',
            actions: [
              RetroButton(
                label: 'NEW TOOL',
                onPressed: () {},
                icon: Icons.add,
                color: accentSlate,
              ),
            ],
          ),
          const SizedBox(height: sp24),
          SectionFrame(
            title: 'Tool Registry',
            accentColor: accentSlate,
            minHeight: 280,
            child: const Padding(
              padding: EdgeInsets.all(sp16),
              child: _EmptyState(
                icon: Icons.build_outlined,
                message: 'No custom tools defined.',
              ),
            ),
          ),
        ],
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
