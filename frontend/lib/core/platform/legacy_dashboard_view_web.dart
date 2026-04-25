// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:html' as html;
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';

class LegacyDashboardView extends StatefulWidget {
  const LegacyDashboardView({super.key, required this.uri});

  final Uri uri;

  @override
  State<LegacyDashboardView> createState() => _LegacyDashboardViewState();
}

class _LegacyDashboardViewState extends State<LegacyDashboardView> {
  late final String _viewType;
  late final html.IFrameElement _iframe;

  @override
  void initState() {
    super.initState();
    _viewType =
        'legacy-dashboard-view-${DateTime.now().microsecondsSinceEpoch}-${identityHashCode(this)}';
    _iframe = _buildIframe(widget.uri);
    ui_web.platformViewRegistry.registerViewFactory(
      _viewType,
      (viewId) => _iframe,
    );
  }

  @override
  void didUpdateWidget(covariant LegacyDashboardView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.uri != widget.uri) {
      _iframe.src = widget.uri.toString();
    }
  }

  html.IFrameElement _buildIframe(Uri uri) {
    return html.IFrameElement()
      ..src = uri.toString()
      ..style.border = '0'
      ..style.width = '100%'
      ..style.height = '100%'
      ..style.backgroundColor = 'transparent'
      ..allow = 'clipboard-read; clipboard-write'
      ..setAttribute('loading', 'eager');
  }

  @override
  Widget build(BuildContext context) {
    return HtmlElementView(viewType: _viewType);
  }
}
