// NAAICO Retro Dawn – Design Tokens
// All raw colour, spacing, typography, and shadow constants live here.
// Nothing is Material-specific; they are consumed by app_theme.dart.

import 'package:flutter/material.dart';

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------
const Color pageBg = Color(0xFFFDF6E3);
const Color cardBg = Color(0xFFFFFDF5);
const Color headerBg = Color(0xF7FDF6E3); // rgba(253,246,227,.97) ≈ 0xF7
const Color textPrimary = Color(0xFF1A1A2E);
const Color textMuted = Color(0xFF5A5A7A);
const Color accentPrimary = Color(0xFFE8434B);
const Color accentTeal = Color(0xFF2B7A78);
const Color accentAmber = Color(0xFFF4A261);
const Color accentSlate = Color(0xFF264653);
const Color accentLavender = Color(0xFFA976F9);
const Color borderColor = Color(0xFF1A1A2E);
const Color shadowColor = Color(0xD91A1A2E); // rgba(26,26,46,.85) ≈ 0xD9

// ---------------------------------------------------------------------------
// Shape — zero radius by default
// ---------------------------------------------------------------------------
const double radiusNone = 0;
const BorderRadius borderRadiusNone = BorderRadius.zero;
const double borderWidth = 2.0;

// ---------------------------------------------------------------------------
// Hard-offset drop shadow (retro pixel look)
// ---------------------------------------------------------------------------
BoxDecoration retroCardDecoration({
  Color background = cardBg,
  double offsetX = 4,
  double offsetY = 4,
}) => BoxDecoration(
  color: background,
  border: Border.all(color: borderColor, width: borderWidth),
  boxShadow: [
    BoxShadow(
      color: shadowColor,
      offset: Offset(offsetX, offsetY),
      blurRadius: 0,
      spreadRadius: 0,
    ),
  ],
);

BoxDecoration retroHeaderDecoration() => const BoxDecoration(
  color: headerBg,
  border: Border(
    bottom: BorderSide(color: borderColor, width: borderWidth),
  ),
);

// ---------------------------------------------------------------------------
// Spacing scale
// ---------------------------------------------------------------------------
const double sp4 = 4;
const double sp8 = 8;
const double sp10 = 10;
const double sp12 = 12;
const double sp16 = 16;
const double sp20 = 20;
const double sp24 = 24;
const double sp32 = 32;
const double sp48 = 48;

// ---------------------------------------------------------------------------
// Typography — pixel-forward sizes tuned for readable 8-bit UI
// ---------------------------------------------------------------------------
const double fontSizeDisplay = 20;
const double fontSizeHeading = 15;
const double fontSizeBody = 13;
const double fontSizeCaption = 11;
const double fontSizeSmall = 10;

const double fontHeightDisplay = 1.45;
const double fontHeightBody = 1.5;
const double letterSpacingDisplay = 1;
const double letterSpacingBody = 0.25;
const double letterSpacingLabel = 0.6;

// Font families (loaded via Google Fonts link in web/index.html)
const String fontDisplay = 'Press Start 2P';
const String fontBody = 'Silkscreen';
const String fontFallback = 'monospace';
