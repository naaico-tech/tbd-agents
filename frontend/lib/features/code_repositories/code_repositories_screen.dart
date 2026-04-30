import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import '../../core/config/app_links.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/widgets/export_import_dialog.dart';
import '../../core/widgets/retro_card.dart';

// ---------------------------------------------------------------------------
// CodeRepositoriesScreen — first-class CRUD UI for the CodeRepository API.
// ---------------------------------------------------------------------------
class CodeRepositoriesScreen extends StatefulWidget {
  const CodeRepositoriesScreen({super.key});

  @override
  State<CodeRepositoriesScreen> createState() => _CodeRepositoriesScreenState();
}

class _CodeRepositoriesScreenState extends State<CodeRepositoriesScreen> {
  final _client = http.Client();
  final _tagFilterCtrl = TextEditingController();

  bool _loading = true;
  Object? _error;
  List<Map<String, dynamic>> _repositories = const [];
  List<Map<String, dynamic>> _tokens = const [];

  @override
  void initState() {
    super.initState();
    _reload();
  }

  @override
  void dispose() {
    _client.close();
    _tagFilterCtrl.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final tag = _tagFilterCtrl.text.trim();
      final query = tag.isEmpty ? null : {'tags': tag};
      final repos = await _getList(
        AppLinks.apiUri('/code-repositories', queryParameters: query),
      );
      final tokens = await _getList(AppLinks.apiUri('/tokens')).catchError(
        (_) => const <Map<String, dynamic>>[],
      );
      if (!mounted) return;
      setState(() {
        _repositories = repos;
        _tokens = tokens;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  Future<List<Map<String, dynamic>>> _getList(Uri uri) async {
    final resp = await _client.get(uri);
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception('GET $uri failed (${resp.statusCode}): ${resp.body}');
    }
    final body = resp.body.trim();
    if (body.isEmpty) return const [];
    final decoded = jsonDecode(body);
    if (decoded is! List) throw Exception('Unexpected response for $uri');
    return decoded.whereType<Map<String, dynamic>>().toList();
  }

  Future<Map<String, dynamic>?> _request(
    String method,
    String path, {
    Object? body,
  }) async {
    final uri = AppLinks.apiUri(path);
    final headers = const {'Content-Type': 'application/json'};
    final encoded = body == null ? null : jsonEncode(body);
    http.Response resp;
    switch (method) {
      case 'POST':
        resp = await _client.post(uri, headers: headers, body: encoded);
        break;
      case 'PUT':
        resp = await _client.put(uri, headers: headers, body: encoded);
        break;
      case 'DELETE':
        resp = await _client.delete(uri, headers: headers);
        break;
      default:
        resp = await _client.get(uri, headers: headers);
    }
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      String detail = resp.body;
      try {
        final parsed = jsonDecode(resp.body);
        if (parsed is Map && parsed['detail'] != null) {
          detail = parsed['detail'].toString();
        }
      } catch (_) {}
      throw Exception('${resp.statusCode}: $detail');
    }
    if (resp.statusCode == 204 || resp.body.trim().isEmpty) return null;
    final decoded = jsonDecode(resp.body);
    return decoded is Map<String, dynamic> ? decoded : {'value': decoded};
  }

  void _toast(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: isError ? accentPrimary : accentSlate,
      ),
    );
  }

  Future<void> _createOrEdit({Map<String, dynamic>? existing}) async {
    final saved = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _RepositoryEditorDialog(
        initial: existing,
        tokens: _tokens,
      ),
    );
    if (saved == null) return;
    try {
      if (existing == null) {
        await _request('POST', '/code-repositories', body: saved);
        _toast('Repository created');
      } else {
        await _request(
          'PUT',
          '/code-repositories/${existing['id']}',
          body: saved,
        );
        _toast('Repository updated');
      }
      _reload();
    } catch (e) {
      _toast('Save failed: $e', isError: true);
    }
  }

  Future<void> _sync(Map<String, dynamic> repo) async {
    _toast('Syncing ${repo['name']}…');
    try {
      final res = await _request(
        'POST',
        '/code-repositories/${repo['id']}/sync',
      );
      final sha = (res?['last_commit_sha'] as String?)?.substring(0, 7) ?? '';
      _toast(
        'Sync ${res?['status'] ?? 'done'}${sha.isNotEmpty ? ' @ $sha' : ''}',
      );
      _reload();
    } catch (e) {
      _toast('Sync failed: $e', isError: true);
    }
  }

  Future<void> _index(Map<String, dynamic> repo) async {
    _toast('Indexing ${repo['name']}…');
    try {
      final res = await _request(
        'POST',
        '/code-repositories/${repo['id']}/index',
      );
      if (res?['indexed'] == true) {
        _toast(
          'Indexed ${res?['file_count'] ?? 0} files / '
          '${res?['chunk_count'] ?? 0} chunks',
        );
      } else {
        _toast('Index skipped: ${res?['reason'] ?? 'no changes'}');
      }
      _reload();
    } catch (e) {
      _toast('Index failed: $e', isError: true);
    }
  }

  Future<void> _delete(Map<String, dynamic> repo) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete repository?'),
        content: Text(
          'Drop "${repo['name']}", its local checkout and vector index? '
          'This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text(
              'Delete',
              style: TextStyle(color: accentPrimary),
            ),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _request('DELETE', '/code-repositories/${repo['id']}');
      _toast('Repository deleted');
      _reload();
    } catch (e) {
      _toast('Delete failed: $e', isError: true);
    }
  }

  Future<void> _search(Map<String, dynamic> repo) async {
    await showDialog<void>(
      context: context,
      builder: (_) => _RepositorySearchDialog(
        repo: repo,
        runSearch: (query, limit) async {
          final res = await _request(
            'POST',
            '/code-repositories/${repo['id']}/search',
            body: {'query': query, 'limit': limit},
          );
          final results = (res?['results'] as List?) ?? const [];
          return results.whereType<Map<String, dynamic>>().toList();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(sp24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ScreenHeader(
            title: 'CODE REPOSITORIES',
            subtitle: 'Indexed codebases attached to workflows by id or tag',
            actions: [
              RetroButton(
                label: 'EXPORT',
                onPressed: () => showExportDialog(
                  context,
                  apiPath: '/code-repositories/export',
                  resourceLabel: 'CODE REPOSITORIES',
                ),
                icon: Icons.download_outlined,
                color: accentSlate,
              ),
              RetroButton(
                label: 'IMPORT',
                onPressed: () => showImportDialog(
                  context,
                  apiPath: '/code-repositories/import',
                  resourceLabel: 'CODE REPOSITORIES',
                ),
                icon: Icons.upload_outlined,
                color: accentSlate,
              ),
              RetroButton(
                label: 'NEW',
                onPressed: () => _createOrEdit(),
                icon: Icons.add,
                color: accentPrimary,
              ),
            ],
          ),
          const SizedBox(height: sp16),
          _FilterBar(
            controller: _tagFilterCtrl,
            onSubmit: _reload,
            onReload: _reload,
          ),
          const SizedBox(height: sp16),
          SectionFrame(
            title: 'Registered Repositories',
            accentColor: accentSlate,
            minHeight: 280,
            child: _buildBody(),
          ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.all(sp24),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null) {
      return Padding(
        padding: const EdgeInsets.all(sp16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Failed to load repositories.',
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 16,
                color: textPrimary,
              ),
            ),
            const SizedBox(height: sp8),
            Text(
              _error.toString(),
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 14,
                color: textMuted,
              ),
            ),
            const SizedBox(height: sp16),
            RetroButton(
              label: 'RETRY',
              icon: Icons.refresh,
              onPressed: _reload,
              color: accentPrimary,
            ),
          ],
        ),
      );
    }
    if (_repositories.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(sp24),
        child: _EmptyState(
          icon: Icons.source_outlined,
          message: 'No code repositories registered yet.',
          hint: 'Register one to enable semantic code search across workflows.',
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.all(sp16),
      child: Column(
        children: [
          for (final repo in _repositories)
            Padding(
              padding: const EdgeInsets.only(bottom: sp16),
              child: _RepositoryCard(
                repo: repo,
                onEdit: () => _createOrEdit(existing: repo),
                onSync: () => _sync(repo),
                onIndex: () => _index(repo),
                onSearch: () => _search(repo),
                onDelete: () => _delete(repo),
              ),
            ),
        ],
      ),
    );
  }
}

