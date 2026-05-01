"""Language-aware code chunking.

Phase-3 ``treesitter-chunker`` deliverable. Splits a source file into chunks
suitable for embedding while preserving as much semantic structure as
possible. Strategy in order of preference:

1. **tree-sitter** (preferred). Walk the AST, emit one chunk per top-level
   declaration (function / class / etc., per language). Oversized
   declarations are split on blank-line boundaries; tiny declarations
   (imports, single-line constants) are coalesced into one chunk up to
   ``MAX_CHARS``.
2. **pygments** lexer fallback when no tree-sitter grammar is available.
   Token-aware splitter that breaks on logical boundaries (newline + matching
   dedent) until ``MAX_CHARS`` is reached.
3. **Char-window fallback** when pygments cannot lex the file or fails.
   Identical to the legacy ``_chunk_text`` splitter so behaviour degrades
   gracefully.

Public surface:

* :class:`CodeChunk` — dataclass returned to callers.
* :func:`chunk_code` — sole entry point.

Design constraints (called out by the indexing-redesign doc, section 9):

* Chunk indices must remain a stable monotonically-increasing 0..N-1 per
  file so :func:`code_repository_manager._point_id` stays deterministic.
* Files larger than :data:`MAX_FILE_BYTES_FOR_TREESITTER` (default 2 MiB)
  short-circuit straight to the char-window fallback to avoid pathological
  parses.
* The chunker is intentionally pure / synchronous; the manager streams files
  one at a time so peak memory stays bounded.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type-only
    pass

logger = logging.getLogger(__name__)


# ── Public types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CodeChunk:
    """One unit of code text scheduled for embedding.

    Attributes:
        text: The chunk source as UTF-8 text.
        language: A short language tag (e.g. ``"python"``, ``"typescript"``,
            ``"unknown"``). Derived from the file extension; never raises.
        symbol: Best-effort name of the enclosing function / class, or
            ``None`` for coalesced/oversized fragments.
        start_line: 1-indexed first source line covered by ``text``.
        end_line: 1-indexed last source line (inclusive).
    """

    text: str
    language: str
    symbol: str | None
    start_line: int
    end_line: int


# ── Tunables ─────────────────────────────────────────────────────────────────


# Approximation: 1 token ≈ 4 chars. Plenty good enough for chunking
# decisions; we do NOT need true tokenizer fidelity here.
_DEFAULT_MAX_TOKENS = 512
_CHARS_PER_TOKEN = 4

# Hard ceiling above which we never invoke tree-sitter (peak mem ≈ 3× file).
MAX_FILE_BYTES_FOR_TREESITTER = 2 * 1024 * 1024  # 2 MiB

# Below this threshold, adjacent declarations (typically imports, one-line
# consts) are merged greedily into a single chunk.
TINY_CHUNK_THRESHOLD = 200


def _resolved_max_chars(override: int | None) -> int:
    """Resolve the per-chunk character budget.

    ``override`` (when truthy & positive) wins, otherwise the env var
    ``INDEX_CHUNK_MAX_TOKENS`` is read on every call so monkeypatching in
    tests works without module reloads.
    """
    if override and override > 0:
        return override
    try:
        max_tokens = int(os.getenv("INDEX_CHUNK_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS)))
    except ValueError:
        max_tokens = _DEFAULT_MAX_TOKENS
    if max_tokens <= 0:
        max_tokens = _DEFAULT_MAX_TOKENS
    return max_tokens * _CHARS_PER_TOKEN


# ── Language detection ───────────────────────────────────────────────────────


_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".java": "java",
    ".go": "go",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
}


def _language_from_path(file_path: str) -> str:
    """Return the language tag for ``file_path``'s extension, or 'unknown'."""
    if not file_path:
        return "unknown"
    # Use the last dot-segment; ``os.path.splitext`` chops only the trailing
    # extension which is exactly what we want.
    _, ext = os.path.splitext(file_path)
    return _LANG_BY_EXT.get(ext.lower(), "unknown")


