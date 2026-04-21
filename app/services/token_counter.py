"""Token counting utilities.

Provides a unified ``count_tokens(text, model)`` function that dispatches to
the best available counter for the given model family:

* ``tiktoken`` for OpenAI / OpenAI-compatible models
* ``anthropic.Anthropic().count_tokens`` (synchronous) for Anthropic Claude
* Character-based fallback (``len(text) // 4``) when neither library is
  available or the model family is unknown

All failures are caught and the fallback is applied so callers never need to
handle exceptions from this module.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── tiktoken ────────────────────────────────────────────────────────────────

try:
    import tiktoken as _tiktoken  # type: ignore[import]

    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logger.debug("tiktoken not installed — OpenAI token counting will use char fallback")

# Cache tiktoken encodings to avoid repeated disk I/O
_encoding_cache: dict[str, object] = {}


def _get_tiktoken_encoding(model: str):
    if model not in _encoding_cache:
        try:
            enc = _tiktoken.encoding_for_model(model)
        except KeyError:
            # Unknown model — fall back to the cl100k_base encoder (GPT-4 family)
            enc = _tiktoken.get_encoding("cl100k_base")
        _encoding_cache[model] = enc
    return _encoding_cache[model]


# ── Anthropic ───────────────────────────────────────────────────────────────

try:
    import anthropic as _anthropic  # type: ignore[import]

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    logger.debug("anthropic not installed — Claude token counting will use char fallback")

_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = _anthropic.Anthropic(api_key="dummy")  # count_tokens is local
    return _anthropic_client


# ── Model routing helpers ────────────────────────────────────────────────────

_CLAUDE_RE = re.compile(r"claude", re.IGNORECASE)
_OPENAI_RE = re.compile(r"gpt-|o1|o3|o4|text-davinci|codex", re.IGNORECASE)


def _is_claude(model: str) -> bool:
    return bool(_CLAUDE_RE.search(model))


def _is_openai_compat(model: str) -> bool:
    return bool(_OPENAI_RE.search(model))


# ── Public API ───────────────────────────────────────────────────────────────


def count_tokens(text: str, model: str = "") -> int:
    """Return estimated token count for *text* given *model* name.

    Falls back to ``len(text) // 4`` if precise counting is unavailable.
    Never raises.
    """
    if not text:
        return 0

    # ── Anthropic Claude ────────────────────────────────────────────────────
    if _is_claude(model) and _ANTHROPIC_AVAILABLE:
        try:
            return _get_anthropic_client().count_tokens(text)
        except Exception as exc:
            logger.debug("anthropic.count_tokens failed: %s", exc)

    # ── OpenAI / tiktoken ───────────────────────────────────────────────────
    if _TIKTOKEN_AVAILABLE and (_is_openai_compat(model) or not _is_claude(model)):
        try:
            enc = _get_tiktoken_encoding(model or "gpt-4o")
            return len(enc.encode(text))
        except Exception as exc:
            logger.debug("tiktoken encode failed for model '%s': %s", model, exc)

    # ── Fallback: 4 chars ≈ 1 token ─────────────────────────────────────────
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict], model: str = "") -> int:
    """Estimate total tokens for an OpenAI-style messages list.

    Counts content of every message plus a fixed per-message overhead of 4
    tokens (role + separators), matching the OpenAI cookbook heuristic.
    """
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):
            # Multipart content — join text parts
            parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            content = " ".join(parts)
        total += count_tokens(str(content), model) + 4
    return total + 2  # priming tokens