// ── Filter bar ──────────────────────────────────────────────────────────────
class _FilterBar extends StatelessWidget {
  const _FilterBar({
    required this.controller,
    required this.onSubmit,
    required this.onReload,
  });

  final TextEditingController controller;
  final VoidCallback onSubmit;
  final VoidCallback onReload;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: controller,
            onSubmitted: (_) => onSubmit(),
            style: const TextStyle(fontFamily: fontBody, fontSize: 14),
            decoration: const InputDecoration(
              labelText: 'Filter by tags (comma-separated)',
              border: OutlineInputBorder(borderRadius: borderRadiusNone),
              isDense: true,
              contentPadding: EdgeInsets.symmetric(
                horizontal: sp12,
                vertical: sp12,
              ),
            ),
          ),
        ),
        const SizedBox(width: sp8),
        RetroButton(
          label: 'APPLY',
          icon: Icons.filter_alt_outlined,
          onPressed: onSubmit,
          color: accentTeal,
        ),
        const SizedBox(width: sp8),
        RetroButton(
          label: 'RELOAD',
          icon: Icons.refresh,
          onPressed: onReload,
          color: accentAmber,
          textColor: textPrimary,
        ),
      ],
    );
  }
}

// ── Repository card ─────────────────────────────────────────────────────────
class _RepositoryCard extends StatelessWidget {
  const _RepositoryCard({
    required this.repo,
    required this.onEdit,
    required this.onSync,
    required this.onIndex,
    required this.onSearch,
    required this.onDelete,
  });

