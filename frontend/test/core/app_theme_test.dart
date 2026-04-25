import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:naaico_frontend/core/theme/app_theme.dart';
import 'package:naaico_frontend/core/theme/design_tokens.dart';

void main() {
  group('AppTheme typography', () {
    test('uses pixel fonts across display, body, and labels', () {
      final theme = AppTheme.light;
      final textTheme = theme.textTheme;

      expect(textTheme.displayLarge?.fontFamily, fontDisplay);
      expect(textTheme.headlineMedium?.fontFamily, fontDisplay);
      expect(textTheme.bodyMedium?.fontFamily, fontBody);
      expect(textTheme.labelLarge?.fontFamily, fontBody);
      expect(textTheme.labelSmall?.fontFamily, fontBody);
    });

    test('uses readable 8-bit button typography', () {
      final theme = AppTheme.light;
      final elevatedStyle = theme.elevatedButtonTheme.style;
      final outlinedStyle = theme.outlinedButtonTheme.style;

      expect(
        elevatedStyle?.textStyle?.resolve(const <WidgetState>{})?.fontFamily,
        fontBody,
      );
      expect(
        outlinedStyle?.textStyle?.resolve(const <WidgetState>{})?.fontFamily,
        fontBody,
      );
    });
  });
}
