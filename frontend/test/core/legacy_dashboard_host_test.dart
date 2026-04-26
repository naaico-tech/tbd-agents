import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:naaico_frontend/core/config/app_links.dart';
import 'package:naaico_frontend/core/widgets/legacy_dashboard_host.dart';

void main() {
  testWidgets('shows a non-web fallback outside Flutter web', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox.expand(
            child: LegacyDashboardHost(routeUri: Uri(path: AppLinks.agents)),
          ),
        ),
      ),
    );

    expect(
      find.text(
        'Legacy functionality is embedded here until this screen reaches Flutter parity.',
      ),
      findsOneWidget,
    );
    expect(
      find.text('Legacy agents embed is available on Flutter web.'),
      findsOneWidget,
    );
    expect(
      find.text('/dashboard?embed=1&chrome=none&page=agents'),
      findsOneWidget,
    );
    expect(find.text('OPEN LEGACY'), findsNothing);
  });
}