  final Map<String, dynamic> repo;
  final VoidCallback onEdit;
  final VoidCallback onSync;
  final VoidCallback onIndex;
  final VoidCallback onSearch;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final tags = (repo['tags'] as List?)?.whereType<String>().toList() ?? [];
    final status = (repo['status'] ?? 'registered').toString();
    final lastError = repo['last_error']?.toString();
    final fileCount = repo['file_count'] ?? 0;
    final chunkCount = repo['chunk_count'] ?? 0;
    final lastSynced = repo['last_synced_at']?.toString();

    return RetroCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      (repo['name'] ?? '—').toString(),
                      style: const TextStyle(
                        fontFamily: fontDisplay,
                        fontSize: 12,
                        color: textPrimary,
                      ),
                    ),
                    if ((repo['description'] ?? '').toString().isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        repo['description'].toString(),
                        style: const TextStyle(
                          fontFamily: fontBody,
                          fontSize: 13,
                          color: textMuted,
                        ),
                      ),
                    ],
                    const SizedBox(height: sp8),
                    SelectableText(
                      '${repo['repo_url']}  ·  ${repo['default_branch'] ?? 'main'}',
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: 12,
                        color: textMuted,
                      ),
                    ),
                  ],
                ),
              ),
              RetroChip(label: status, color: _statusColor(status)),
            ],
          ),
          const SizedBox(height: sp12),
          Wrap(
            spacing: sp8,
            runSpacing: 4,
            children: [
              for (final t in tags)
                RetroChip(
                  label: t,
                  color: accentLavender,
                  textColor: cardBg,
                ),
              if (tags.isEmpty)
                const Text(
                  'no tags',
                  style: TextStyle(
                    fontFamily: fontBody,
                    fontSize: 12,
                    color: textMuted,
                  ),
                ),
            ],
          ),
          const SizedBox(height: sp12),
          Wrap(
            spacing: sp16,
            runSpacing: 4,
            children: [
              _InfoBit(label: 'FILES', value: '$fileCount'),
              _InfoBit(label: 'CHUNKS', value: '$chunkCount'),
              _InfoBit(label: 'LAST SYNC', value: _relative(lastSynced)),
              if (repo['last_commit_sha'] != null)
                _InfoBit(
                  label: 'COMMIT',
                  value: repo['last_commit_sha'].toString().substring(
                    0,
                    repo['last_commit_sha'].toString().length < 7
                        ? repo['last_commit_sha'].toString().length
                        : 7,
                  ),
                ),
            ],
          ),
          if (lastError != null && lastError.isNotEmpty) ...[
            const SizedBox(height: sp8),
            Container(
              padding: const EdgeInsets.all(sp8),
              decoration: BoxDecoration(
                color: accentPrimary.withAlpha(28),
                border: Border.all(color: accentPrimary, width: 1),
              ),
              child: Text(
                '⚠ $lastError',
                style: const TextStyle(
                  fontFamily: fontBody,
                  fontSize: 12,
                  color: accentPrimary,
                ),
              ),
            ),
          ],
          const SizedBox(height: sp12),
          Wrap(
            spacing: sp8,
            runSpacing: sp8,
            children: [
              RetroButton(
                label: 'EDIT',
                onPressed: onEdit,
                color: accentTeal,
                icon: Icons.edit_outlined,
              ),
              RetroButton(
                label: 'SYNC',
                onPressed: onSync,
                color: accentAmber,
                textColor: textPrimary,
                icon: Icons.sync,
              ),
              RetroButton(
                label: 'INDEX',
                onPressed: onIndex,
                color: accentLavender,
                icon: Icons.auto_awesome_outlined,
              ),
              RetroButton(
                label: 'SEARCH',
                onPressed: onSearch,
                color: accentSlate,
                icon: Icons.search,
              ),
              RetroButton(
                label: 'DELETE',
                onPressed: onDelete,
                color: accentPrimary,
                icon: Icons.delete_outline,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'indexed':
      case 'connected':
        return accentTeal;
      case 'synced':
        return accentSlate;
      case 'syncing':
      case 'indexing':
        return accentAmber;
      case 'error':
        return accentPrimary;
      default:
        return accentLavender;
    }
  }

  String _relative(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    final dt = DateTime.tryParse(iso);
    if (dt == null) return iso;
    final diff = DateTime.now().toUtc().difference(dt.toUtc());
    if (diff.inSeconds < 60) return '${diff.inSeconds}s ago';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}

class _InfoBit extends StatelessWidget {
  const _InfoBit({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontFamily: fontDisplay,
            fontSize: 7,
            color: textMuted,
            letterSpacing: 0.8,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 14,
            color: textPrimary,
          ),
        ),
      ],
    );
  }
}

