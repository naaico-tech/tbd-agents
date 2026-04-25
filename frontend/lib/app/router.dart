import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
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
  initialLocation: '/dashboard',
  routes: [
    ShellRoute(
      builder: (context, state, child) =>
          _ShellWrapper(state: state, child: child),
      routes: [
        GoRoute(
          path: '/dashboard',
          builder: (context, state) => const DashboardScreen(),
        ),
        GoRoute(
          path: '/agents',
          builder: (context, state) => const AgentsScreen(),
        ),
        GoRoute(
          path: '/mcp-servers',
          builder: (context, state) => const McpServersScreen(),
        ),
        GoRoute(
          path: '/custom-tools',
          builder: (context, state) => const CustomToolsScreen(),
        ),
        GoRoute(
          path: '/skills',
          builder: (context, state) => const SkillsScreen(),
        ),
        GoRoute(
          path: '/knowledge',
          builder: (context, state) => const KnowledgeScreen(),
        ),
        GoRoute(
          path: '/guardrails',
          builder: (context, state) => const GuardrailsScreen(),
        ),
        GoRoute(
          path: '/tokens',
          builder: (context, state) => const TokensScreen(),
        ),
        GoRoute(
          path: '/providers',
          builder: (context, state) => const ProvidersScreen(),
        ),
        GoRoute(
          path: '/workflows',
          builder: (context, state) => const WorkflowsScreen(),
        ),
        GoRoute(
          path: '/tasks',
          builder: (context, state) => const TasksScreen(),
        ),
        GoRoute(
          path: '/scheduled-agents',
          builder: (context, state) => const ScheduledAgentsScreen(),
        ),
        GoRoute(
          path: '/run-task',
          builder: (context, state) => const RunTaskScreen(),
        ),
        GoRoute(path: '/chat', builder: (context, state) => const ChatScreen()),
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
    // Derive the top-level route segment for active-nav highlighting.
    final uri = state.uri.toString();
    final route = '/${uri.split('/').where((s) => s.isNotEmpty).first}';
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: AppShell(currentRoute: route, child: child),
    );
  }
}
