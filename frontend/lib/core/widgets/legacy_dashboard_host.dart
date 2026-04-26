import 'package:flutter/material.dart';

import '../config/app_links.dart';
import '../platform/browser_navigation.dart';
import '../platform/legacy_dashboard_view.dart';
import '../theme/design_tokens.dart';
import 'retro_card.dart';

class LegacyDashboardHost extends StatelessWidget {
  const LegacyDashboardHost({
    super.key,
    required this.routeUri,
    this.routeOverride,
  });

  final Uri routeUri;
  final String? routeOverride;

  Uri get _legacyUri {
    if (routeOverride != null) {
      return AppLinks.legacyDashboardUri(route: routeOverride);
    }
    return AppLinks.legacyDashboardUriForAppUri(routeUri);
  }

  String get _routeLabel {
    final parts = (routeOverride ?? routeUri.path)
        .split('/')
        .where((part) => part.isNotEmpty)
        .toList();
    return parts.isEmpty ? 'dashboard' : parts.last;
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(sp16),
      child: LayoutBuilder(
        builder: (context, constraints) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _LegacyHeader(
              legacyUri: _legacyUri,
              stacked: constraints.maxWidth < 720,
            ),
            const SizedBox(height: sp12),
            Expanded(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: cardBg,
                  border: Border.all(color: borderColor, width: borderWidth),
                ),
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: LegacyDashboardView(uri: _legacyUri),
                    ),
                    if (!canUseBrowserNavigation)
                      _LegacyUnavailableFallback(
                        routeLabel: _routeLabel,
                        uri: _legacyUri,
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LegacyHeader extends StatelessWidget {
  const _LegacyHeader({required this.legacyUri, required this.stacked});

  final Uri legacyUri;
  final bool stacked;

  @override
  Widget build(BuildContext context) {
    final action = canUseBrowserNavigation
        ? RetroButton(
            label: 'OPEN LEGACY',
            icon: Icons.open_in_new,
            color: accentAmber,
            textColor: textPrimary,
            onPressed: () => openInBrowser(legacyUri.toString()),
          )
        : null;

    if (stacked) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _LegacyNotice(),
          if (action != null) ...[const SizedBox(height: sp8), action],
        ],
      );
    }

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Expanded(child: _LegacyNotice()),
        if (action != null) ...[const SizedBox(width: sp8), action],
      ],
    );
  }
}

class _LegacyNotice extends StatelessWidget {
  const _LegacyNotice();

  @override
  Widget build(BuildContext context) {
    return const Text(
      'Legacy functionality is embedded here until this screen reaches Flutter parity.',
      style: TextStyle(fontFamily: fontBody, fontSize: 16, color: textMuted),
    );
  }
}

class _LegacyUnavailableFallback extends StatelessWidget {
  const _LegacyUnavailableFallback({
    required this.routeLabel,
    required this.uri,
  });

  final String routeLabel;
  final Uri uri;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: cardBg,
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: RetroCard(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.web_asset_outlined,
                  size: 40,
                  color: accentSlate,
                ),
                const SizedBox(height: sp12),
                Text(
                  'Legacy $routeLabel embed is available on Flutter web.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 18,
                    color: textPrimary,
                  ),
                ),
                const SizedBox(height: sp8),
                SelectableText(
                  uri.toString(),
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 16,
                    color: textMuted,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