# Top-level AST node types per language that mark "good chunk boundaries".
# These are intentionally conservative — we'd rather emit one chunk per
# function than try to be clever about nested closures.
_TOPLEVEL_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "function_definition",
        "class_definition",
        "decorated_definition",
    },
    "typescript": {
        "function_declaration",
        "class_declaration",
        "method_definition",
        "interface_declaration",
        "enum_declaration",
        "export_statement",
        "abstract_class_declaration",
    },
    "tsx": {
        "function_declaration",
        "class_declaration",
        "method_definition",
        "interface_declaration",
        "enum_declaration",
        "export_statement",
        "abstract_class_declaration",
    },
    "javascript": {
        "function_declaration",
        "class_declaration",
        "method_definition",
        "export_statement",
    },
    "java": {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "method_declaration",
        "record_declaration",
    },
    "kotlin": {
        "class_declaration",
        "object_declaration",
        "function_declaration",
        "property_declaration",
    },
    "csharp": {
        "class_declaration",
        "interface_declaration",
        "struct_declaration",
        "enum_declaration",
        "method_declaration",
        "record_declaration",
        "namespace_declaration",
    },
    "go": {
        "function_declaration",
        "method_declaration",
        "type_declaration",
    },
    "rust": {
        "function_item",
        "impl_item",
        "struct_item",
        "enum_item",
        "trait_item",
        "mod_item",
    },
    "c": {
        "function_definition",
        "struct_specifier",
        "enum_specifier",
    },
    "cpp": {
        "function_definition",
        "class_specifier",
        "struct_specifier",
        "namespace_definition",
    },
    "ruby": {
        "method",
        "class",
        "module",
        "singleton_method",
    },
    "php": {
        "function_definition",
        "class_declaration",
        "interface_declaration",
        "trait_declaration",
        "method_declaration",
    },
    "swift": {
        "function_declaration",
        "class_declaration",
        "protocol_declaration",
        "enum_declaration",
        "struct_declaration",
    },
    "scala": {
        "function_definition",
        "class_definition",
        "object_definition",
        "trait_definition",
    },
}


# ── tree-sitter parser cache (lazy & thread-safe) ────────────────────────────


_PARSERS: dict[str, Any] = {}
_PARSER_FAILED: set[str] = set()
_PARSER_LOCK = threading.Lock()


def _get_parser(language: str) -> Any | None:
    """Return a cached :class:`tree_sitter.Parser` for ``language`` or None.

    None is returned (and remembered) if the grammar isn't available — this
    avoids paying the import + load cost on every subsequent file.
    """
    if language in _PARSER_FAILED:
        return None
    cached = _PARSERS.get(language)
    if cached is not None:
        return cached
    with _PARSER_LOCK:
        cached = _PARSERS.get(language)
        if cached is not None:
            return cached
        if language in _PARSER_FAILED:
            return None
        try:
            from tree_sitter_language_pack import get_parser
        except Exception as exc:  # pragma: no cover - install issue
            logger.debug("tree_sitter_language_pack unavailable: %s", exc)
            _PARSER_FAILED.add(language)
            return None
        try:
            parser = get_parser(language)
        except Exception as exc:
            logger.debug("no tree-sitter grammar for %s: %s", language, exc)
            _PARSER_FAILED.add(language)
            return None
        _PARSERS[language] = parser
        return parser


# ── Char-window fallback (kept tiny; mirrors legacy `_chunk_text`) ───────────


