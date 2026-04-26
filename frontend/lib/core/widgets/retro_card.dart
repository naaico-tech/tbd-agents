import 'package:flutter/material.dart';
import '../theme/design_tokens.dart';

// ---------------------------------------------------------------------------
// RetroCard — a bordered, hard-shadow card used throughout the app.
// ---------------------------------------------------------------------------
class RetroCard extends StatelessWidget {
  const RetroCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(sp16),
    this.background = cardBg,
    this.shadowOffsetX = 4,
    this.shadowOffsetY = 4,
    this.header,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color background;
  final double shadowOffsetX;
  final double shadowOffsetY;

  /// Optional header row rendered above the padded content with an accent-
  /// colour left strip and bottom border.
  final Widget? header;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: retroCardDecoration(
        background: background,
        offsetX: shadowOffsetX,
        offsetY: shadowOffsetY,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (header != null) ...[
            _CardHeader(child: header!),
            const Divider(height: 0),
          ],
          Padding(padding: padding, child: child),
        ],
      ),
    );
  }
}

class _CardHeader extends StatelessWidget {
  const _CardHeader({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: sp12, vertical: sp8),
      decoration: const BoxDecoration(
        border: Border(left: BorderSide(color: accentPrimary, width: 4)),
      ),
      child: child,
    );
  }
}

// ---------------------------------------------------------------------------
// RetroChip — small status badge
// ---------------------------------------------------------------------------
class RetroChip extends StatelessWidget {
  const RetroChip({
    super.key,
    required this.label,
    this.color = accentTeal,
    this.textColor = cardBg,
  });

  final String label;
  final Color color;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: sp8, vertical: 2),
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: borderColor, width: 1),
      ),
      child: Text(
        label.toUpperCase(),
        style: TextStyle(
          fontFamily: fontBody,
          fontSize: fontSizeSmall,
          color: textColor,
          letterSpacing: 1,
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// RetroButton — primary CTA with hard shadow
// ---------------------------------------------------------------------------
class RetroButton extends StatefulWidget {
  const RetroButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.color = accentPrimary,
    this.textColor = cardBg,
    this.icon,
  });

  final String label;
  final VoidCallback? onPressed;
  final Color color;
  final Color textColor;
  final IconData? icon;

  @override
  State<RetroButton> createState() => _RetroButtonState();
}

class _RetroButtonState extends State<RetroButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final offset = _pressed ? 1.0 : 3.0;
    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) {
        setState(() => _pressed = false);
        widget.onPressed?.call();
      },
      onTapCancel: () => setState(() => _pressed = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 60),
        transform: Matrix4.translationValues(
          _pressed ? 2 : 0,
          _pressed ? 2 : 0,
          0,
        ),
        decoration: BoxDecoration(
          color: widget.color,
          border: Border.all(color: borderColor, width: borderWidth),
          boxShadow: [
            BoxShadow(
              color: shadowColor,
              offset: Offset(offset, offset),
              blurRadius: 0,
            ),
          ],
        ),
        padding: const EdgeInsets.symmetric(horizontal: sp16, vertical: sp8),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (widget.icon != null) ...[
              Icon(widget.icon, size: 14, color: widget.textColor),
              const SizedBox(width: sp8),
            ],
            Text(
              widget.label,
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeCaption,
                height: fontHeightBody,
                color: widget.textColor,
                letterSpacing: letterSpacingLabel,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// SectionFrame — migration-safe content region.
// Renders a labelled border frame with optional coming-soon indicator.
// When `child` is provided it renders that; otherwise shows a placeholder.
// ---------------------------------------------------------------------------
class SectionFrame extends StatelessWidget {
  const SectionFrame({
    super.key,
    required this.title,
    this.child,
    this.accentColor = accentTeal,
    this.minHeight = 160,
  });

  final String title;
  final Widget? child;
  final Color accentColor;
  final double minHeight;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _FrameLabel(title: title, color: accentColor),
        Container(
          constraints: BoxConstraints(minHeight: minHeight),
          decoration: BoxDecoration(
            border: Border(
              left: BorderSide(color: accentColor, width: borderWidth),
              right: const BorderSide(color: borderColor, width: borderWidth),
              bottom: const BorderSide(color: borderColor, width: borderWidth),
            ),
          ),
          child:
              child ??
              Center(
                child: Text(
                  '[ $title ]',
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: 16,
                    color: textMuted,
                    letterSpacing: 1,
                  ),
                ),
              ),
        ),
      ],
    );
  }
}

class _FrameLabel extends StatelessWidget {
  const _FrameLabel({required this.title, required this.color});
  final String title;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: sp8, vertical: 4),
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: borderColor, width: borderWidth),
      ),
      child: Text(
        title.toUpperCase(),
        style: const TextStyle(
          fontFamily: fontDisplay,
          fontSize: 9,
          color: cardBg,
          letterSpacing: 1,
        ),
      ),
    );
  }
}
