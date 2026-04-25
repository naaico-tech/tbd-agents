// Smoke tests for all route screens — verify each builds without error.

import 'package:flutter_test/flutter_test.dart';
import 'package:naaico_frontend/app/app.dart';

void main() {
  testWidgets('App mounts and navigates to /dashboard-new-ui by default', (
    tester,
  ) async {
    await tester.pumpWidget(const NaaicoApp());
    await tester.pumpAndSettle(const Duration(seconds: 2));
    // The app bar title should contain 'DASHBOARD'
    expect(find.textContaining('DASHBOARD'), findsWidgets);
  });
}
