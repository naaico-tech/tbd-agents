"""Tests for :mod:`app.services.code_chunker` (PR3 ``treesitter-chunker``).

Exercise the public :func:`chunk_code` contract: language detection, AST
boundary chunking, oversized splitting, tiny-import coalescing, fallback to
pygments and ultimately the char-window splitter, env-var sizing override,
and graceful tree-sitter parse-failure recovery.
"""

from __future__ import annotations

import textwrap

import pytest

from app.services import code_chunker as cc
from app.services.code_chunker import CodeChunk, chunk_code

# ── 1. Top-level functions become separate chunks ────────────────────────────


def test_python_function_chunked_by_def():
    src = textwrap.dedent(
        """
        def alpha():
            return 1

        def beta():
            return 2

        def gamma():
            return 3
        """
    ).strip()

    chunks = chunk_code(src, "x.py")
    fn_chunks = [c for c in chunks if c.symbol in {"alpha", "beta", "gamma"}]
    assert len(fn_chunks) == 3
    syms = [c.symbol for c in fn_chunks]
    assert syms == ["alpha", "beta", "gamma"]
    for c in fn_chunks:
        assert c.language == "python"
        assert c.start_line >= 1
        assert c.end_line >= c.start_line


# ── 2. Class with methods kept as one cohesive chunk (under MAX_CHARS) ───────


def test_python_class_methods_kept_with_class():
    src = textwrap.dedent(
        """
        class Widget:
            def __init__(self):
                self.x = 1

            def render(self):
                return self.x
        """
    ).strip()

    chunks = chunk_code(src, "widget.py")
    # The whole class fits well below 2 KiB → exactly one chunk.
    class_chunks = [c for c in chunks if c.symbol == "Widget"]
    assert len(class_chunks) == 1
    assert "def __init__" in class_chunks[0].text
    assert "def render" in class_chunks[0].text
    assert class_chunks[0].language == "python"


# ── 3. Oversized declaration splits on statement boundaries ──────────────────


def test_oversized_function_split_on_statements():
    body_groups = []
    for grp in range(8):
        body_groups.append("\n".join(f"    x{grp}_{i} = {i}" for i in range(15)))
    body = "\n\n".join(body_groups)
    src = f"def big():\n{body}\n"

    chunks = chunk_code(src, "big.py", max_chars=400)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 400
        # No chunk starts mid-line (first char is not pure whitespace gap).
        assert not c.text.startswith(" \n")


# ── 4. TypeScript: class + function chunked separately ───────────────────────


def test_typescript_arrow_and_class():
    src = textwrap.dedent(
        """
        export class Greeter {
          constructor(public name: string) {}

          greet(): string {
            return `hello ${this.name}`;
          }
        }

        export function farewell(name: string): string {
          return `bye ${name}`;
        }
        """
    ).strip()

    chunks = chunk_code(src, "greeter.ts")
    texts = [c.text for c in chunks]
    assert any("class Greeter" in t for t in texts)
    assert any("function farewell" in t for t in texts)
    assert all(c.language == "typescript" for c in chunks)


# ── 5. Go: struct + func emitted as distinct chunks ──────────────────────────


def test_go_struct_and_func_separate_chunks():
    src = textwrap.dedent(
        """
        package main

        type Point struct {
            X int
            Y int
        }

        func Add(a, b int) int {
            return a + b
        }
        """
    ).strip()

    chunks = chunk_code(src, "main.go")
    texts = [c.text for c in chunks]
    assert any("type Point struct" in t for t in texts)
    assert any("func Add" in t for t in texts)
    assert all(c.language == "go" for c in chunks)


# ── 6. Unknown extension falls back gracefully (no exception) ────────────────


def test_unknown_language_falls_back_to_pygments():
    src = "this is just some prose with no syntax at all\n" * 5
    chunks = chunk_code(src, "notes.weirdext")
    assert chunks  # never empty for non-empty input
    for c in chunks:
        assert c.language == "unknown"
        assert isinstance(c, CodeChunk)


# ── 7. Pygments path for an extension we recognise but force fallback ────────