def _char_window_chunks(
    text: str,
    language: str,
    max_chars: int,
    overlap_chars: int = 0,
) -> list[CodeChunk]:
    """Slide a fixed-size character window over ``text``.

    Drops empty/whitespace-only pieces. Line numbers are computed accurately
    so callers (search UI) can still highlight ranges even on the fallback
    path. ``overlap_chars`` mirrors the legacy semantics — caller passes
    ``0`` from the AST path because chunks are already disjoint declarations.
    """
    if max_chars <= 0:
        if not text.strip():
            return []
        return [
            CodeChunk(
                text=text,
                language=language,
                symbol=None,
                start_line=1,
                end_line=text.count("\n") + 1,
            )
        ]
    if not text:
        return []
    if len(text) <= max_chars:
        if not text.strip():
            return []
        return [
            CodeChunk(
                text=text,
                language=language,
                symbol=None,
                start_line=1,
                end_line=text.count("\n") + 1,
            )
        ]

    out: list[CodeChunk] = []
    step = max(1, max_chars - max(0, overlap_chars))
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        piece = text[start:end]
        if piece.strip():
            line_start = text.count("\n", 0, start) + 1
            line_end = line_start + piece.count("\n")
            out.append(
                CodeChunk(
                    text=piece,
                    language=language,
                    symbol=None,
                    start_line=line_start,
                    end_line=line_end,
                )
            )
        if end == n:
            break
        start += step
    return out


# ── Tree-sitter helpers ──────────────────────────────────────────────────────


def _node_text(source: bytes, node: Any) -> str:
    """Decode a tree-sitter node's slice of the source as UTF-8 text."""
    try:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - defensive
        return ""


def _extract_symbol(node: Any) -> str | None:
    """Best-effort symbol name: first ``identifier``-ish child of ``node``.

    Walks one level deep and looks for identifier-like fields by name. Works
    consistently across grammars without us having to encode language-specific
    field names exhaustively.
    """
    try:
        # ``child_by_field_name`` returns None when the field doesn't exist.
        for field in ("name", "declarator"):
            named = (
                node.child_by_field_name(field)
                if hasattr(node, "child_by_field_name")
                else None
            )
            if named is not None:
                # ``declarator`` can wrap a function name; keep digging.
                if named.type in {"identifier", "type_identifier", "property_identifier",
                                  "field_identifier", "constant"}:
                    return named.text.decode("utf-8", errors="replace")
                inner = _extract_symbol(named)
                if inner:
                    return inner
        for child in getattr(node, "children", []) or []:
            if child.type in {"identifier", "type_identifier", "property_identifier",
                              "field_identifier", "constant"}:
                return child.text.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - grammar quirk
        return None
    return None


