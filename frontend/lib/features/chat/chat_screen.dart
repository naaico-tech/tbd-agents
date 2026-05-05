import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../../core/config/app_links.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/retro_card.dart';

// ---------------------------------------------------------------------------
// Data models
// ---------------------------------------------------------------------------

class _ChatAgent {
  final String id;
  final String name;

  const _ChatAgent({required this.id, required this.name});

  factory _ChatAgent.fromJson(Map<String, dynamic> j) => _ChatAgent(
    id: j['id']?.toString() ?? '',
    name: j['name']?.toString() ?? 'Unknown',
  );
}

class _ChatMessage {
  final String role; // 'user' | 'assistant'
  final String content;
  final bool isError;

  const _ChatMessage({
    required this.role,
    required this.content,
    this.isError = false,
  });
}

// ---------------------------------------------------------------------------
// ChatScreen — full chat interface with agent selector and message bubbles.
// ---------------------------------------------------------------------------
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, this.client});

  /// Optional injected [http.Client] — useful for testing. When null, the
  /// screen creates and owns its own client (closed in [dispose]).
  final http.Client? client;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  late final http.Client _client;
  bool _ownsClient = false;

  // ── state ────────────────────────────────────────────────────────────────
  List<_ChatAgent> _agents = [];
  String? _selectedAgentId;
  String? _workflowId;
  final List<_ChatMessage> _messages = [];
  final _inputCtrl = TextEditingController();
  bool _isSending = false;
  final _scrollCtrl = ScrollController();

  bool _loadingAgents = false;
  String? _agentsError;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    if (widget.client != null) {
      _client = widget.client!;
      _ownsClient = false;
    } else {
      _client = http.Client();
      _ownsClient = true;
    }
    _loadAgents();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    if (_ownsClient) _client.close();
    super.dispose();
  }

  // ── scroll ───────────────────────────────────────────────────────────────

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // ── agents ───────────────────────────────────────────────────────────────

  Future<void> _loadAgents() async {
    setState(() {
      _loadingAgents = true;
      _agentsError = null;
    });
    try {
      final resp = await _client.get(AppLinks.apiUri('/agents'));
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        throw Exception('Failed to load agents (${resp.statusCode})');
      }
      final decoded = jsonDecode(resp.body);
      if (decoded is! List) throw Exception('Unexpected response format');
      final list = decoded
          .whereType<Map<String, dynamic>>()
          .map(_ChatAgent.fromJson)
          .where((a) => a.id.isNotEmpty)
          .toList();
      if (!mounted) return;
      setState(() {
        _agents = list;
        _loadingAgents = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _agentsError = e.toString();
        _loadingAgents = false;
      });
    }
  }

  // ── agent selection / chat start ─────────────────────────────────────────

  Future<void> _onAgentSelected(String? agentId) async {
    if (agentId == null || agentId == _selectedAgentId) return;
    setState(() {
      _selectedAgentId = agentId;
      _workflowId = null;
      _messages.clear();
    });
    try {
      final resp = await _client.post(
        AppLinks.apiUri('/chat/start'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'agent_id': agentId}),
      );
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        throw Exception('Failed to start chat session (${resp.statusCode})');
      }
      final decoded = jsonDecode(resp.body) as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _workflowId = decoded['workflow_id']?.toString();
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _messages.add(
          _ChatMessage(
            role: 'assistant',
            content: 'Failed to start chat session: $e',
            isError: true,
          ),
        );
      });
      _scrollToBottom();
    }
  }

  // ── send / polling ───────────────────────────────────────────────────────

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty || _isSending || _workflowId == null) return;

    setState(() {
      _messages.add(_ChatMessage(role: 'user', content: text));
      _inputCtrl.clear();
      _isSending = true;
    });
    _scrollToBottom();

    try {
      final resp = await _client.post(
        AppLinks.apiUri('/workflows/$_workflowId/prompt'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'prompt': text}),
      );
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        final decoded = jsonDecode(resp.body);
        throw Exception(
          decoded is Map ? (decoded['detail'] ?? 'Send failed (${resp.statusCode})') : 'Send failed (${resp.statusCode})',
        );
      }
      final decoded = jsonDecode(resp.body) as Map<String, dynamic>;
      final taskId = decoded['task_id']?.toString();

      if (taskId == null || taskId.isEmpty) {
        // Immediate response — no polling needed.
        final response = decoded['response']?.toString() ?? '';
        if (!mounted) return;
        setState(() {
          _messages.add(_ChatMessage(role: 'assistant', content: response));
          _isSending = false;
        });
        _scrollToBottom();
        return;
      }

      await _pollUntilDone(taskId);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _messages.add(
          _ChatMessage(role: 'assistant', content: 'Error: $e', isError: true),
        );
        _isSending = false;
      });
      _scrollToBottom();
    }
  }

  Future<void> _pollUntilDone(String taskId) async {
    _pollTimer?.cancel();
    final completer = Completer<void>();

    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) async {
      if (!mounted) {
        _pollTimer?.cancel();
        if (!completer.isCompleted) completer.complete();
        return;
      }
      try {
        final resp = await _client.get(AppLinks.apiUri('/tasks/$taskId'));
        if (resp.statusCode < 200 || resp.statusCode >= 300) return;
        final decoded = jsonDecode(resp.body) as Map<String, dynamic>;
        final status = decoded['status']?.toString() ?? '';
        if (status == 'completed' || status == 'failed') {
          _pollTimer?.cancel();
          final response = decoded['response']?.toString() ?? '';
          if (!mounted) {
            if (!completer.isCompleted) completer.complete();
            return;
          }
          setState(() {
            _messages.add(
              _ChatMessage(
                role: 'assistant',
                content: response.isNotEmpty
                    ? response
                    : (status == 'failed' ? 'Task failed.' : '(No response)'),
                isError: status == 'failed',
              ),
            );
            _isSending = false;
          });
          _scrollToBottom();
          if (!completer.isCompleted) completer.complete();
        }
      } catch (_) {
        // Ignore transient poll errors and keep retrying.
      }
    });

    await completer.future;
  }

  // ── clear ────────────────────────────────────────────────────────────────

  void _clearChat() {
    setState(() => _messages.clear());
  }

  // ── build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final selectedAgent = _agents.firstWhere(
      (a) => a.id == _selectedAgentId,
      orElse: () => const _ChatAgent(id: '', name: ''),
    );

    return Padding(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ── Header ───────────────────────────────────────────────────
          _ScreenHeader(
            title: 'CHAT',
            subtitle: selectedAgent.name.isNotEmpty
                ? selectedAgent.name
                : 'Talk to an agent',
            actions: [
              if (_messages.isNotEmpty)
                RetroButton(
                  label: 'CLEAR',
                  icon: Icons.delete_outline,
                  onPressed: _clearChat,
                  color: accentSlate,
                ),
            ],
          ),
          const SizedBox(height: sp16),

          // ── Agent selector ────────────────────────────────────────────
          _AgentSelector(
            agents: _agents,
            selectedAgentId: _selectedAgentId,
            loading: _loadingAgents,
            error: _agentsError,
            onRetry: _loadAgents,
            onChanged: _onAgentSelected,
          ),
          const SizedBox(height: sp12),

          // ── Messages area ─────────────────────────────────────────────
          Expanded(
            child: RetroCard(
              padding: EdgeInsets.zero,
              child: _MessagesArea(
                messages: _messages,
                scrollCtrl: _scrollCtrl,
                workflowId: _workflowId,
                selectedAgentId: _selectedAgentId,
              ),
            ),
          ),

          // ── Typing indicator ──────────────────────────────────────────
          if (_isSending) ...[
            const SizedBox(height: sp8),
            const _TypingIndicator(),
          ],
          const SizedBox(height: sp12),

          // ── Input area ────────────────────────────────────────────────
          _InputArea(
            controller: _inputCtrl,
            isSending: _isSending,
            canSend: _workflowId != null,
            onSend: _send,
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _ScreenHeader
// ---------------------------------------------------------------------------

class _ScreenHeader extends StatelessWidget {
  const _ScreenHeader({
    required this.title,
    required this.subtitle,
    this.actions = const [],
  });

  final String title;
  final String subtitle;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(
            horizontal: sp12,
            vertical: sp8,
          ),
          decoration: BoxDecoration(
            color: accentLavender.withAlpha(20),
            border: Border.all(color: accentLavender, width: borderWidth),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.chat_bubble_outline,
                size: 14,
                color: accentLavender,
              ),
              const SizedBox(width: sp8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontFamily: fontDisplay,
                      fontSize: 10,
                      color: accentLavender,
                      letterSpacing: 2,
                    ),
                  ),
                  Text(
                    subtitle,
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: fontSizeSmall,
                      color: textMuted,
                      letterSpacing: 1,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const Spacer(),
        ...actions
            .expand((w) => [w, const SizedBox(width: sp8)])
            .toList()
          ..removeLast(),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// _AgentSelector
// ---------------------------------------------------------------------------

class _AgentSelector extends StatelessWidget {
  const _AgentSelector({
    required this.agents,
    required this.selectedAgentId,
    required this.loading,
    required this.error,
    required this.onRetry,
    required this.onChanged,
  });

  final List<_ChatAgent> agents;
  final String? selectedAgentId;
  final bool loading;
  final String? error;
  final VoidCallback onRetry;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return _selectorShell(
        child: const Row(
          children: [
            SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(accentTeal),
              ),
            ),
            SizedBox(width: sp8),
            Text(
              'Loading agents…',
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeSmall,
                color: textMuted,
              ),
            ),
          ],
        ),
      );
    }

    if (error != null) {
      return _selectorShell(
        borderColor: accentPrimary,
        child: Row(
          children: [
            const Icon(Icons.error_outline, size: 14, color: accentPrimary),
            const SizedBox(width: sp8),
            const Expanded(
              child: Text(
                'Failed to load agents',
                style: TextStyle(
                  fontFamily: fontBody,
                  fontSize: fontSizeSmall,
                  color: accentPrimary,
                ),
              ),
            ),
            RetroButton(
              label: 'RETRY',
              onPressed: onRetry,
              color: accentAmber,
            ),
          ],
        ),
      );
    }

    if (agents.isEmpty) {
      return _selectorShell(
        child: const Text(
          'No agents available',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: fontSizeSmall,
            color: textMuted,
          ),
        ),
      );
    }

    return Container(
      decoration: BoxDecoration(
        color: cardBg,
        border: Border.all(color: borderColor, width: borderWidth),
      ),
      padding: const EdgeInsets.symmetric(horizontal: sp12),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: selectedAgentId,
          hint: const Text(
            'Select an agent…',
            style: TextStyle(
              fontFamily: fontBody,
              fontSize: fontSizeSmall,
              color: textMuted,
            ),
          ),
          isExpanded: true,
          dropdownColor: cardBg,
          icon: const Icon(Icons.expand_more, size: 14, color: textMuted),
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: fontSizeSmall,
            color: textPrimary,
          ),
          items: agents
              .map(
                (a) => DropdownMenuItem<String>(
                  value: a.id,
                  child: Text(
                    a.name,
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: fontSizeSmall,
                      color: textPrimary,
                    ),
                  ),
                ),
              )
              .toList(),
          onChanged: onChanged,
        ),
      ),
    );
  }

  Widget _selectorShell({required Widget child, Color borderColor = const Color(0xFF1A1A2E)}) {
    return Container(
      padding: const EdgeInsets.all(sp12),
      decoration: BoxDecoration(
        color: cardBg,
        border: Border.all(color: borderColor, width: borderWidth),
      ),
      child: child,
    );
  }
}