def test_pygments_lexer_recognized(monkeypatch):
    """Force the tree-sitter parser to be unavailable for ruby; ensure
    pygments fallback still produces ruby-tagged chunks."""
    # Reset caches so our patch takes effect deterministically.
    monkeypatch.setattr(cc, "_PARSERS", {})
    monkeypatch.setattr(cc, "_PARSER_FAILED", {"ruby"})

    src = textwrap.dedent(
        """
        def hello(name)
          puts "hi #{name}"
        end
        """
    ).strip()

    chunks = chunk_code(src, "h.rb")
    assert chunks
    assert all(c.language == "ruby" for c in chunks)


# ── 8. Empty / whitespace input ──────────────────────────────────────────────


def test_empty_file_returns_empty_list():
    assert chunk_code("", "x.py") == []
    assert chunk_code("   \n\n  \t\n", "x.py") == []


# ── 9. Many tiny imports coalesce ────────────────────────────────────────────


def test_tiny_imports_coalesced():
    src = "\n".join(f"import mod{i}" for i in range(20))
    chunks = chunk_code(src, "imp.py")
    assert len(chunks) == 1
    assert chunks[0].text.count("import") == 20


# ── 10. Determinism ──────────────────────────────────────────────────────────


def test_chunk_idx_stable_for_same_input():
    src = textwrap.dedent(
        """
        def a():
            return 1

        def b():
            return 2
        """
    ).strip()
    a = chunk_code(src, "x.py")
    b = chunk_code(src, "x.py")
    assert a == b


# ── 11. Env var override ─────────────────────────────────────────────────────


def test_max_tokens_env_var_overrides(monkeypatch):
    src = "def f():\n" + "\n".join(f"    x{i} = {i}" for i in range(40)) + "\n"
    monkeypatch.setenv("INDEX_CHUNK_MAX_TOKENS", "8")  # 8*4 = 32 chars
    small = chunk_code(src, "x.py")
    monkeypatch.setenv("INDEX_CHUNK_MAX_TOKENS", "512")
    big = chunk_code(src, "x.py")
    assert len(small) > len(big)


# ── 12. Binary-ish data does not crash ───────────────────────────────────────


def test_binary_data_does_not_crash():
    blob = "abc\x00\x01\x02 def garbled\nrandom \x7f bytes\n"
    out = chunk_code(blob, "weird.dat")
    assert isinstance(out, list)


# ── 13. Language tagging is consistent across known extensions ───────────────


@pytest.mark.parametrize(
    "path,expected_lang",
    [
        ("a.py", "python"),
        ("a.ts", "typescript"),
        ("a.go", "go"),
        ("Foo.java", "java"),
        ("a.rs", "rust"),
    ],
)
def test_language_tag_for_known_extensions(path, expected_lang):
    src = "x = 1\n" * 5  # syntactically harmless across most langs
    out = chunk_code(src, path)
    assert out
    assert out[0].language == expected_lang


# ── 14. Tree-sitter parse failure falls back, no exception ───────────────────


def test_treesitter_parse_failure_falls_back(monkeypatch):
    """Replace the parser with a stub that raises on parse(); ensure
    :func:`chunk_code` still emits chunks via pygments / char fallback."""

    class _BadParser:
        def parse(self, _src):  # noqa: D401 - simple stub
            raise RuntimeError("synthetic parse failure")

    monkeypatch.setattr(cc, "_PARSERS", {"python": _BadParser()})
    # Make sure get_parser returns our bad one (cache hit path).
    monkeypatch.setattr(cc, "_PARSER_FAILED", set())

    src = "def f():\n    return 1\n"
    out = chunk_code(src, "x.py")
    assert out
    # We still tag language from the extension, even on fallback.
    assert out[0].language == "python"


# ── 15. Bonus: oversized single line hard-cuts ───────────────────────────────


def test_single_long_line_hard_cut():
    long_line = "x" * 5000
    out = chunk_code(long_line, "min.js", max_chars=200)
    assert len(out) > 1
    for c in out:
        assert len(c.text) <= 200
