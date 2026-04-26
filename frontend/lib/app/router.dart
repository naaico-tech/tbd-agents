import 'package:go_router/go_router.dart';
import 'package:flutter/material.dart';
import '../core/config/app_links.dart';
import '../core/widgets/app_shell.dart';
import '../core/widgets/legacy_dashboard_host.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/agents/agents_screen.dart';
import '../features/workflows/workflows_exports.dart';
import '../features/run_task/run_task_screen.dart';
import '../features/chat/chat_screen.dart';

// ---------------------------------------------------------------------------
// AppRouter — GoRouter configuration for all named routes.
// All shell routes share [AppShell] as a persistent layout wrapper.
// ---------------------------------------------------------------------------
final appRouter = createAppRouter();

GoRouter createAppRouter({WidgetBuilder? dashboardBuilder}) {
  final resolvedDashboardBuilder =
      dashboardBuilder ?? (_) => const DashboardScreen();
  return GoRouter(
    initialLocation: AppLinks.dashboardRoot,
    routes: [
      ShellRoute(
        pageBuilder: (context, state, child) => _buildNoTransitionPage(
          state: state,
          child: _ShellWrapper(currentUri: state.uri, child: child),
        ),
        routes: [
          _buildShellChildRoute(
            path: AppLinks.dashboardRoot,
            builder: resolvedDashboardBuilder,
          ),
          _buildShellChildRoute(
            path: AppLinks.agents,
            builder: (_) => const AgentsScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.agentMemoryPattern,
            builder: (_) => const SizedBox.shrink(),
          ),
          _buildShellChildRoute(
            path: AppLinks.mcpServers,
            builder: (_) => const McpServersScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.customTools,
            builder: (_) => const CustomToolsScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.skills,
            builder: (_) => const SkillsScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.knowledge,
            builder: (_) => const KnowledgeScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.guardrails,
            builder: (_) => const GuardrailsScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.tokens,
            builder: (_) => const TokensScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.providers,
            builder: (_) => const ProvidersScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.workflows,
            builder: (_) => const WorkflowsScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.workflowDetailPattern,
            builder: (_) => const SizedBox.shrink(),
          ),
          _buildShellChildRoute(
            path: AppLinks.tasks,
            builder: (_) => const TasksScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.taskLogsPattern,
            builder: (_) => const SizedBox.shrink(),
          ),
          _buildShellChildRoute(
            path: AppLinks.scheduledAgents,
            builder: (_) => const ScheduledAgentsScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.runTask,
            builder: (_) => const RunTaskScreen(),
          ),
          _buildShellChildRoute(
            path: AppLinks.chat,
            builder: (_) => const ChatScreen(),
          ),
        ],
      ),
    ],
  );
}

GoRoute _buildShellChildRoute({
  required String path,
  required WidgetBuilder builder,
}) {
  return GoRoute(
    path: path,
    pageBuilder: (context, state) =>
        _buildNoTransitionPage(state: state, child: builder(context)),
  );
}

NoTransitionPage<void> _buildNoTransitionPage({
  required GoRouterState state,
  required Widget child,
}) {
  return NoTransitionPage<void>(key: state.pageKey, child: child);
}

class _ShellWrapper extends StatelessWidget {
  const _ShellWrapper({required this.currentUri, required this.child});

  final Uri currentUri;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final currentRoute = currentUri.path;
    final routeChild = AppLinks.shouldEmbedLegacyRoute(currentRoute)
        ? LegacyDashboardHost(routeUri: currentUri)
        : child;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: AppShell(currentRoute: currentRoute, child: routeChild),
    );
  }
}
