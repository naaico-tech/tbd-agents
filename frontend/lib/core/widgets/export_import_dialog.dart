import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import '../config/app_links.dart';
import '../theme/design_tokens.dart';
import 'retro_card.dart';

// ── Export ───────────────────────────────────────────────────────────────────

/// Fetches [apiPath] from the backend and shows a scrollable JSON preview
/// dialog with a "COPY JSON" button.
Future<void> showExportDialog(
  BuildContext context, {
  required String apiPath,
  required String resourceLabel,
}) async {
  // Show a loading indicator while fetching.
  showDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => const Center(child: CircularProgressIndicator()),
  );

  String jsonText;
  try {
    final response = await http.get(AppLinks.apiUri(apiPath));
    if (!context.mounted) return;
    Navigator.of(context).pop(); // dismiss loading

    if (response.statusCode < 200 || response.statusCode >= 300) {
      _showErrorSnackbar(
        context,
        'Export failed (${response.statusCode}): ${response.body}',
      );
      return;
    }
    // Pretty-print the JSON for readability.
    final decoded = jsonDecode(response.body);
    jsonText = const JsonEncoder.withIndent('  ').convert(decoded);
  } catch (e) {
    if (!context.mounted) return;
    Navigator.of(context).pop();
    _showErrorSnackbar(context, 'Export error: $e');
    return;
  }

  if (!context.mounted) return;
  showDialog(
    context: context,
    builder: (ctx) => _ExportDialog(
      resourceLabel: resourceLabel,
      jsonText: jsonText,
    ),
  );
}

class _ExportDialog extends StatelessWidget {
  const _ExportDialog({
    required this.resourceLabel,
    required this.jsonText,
  });

