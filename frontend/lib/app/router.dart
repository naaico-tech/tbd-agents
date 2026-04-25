import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../core/config/app_links.dart';
import '../core/widgets/app_shell.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/agents/agents_screen.dart';
import '../features/workflows/workflows_exports.dart';
import '../features/run_task/run_task_screen.dart';
import '../features/chat/chat_screen.dart';

// ---------------------------------------------------------------------------
// AppRouter — GoRouter configuration for all named routes.
// All shell routes share [AppShell] as a persistent layout wrapper.
// ---------------------------------------------------------------------------
final appRouter = GoRouter(
  initialLocation: AppLinks.dashboardRoot,
  routes: [
    ShellRoute(
      builder: (context, state, child) =>
          _ShellWrapper(state: state, child: child),
      routes: [
        GoRoute(
          path: AppLinks.dashboardRoot,
          builder: (context, state) => const DashboardScreen(),
        ),
        GoRoute(
          path: AppLinks.agents,
          builder: (context, state) => const AgentsScreen(),
        ),
        GoRoute(
          path: AppLinks.mcpServers,
          builder: (context, state) => const McpServersScreen(),
        ),
        GoRoute(
          path: AppLinks.customTools,
          builder: (context, state) => const CustomToolsScreen(),
        ),
        GoRoute(
          path: AppLinks.skills,
          builder: (context, state) => const SkillsScreen(),
        ),
        GoRoute(
          path: AppLinks.knowledge,
          builder: (context, state) => const KnowledgeScreen(),
        ),
        GoRoute(
          path: AppLinks.guardrails,
          builder: (context, state) => const GuardrailsScreen(),
        ),
        GoRoute(
          path: AppLinks.tokens,
          builder: (context, state) => const TokensScreen(),
        ),
        GoRoute(
          path: AppLinks.providers,
          builder: (context, state) => const ProvidersScreen(),
        ),
        GoRoute(
          path: AppLinks.workflows,
          builder: (context, state) => const WorkflowsScreen(),
        ),
        GoRoute(
          path: AppLinks.tasks,
          builder: (context, state) => const TasksScreen(),
        ),
        GoRoute(
          path: AppLinks.scheduledAgents,
          builder: (context, state) => const ScheduledAgentsScreen(),
        ),
        GoRoute(
          path: AppLinks.runTask,
          builder: (context, state) => const RunTaskScreen(),
        ),
        GoRoute(
          path: AppLinks.chat,
          builder: (context, state) => const ChatScreen(),
        ),
      ],
    ),
  ],
);

class _ShellWrapper extends StatelessWidget {
  const _ShellWrapper({required this.state, required this.child});

  final GoRouterState state;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final route = state.uri.path;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: AppShell(currentRoute: route, child: child),
    );
  }
}