def _split_oversized(
    text: str,
    language: str,
    base_line: int,
    max_chars: int,
) -> list[CodeChunk]:
    """Split ``text`` into chunks ≤ ``max_chars`` without breaking mid-line.

    Strategy:
    1. Greedy fill on blank-line groups (preserves logical paragraphs).
    2. If a single paragraph still exceeds ``max_chars``, split it on
       newline boundaries.
    3. If a single line still exceeds ``max_chars`` (e.g. minified JS),
       hard-cut on character boundaries — last resort.
    """
    if not text:
        return []
    if len(text) <= max_chars:
        if not text.strip():
            return []
        return [
            CodeChunk(
                text=text,
                language=language,
                symbol=None,
                start_line=base_line,
                end_line=base_line + text.count("\n"),
            )
        ]

    lines = text.splitlines(keepends=True)
    # Collapse into blank-line separated groups.
    groups: list[tuple[int, list[str]]] = []
    current: list[str] = []
    current_start = 0  # line offset within ``text``
    for i, line in enumerate(lines):
        if line.strip() == "":
            if current:
                groups.append((current_start, current))
                current = []
            # Defer assigning a new ``current_start`` until we collect the
            # next non-blank line.
            current_start = i + 1
        else:
            if not current:
                current_start = i
            current.append(line)
    if current:
        groups.append((current_start, current))

    if not groups:
        # All blank — nothing meaningful.
        return []

    out: list[CodeChunk] = []

    def _flush(buf: list[tuple[int, list[str]]]) -> None:
        if not buf:
            return
        first_line_off = buf[0][0]
        joined = "".join("".join(g[1]) for g in buf)
        if not joined.strip():
            return
        out.append(
            CodeChunk(
                text=joined,
                language=language,
                symbol=None,
                start_line=base_line + first_line_off,
                end_line=base_line + first_line_off + joined.count("\n"),
            )
        )

    pending: list[tuple[int, list[str]]] = []
    pending_chars = 0
    for off, group_lines in groups:
        group_text = "".join(group_lines)
        glen = len(group_text)
        if glen > max_chars:
            # Flush whatever's queued first.
            _flush(pending)
            pending = []
            pending_chars = 0
            # Split this monster group on line boundaries.
            line_buf: list[str] = []
            line_buf_chars = 0
            line_buf_start_off = off
            for li, ln in enumerate(group_lines):
                ln_len = len(ln)
                if ln_len > max_chars:
                    # Flush queued lines, then hard-cut this single line.
                    if line_buf:
                        joined = "".join(line_buf)
                        if joined.strip():
                            out.append(
                                CodeChunk(
                                    text=joined,
                                    language=language,
                                    symbol=None,
                                    start_line=base_line + line_buf_start_off,
                                    end_line=(
                                        base_line + line_buf_start_off
                                        + joined.count("\n")
                                    ),
                                )
                            )
                        line_buf = []
                        line_buf_chars = 0
                        line_buf_start_off = off + li + 1
                    # Hard-cut.
                    for piece_start in range(0, ln_len, max_chars):
                        piece = ln[piece_start:piece_start + max_chars]
                        if piece.strip():
                            out.append(
                                CodeChunk(
                                    text=piece,
                                    language=language,
                                    symbol=None,
                                    start_line=base_line + off + li,
                                    end_line=base_line + off + li,
                                )
                            )
                    line_buf_start_off = off + li + 1
                    continue
                if line_buf_chars + ln_len > max_chars and line_buf:
                    joined = "".join(line_buf)
                    if joined.strip():
                        out.append(
                            CodeChunk(
                                text=joined,
                                language=language,
                                symbol=None,
                                start_line=base_line + line_buf_start_off,
                                end_line=(
                                    base_line + line_buf_start_off
                                    + joined.count("\n")
                                ),
                            )
                        )
                    line_buf = []
                    line_buf_chars = 0
                    line_buf_start_off = off + li
                if not line_buf:
                    line_buf_start_off = off + li
                line_buf.append(ln)
                line_buf_chars += ln_len
            if line_buf:
                joined = "".join(line_buf)
                if joined.strip():
                    out.append(
                        CodeChunk(
                            text=joined,
                            language=language,
                            symbol=None,
                            start_line=base_line + line_buf_start_off,
                            end_line=(
                                base_line + line_buf_start_off
                                + joined.count("\n")
                            ),
                        )
                    )
            continue
        if pending_chars + glen > max_chars and pending:
            _flush(pending)
            pending = []
            pending_chars = 0
        pending.append((off, group_lines))
        pending_chars += glen
    _flush(pending)

    return out


def _coalesce_tiny(chunks: list[CodeChunk], max_chars: int) -> list[CodeChunk]:
    """Merge adjacent <:data:`TINY_CHUNK_THRESHOLD`-char chunks.

    Two chunks are merged only when:

    * both are below the tiny threshold, AND
    * the merged result still fits within ``max_chars``, AND
    * the second chunk starts on a line ≤ 2 lines after the first ends
      (so we don't span giant gaps in the file).

    Symbol of merged chunks is dropped (it would no longer be accurate).
    """
    if not chunks:
        return chunks
    out: list[CodeChunk] = []
    for ch in chunks:
        if (
            out
            and len(out[-1].text) < TINY_CHUNK_THRESHOLD
            and len(ch.text) < TINY_CHUNK_THRESHOLD
            and len(out[-1].text) + len(ch.text) + 1 <= max_chars
            and ch.start_line - out[-1].end_line <= 2
        ):
            prev = out[-1]
            sep = "" if prev.text.endswith("\n") else "\n"
            merged = CodeChunk(
                text=prev.text + sep + ch.text,
                language=prev.language,
                symbol=None,
                start_line=prev.start_line,
                end_line=ch.end_line,
            )
            out[-1] = merged
        else:
            out.append(ch)
    return out