// ── Editor dialog ───────────────────────────────────────────────────────────
class _RepositoryEditorDialog extends StatefulWidget {
  const _RepositoryEditorDialog({
    required this.initial,
    required this.tokens,
  });

  final Map<String, dynamic>? initial;
  final List<Map<String, dynamic>> tokens;

  @override
  State<_RepositoryEditorDialog> createState() =>
      _RepositoryEditorDialogState();
}

class _RepositoryEditorDialogState extends State<_RepositoryEditorDialog> {
  late final TextEditingController _name;
  late final TextEditingController _desc;
  late final TextEditingController _url;
  late final TextEditingController _branch;
  late final TextEditingController _tags;
  late final TextEditingController _chunk;
  late final TextEditingController _overlap;
  late final TextEditingController _maxKb;
  late final TextEditingController _include;
  late final TextEditingController _exclude;
  String? _tokenName;
  bool _indexingEnabled = true;

  @override
  void initState() {
    super.initState();
    final r = widget.initial;
    final idx = (r?['indexing'] as Map<String, dynamic>?) ?? const {};
    _name = TextEditingController(text: r?['name']?.toString() ?? '');
    _desc = TextEditingController(text: r?['description']?.toString() ?? '');
    _url = TextEditingController(text: r?['repo_url']?.toString() ?? '');
    _branch = TextEditingController(
      text: r?['default_branch']?.toString() ?? 'main',
    );
    _tags = TextEditingController(
      text:
          ((r?['tags'] as List?)?.whereType<String>().toList() ?? []).join(', '),
    );
    _chunk = TextEditingController(
      text: (idx['chunk_chars'] ?? 1200).toString(),
    );
    _overlap = TextEditingController(
      text: (idx['overlap_chars'] ?? 150).toString(),
    );
    _maxKb = TextEditingController(
      text: (idx['max_file_kb'] ?? 256).toString(),
    );
    _include = TextEditingController(
      text:
          ((idx['include_globs'] as List?)?.whereType<String>().toList() ?? [])
              .join('\n'),
    );
    _exclude = TextEditingController(
      text:
          ((idx['exclude_globs'] as List?)?.whereType<String>().toList() ?? [])
              .join('\n'),
    );
    _tokenName = r?['token_name']?.toString();
    _indexingEnabled = idx['enabled'] != false;
  }

