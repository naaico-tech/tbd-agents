import 'package:flutter/material.dart';
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