// ---------------------------------------------------------------------------
// _MessagesArea
// ---------------------------------------------------------------------------

class _MessagesArea extends StatelessWidget {
  const _MessagesArea({
    required this.messages,
    required this.scrollCtrl,
    required this.workflowId,
    required this.selectedAgentId,
  });

  final List<_ChatMessage> messages;
  final ScrollController scrollCtrl;
  final String? workflowId;
  final String? selectedAgentId;

  @override
  Widget build(BuildContext context) {
    if (selectedAgentId == null) {
      return const Center(
        child: Text(
          '▲  Select an agent above to start chatting',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: fontSizeSmall,
            color: textMuted,
            letterSpacing: 1,
          ),
          textAlign: TextAlign.center,
        ),
      );
    }

    if (workflowId == null) {
      return const Center(
        child: SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            valueColor: AlwaysStoppedAnimation<Color>(accentTeal),
          ),
        ),
      );
    }

    if (messages.isEmpty) {
      return const Center(
        child: Text(
          'Start a conversation…',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: fontSizeSmall,
            color: textMuted,
            letterSpacing: 1,
          ),
        ),
      );
    }

    return ListView.separated(
      controller: scrollCtrl,
      padding: const EdgeInsets.all(sp16),
      itemCount: messages.length,
      separatorBuilder: (context, index) => const SizedBox(height: sp12),
      itemBuilder: (_, i) => _MessageBubble(message: messages[i]),
    );
  }
}