  @override
  void dispose() {
    for (final c in [
      _name,
      _desc,
      _url,
      _branch,
      _tags,
      _chunk,
      _overlap,
      _maxKb,
      _include,
      _exclude,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  List<String> _splitGlobs(String value) =>
      value.split(RegExp(r'[\n,]')).map((s) => s.trim()).where((s) => s.isNotEmpty).toList();

  void _submit() {
    if (_name.text.trim().isEmpty || _url.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Name and Repo URL are required')),
      );
      return;
    }
    final body = <String, dynamic>{
      'name': _name.text.trim(),
      'description': _desc.text,
      'repo_url': _url.text.trim(),
      'default_branch': _branch.text.trim().isEmpty ? 'main' : _branch.text.trim(),
      'token_name': (_tokenName?.isEmpty ?? true) ? null : _tokenName,
      'tags': _tags.text
          .split(',')
          .map((t) => t.trim())
          .where((t) => t.isNotEmpty)
          .toList(),
      'indexing': {
        'enabled': _indexingEnabled,
        'chunk_chars': int.tryParse(_chunk.text) ?? 1200,
        'overlap_chars': int.tryParse(_overlap.text) ?? 150,
        'max_file_kb': int.tryParse(_maxKb.text) ?? 256,
        'include_globs': _splitGlobs(_include.text),
        'exclude_globs': _splitGlobs(_exclude.text),
      },
    };
    Navigator.of(context).pop(body);
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.initial != null;
    return AlertDialog(
      backgroundColor: cardBg,
      shape: const RoundedRectangleBorder(borderRadius: borderRadiusNone),
      title: Text(
        isEdit ? 'EDIT REPOSITORY' : 'NEW REPOSITORY',
        style: const TextStyle(
          fontFamily: fontDisplay,
          fontSize: 12,
          color: textPrimary,
          letterSpacing: 1,
        ),
      ),
      content: SizedBox(
        width: 560,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              _field('Name', _name, hint: 'e.g. tbd-agents'),
              _field('Description', _desc, hint: 'Optional'),
              _field('Repo URL', _url, hint: 'https://github.com/owner/repo'),
              _field('Default Branch', _branch, hint: 'main'),
              const SizedBox(height: sp8),
              _label('Auth Token (Token Store key)'),
              DropdownButtonFormField<String?>(
                initialValue: _tokenName?.isEmpty == true ? null : _tokenName,
                isExpanded: true,
                decoration: const InputDecoration(
                  border: OutlineInputBorder(borderRadius: borderRadiusNone),
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(
                    horizontal: sp12,
                    vertical: sp12,
                  ),
                ),
                items: <DropdownMenuItem<String?>>[
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('— none (public repo) —'),
                  ),
                  ...widget.tokens.map(
                    (t) => DropdownMenuItem<String?>(
                      value: t['name']?.toString(),
                      child: Text(t['name']?.toString() ?? ''),
                    ),
                  ),
                ],
                onChanged: (v) => setState(() => _tokenName = v),
              ),
              const SizedBox(height: sp12),
              _field('Tags (comma-separated)', _tags, hint: 'backend, infra'),
              const Divider(height: sp24),
              _label('Indexing'),
              CheckboxListTile(
                value: _indexingEnabled,
                onChanged: (v) =>
                    setState(() => _indexingEnabled = v ?? true),
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text(
                  'Enable semantic indexing (required for code_search tool)',
                  style: TextStyle(fontFamily: fontBody, fontSize: 13),
                ),
              ),
              Row(
                children: [
                  Expanded(
                    child: _field(
                      'Chunk chars',
                      _chunk,
                      keyboard: TextInputType.number,
                    ),
                  ),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: _field(
                      'Overlap chars',
                      _overlap,
                      keyboard: TextInputType.number,
                    ),
                  ),
                  const SizedBox(width: sp8),
                  Expanded(
                    child: _field(
                      'Max file KB',
                      _maxKb,
                      keyboard: TextInputType.number,
                    ),
                  ),
                ],
              ),
              _field(
                'Include globs (comma- or newline-separated)',
                _include,
                hint: '**/*.py, **/*.md',
                maxLines: 3,
              ),
              _field(
                'Exclude globs (comma- or newline-separated)',
                _exclude,
                hint: '**/node_modules/**, **/.git/**',
                maxLines: 3,
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: _submit,
          child: Text(isEdit ? 'Update' : 'Create'),
        ),
      ],
    );
  }

