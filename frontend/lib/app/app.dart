import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';
import 'router.dart';

// ---------------------------------------------------------------------------
// NaaicoApp — root widget that wires theme + router.
// ---------------------------------------------------------------------------
class NaaicoApp extends StatelessWidget {
  const NaaicoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'TBD Agents',
      theme: AppTheme.light,
      routerConfig: appRouter,
      debugShowCheckedModeBanner: false,
    );
  }
}