// ---------------------------------------------------------------------------
// _MessageBubble
// ---------------------------------------------------------------------------

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final _ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    final isError = message.isError;

    final bubbleColor = isError
        ? accentPrimary.withAlpha(20)
        : isUser
            ? accentLavender.withAlpha(20)
            : accentSlate.withAlpha(20);

    final borderCol = isError
        ? accentPrimary
        : isUser
            ? accentLavender
            : accentSlate;

    final textColor = isError
        ? accentPrimary
        : isUser
            ? accentLavender
            : textPrimary;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.75,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!isUser) ...[
              Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  color: accentTeal.withAlpha(30),
                  border: Border.all(color: accentTeal, width: 1),
                ),
                child: const Icon(
                  Icons.smart_toy_outlined,
                  size: 12,
                  color: accentTeal,
                ),
              ),
              const SizedBox(width: sp8),
            ],
            Flexible(
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: sp12,
                  vertical: sp8,
                ),
                decoration: BoxDecoration(
                  color: bubbleColor,
                  border: Border.all(color: borderCol, width: 1),
                ),
                child: SelectableText(
                  message.content,
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeSmall,
                    color: textColor,
                    height: fontHeightBody,
                  ),
                ),
              ),
            ),
            if (isUser) const SizedBox(width: sp16),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _TypingIndicator — animated "Agent is thinking…"