def _chunks_from_treesitter(
    text: str,
    language: str,
    parser: Any,
    max_chars: int,
) -> list[CodeChunk] | None:
    """Run tree-sitter and emit one chunk per top-level declaration.

    Returns ``None`` on parse failure — caller falls back to pygments / char
    window. Returns ``[]`` only when ``text`` is genuinely empty/whitespace.
    """
    try:
        source = text.encode("utf-8", errors="replace")
        tree = parser.parse(source)
    except Exception as exc:
        logger.debug("tree-sitter parse failed for %s: %s", language, exc)
        return None

    boundary = _TOPLEVEL_NODE_TYPES.get(language, set())
    root = tree.root_node
    children = list(getattr(root, "children", []) or [])
    if not children:
        return _split_oversized(text, language, base_line=1, max_chars=max_chars)

    out: list[CodeChunk] = []
    # Buffer of contiguous "non-boundary" leading nodes (imports, consts).
    pending_text_parts: list[str] = []
    pending_start_line: int | None = None
    pending_end_line: int = 0

    def _flush_pending() -> None:
        nonlocal pending_text_parts, pending_start_line, pending_end_line
        if not pending_text_parts:
            return
        joined = "".join(pending_text_parts).strip("\n")
        if joined.strip() and pending_start_line is not None:
            for piece in _split_oversized(
                joined, language, base_line=pending_start_line, max_chars=max_chars
            ):
                out.append(piece)
        pending_text_parts = []
        pending_start_line = None
        pending_end_line = 0

    for node in children:
        node_text = _node_text(source, node)
        node_start_line = node.start_point[0] + 1  # 1-indexed
        node_end_line = node.end_point[0] + 1

        if node.type in boundary:
            _flush_pending()
            symbol = _extract_symbol(node)
            if len(node_text) <= max_chars:
                if node_text.strip():
                    out.append(
                        CodeChunk(
                            text=node_text,
                            language=language,
                            symbol=symbol,
                            start_line=node_start_line,
                            end_line=node_end_line,
                        )
                    )
            else:
                # Oversized declaration — split, propagate symbol to first.
                pieces = _split_oversized(
                    node_text, language, base_line=node_start_line, max_chars=max_chars
                )
                if pieces:
                    pieces[0] = CodeChunk(
                        text=pieces[0].text,
                        language=language,
                        symbol=symbol,
                        start_line=pieces[0].start_line,
                        end_line=pieces[0].end_line,
                    )
                out.extend(pieces)
        else:
            # Tiny / non-boundary statement — coalesce.
            if pending_start_line is None:
                pending_start_line = node_start_line
            pending_text_parts.append(node_text)
            pending_text_parts.append("\n")
            pending_end_line = node_end_line

    _flush_pending()

    if not out:
        # Grammar found nothing recognisable — defer to the splitter so we
        # still emit chunks rather than swallowing the file silently.
        return _split_oversized(text, language, base_line=1, max_chars=max_chars)

    # Non-boundary nodes were already coalesced in the pending buffer.
    # Boundary chunks (functions / classes) stay distinct so per-symbol
    # retrieval works.
    return out


# ── Pygments fallback ────────────────────────────────────────────────────────


