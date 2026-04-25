import 'package:flutter/material.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/retro_card.dart';

// ---------------------------------------------------------------------------
// DashboardScreen — summary view: status tiles + section frames.
// ---------------------------------------------------------------------------
class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _PageTitle(title: 'DASHBOARD', subtitle: 'System Overview'),
          const SizedBox(height: sp24),
          _StatusGrid(),
          const SizedBox(height: sp32),
          SectionFrame(
            title: 'Recent Workflow Runs',
            accentColor: accentLavender,
            minHeight: 180,
            child: const _PlaceholderTable(
              columns: ['ID', 'Workflow', 'Status', 'Duration', 'Started'],
            ),
          ),
          const SizedBox(height: sp24),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: SectionFrame(
                  title: 'Active Agents',
                  accentColor: accentTeal,
                  minHeight: 140,
                  child: const _PlaceholderTable(
                    columns: ['Agent', 'Status', 'Last Seen'],
                  ),
                ),
              ),
              const SizedBox(width: sp24),
              Expanded(
                child: SectionFrame(
                  title: 'Recent Tasks',
                  accentColor: accentAmber,
                  minHeight: 140,
                  child: const _PlaceholderTable(
                    columns: ['Task', 'Agent', 'State'],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusGrid extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final cols = constraints.maxWidth > 900
            ? 4
            : constraints.maxWidth > 600
            ? 2
            : 1;
        return Wrap(
          spacing: sp16,
          runSpacing: sp16,
          children: [
            _StatTile(
              label: 'Agents',
              value: '—',
              icon: Icons.smart_toy_outlined,
              accent: accentTeal,
              width: (constraints.maxWidth - (cols - 1) * sp16) / cols,
            ),
            _StatTile(
              label: 'Workflows',
              value: '—',
              icon: Icons.account_tree_outlined,
              accent: accentLavender,
              width: (constraints.maxWidth - (cols - 1) * sp16) / cols,
            ),
            _StatTile(
              label: 'Tasks Today',
              value: '—',
              icon: Icons.list_alt_outlined,
              accent: accentAmber,
              width: (constraints.maxWidth - (cols - 1) * sp16) / cols,
            ),
            _StatTile(
              label: 'MCP Servers',
              value: '—',
              icon: Icons.power_outlined,
              accent: accentPrimary,
              width: (constraints.maxWidth - (cols - 1) * sp16) / cols,
            ),
          ],
        );
      },
    );
  }
}

class _StatTile extends StatelessWidget {
  const _StatTile({
    required this.label,
    required this.value,
    required this.icon,
    required this.accent,
    required this.width,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color accent;
  final double width;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      child: RetroCard(
        shadowOffsetX: 4,
        shadowOffsetY: 4,
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: accent.withAlpha(28),
                border: Border.all(color: accent, width: 1),
              ),
              child: Icon(icon, color: accent, size: 22),
            ),
            const SizedBox(width: sp12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  value,
                  style: const TextStyle(
                    fontFamily: fontDisplay,
                    fontSize: 18,
                    color: textPrimary,
                  ),
                ),
                Text(
                  label,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 14,
                    color: textMuted,
                    letterSpacing: 1,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// Shared helpers -----------------------------------------------------------

class _PageTitle extends StatelessWidget {
  const _PageTitle({required this.title, required this.subtitle});
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 4),
        Text(
          subtitle,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            color: textMuted,
            letterSpacing: 1,
          ),
        ),
      ],
    );
  }
}

class _PlaceholderTable extends StatelessWidget {
  const _PlaceholderTable({required this.columns});
  final List<String> columns;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(sp8),
      child: Table(
        border: TableBorder.all(color: borderColor.withAlpha(60), width: 1),
        children: [
          TableRow(
            decoration: BoxDecoration(color: accentSlate.withAlpha(20)),
            children: columns
                .map(
                  (c) => Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: sp8,
                      vertical: sp4,
                    ),
                    child: Text(
                      c.toUpperCase(),
                      style: const TextStyle(
                        fontFamily: fontDisplay,
                        fontSize: 8,
                        color: textMuted,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
          TableRow(
            children: columns
                .map(
                  (_) => const Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: sp8,
                      vertical: sp12,
                    ),
                    child: Text(
                      '—',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: 16,
                        color: textMuted,
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        ],
      ),
    );
  }
}
