import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../core/theme/app_theme.dart';
import 'router.dart';

// ---------------------------------------------------------------------------
// NaaicoApp — root widget that wires theme + router.
// ---------------------------------------------------------------------------
class NaaicoApp extends StatelessWidget {
  const NaaicoApp({super.key, this.router});

  final GoRouter? router;

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'TBD Agents',
      theme: AppTheme.light,
      routerConfig: router ?? appRouter,
      debugShowCheckedModeBanner: false,
    );
  }
}