  Widget _label(String text) => Padding(
    padding: const EdgeInsets.only(bottom: 4, top: sp8),
    child: Text(
      text,
      style: const TextStyle(
        fontFamily: fontBody,
        fontSize: 12,
        color: textMuted,
        letterSpacing: 0.5,
      ),
    ),
  );

  Widget _field(
    String label,
    TextEditingController controller, {
    String? hint,
    int maxLines = 1,
    TextInputType? keyboard,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _label(label),
          TextField(
            controller: controller,
            keyboardType: keyboard,
            maxLines: maxLines,
            inputFormatters: keyboard == TextInputType.number
                ? [FilteringTextInputFormatter.digitsOnly]
                : null,
            decoration: InputDecoration(
              hintText: hint,
              border: const OutlineInputBorder(
                borderRadius: borderRadiusNone,
              ),
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(
                horizontal: sp12,
                vertical: sp12,
              ),
            ),
            style: const TextStyle(fontFamily: fontBody, fontSize: 13),
          ),
        ],
      ),
    );
  }
}

// ── Search dialog ───────────────────────────────────────────────────────────
typedef _SearchRunner =
    Future<List<Map<String, dynamic>>> Function(String query, int limit);

class _RepositorySearchDialog extends StatefulWidget {
  const _RepositorySearchDialog({required this.repo, required this.runSearch});

  final Map<String, dynamic> repo;
  final _SearchRunner runSearch;

  @override
  State<_RepositorySearchDialog> createState() =>
      _RepositorySearchDialogState();
}

class _RepositorySearchDialogState extends State<_RepositorySearchDialog> {
  final _query = TextEditingController();
  final _limit = TextEditingController(text: '10');
  bool _loading = false;
  Object? _error;
  List<Map<String, dynamic>> _results = const [];

  @override
  void dispose() {
    _query.dispose();
    _limit.dispose();
    super.dispose();
  }