  final String resourceLabel;
  final String jsonText;

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 680, maxHeight: 560),
        decoration: retroCardDecoration(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── Header ──────────────────────────────────────────────────
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: sp16,
                vertical: sp12,
              ),
              decoration: const BoxDecoration(
                color: accentTeal,
                border: Border(
                  bottom: BorderSide(color: borderColor, width: borderWidth),
                ),
              ),
              child: Row(
                children: [
                  const Icon(Icons.download_outlined, size: 14, color: cardBg),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: Text(
                      'EXPORT $resourceLabel'.toUpperCase(),
                      style: const TextStyle(
                        fontFamily: fontDisplay,
                        fontSize: 9,
                        color: cardBg,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  GestureDetector(
                    onTap: () => Navigator.of(context).pop(),
                    child: const Icon(Icons.close, size: 16, color: cardBg),
                  ),
                ],
              ),
            ),
            // ── Body ────────────────────────────────────────────────────
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(sp16),
                child: SelectableText(
                  jsonText,
                  style: const TextStyle(
                    fontFamily: fontFallback,
                    fontSize: 11,
                    color: textPrimary,
                    height: 1.5,
                  ),
                ),
              ),
            ),
            // ── Footer ──────────────────────────────────────────────────
            Container(
              padding: const EdgeInsets.all(sp12),
              decoration: const BoxDecoration(
                border: Border(
                  top: BorderSide(color: borderColor, width: borderWidth),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  RetroButton(
                    label: 'COPY JSON',
                    icon: Icons.copy_outlined,
                    color: accentTeal,
                    onPressed: () async {
                      await Clipboard.setData(ClipboardData(text: jsonText));
                      if (context.mounted) {
                        _showSuccessSnackbar(context, 'Copied to clipboard');
                      }
                    },
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: 'CLOSE',
                    color: accentSlate,
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Import ───────────────────────────────────────────────────────────────────

/// Shows a dialog with a multi-line JSON text field. On submit, POSTs the
/// parsed `items` array to [apiPath] and displays the result.
Future<void> showImportDialog(
  BuildContext context, {
  required String apiPath,
  required String resourceLabel,
}) async {
  showDialog(
    context: context,
    builder: (ctx) => _ImportDialog(
      apiPath: apiPath,
      resourceLabel: resourceLabel,
    ),
  );
}

class _ImportDialog extends StatefulWidget {
  const _ImportDialog({
    required this.apiPath,
    required this.resourceLabel,
  });

  final String apiPath;
  final String resourceLabel;

  @override
  State<_ImportDialog> createState() => _ImportDialogState();
}

class _ImportDialogState extends State<_ImportDialog> {
  final TextEditingController _controller = TextEditingController();
  bool _loading = false;
  String? _resultMessage;
  bool _resultIsError = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final raw = _controller.text.trim();
    if (raw.isEmpty) return;

    // Parse the pasted JSON to extract the items array.
    Map<String, dynamic> parsed;
    try {
      parsed = jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      setState(() {
        _resultMessage = 'Invalid JSON — could not parse.';
        _resultIsError = true;
      });
      return;
    }

    if (!parsed.containsKey('items')) {
      setState(() {
        _resultMessage = 'JSON must contain an "items" array.';
        _resultIsError = true;
      });
      return;
    }

    final items = parsed['items'] as List<dynamic>;

    setState(() {
      _loading = true;
      _resultMessage = null;
    });

    try {
      final body = jsonEncode({'items': items});
      final response = await http.post(
        AppLinks.apiUri(widget.apiPath),
        headers: {'Content-Type': 'application/json'},
        body: body,
      );

      if (!mounted) return;
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      final created = decoded['created'] as int? ?? 0;
      final errors = (decoded['errors'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList();

      final msg = StringBuffer('Imported $created item(s).');
      if (errors.isNotEmpty) {
        msg.write('\n\nErrors:\n${errors.join('\n')}');
      }

      setState(() {
        _loading = false;
        _resultMessage = msg.toString();
        _resultIsError = errors.isNotEmpty && created == 0;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _resultMessage = 'Request failed: $e';
        _resultIsError = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: cardBg,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 680, maxHeight: 600),
        decoration: retroCardDecoration(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── Header ──────────────────────────────────────────────────
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: sp16,
                vertical: sp12,
              ),
              decoration: const BoxDecoration(
                color: accentSlate,
                border: Border(
                  bottom: BorderSide(color: borderColor, width: borderWidth),
                ),
              ),
              child: Row(
                children: [
                  const Icon(Icons.upload_outlined, size: 14, color: cardBg),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: Text(
                      'IMPORT ${widget.resourceLabel}'.toUpperCase(),
                      style: const TextStyle(
                        fontFamily: fontDisplay,
                        fontSize: 9,
                        color: cardBg,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  GestureDetector(
                    onTap: () => Navigator.of(context).pop(),
                    child: const Icon(Icons.close, size: 16, color: cardBg),
                  ),
                ],
              ),
            ),
            // ── Body ────────────────────────────────────────────────────
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(sp16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Paste exported JSON bundle below:',
                      style: TextStyle(
                        fontFamily: fontBody,
                        fontSize: 12,
                        color: textMuted,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: sp12),
                    Container(
                      decoration: BoxDecoration(
                        border: Border.all(
                          color: borderColor,
                          width: borderWidth,
                        ),
                        color: pageBg,
                      ),
                      child: TextField(
                        controller: _controller,
                        maxLines: 14,
                        style: const TextStyle(
                          fontFamily: fontFallback,
                          fontSize: 11,
                          color: textPrimary,
                          height: 1.5,
                        ),
                        decoration: const InputDecoration(
                          contentPadding: EdgeInsets.all(sp12),
                          hintText: '{ "items": [ ... ] }',
                          hintStyle: TextStyle(color: textMuted),
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                    if (_resultMessage != null) ...[
                      const SizedBox(height: sp12),
                      Container(
                        padding: const EdgeInsets.all(sp12),
                        decoration: BoxDecoration(
                          color: _resultIsError
                              ? accentPrimary.withAlpha(30)
                              : accentTeal.withAlpha(30),
                          border: Border.all(
                            color:
                                _resultIsError ? accentPrimary : accentTeal,
                            width: borderWidth,
                          ),
                        ),
                        child: Text(
                          _resultMessage!,
                          style: TextStyle(
                            fontFamily: fontBody,
                            fontSize: 11,
                            color:
                                _resultIsError ? accentPrimary : accentTeal,
                            height: 1.5,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            // ── Footer ──────────────────────────────────────────────────
            Container(
              padding: const EdgeInsets.all(sp12),
              decoration: const BoxDecoration(
                border: Border(
                  top: BorderSide(color: borderColor, width: borderWidth),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  if (_loading)
                    const Padding(
                      padding: EdgeInsets.only(right: sp12),
                      child: SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    ),
                  RetroButton(
                    label: 'IMPORT',
                    icon: Icons.upload_outlined,
                    color: accentSlate,
                    onPressed: _loading ? null : _submit,
                  ),
                  const SizedBox(width: sp8),
                  RetroButton(
                    label: 'CLOSE',
                    color: accentPrimary,
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Snackbar helpers ─────────────────────────────────────────────────────────

void _showSuccessSnackbar(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(
        message,
        style: const TextStyle(fontFamily: fontBody, fontSize: 11),
      ),
      backgroundColor: accentTeal,
      duration: const Duration(seconds: 2),
    ),
  );
}

void _showErrorSnackbar(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(
        message,
        style: const TextStyle(fontFamily: fontBody, fontSize: 11),
      ),
      backgroundColor: accentPrimary,
      duration: const Duration(seconds: 4),
    ),
  );
}
