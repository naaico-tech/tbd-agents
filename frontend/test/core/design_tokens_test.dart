// Tests for design token values — guard against accidental token changes.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:naaico_frontend/core/theme/design_tokens.dart';

void main() {
  group('Design tokens', () {
    test('pageBg is warm parchment #FDF6E3', () {
      expect(pageBg.toARGB32(), equals(const Color(0xFFFDF6E3).toARGB32()));
    });

    test('accentPrimary is retro red #E8434B', () {
      expect(accentPrimary.toARGB32(), equals(const Color(0xFFE8434B).toARGB32()));
    });

    test('accentTeal is #2B7A78', () {
      expect(accentTeal.toARGB32(), equals(const Color(0xFF2B7A78).toARGB32()));
    });

    test('accentLavender is #A976F9', () {
      expect(accentLavender.toARGB32(), equals(const Color(0xFFA976F9).toARGB32()));
    });

    test('borderColor is textPrimary #1A1A2E', () {
      expect(borderColor.toARGB32(), equals(const Color(0xFF1A1A2E).toARGB32()));
    });

    test('borderWidth is 2', () {
      expect(borderWidth, equals(2.0));
    });

    test('borderRadiusNone is zero', () {
      expect(borderRadiusNone, equals(BorderRadius.zero));
    });

    test('retroCardDecoration has hard shadow offset 4,4 by default', () {
      final decoration = retroCardDecoration();
      expect(decoration.boxShadow, isNotNull);
      expect(decoration.boxShadow!.length, 1);
      final shadow = decoration.boxShadow!.first;
      expect(shadow.offset, equals(const Offset(4, 4)));
      expect(shadow.blurRadius, equals(0));
    });

    test('retroCardDecoration allows custom shadow offset', () {
      final decoration = retroCardDecoration(offsetX: 2, offsetY: 6);
      final shadow = decoration.boxShadow!.first;
      expect(shadow.offset, equals(const Offset(2, 6)));
    });

    test('spacing constants are positive and ascending', () {
      final spacings = [sp4, sp8, sp10, sp12, sp16, sp20, sp24, sp32, sp48];
      for (var i = 1; i < spacings.length; i++) {
        expect(
          spacings[i],
          greaterThan(spacings[i - 1]),
          reason: 'spacing[$i] should be > spacing[${i - 1}]',
        );
      }
    });

    test('fontDisplay constant matches expected family name', () {
      expect(fontDisplay, equals('Press Start 2P'));
    });

    test('fontBody constant matches expected family name', () {
      expect(fontBody, equals('VT323'));
    });
  });
}
