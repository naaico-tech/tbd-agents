"""RepoInspectorPlugin — read-only repository inspection plugin.

Migrated from ``app/tools/repo_inspector.py`` into the plugin system.
All helper functions are kept at module level so ``execute`` stays clean.
"""

from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

MAX_DEPTH_LIMIT = 6
MAX_LINES_LIMIT = 400
MAX_RESULTS_LIMIT = 200
MAX_FILE_BYTES = 256_000
MAX_MATCH_LINE_LENGTH = 240


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


def _get_repo_root() -> str:
    return os.environ.get("TBD_AGENTS_REPO_ROOT", "").strip()


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _resolve_within_root(root_path: Path, requested_path: str) -> Path:
    candidate = (root_path / requested_path).resolve()
    if candidate != root_path and root_path not in candidate.parents:
        raise ValueError(f"Path escapes repository root: {requested_path}")
    return candidate


def _relative_to_root(root_path: Path, path: Path) -> str:
    if path == root_path:
        return "."
    return str(path.relative_to(root_path))


def _should_skip_path(root_path: Path, path: Path, include_hidden: bool) -> bool:
    if include_hidden:
        return False
    rel_parts = path.relative_to(root_path).parts
    return any(part.startswith(".") for part in rel_parts)


def _iter_paths(root_path: Path, target_path: Path, max_depth: int, include_hidden: bool):
    if not target_path.exists():
        return
    stack = [(target_path, 0)]
    while stack:
        current_path, depth = stack.pop()
        yield current_path, depth
        if not current_path.is_dir() or depth >= max_depth:
            continue

        try:
            children = sorted(
                current_path.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            )
        except OSError:
            continue

        for child in reversed(children):
            if child.name in {".", ".."}:
                continue
            if _should_skip_path(root_path, child, include_hidden):
                continue
            stack.append((child, depth + 1))


def _list_tree(
    root_path: Path,
    target_path: Path,
    max_depth: int,
    max_results: int,
    include_hidden: bool,
) -> dict:
    if not target_path.exists():
        return {"error": f"Path does not exist: {_relative_to_root(root_path, target_path)}"}

    entries = []
    truncated = False
    for current_path, depth in _iter_paths(root_path, target_path, max_depth, include_hidden):
        if current_path == target_path:
            continue
        if len(entries) >= max_results:
            truncated = True
            break
        entry = {
            "path": _relative_to_root(root_path, current_path),
            "type": "directory" if current_path.is_dir() else "file",
            "depth": depth,
        }
        if current_path.is_file():
            try:
                entry["size_bytes"] = current_path.stat().st_size
            except OSError:
                pass
        entries.append(entry)

    return {
        "operation": "list_tree",
        "path": _relative_to_root(root_path, target_path),
        "entries": entries,
        "truncated": truncated,
    }


def _read_file(root_path: Path, target_path: Path, start_line: int, max_lines: int) -> dict:
    if not target_path.exists() or not target_path.is_file():
        return {"error": f"File does not exist: {_relative_to_root(root_path, target_path)}"}
    try:
        size_bytes = target_path.stat().st_size
    except OSError as exc:
        return {"error": str(exc)}
    if size_bytes > MAX_FILE_BYTES:
        return {"error": f"File exceeds size limit of {MAX_FILE_BYTES} bytes"}

    raw = target_path.read_bytes()
    if b"\x00" in raw[:4096]:
        return {"error": "Binary files are not supported"}

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    total_lines = len(lines)
    start_index = min(max(start_line - 1, 0), total_lines)
    end_index = min(start_index + max_lines, total_lines)
    snippet = "\n".join(lines[start_index:end_index])

    return {
        "operation": "read_file",
        "path": _relative_to_root(root_path, target_path),
        "start_line": start_index + 1 if total_lines else 1,
        "end_line": end_index,
        "total_lines": total_lines,
        "truncated": end_index < total_lines,
        "content": snippet,
    }


def _find_files(
    root_path: Path,
    target_path: Path,
    glob_pattern: str,
    max_depth: int,
    max_results: int,
    include_hidden: bool,
) -> dict:
    if not target_path.exists():
        return {"error": f"Path does not exist: {_relative_to_root(root_path, target_path)}"}

    matches = []
    truncated = False
    for current_path, _depth in _iter_paths(root_path, target_path, max_depth, include_hidden):
        if current_path.is_dir():
            continue
        rel_path = _relative_to_root(root_path, current_path)
        if not fnmatch(rel_path, glob_pattern) and not fnmatch(current_path.name, glob_pattern):
            continue
        if len(matches) >= max_results:
            truncated = True
            break
        matches.append(rel_path)

    return {
        "operation": "find_files",
        "path": _relative_to_root(root_path, target_path),
        "glob": glob_pattern,
        "matches": matches,
        "truncated": truncated,
    }