  Future<void> _go() async {
    final q = _query.text.trim();
    if (q.isEmpty) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final hits = await widget.runSearch(q, int.tryParse(_limit.text) ?? 10);
      if (!mounted) return;
      setState(() {
        _results = hits;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: cardBg,
      shape: const RoundedRectangleBorder(borderRadius: borderRadiusNone),
      title: Text(
        'SEARCH ${(widget.repo['name'] ?? '').toString().toUpperCase()}',
        style: const TextStyle(
          fontFamily: fontDisplay,
          fontSize: 12,
          color: textPrimary,
          letterSpacing: 1,
        ),
      ),
      content: SizedBox(
        width: 640,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _query,
                    autofocus: true,
                    onSubmitted: (_) => _go(),
                    decoration: const InputDecoration(
                      labelText: 'Query',
                      border: OutlineInputBorder(
                        borderRadius: borderRadiusNone,
                      ),
                      isDense: true,
                      contentPadding: EdgeInsets.symmetric(
                        horizontal: sp12,
                        vertical: sp12,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: sp8),
                SizedBox(
                  width: 80,
                  child: TextField(
                    controller: _limit,
                    keyboardType: TextInputType.number,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                    ],
                    decoration: const InputDecoration(
                      labelText: 'Limit',
                      border: OutlineInputBorder(
                        borderRadius: borderRadiusNone,
                      ),
                      isDense: true,
                      contentPadding: EdgeInsets.symmetric(
                        horizontal: sp8,
                        vertical: sp12,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: sp8),
                RetroButton(
                  label: 'GO',
                  onPressed: _go,
                  icon: Icons.search,
                  color: accentSlate,
                ),
              ],
            ),
            const SizedBox(height: sp16),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 420, minHeight: 80),
              child: _buildResults(),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _buildResults() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Padding(
        padding: const EdgeInsets.all(sp8),
        child: Text(
          'Search failed: $_error',
          style: const TextStyle(
            fontFamily: fontBody,
            fontSize: 13,
            color: accentPrimary,
          ),
        ),
      );
    }
    if (_results.isEmpty) {
      return const Center(
        child: Text(
          'No results yet. Enter a query and press GO.',
          style: TextStyle(
            fontFamily: fontBody,
            fontSize: 13,
            color: textMuted,
          ),
        ),
      );
    }
    return ListView.separated(
      itemCount: _results.length,
      separatorBuilder: (_, _) => const SizedBox(height: sp8),
      itemBuilder: (_, i) {
        final h = _results[i];
        final score = (h['score'] as num?)?.toStringAsFixed(3) ?? '—';
        return Container(
          padding: const EdgeInsets.all(sp8),
          decoration: BoxDecoration(
            color: const Color(0xFFF7F1DD),
            border: Border.all(color: borderColor, width: 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${h['file_path']}:${h['line_start']}-${h['line_end']}',
                      style: const TextStyle(
                        fontFamily: fontBody,
                        fontSize: 12,
                        color: accentPrimary,
                      ),
                    ),
                  ),
                  Text(
                    'score $score',
                    style: const TextStyle(
                      fontFamily: fontBody,
                      fontSize: 11,
                      color: textMuted,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: sp4),
              SelectableText(
                (h['text'] ?? '').toString(),
                style: const TextStyle(
                  fontFamily: fontFallback,
                  fontSize: 12,
                  color: textPrimary,
                  height: 1.4,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ── Shared local helpers (mirrors private widgets in other screens) ──
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
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
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
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
        ),
        ...actions.map(
          (a) => Padding(
            padding: const EdgeInsets.only(left: sp8),
            child: a,
          ),
        ),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.icon, required this.message, this.hint});

  final IconData icon;
  final String message;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 40, color: textMuted.withAlpha(100)),
          const SizedBox(height: sp12),
          Text(
            message,
            style: const TextStyle(
              fontFamily: fontBody,
              fontSize: 16,
              color: textMuted,
              letterSpacing: 0.5,
            ),
            textAlign: TextAlign.center,
          ),
          if (hint != null) ...[
            const SizedBox(height: sp4),
            Text(
              hint!,
              style: const TextStyle(
                fontFamily: fontBody,
                fontSize: 14,
                color: textMuted,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ],
      ),
    );
  }
}
