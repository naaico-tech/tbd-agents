import 'package:flutter/material.dart';
import 'design_tokens.dart';

// ---------------------------------------------------------------------------
// AppTheme — builds the single ThemeData used by the entire app.
// ---------------------------------------------------------------------------
class AppTheme {
  const AppTheme._();

  static ThemeData get light => _build();

  static ThemeData _build() {
    const colorScheme = ColorScheme(
      brightness: Brightness.light,
      primary: accentPrimary,
      onPrimary: cardBg,
      secondary: accentTeal,
      onSecondary: cardBg,
      tertiary: accentAmber,
      onTertiary: textPrimary,
      error: accentPrimary,
      onError: cardBg,
      surface: cardBg,
      onSurface: textPrimary,
    );

    return ThemeData(
      colorScheme: colorScheme,
      scaffoldBackgroundColor: pageBg,
      fontFamily: fontBody,

      // ---- AppBar ----
      appBarTheme: const AppBarTheme(
        backgroundColor: headerBg,
        foregroundColor: textPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleTextStyle: TextStyle(
          fontFamily: fontDisplay,
          fontSize: fontSizeCaption,
          color: textPrimary,
          letterSpacing: 1,
        ),
        shape: Border(
          bottom: BorderSide(color: borderColor, width: borderWidth),
        ),
      ),

      // ---- Text ----
      textTheme: const TextTheme(
        displayLarge: TextStyle(
          fontFamily: fontDisplay,
          fontSize: fontSizeDisplay,
          fontWeight: FontWeight.w400,
          color: textPrimary,
          letterSpacing: 1.5,
        ),
        headlineMedium: TextStyle(
          fontFamily: fontDisplay,
          fontSize: fontSizeHeading,
          fontWeight: FontWeight.w400,
          color: textPrimary,
          letterSpacing: 1,
        ),
        titleMedium: TextStyle(
          fontFamily: fontDisplay,
          fontSize: fontSizeSmall,
          fontWeight: FontWeight.w400,
          color: textPrimary,
          letterSpacing: 0.5,
        ),
        bodyLarge: TextStyle(
          fontFamily: fontBody,
          fontSize: 18,
          color: textPrimary,
        ),
        bodyMedium: TextStyle(
          fontFamily: fontBody,
          fontSize: 16,
          color: textPrimary,
        ),
        bodySmall: TextStyle(
          fontFamily: fontBody,
          fontSize: fontSizeCaption,
          color: textMuted,
        ),
        labelSmall: TextStyle(
          fontFamily: fontBody,
          fontSize: fontSizeSmall,
          color: textMuted,
          letterSpacing: 0.5,
        ),
      ),

      // ---- Divider ----
      dividerTheme: const DividerThemeData(
        color: borderColor,
        thickness: borderWidth,
        space: 0,
      ),

      // ---- Card ----
      cardTheme: CardThemeData(
        color: cardBg,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: borderRadiusNone,
          side: const BorderSide(color: borderColor, width: borderWidth),
        ),
      ),

      // ---- Elevated Button ----
      elevatedButtonTheme: ElevatedButtonThemeData(
        style:
            ElevatedButton.styleFrom(
              backgroundColor: accentPrimary,
              foregroundColor: cardBg,
              elevation: 0,
              shape: const RoundedRectangleBorder(
                borderRadius: borderRadiusNone,
              ),
              side: const BorderSide(color: borderColor, width: borderWidth),
              textStyle: const TextStyle(
                fontFamily: fontDisplay,
                fontSize: fontSizeSmall,
                letterSpacing: 0.5,
              ),
              padding: const EdgeInsets.symmetric(
                horizontal: sp16,
                vertical: sp12,
              ),
            ).copyWith(
              overlayColor: WidgetStateProperty.resolveWith(
                (states) => states.contains(WidgetState.hovered)
                    ? shadowColor.withAlpha(30)
                    : null,
              ),
            ),
      ),

      // ---- Outlined Button ----
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: textPrimary,
          side: const BorderSide(color: borderColor, width: borderWidth),
          shape: const RoundedRectangleBorder(borderRadius: borderRadiusNone),
          textStyle: const TextStyle(
            fontFamily: fontDisplay,
            fontSize: fontSizeSmall,
            letterSpacing: 0.5,
          ),
          padding: const EdgeInsets.symmetric(horizontal: sp16, vertical: sp12),
        ),
      ),

      useMaterial3: true,
    );
  }
}
