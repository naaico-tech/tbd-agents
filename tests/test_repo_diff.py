"""Tests for ``code_repository_manager.discover_changes``.

Uses a real ``git`` binary against a ``tempfile.TemporaryDirectory`` so we
exercise actual ls-tree / diff plumbing rather than mocked subprocess output.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

from app.models.code_repository import IndexingConfig
from app.services.code_repository_manager import (
    FileChange,
    Manifest,
    discover_changes,
)


def _run(cwd: str, *args: str) -> str:
    """Run a git command synchronously inside ``cwd`` and return stdout."""
    out = subprocess.run(
        ["git", "-C", cwd, *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _init_repo(cwd: str) -> None:
    _run(cwd, "init", "-q", "-b", "main")
    _run(cwd, "config", "user.email", "t@example.com")
    _run(cwd, "config", "user.name", "tester")
    # No GPG signing in tests.
    _run(cwd, "config", "commit.gpgsign", "false")


def _commit_all(cwd: str, msg: str) -> str:
    _run(cwd, "add", "-A")
    _run(cwd, "commit", "-q", "-m", msg)
    return _run(cwd, "rev-parse", "HEAD")


def _write(cwd: str, rel: str, content: str) -> None:
    path = os.path.join(cwd, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(rel) else None
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _fake_repo(local_path: str, *, include=None, exclude=None, max_kb=256):
    cfg = IndexingConfig(
        include_globs=include if include is not None else ["*.py", "*.md"],
        exclude_globs=exclude if exclude is not None else ["excluded/**"],
        max_file_kb=max_kb,
    )
    return SimpleNamespace(local_path=local_path, indexing=cfg)


# ── First-time index path (base_sha=None) ─────────────────────────────────


def test_first_time_index_uses_ls_tree_and_filters():
    with tempfile.TemporaryDirectory() as td:
        _init_repo(td)
        _write(td, "a.py", "print('a')\n")
        _write(td, "b.md", "# hi\n")
        _write(td, "skip.txt", "ignored\n")  # not in include
        _write(td, "excluded/c.py", "x\n")    # excluded
        head = _commit_all(td, "init")

        repo = _fake_repo(td)
        manifest = asyncio.run(discover_changes(repo, None, head))

        assert isinstance(manifest, Manifest)
        assert manifest.head_sha == head
        assert manifest.base_sha is None
        paths = sorted(c.path for c in manifest.changes)
        assert paths == ["a.py", "b.md"]
        for c in manifest.changes:
            assert c.change == "added"
            assert c.blob_sha and len(c.blob_sha) == 40
            assert c.size > 0


def test_first_time_index_respects_max_file_kb():
    with tempfile.TemporaryDirectory() as td:
        _init_repo(td)
        _write(td, "small.py", "x = 1\n")
        _write(td, "huge.py", "x = '" + ("a" * 5000) + "'\n")
        head = _commit_all(td, "init")
        repo = _fake_repo(td, max_kb=1)  # 1KB cap → huge.py excluded

        manifest = asyncio.run(discover_changes(repo, None, head))

        paths = [c.path for c in manifest.changes]
        assert "small.py" in paths
        assert "huge.py" not in paths


# ── Diff-based incremental path ───────────────────────────────────────────


def test_diff_classifies_added_modified_deleted():
    with tempfile.TemporaryDirectory() as td:
        _init_repo(td)
        _write(td, "keep.py", "v = 1\n")
        _write(td, "doomed.py", "v = 2\n")
        base = _commit_all(td, "c1")

        # Modify keep.py, delete doomed.py, add new.py.
        _write(td, "keep.py", "v = 99\n")
        os.remove(os.path.join(td, "doomed.py"))
        _write(td, "new.py", "v = 3\n")
        head = _commit_all(td, "c2")

        repo = _fake_repo(td)
        manifest = asyncio.run(discover_changes(repo, base, head))

        assert manifest.base_sha == base
        assert manifest.head_sha == head
        by_path = {c.path: c for c in manifest.changes}
        assert by_path["keep.py"].change == "modified"
        assert by_path["keep.py"].blob_sha
        assert by_path["doomed.py"].change == "deleted"
        assert by_path["doomed.py"].blob_sha == ""
        assert by_path["doomed.py"].size == 0
        assert by_path["new.py"].change == "added"
        assert by_path["new.py"].blob_sha


def test_diff_applies_filters():
    with tempfile.TemporaryDirectory() as td:
        _init_repo(td)
        _write(td, "src/app.py", "v = 1\n")
        base = _commit_all(td, "c1")
        _write(td, "src/app.py", "v = 2\n")
        _write(td, "node_modules/lib.js", "noop\n")
        head = _commit_all(td, "c2")

        repo = _fake_repo(
            td,
            include=["src/**"],
            exclude=["node_modules/**"],
        )
        manifest = asyncio.run(discover_changes(repo, base, head))
        paths = [c.path for c in manifest.changes]
        assert paths == ["src/app.py"]


def test_unreachable_base_sha_falls_back_to_first_time():
    """An unknown ``base_sha`` must trigger the ls-tree path."""
    with tempfile.TemporaryDirectory() as td:
        _init_repo(td)
        _write(td, "a.py", "x = 1\n")
        head = _commit_all(td, "init")

        repo = _fake_repo(td)
        bogus = "0" * 40
        manifest = asyncio.run(discover_changes(repo, bogus, head))

        assert manifest.base_sha is None  # treated as first-time
        assert [c.change for c in manifest.changes] == ["added"]


def test_no_local_path_raises():
    repo = SimpleNamespace(local_path=None, indexing=IndexingConfig())
    with pytest.raises(RuntimeError):
        asyncio.run(discover_changes(repo, None, "deadbeef"))


# ── FileChange dataclass ──────────────────────────────────────────────────


def test_file_change_dataclass_fields():
    fc = FileChange(path="a.py", blob_sha="sha", change="added", size=10)
    assert fc.path == "a.py"
    assert fc.change == "added"
    assert fc.size == 10
