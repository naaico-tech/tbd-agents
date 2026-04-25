import 'package:flutter_test/flutter_test.dart';
import 'package:naaico_frontend/core/config/app_links.dart';

void main() {
  group('AppLinks', () {
    test('builds same-origin API URIs under /api', () {
      expect(AppLinks.apiUri('/agents').toString(), '/api/agents');
      expect(AppLinks.apiUri('/api/tasks').toString(), '/api/tasks');
    });

    test('builds legacy embed URIs for migrated routes', () {
      expect(
        AppLinks.legacyDashboardUri(route: AppLinks.agents).toString(),
        '/dashboard-legacy?embed=1&chrome=none&page=agents',
      );
      expect(
        AppLinks.legacyDashboardUri(route: AppLinks.runTask).toString(),
        '/dashboard-legacy?embed=1&chrome=none&page=task',
      );
    });

    test('marks mapped routes as legacy-backed until native parity lands', () {
      expect(AppLinks.shouldEmbedLegacyRoute(AppLinks.dashboardRoot), isFalse);
      expect(AppLinks.shouldEmbedLegacyRoute(AppLinks.tasks), isTrue);
      expect(AppLinks.shouldEmbedLegacyRoute('/settings'), isFalse);
    });

    test('preserves nested legacy hash routes for deeper app links', () {
      expect(
        AppLinks.legacyDashboardUriForAppUri(
          Uri(
            path: '${AppLinks.tasks}/task-123/logs',
            queryParameters: {'workflowId': 'wf-456'},
          ),
        ).toString(),
        '/dashboard-legacy?embed=1&chrome=none&page=tasks#/tasks/task-123/logs?workflowId=wf-456',
      );
    });

    test(
      'builds detail app links for workflow, task logs, and agent memory',
      () {
        expect(
          AppLinks.workflowDetail('wf-123'),
          '/dashboard/workflows/wf-123',
        );
        expect(AppLinks.taskLogs('task-123'), '/dashboard/tasks/task-123/logs');
        expect(
          AppLinks.agentMemory('agent-123'),
          '/dashboard/agents/agent-123/memory',
        );
      },
    );
  });
}
