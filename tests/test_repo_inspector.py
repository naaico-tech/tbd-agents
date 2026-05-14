from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repo_inspector_requires_repo_root(monkeypatch):
    from app.plugins.repo_inspector import RepoInspectorPlugin
    repo_inspector = RepoInspectorPlugin().execute

    monkeypatch.delenv("TBD_AGENTS_REPO_ROOT", raising=False)

    result = repo_inspector(operation="list_tree")

    assert "error" in result
    assert "TBD_AGENTS_REPO_ROOT" in result["error"]


def test_repo_inspector_rejects_path_escape(tmp_path, monkeypatch):
    from app.plugins.repo_inspector import RepoInspectorPlugin
    repo_inspector = RepoInspectorPlugin().execute

    _write(tmp_path / "src" / "main.py", "print('ok')\n")
    monkeypatch.setenv("TBD_AGENTS_REPO_ROOT", str(tmp_path))

    result = repo_inspector(operation="list_tree", path="../")

    assert "error" in result
    assert "escapes repository root" in result["error"]


def test_repo_inspector_read_file_returns_bounded_slice(tmp_path, monkeypatch):
    from app.plugins.repo_inspector import RepoInspectorPlugin
    repo_inspector = RepoInspectorPlugin().execute

    _write(tmp_path / "README.md", "line1\nline2\nline3\nline4\n")
    monkeypatch.setenv("TBD_AGENTS_REPO_ROOT", str(tmp_path))

    result = repo_inspector(operation="read_file", path="README.md", start_line=2, max_lines=2)

    assert result["operation"] == "read_file"
    assert result["path"] == "README.md"
    assert result["start_line"] == 2
    assert result["end_line"] == 3
    assert result["truncated"] is True
    assert result["content"] == "line2\nline3"


def test_repo_inspector_search_text_and_find_files(tmp_path, monkeypatch):
    from app.plugins.repo_inspector import RepoInspectorPlugin
    repo_inspector = RepoInspectorPlugin().execute

    _write(tmp_path / "app" / "service.py", "def run():\n    return 'needle'\n")
    _write(tmp_path / "app" / "other.txt", "needle here too\n")
    _write(tmp_path / "docs" / "notes.md", "no match\n")
    monkeypatch.setenv("TBD_AGENTS_REPO_ROOT", str(tmp_path))

    search_result = repo_inspector(
        operation="search_text",
        path="app",
        query="needle",
        glob="*.py",
        max_results=5,
    )
    find_result = repo_inspector(
        operation="find_files",
        path=".",
        glob="*.md",
        max_results=5,
    )

    assert search_result["operation"] == "search_text"
    assert search_result["files_scanned"] == 1
    assert search_result["matches"] == [{
        "path": "app/service.py",
        "line": 2,
        "preview": "    return 'needle'",
    }]

    assert find_result["operation"] == "find_files"
    assert find_result["matches"] == ["docs/notes.md"]
