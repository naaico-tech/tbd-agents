"""BM25-based knowledge retrieval for injecting context into agent prompts.

Uses ``rank_bm25`` (BM25Okapi implementation) to rank knowledge chunks against
a user query and return the top-k most relevant chunks.  All data is read from
MongoDB — no separate vector database is required.

Upgrade path
------------
When semantic (dense) retrieval is needed, replace ``_score_chunks`` with an
embedding-based approach (e.g. ``fastembed`` + cosine similarity or a dedicated
vector store such as Qdrant).  The ``retrieve`` function signature and its
callers do not need to change.
"""

import logging
import re

from app.models.knowledge_base import KnowledgeChunk

logger = logging.getLogger(__name__)

# Regex for simple word tokenisation (handles Unicode letters and digits)
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _tokenise(text: str) -> list[str]:
    """Lower-case word tokeniser shared between indexing and querying."""
    return _TOKEN_RE.findall(text.lower())


async def retrieve(
    knowledge_base_ids: list[str],
    query: str,
    top_k: int = 5,
    max_chars: int = 4000,
) -> str:
    """Return a formatted context block with the top-k relevant chunks.

    Parameters
    ----------
    knowledge_base_ids:
        IDs of the KnowledgeBases to search.
    query:
        The user's prompt / question used for ranking.
    top_k:
        Maximum number of chunks to return (default 5).
    max_chars:
        Hard cap on total character count of returned content (default 4 000).

    Returns
    -------
    A ``<knowledge_context>`` XML block ready to be appended to the system
    prompt, or an empty string if no chunks were found.
    """
    if not knowledge_base_ids or not query.strip():
        return ""

    # ── Load all chunks for the requested knowledge bases ────────────────────
    chunks = await KnowledgeChunk.find(
        {"knowledge_base_id": {"$in": knowledge_base_ids}}
    ).to_list()

    if not chunks:
        return ""

    # ── BM25 scoring ─────────────────────────────────────────────────────────
    try:
        from rank_bm25 import BM25Plus
    except ImportError:
        logger.warning(
            "rank_bm25 is not installed — falling back to unranked knowledge injection. "
            "Run `pip install rank-bm25` to enable ranked retrieval."
        )
        selected = chunks[:top_k]
    else:
        corpus = [c.tokens if c.tokens else _tokenise(c.content) for c in chunks]
        bm25 = BM25Plus(corpus)
        query_tokens = _tokenise(query)
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
        # BM25Plus scores are always positive; a score near the minimum means no relevance
        min_score = min(s for s, _ in ranked) if ranked else 0
        max_score = max(s for s, _ in ranked) if ranked else 0
        # Return top-k only when there is meaningful signal (not all scores identical)
        if max_score == min_score:
            # All chunks equally (ir)relevant — skip injection
            return ""
        selected = [c for _, c in ranked[:top_k]]

    # ── Format output ─────────────────────────────────────────────────────────
    sections: list[str] = []
    char_count = 0
    for chunk in selected:
        label = f' source="{chunk.source}"' if chunk.source else ""
        snippet = chunk.content.strip()
        block = f'<chunk{label}>\n{snippet}\n</chunk>'
        if char_count + len(block) > max_chars:
            break
        sections.append(block)
        char_count += len(block)

    if not sections:
        return ""

    return "<knowledge_context>\n" + "\n".join(sections) + "\n</knowledge_context>"