// ---------------------------------------------------------------------------

class _TypingIndicator extends StatefulWidget {
  const _TypingIndicator();

  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _fade;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..repeat(reverse: true);
    _fade = Tween<double>(begin: 0.4, end: 1.0).animate(_ctrl);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: FadeTransition(
        opacity: _fade,
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: sp12,
            vertical: sp8,
          ),
          decoration: BoxDecoration(
            color: accentTeal.withAlpha(20),
            border: Border.all(color: accentTeal, width: 1),
          ),
          child: const Text(
            'Agent is thinking…',
            style: TextStyle(
              fontFamily: fontBody,
              fontSize: fontSizeSmall,
              color: accentTeal,
              letterSpacing: 1,
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _InputArea
// ---------------------------------------------------------------------------

class _InputArea extends StatelessWidget {
  const _InputArea({
    required this.controller,
    required this.isSending,
    required this.canSend,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool isSending;
  final bool canSend;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Container(
            decoration: BoxDecoration(
              color: cardBg,
              border: Border.all(color: borderColor, width: borderWidth),
            ),
            child: TextField(
              controller: controller,
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeSmall,
                color: textPrimary,
              ),
              decoration: const InputDecoration(
                contentPadding: EdgeInsets.symmetric(
                  horizontal: sp12,
                  vertical: sp10,
                ),
                border: InputBorder.none,
                hintText: 'Type a message…',
                hintStyle: TextStyle(
                  fontFamily: fontBody,
                  fontSize: fontSizeSmall,
                  color: textMuted,
                ),
              ),
              onSubmitted: (_) {
                if (!isSending && canSend) onSend();
              },
            ),
          ),
        ),
        const SizedBox(width: sp8),
        RetroButton(
          label: isSending ? '…' : 'SEND',
          icon: Icons.send,
          onPressed: (!isSending && canSend) ? onSend : null,
          color: accentPrimary,
        ),
      ],
    );
  }
}
