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
        '/dashboard-legacy?embed=1&page=agents',
      );
      expect(
        AppLinks.legacyDashboardUri(route: AppLinks.runTask).toString(),
        '/dashboard-legacy?embed=1&page=task',
      );
    });
  });
}
