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

  @override
  bool operator ==(Object other) =>
      identical(this, other) || (other is _ChatAgent && other.id == id);

  @override
  int get hashCode => id.hashCode;
}

enum _MsgRole { user, assistant }

class _ChatMessage {
  _ChatMessage({
    required this.role,
    required this.content,
    this.isStreaming = false,
  });

  final _MsgRole role;
  String content;
  bool isStreaming;
}

// ---------------------------------------------------------------------------
// ChatScreen — SSE-based chat with any agent (no workflow creation).
//
// Users can ask about:
//  - Status of recent task runs
//  - Previous run outcomes / errors
//  - How an agent behaves / what it can do
//  - Direct questions within the agent's domain
//
// Each conversation is a persistent ChatSession on the backend.
// The session_id is kept in memory; selecting a different agent starts fresh.
// ---------------------------------------------------------------------------

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, this.client});

  /// Optional injected [http.Client] for testing.
  final http.Client? client;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  late final http.Client _client;
  bool _ownsClient = false;

  // ── agents ───────────────────────────────────────────────────────────────
  List<_ChatAgent> _agents = [];
  bool _loadingAgents = false;
  String? _agentsError;
  _ChatAgent? _selectedAgent;

  // ── conversation ──────────────────────────────────────────────────────────
  String? _sessionId;
  final List<_ChatMessage> _messages = [];
  bool _streaming = false;

  // ── input ─────────────────────────────────────────────────────────────────
  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();

  @override
  void initState() {
    super.initState();
    _client = widget.client ?? http.Client();
    _ownsClient = widget.client == null;
    _loadAgents();
  }

  @override
  void dispose() {
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    if (_ownsClient) _client.close();
    super.dispose();
  }

  // ── helpers ───────────────────────────────────────────────────────────────

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

  // ── agents ────────────────────────────────────────────────────────────────

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
      if (decoded is! List) throw Exception('Unexpected format');
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

  void _onAgentSelected(_ChatAgent? agent) {
    if (agent == null || agent.id == _selectedAgent?.id) return;
    setState(() {
      _selectedAgent = agent;
      _sessionId = null; // new agent → new session
      _messages.clear();
    });
  }

  void _clearConversation() {
    setState(() {
      _sessionId = null;
      _messages.clear();
    });
  }

  // ── SSE send ─────────────────────────────────────────────────────────────

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty || _streaming || _selectedAgent == null) return;

    setState(() {
      _messages.add(_ChatMessage(role: _MsgRole.user, content: text));
      _inputCtrl.clear();
      _streaming = true;
    });
    _scrollToBottom();

    // Placeholder for streaming assistant reply
    final assistantMsg = _ChatMessage(
      role: _MsgRole.assistant,
      content: '',
      isStreaming: true,
    );
    setState(() => _messages.add(assistantMsg));
    _scrollToBottom();

    try {
      final url = AppLinks.apiUri('/agents/${_selectedAgent!.id}/chat');
      final request = http.Request('POST', url)
        ..headers['Content-Type'] = 'application/json'
        ..headers['Accept'] = 'text/event-stream'
        ..body = jsonEncode({
          'message': text,
          if (_sessionId != null) 'session_id': _sessionId,
        });

      final response = await _client.send(request);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final body = await response.stream.bytesToString();
        throw Exception('Chat failed (${response.statusCode}): $body');
      }

      String buffer = '';
      await for (final chunk
          in response.stream.transform(utf8.decoder)) {
        if (!mounted) break;
        buffer += chunk;
        // Parse complete SSE lines from buffer
        while (buffer.contains('\n')) {
          final idx = buffer.indexOf('\n');
          final line = buffer.substring(0, idx).trimRight();
          buffer = buffer.substring(idx + 1);

          if (!line.startsWith('data: ')) continue;
          final raw = line.substring(6);
          if (raw == '[DONE]') break;

          Map<String, dynamic> event;
          try {
            event = jsonDecode(raw) as Map<String, dynamic>;
          } catch (_) {
            continue;
          }

          final type = event['type']?.toString();
          if (type == 'session') {
            _sessionId = event['session_id']?.toString();
          } else if (type == 'delta') {
            final content = event['content']?.toString() ?? '';
            if (!mounted) break;
            setState(() {
              assistantMsg.content += content;
            });
            _scrollToBottom();
          } else if (type == 'done') {
            if (mounted) {
              setState(() {
                assistantMsg.isStreaming = false;
                _streaming = false;
              });
              _scrollToBottom();
            }
            return; // streaming complete — finally still runs (harmless)
          } else if (type == 'error') {
            final errMsg = event['message']?.toString() ?? 'Unknown error';
            if (!mounted) break;
            setState(() {
              assistantMsg.content =
                  assistantMsg.content.isEmpty ? errMsg : '${assistantMsg.content}\n\n⚠ $errMsg';
              assistantMsg.isStreaming = false;
            });
          }
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        assistantMsg.content = 'Error: $e';
        assistantMsg.isStreaming = false;
      });
    } finally {
      if (mounted) {
        setState(() {
          assistantMsg.isStreaming = false;
          _streaming = false;
        });
        _scrollToBottom();
      }
    }
  }

  // ── build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // ── Header bar ────────────────────────────────────────────────────
        _buildHeader(),
        // ── Message list ──────────────────────────────────────────────────
        Expanded(child: _buildMessageList()),
        // ── Input bar ─────────────────────────────────────────────────────
        _buildInputBar(),
      ],
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: sp16, vertical: sp12),
      decoration: const BoxDecoration(
        color: cardBg,
        border: Border(bottom: BorderSide(color: borderColor, width: 1)),
      ),
      child: Row(
        children: [
          // ── Title ────────────────────────────────────────────────────
          const Text(
            'AGENT CHAT',
            style: TextStyle(
              fontFamily: fontBody,
              fontSize: fontSizeBody,
              color: accentTeal,
              letterSpacing: 1.2,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(width: sp16),
          // ── Agent selector ────────────────────────────────────────────
          Expanded(child: _buildAgentDropdown()),
          // ── Clear button ──────────────────────────────────────────────
          if (_messages.isNotEmpty && !_streaming) ...[
            const SizedBox(width: sp8),
            RetroButton(
              label: 'CLEAR',
              icon: Icons.delete_outline,
              color: accentSlate,
              onPressed: _clearConversation,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAgentDropdown() {
    if (_loadingAgents) {
      return const SizedBox(
        width: 16,
        height: 16,
        child: CircularProgressIndicator(strokeWidth: 2, color: accentTeal),
      );
    }
    if (_agentsError != null) {
      return GestureDetector(
        onTap: _loadAgents,
        child: Text(
          'Error loading agents — tap to retry',
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: fontSizeSmall,
            color: accentPrimary,
          ),
        ),
      );
    }
    if (_agents.isEmpty) {
      return const Text(
        'No agents available',
        style: TextStyle(
          fontFamily: fontBody,
          fontSize: fontSizeSmall,
          color: textMuted,
        ),
      );
    }
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: borderColor),
        color: pageBg,
      ),
      padding: const EdgeInsets.symmetric(horizontal: sp8),
      child: DropdownButton<_ChatAgent>(
        value: _selectedAgent,
        isExpanded: true,
        underline: const SizedBox(),
        dropdownColor: cardBg,
        hint: const Text(
          'Select an agent…',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: fontSizeSmall,
            color: textMuted,
          ),
        ),
        style: const TextStyle(
          fontFamily: fontBody,
          fontSize: fontSizeSmall,
          color: textPrimary,
        ),
        items: _agents
            .map(
              (a) => DropdownMenuItem<_ChatAgent>(
                value: a,
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
        onChanged: _streaming ? null : _onAgentSelected,
      ),
    );
  }

  Widget _buildMessageList() {
    if (_selectedAgent == null) {
      return const Center(
        child: Text(
          'Select an agent above to start chatting.\n\nAsk about task status, previous runs, or anything within the agent\'s domain.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: fontSizeSmall,
            color: textMuted,
          ),
        ),
      );
    }
    if (_messages.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.chat_bubble_outline, color: textMuted, size: 36),
            const SizedBox(height: sp12),
            Text(
              'Chatting with ${_selectedAgent!.name}',
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: fontSizeBody,
                color: textPrimary,
              ),
            ),
            const SizedBox(height: sp4),
            const Text(
              'Ask about task status, previous runs,\nbehavior questions, or anything this agent knows.',
              textAlign: TextAlign.center,
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
    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.symmetric(horizontal: sp16, vertical: sp12),
      itemCount: _messages.length,
      itemBuilder: (ctx, i) => _MessageBubble(message: _messages[i]),
    );
  }

  Widget _buildInputBar() {
    final canSend = !_streaming && _selectedAgent != null;
    return Container(
      decoration: const BoxDecoration(
        color: cardBg,
        border: Border(top: BorderSide(color: borderColor, width: 1)),
      ),
      padding: const EdgeInsets.all(sp12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                border: Border.all(color: borderColor),
                color: pageBg,
              ),
              child: TextField(
                controller: _inputCtrl,
                minLines: 1,
                maxLines: 5,
                enabled: canSend,
                onSubmitted: canSend ? (_) => _send() : null,
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: fontSizeSmall,
                  color: textPrimary,
                ),
                decoration: InputDecoration(
                  contentPadding: const EdgeInsets.all(sp12),
                  border: InputBorder.none,
                  hintText: _selectedAgent == null
                      ? 'Select an agent first…'
                      : 'Ask anything…  (Enter to send)',
                  hintStyle: const TextStyle(
                    fontFamily: fontBody,
                    fontSize: fontSizeSmall,
                    color: textMuted,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: sp8),
          RetroButton(
            label: _streaming ? '…' : 'SEND',
            icon: _streaming ? null : Icons.send,
            color: accentTeal,
            onPressed: canSend ? _send : null,
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _MessageBubble — single chat bubble
// ---------------------------------------------------------------------------

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final _ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == _MsgRole.user;
    final bubbleColor = isUser ? accentTeal.withAlpha(30) : cardBg;
    final borderCol = isUser ? accentTeal : borderColor;
    final label = isUser ? 'YOU' : 'AGENT';
    final labelColor = isUser ? accentTeal : accentSlate;

    return Padding(
      padding: const EdgeInsets.only(bottom: sp12),
      child: Align(
        alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.78,
          ),
          child: Container(
            decoration: BoxDecoration(
              color: bubbleColor,
              border: Border.all(color: borderCol, width: 1),
            ),
            padding: const EdgeInsets.all(sp12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      label,
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: fontSizeSmall,
                        color: labelColor,
                        letterSpacing: 0.8,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (message.isStreaming) ...[
                      const SizedBox(width: sp8),
                      const SizedBox(
                        width: 10,
                        height: 10,
                        child: CircularProgressIndicator(
                          strokeWidth: 1.5,
                          color: accentTeal,
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: sp4),
                if (message.content.isNotEmpty)
                  SelectableText(
                    message.content,
                    style: TextStyle(
                      fontFamily: fontBody,
                      fontSize: fontSizeSmall,
                      color: textPrimary,
                      height: 1.5,
                    ),
                  )
                else if (message.isStreaming)
                  const Text(
                    '▋',
                    style: TextStyle(
                      fontFamily: fontBody,
                      fontSize: fontSizeSmall,
                      color: accentTeal,
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
