import 'package:flutter_test/flutter_test.dart';
import 'package:naaico_frontend/app/app.dart';
import 'package:naaico_frontend/app/router.dart';
import 'package:naaico_frontend/core/config/app_links.dart';
import 'package:naaico_frontend/features/dashboard/dashboard_screen.dart';

Future<DashboardSnapshot> _dashboardSnapshot() async {
  return const DashboardSnapshot(
    agentsCount: 4,
    mcpServersCount: 1,
    skillsCount: 2,
    tokensCount: 3,
    providersCount: 2,
    knowledgeSourcesCount: 1,
    workflowsCount: 5,
    scheduledAgentsCount: 1,
    taskExecutionsCount: 9,
    recentWorkflows: [
      WorkflowSummary(
        id: 'wf-1',
        title: 'Weather Agent',
        agentName: 'Weather Agent',
        taskCount: 9,
        lastTaskStatus: 'completed',
        model: 'gpt-5.4-mini',
        createdAt: null,
      ),
    ],
  );
}

void main() {
  testWidgets('shell swaps pages immediately without retaining prior content', (
    tester,
  ) async {
    final router = createAppRouter(
      dashboardBuilder: (_) =>
          DashboardScreen(snapshotFuture: _dashboardSnapshot()),
    );

    await tester.pumpWidget(NaaicoApp(router: router));
    await tester.pumpAndSettle();

    expect(find.text('Live system overview'), findsOneWidget);
    expect(
      find.text(
        'Legacy functionality is embedded here until this screen reaches Flutter parity.',
      ),
      findsNothing,
    );

    router.go(AppLinks.agents);
    await tester.pumpAndSettle();

    // "AGENTS" now appears in both the nav tab and the native screen header.
    expect(find.text('AGENTS'), findsAtLeast(1));
    expect(find.text('DASHBOARD'), findsNothing);
  });

  testWidgets('detail routes stay inside the portal shell', (tester) async {
    final router = createAppRouter(
      dashboardBuilder: (_) =>
          DashboardScreen(snapshotFuture: _dashboardSnapshot()),
    );

    await tester.pumpWidget(NaaicoApp(router: router));
    router.go(AppLinks.workflowDetail('wf-123'));
    await tester.pumpAndSettle();

    expect(find.text('WORKFLOWS'), findsOneWidget);
    // workflowDetailPattern is now native (inherits from workflows in _nativeRoutes)
    // so no legacy embed is shown; the portal shell remains visible.
    expect(
      find.text(
        'Legacy functionality is embedded here until this screen reaches Flutter parity.',
      ),
      findsNothing,
    );
  });
}
