import 'package:flutter_test/flutter_test.dart';
import 'package:naaico_frontend/app/app.dart';
import 'package:naaico_frontend/app/router.dart';
import 'package:naaico_frontend/core/config/app_links.dart';

void main() {
  testWidgets('shell swaps pages immediately without retaining prior content', (
    tester,
  ) async {
    final router = createAppRouter();

    await tester.pumpWidget(NaaicoApp(router: router));
    await tester.pumpAndSettle();

    expect(find.text('DASHBOARD'), findsOneWidget);
    expect(
      find.text(
        'Legacy functionality is embedded here until this screen reaches Flutter parity.',
      ),
      findsOneWidget,
    );

    router.go(AppLinks.agents);
    await tester.pumpAndSettle();

    expect(find.text('AGENTS'), findsOneWidget);
    expect(find.text('DASHBOARD'), findsNothing);
  });

  testWidgets('detail routes stay inside the portal shell', (tester) async {
    final router = createAppRouter();

    await tester.pumpWidget(NaaicoApp(router: router));
    router.go(AppLinks.workflowDetail('wf-123'));
    await tester.pumpAndSettle();

    expect(find.text('WORKFLOWS'), findsOneWidget);
    expect(
      find.text(
        'Legacy functionality is embedded here until this screen reaches Flutter parity.',
      ),
      findsOneWidget,
    );
  });
}
