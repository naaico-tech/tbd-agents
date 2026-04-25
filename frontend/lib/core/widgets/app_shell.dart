import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme/design_tokens.dart';

// ---------------------------------------------------------------------------
// NavDestination — data model for a single sidebar entry.
// ---------------------------------------------------------------------------
class NavDestination {
  const NavDestination({
    required this.route,
    required this.label,
    required this.icon,
    this.accentColor = accentPrimary,
  });

  final String route;
  final String label;
  final IconData icon;
  final Color accentColor;
}

// ---------------------------------------------------------------------------
// AppShell — persistent scaffold: header + collapsible sidebar + content.
// ---------------------------------------------------------------------------
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.child, required this.currentRoute});

  final Widget child;
  final String currentRoute;

  static const List<NavDestination> _destinations = [
    NavDestination(
      route: '/dashboard',
      label: 'Dashboard',
      icon: Icons.bar_chart,
      accentColor: accentPrimary,
    ),
    NavDestination(
      route: '/agents',
      label: 'Agents',
      icon: Icons.smart_toy_outlined,
      accentColor: accentTeal,
    ),
    NavDestination(
      route: '/mcp-servers',
      label: 'MCP Servers',
      icon: Icons.power_outlined,
      accentColor: accentAmber,
    ),
    NavDestination(
      route: '/custom-tools',
      label: 'Custom Tools',
      icon: Icons.build_outlined,
      accentColor: accentSlate,
    ),
    NavDestination(
      route: '/skills',
      label: 'Skills',
      icon: Icons.bolt_outlined,
      accentColor: accentLavender,
    ),
    NavDestination(
      route: '/knowledge',
      label: 'Knowledge',
      icon: Icons.library_books_outlined,
      accentColor: accentTeal,
    ),
    NavDestination(
      route: '/guardrails',
      label: 'Guardrails',
      icon: Icons.shield_outlined,
      accentColor: accentPrimary,
    ),
    NavDestination(
      route: '/tokens',
      label: 'Tokens',
      icon: Icons.key_outlined,
      accentColor: accentAmber,
    ),
    NavDestination(
      route: '/providers',
      label: 'Providers',
      icon: Icons.business_outlined,
      accentColor: accentSlate,
    ),
    NavDestination(
      route: '/workflows',
      label: 'Workflows',
      icon: Icons.account_tree_outlined,
      accentColor: accentLavender,
    ),
    NavDestination(
      route: '/scheduled-agents',
      label: 'Scheduled',
      icon: Icons.schedule_outlined,
      accentColor: accentTeal,
    ),
    NavDestination(
      route: '/tasks',
      label: 'Tasks',
      icon: Icons.list_alt_outlined,
      accentColor: accentAmber,
    ),
    NavDestination(
      route: '/run-task',
      label: 'Run Task',
      icon: Icons.play_circle_outline,
      accentColor: accentPrimary,
    ),
    NavDestination(
      route: '/chat',
      label: 'Chat',
      icon: Icons.chat_bubble_outline,
      accentColor: accentLavender,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final isMobile = MediaQuery.sizeOf(context).width < 768;

    if (isMobile) {
      return _MobileShell(
        destinations: _destinations,
        currentRoute: currentRoute,
        child: child,
      );
    }

    return _DesktopShell(
      destinations: _destinations,
      currentRoute: currentRoute,
      child: child,
    );
  }
}

// ---------------------------------------------------------------------------
// Desktop two-column layout: fixed sidebar + scrollable content
// ---------------------------------------------------------------------------
class _DesktopShell extends StatelessWidget {
  const _DesktopShell({
    required this.destinations,
    required this.currentRoute,
    required this.child,
  });

  final List<NavDestination> destinations;
  final String currentRoute;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _Sidebar(destinations: destinations, currentRoute: currentRoute),
        // Vertical separator
        Container(width: 2, color: borderColor),
        Expanded(
          child: Column(
            children: [
              _TopBar(currentRoute: currentRoute),
              Expanded(
                child: Container(color: pageBg, child: child),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Mobile: Drawer + bottom header
// ---------------------------------------------------------------------------
class _MobileShell extends StatelessWidget {
  const _MobileShell({
    required this.destinations,
    required this.currentRoute,
    required this.child,
  });

  final List<NavDestination> destinations;
  final String currentRoute;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: pageBg,
      appBar: PreferredSize(
        preferredSize: const Size.fromHeight(48),
        child: _TopBar(currentRoute: currentRoute),
      ),
      drawer: Drawer(
        backgroundColor: pageBg,
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
        child: _SidebarContent(
          destinations: destinations,
          currentRoute: currentRoute,
        ),
      ),
      body: child,
    );
  }
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------
class _Sidebar extends StatelessWidget {
  const _Sidebar({required this.destinations, required this.currentRoute});

  final List<NavDestination> destinations;
  final String currentRoute;

  static const double _sidebarWidth = 220;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: _sidebarWidth,
      child: Container(
        color: pageBg,
        child: _SidebarContent(
          destinations: destinations,
          currentRoute: currentRoute,
        ),
      ),
    );
  }
}

class _SidebarContent extends StatelessWidget {
  const _SidebarContent({
    required this.destinations,
    required this.currentRoute,
  });

  final List<NavDestination> destinations;
  final String currentRoute;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SidebarHeader(),
        const Divider(height: 0),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.symmetric(vertical: 8),
            itemCount: destinations.length,
            itemBuilder: (context, i) => _NavItem(
              destination: destinations[i],
              isActive:
                  currentRoute == destinations[i].route ||
                  currentRoute.startsWith('${destinations[i].route}/'),
            ),
          ),
        ),
        const Divider(height: 0),
        _SidebarFooter(),
      ],
    );
  }
}