def _search_text(
    root_path: Path,
    target_path: Path,
    query: str,
    glob_pattern: str,
    max_depth: int,
    max_results: int,
    include_hidden: bool,
) -> dict:
    if not target_path.exists():
        return {"error": f"Path does not exist: {_relative_to_root(root_path, target_path)}"}

    matches = []
    truncated = False
    query_folded = query.casefold()
    files_scanned = 0

    for current_path, _depth in _iter_paths(root_path, target_path, max_depth, include_hidden):
        if current_path.is_dir():
            continue
        rel_path = _relative_to_root(root_path, current_path)
        if not fnmatch(rel_path, glob_pattern) and not fnmatch(current_path.name, glob_pattern):
            continue
        try:
            size_bytes = current_path.stat().st_size
        except OSError:
            continue
        if size_bytes > MAX_FILE_BYTES:
            continue
        raw = current_path.read_bytes()
        if b"\x00" in raw[:4096]:
            continue

        files_scanned += 1
        lines = raw.decode("utf-8", errors="replace").splitlines()
        for line_number, line_text in enumerate(lines, start=1):
            if query_folded not in line_text.casefold():
                continue
            if len(matches) >= max_results:
                truncated = True
                break
            matches.append({
                "path": rel_path,
                "line": line_number,
                "preview": line_text[:MAX_MATCH_LINE_LENGTH],
            })
        if truncated:
            break

    return {
        "operation": "search_text",
        "path": _relative_to_root(root_path, target_path),
        "query": query,
        "glob": glob_pattern,
        "files_scanned": files_scanned,
        "matches": matches,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class RepoInspectorPlugin(PluginBase):
    """Read-only repository inspection plugin."""

    @property
    def name(self) -> str:
        return "repo_inspector"

    @property
    def description(self) -> str:
        return (
            "Read-only repository inspection for synced workflow clones. "
            "Supports bounded tree listing, file reads, filename matching, "
            "and text search without shell access."
        )

    @property
    def tags(self) -> list[str]:
        return ["auto-loaded", "repo", "byok", "read-only"]

    @property
    def env_config(self) -> dict[str, str]:
        return {}

    def execute(
        self,
        operation: str,
        path: str = ".",
        query: str = "",
        glob: str = "*",
        start_line: int = 1,
        max_lines: int = 200,
        max_depth: int = 2,
        max_results: int = 50,
        include_hidden: bool = False,
    ) -> dict:
        """Inspect the synced repository without shell access.

        Operations:
        - list_tree: list files and directories under path
        - read_file: read a bounded slice of a text file
        - find_files: find files under path matching glob
        - search_text: search text matches under path
        """
        repo_root = _get_repo_root()
        if not repo_root:
            return {"error": "TBD_AGENTS_REPO_ROOT is not set for this tool invocation"}

        root_path = Path(repo_root).resolve()
        if not root_path.exists() or not root_path.is_dir():
            return {"error": f"Repository root is unavailable: {root_path}"}

        try:
            target_path = _resolve_within_root(root_path, path)
        except ValueError as exc:
            return {"error": str(exc)}

        bounded_max_depth = _clamp(max_depth, 0, MAX_DEPTH_LIMIT)
        bounded_max_lines = _clamp(max_lines, 1, MAX_LINES_LIMIT)
        bounded_max_results = _clamp(max_results, 1, MAX_RESULTS_LIMIT)
        operation_name = operation.strip().lower()

        if operation_name == "list_tree":
            return _list_tree(
                root_path, target_path, bounded_max_depth, bounded_max_results, include_hidden
            )
        if operation_name == "read_file":
            return _read_file(root_path, target_path, max(start_line, 1), bounded_max_lines)
        if operation_name == "find_files":
            return _find_files(
                root_path,
                target_path,
                glob or "*",
                bounded_max_depth,
                bounded_max_results,
                include_hidden,
            )
        if operation_name == "search_text":
            if not query:
                return {"error": "query is required for search_text"}
            return _search_text(
                root_path,
                target_path,
                query,
                glob or "*",
                bounded_max_depth,
                bounded_max_results,
                include_hidden,
            )

        return {"error": f"Unsupported operation: {operation}"}