def _chunks_from_pygments(
    text: str,
    language: str,
    file_path: str,
    max_chars: int,
) -> list[CodeChunk] | None:
    """Token-aware fallback when no tree-sitter grammar is available.

    Splits ``text`` on logical boundaries (statement-terminating newlines
    where the next line is non-indented). Returns ``None`` on lexer failure
    so the caller can drop down to the char-window splitter.
    """
    try:
        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound
    except Exception as exc:  # pragma: no cover - install issue
        logger.debug("pygments unavailable: %s", exc)
        return None

    try:
        lexer = get_lexer_for_filename(file_path, text)
    except ClassNotFound:
        return None
    except Exception as exc:  # pragma: no cover - lexer selection oddity
        logger.debug("pygments lexer selection failed for %s: %s", file_path, exc)
        return None

    try:
        tokens = list(lexer.get_tokens(text))
    except Exception as exc:  # pragma: no cover - malformed input
        logger.debug("pygments tokenization failed for %s: %s", file_path, exc)
        return None

    if not tokens:
        return []

    # Reconstruct token stream, tracking byte/char offsets so we can compute
    # accurate line numbers per chunk.
    out: list[CodeChunk] = []
    buf_parts: list[str] = []
    buf_chars = 0
    buf_start_line = 1
    cursor_line = 1

    def _emit_buf() -> None:
        nonlocal buf_parts, buf_chars, buf_start_line
        if not buf_parts:
            return
        joined = "".join(buf_parts)
        if joined.strip():
            out.append(
                CodeChunk(
                    text=joined,
                    language=language,
                    symbol=None,
                    start_line=buf_start_line,
                    end_line=buf_start_line + joined.count("\n"),
                )
            )
        buf_parts = []
        buf_chars = 0

    for ttype, tval in tokens:
        if not tval:
            continue
        if not buf_parts:
            buf_start_line = cursor_line
        buf_parts.append(tval)
        buf_chars += len(tval)
        cursor_line += tval.count("\n")
        # Cut on logical boundaries: token is a statement terminator (newline
        # in Whitespace at top of line) OR we've exceeded the budget.
        ends_on_newline = tval.endswith("\n")
        if buf_chars >= max_chars and ends_on_newline:
            _emit_buf()
        elif buf_chars >= max_chars * 2:
            # Hard cap: lexer never gave us a clean newline (minified file).
            _emit_buf()

    _emit_buf()

    if not out:
        # All-whitespace file or a lexer that yielded nothing meaningful.
        return None
    return out


# ── Public API ───────────────────────────────────────────────────────────────


def chunk_code(
    text: str,
    file_path: str,
    *,
    max_chars: int | None = None,
    overlap_chars: int = 0,
) -> list[CodeChunk]:
    """Split ``text`` into language-aware :class:`CodeChunk` units.

    Args:
        text: Source contents (UTF-8). Empty / whitespace-only ⇒ ``[]``.
        file_path: Used only for language detection (extension lookup) and
            for the pygments lexer hint. May be empty.
        max_chars: Optional override of the per-chunk character budget.
            When ``None`` the env var ``INDEX_CHUNK_MAX_TOKENS`` (default
            512 ⇒ ≈ 2048 chars) is honoured. ``0`` is treated as ``None``.
        overlap_chars: Only used by the legacy char-window fallback, where
            the manager wants to mirror its prior overlap semantics. The
            tree-sitter / pygments paths emit disjoint chunks regardless.

    Returns:
        A deterministic list of chunks in source order. The chunk index
        (its position in the returned list) is the value the manager wires
        into :func:`_point_id`, so two calls with identical input MUST
        return the exact same list.
    """
    if text is None or not text or not text.strip():
        return []

    language = _language_from_path(file_path)
    budget = _resolved_max_chars(max_chars)

    # Sanity: pathological file size ⇒ skip tree-sitter entirely.
    too_big = len(text.encode("utf-8", errors="replace")) > MAX_FILE_BYTES_FOR_TREESITTER

    if not too_big and language != "unknown":
        parser = _get_parser(language)
        if parser is not None:
            ts_chunks = _chunks_from_treesitter(
                text, language, parser, max_chars=budget
            )
            if ts_chunks is not None and ts_chunks:
                return ts_chunks
            # Empty list on a non-empty file ⇒ fall through to fallback.

    # Pygments path — useful for unknown extensions and oversized files.
    pyg_chunks = _chunks_from_pygments(
        text, language, file_path, max_chars=budget
    )
    if pyg_chunks:
        return pyg_chunks

    return _char_window_chunks(
        text, language, max_chars=budget, overlap_chars=overlap_chars
    )
