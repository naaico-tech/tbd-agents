import 'package:flutter/material.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/retro_card.dart';

// ---------------------------------------------------------------------------
// ChatScreen — streaming chat interface, ready to wire to /api/chat SSE.
// ---------------------------------------------------------------------------
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final List<_ChatMessage> _messages = [];
  bool _sending = false;

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _sendMessage() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _sending) return;

    setState(() {
      _messages.add(_ChatMessage(text: text, isUser: true));
      _controller.clear();
      _sending = true;
    });
    _scrollToBottom();

    // TODO: POST /api/chat and stream SSE response tokens
    await Future.delayed(const Duration(milliseconds: 800));
    setState(() {
      _messages.add(
        const _ChatMessage(
          text: '[Agent response will stream here via /api/chat]',
          isUser: false,
        ),
      );
      _sending = false;
    });
    _scrollToBottom();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        children: [
          Expanded(
            child: RetroCard(
              padding: EdgeInsets.zero,
              child: _messages.isEmpty
                  ? const Center(
                      child: Text(
                        'Start a conversation…',
                        style: TextStyle(
                          fontFamily: fontBody,
                          fontSize: 16,
                          color: textMuted,
                        ),
                      ),
                    )
                  : ListView.separated(
                      controller: _scrollController,
                      padding: const EdgeInsets.all(sp16),
                      itemCount: _messages.length,
                      separatorBuilder: (context, index) =>
                          const SizedBox(height: sp12),
                      itemBuilder: (_, i) =>
                          _MessageBubble(message: _messages[i]),
                    ),
            ),
          ),
          const SizedBox(height: sp12),
          _InputBar(
            controller: _controller,
            sending: _sending,
            onSend: _sendMessage,
          ),
        ],
      ),
    );
  }
}

class _ChatMessage {
  const _ChatMessage({required this.text, required this.isUser});
  final String text;
  final bool isUser;
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});
  final _ChatMessage message;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: message.isUser
          ? MainAxisAlignment.end
          : MainAxisAlignment.start,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (!message.isUser) ...[
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: accentTeal.withAlpha(40),
              border: Border.all(color: accentTeal, width: 1),
            ),
            child: const Icon(
              Icons.smart_toy_outlined,
              size: 14,
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
              color: message.isUser ? accentPrimary.withAlpha(20) : cardBg,
              border: Border.all(
                color: message.isUser ? accentPrimary : borderColor,
                width: 1,
              ),
            ),
            child: SelectableText(
              message.text,
              style: TextStyle(
                fontFamily: fontBody,
                fontSize: 16,
                color: message.isUser ? accentPrimary : textPrimary,
              ),
            ),
          ),
        ),
        if (message.isUser) const SizedBox(width: 36),
      ],
    );
  }
}

class _InputBar extends StatelessWidget {
  const _InputBar({
    required this.controller,
    required this.sending,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool sending;
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
                fontSize: 16,
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
                  fontSize: 16,
                  color: textMuted,
                ),
              ),
              onSubmitted: (_) => onSend(),
            ),
          ),
        ),
        const SizedBox(width: sp8),
        RetroButton(
          label: sending ? '…' : 'SEND',
          icon: Icons.send,
          onPressed: sending ? null : onSend,
          color: accentPrimary,
        ),
      ],
    );
  }
}
