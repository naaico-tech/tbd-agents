from datetime import UTC, datetime

from beanie import Document
from pydantic import Field


class KnowledgeBase(Document):
    """A named collection of knowledge chunks that can be attached to workflows.

    The knowledge base stores chunked documents together with their
    pre-tokenised term list so that BM25 retrieval can be performed
    at query time without rebuilding the corpus on every call.
    """

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "knowledge_bases"


class KnowledgeChunk(Document):
    """A single document chunk belonging to a KnowledgeBase.

    ``content`` holds the raw text of the chunk.
    ``tokens`` is the lower-cased, whitespace-split token list used for BM25
    scoring and is computed automatically on insert/update.
    ``source`` is an optional free-form label (file name, URL, section heading)
    for attribution inside the injected context block.
    """

    knowledge_base_id: str
    content: str
    tokens: list[str] = Field(default_factory=list)  # pre-tokenised for BM25
    source: str = ""  # e.g. "docs/readme.md § Installation"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "knowledge_chunks"