class _SidebarHeader extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(sp16),
      decoration: retroHeaderDecoration(),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'NAAICO',
            style: TextStyle(
              fontFamily: fontDisplay,
              fontSize: 13,
              color: accentPrimary,
              letterSpacing: 2,
            ),
          ),
          SizedBox(height: 2),
          Text(
            'TBD AGENTS',
            style: TextStyle(
              fontFamily: fontBody,
              fontSize: 14,
              color: textMuted,
              letterSpacing: 3,
            ),
          ),
        ],
      ),
    );
  }
}

class _SidebarFooter extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(sp12),
      child: Text(
        'v1.0.0',
        style: const TextStyle(
          fontFamily: fontBody,
          fontSize: fontSizeSmall,
          color: textMuted,
          letterSpacing: 1,
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// NavItem
// ---------------------------------------------------------------------------
class _NavItem extends StatefulWidget {
  const _NavItem({required this.destination, required this.isActive});

  final NavDestination destination;
  final bool isActive;

  @override
  State<_NavItem> createState() => _NavItemState();
}

class _NavItemState extends State<_NavItem> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final accent = widget.destination.accentColor;
    final active = widget.isActive;

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTap: () {
          if (Scaffold.maybeOf(context)?.hasDrawer == true) {
            Navigator.of(context).pop();
          }
          context.go(widget.destination.route);
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          decoration: BoxDecoration(
            color: active
                ? accent.withAlpha(28)
                : _hovered
                ? borderColor.withAlpha(10)
                : Colors.transparent,
            border: Border(
              left: BorderSide(
                color: active ? accent : Colors.transparent,
                width: 3,
              ),
            ),
          ),
          padding: const EdgeInsets.symmetric(horizontal: sp16, vertical: sp12),
          child: Row(
            children: [
              Icon(
                widget.destination.icon,
                size: 16,
                color: active ? accent : textMuted,
              ),
              const SizedBox(width: sp12),
              Expanded(
                child: Text(
                  widget.destination.label,
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: 16,
                    color: active ? textPrimary : textMuted,
                    letterSpacing: 0.5,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// TopBar
// ---------------------------------------------------------------------------
class _TopBar extends StatelessWidget {
  const _TopBar({required this.currentRoute});

  final String currentRoute;

  String get _title {
    final map = {
      '/dashboard': 'Dashboard',
      '/agents': 'Agents',
      '/mcp-servers': 'MCP Servers',
      '/custom-tools': 'Custom Tools',
      '/skills': 'Skills',
      '/knowledge': 'Knowledge',
      '/guardrails': 'Guardrails',
      '/tokens': 'Tokens',
      '/providers': 'Providers',
      '/workflows': 'Workflows',
      '/tasks': 'Task Executions',
      '/run-task': 'Run Task',
      '/chat': 'Chat',
      '/scheduled-agents': 'Scheduled Agents',
    };
    for (final e in map.entries) {
      if (currentRoute.startsWith(e.key)) return e.value;
    }
    return 'TBD Agents';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 48,
      decoration: retroHeaderDecoration(),
      padding: const EdgeInsets.symmetric(horizontal: sp16),
      child: Row(
        children: [
          if (MediaQuery.sizeOf(context).width < 768)
            IconButton(
              icon: const Icon(Icons.menu, size: 18, color: textPrimary),
              onPressed: () => Scaffold.of(context).openDrawer(),
              padding: EdgeInsets.zero,
            ),
          const SizedBox(width: sp8),
          Text(
            _title.toUpperCase(),
            style: const TextStyle(
              fontFamily: fontDisplay,
              fontSize: 10,
              color: textPrimary,
              letterSpacing: 1.5,
            ),
          ),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: sp8, vertical: 4),
            decoration: BoxDecoration(
              color: accentTeal,
              border: Border.all(color: borderColor, width: 1),
            ),
            child: const Text(
              'ONLINE',
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeSmall,
                color: cardBg,
                letterSpacing: 1,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
