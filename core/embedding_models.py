"""Schema objects for Aion's embedding pipeline.

Embeddings are the semantic-memory representation of chunks. Instead of storing
only raw text, we also store a numeric vector that captures the chunk's meaning
in a form machine-learning systems can compare mathematically. This is the key
step that moves Aion from string processing into semantic retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EmbeddedChunk:
    """A chunk paired with its embedding vector and retrieval metadata.

    In RAG systems, the embedding vector is rarely useful by itself. We need to
    keep it attached to the original text and metadata so later retrieval,
    reranking, citations, and memory features can trace each vector back to the
    source chunk that produced it.

    Keeping metadata with embeddings is especially important because semantic
    similarity tells us which chunks are conceptually close, but metadata tells
    us how to interpret, filter, and ground those results inside the broader
    document system.
    """

    # Stable chunk identifier used to connect the vector back to its source.
    chunk_id: str

    # Parent document identifier for document-level grouping and traceability.
    document_id: str

    # Original chunk text preserved for debugging and future retrieval display.
    text: str

    # Dense semantic vector produced by an embedding model. Lists are used here
    # so the object stays straightforward to serialize into JSON when needed.
    embedding: list[float]

    # Extensible retrieval and provenance context attached to the embedding.
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["EmbeddedChunk"]
