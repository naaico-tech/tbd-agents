// Widget tests for RetroCard, RetroChip, RetroButton, SectionFrame.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:naaico_frontend/core/theme/app_theme.dart';
import 'package:naaico_frontend/core/theme/design_tokens.dart';
import 'package:naaico_frontend/core/widgets/retro_card.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: AppTheme.light,
  home: Scaffold(body: child),
);

void main() {
  group('RetroCard', () {
    testWidgets('renders child content', (tester) async {
      await tester.pumpWidget(
        _wrap(const RetroCard(child: Text('hello card'))),
      );
      expect(find.text('hello card'), findsOneWidget);
    });

    testWidgets('renders header when provided', (tester) async {
      await tester.pumpWidget(
        _wrap(const RetroCard(header: Text('HEADER'), child: Text('body'))),
      );
      expect(find.text('HEADER'), findsOneWidget);
      expect(find.text('body'), findsOneWidget);
    });

    testWidgets('applies custom padding', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const RetroCard(padding: EdgeInsets.all(32), child: Text('padded')),
        ),
      );
      final padding = tester.widget<Padding>(
        find
            .ancestor(of: find.text('padded'), matching: find.byType(Padding))
            .first,
      );
      expect(padding.padding, equals(const EdgeInsets.all(32)));
    });
  });

  group('RetroChip', () {
    testWidgets('displays upper-cased label', (tester) async {
      await tester.pumpWidget(_wrap(const RetroChip(label: 'active')));
      expect(find.text('ACTIVE'), findsOneWidget);
    });

    testWidgets('uses custom color', (tester) async {
      await tester.pumpWidget(
        _wrap(const RetroChip(label: 'ok', color: accentPrimary)),
      );
      final container = tester.widget<Container>(find.byType(Container).first);
      final decoration = container.decoration as BoxDecoration;
      expect(decoration.color, equals(accentPrimary));
    });
  });

  group('RetroButton', () {
    testWidgets('displays label', (tester) async {
      await tester.pumpWidget(
        _wrap(RetroButton(label: 'GO', onPressed: () {})),
      );
      expect(find.text('GO'), findsOneWidget);
    });

    testWidgets('calls onPressed when tapped', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        _wrap(RetroButton(label: 'TAP', onPressed: () => tapped = true)),
      );
      await tester.tap(find.byType(RetroButton));
      await tester.pumpAndSettle();
      expect(tapped, isTrue);
    });

    testWidgets('shows icon when provided', (tester) async {
      await tester.pumpWidget(
        _wrap(RetroButton(label: 'ADD', icon: Icons.add, onPressed: () {})),
      );
      expect(find.byIcon(Icons.add), findsOneWidget);
    });
  });

  group('SectionFrame', () {
    testWidgets('shows label and placeholder when no child', (tester) async {
      await tester.pumpWidget(_wrap(const SectionFrame(title: 'my section')));
      // Label is rendered upper-cased inside _FrameLabel
      expect(find.text('MY SECTION'), findsOneWidget);
      // Placeholder text contains the title
      expect(find.textContaining('my section'), findsWidgets);
    });

    testWidgets('renders provided child instead of placeholder', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const SectionFrame(title: 'data', child: Text('real content'))),
      );
      expect(find.text('real content'), findsOneWidget);
    });
  });
}
