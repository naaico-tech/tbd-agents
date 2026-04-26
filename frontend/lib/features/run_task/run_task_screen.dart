import 'package:flutter/material.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/retro_card.dart';

// ---------------------------------------------------------------------------
// RunTaskScreen — kick off an agent task with optional workflow selection.
// ---------------------------------------------------------------------------
class RunTaskScreen extends StatefulWidget {
  const RunTaskScreen({super.key});

  @override
  State<RunTaskScreen> createState() => _RunTaskScreenState();
}

class _RunTaskScreenState extends State<RunTaskScreen> {
  final _promptController = TextEditingController();
  bool _isRunning = false;
  String? _output;

  @override
  void dispose() {
    _promptController.dispose();
    super.dispose();
  }

  Future<void> _submitTask() async {
    final prompt = _promptController.text.trim();
    if (prompt.isEmpty) return;
    setState(() {
      _isRunning = true;
      _output = null;
    });
    // TODO: call POST /api/tasks with prompt and handle SSE stream
    await Future.delayed(const Duration(seconds: 1));
    setState(() {
      _isRunning = false;
      _output = '[Task queued — connect to /api/tasks for live output]';
    });
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('RUN TASK', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 4),
          const Text(
            'Execute a task with a selected agent or workflow.',
            style: TextStyle(
              fontFamily: fontBody,
              fontSize: 16,
              color: textMuted,
            ),
          ),
          const SizedBox(height: sp24),
          RetroCard(
            header: const Text(
              'TASK PROMPT',
              style: TextStyle(
                fontFamily: fontDisplay,
                fontSize: 9,
                color: textPrimary,
                letterSpacing: 1,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: borderColor, width: 1),
                    color: pageBg,
                  ),
                  child: TextField(
                    controller: _promptController,
                    minLines: 4,
                    maxLines: 8,
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: 16,
                      color: textPrimary,
                    ),
                    decoration: const InputDecoration(
                      contentPadding: EdgeInsets.all(sp12),
                      border: InputBorder.none,
                      hintText: 'Describe the task…',
                      hintStyle: TextStyle(
                        fontFamily: fontBody,
                        fontSize: 16,
                        color: textMuted,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: sp12),
                Align(
                  alignment: Alignment.centerRight,
                  child: RetroButton(
                    label: _isRunning ? 'RUNNING…' : 'RUN TASK',
                    icon: Icons.play_circle_outline,
                    onPressed: _isRunning ? null : _submitTask,
                    color: accentPrimary,
                  ),
                ),
              ],
            ),
          ),
          if (_output != null) ...[
            const SizedBox(height: sp24),
            SectionFrame(
              title: 'Output',
              accentColor: accentTeal,
              child: Padding(
                padding: const EdgeInsets.all(sp12),
                child: SelectableText(
                  _output!,
                  style: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: 16,
                    color: textPrimary,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
