"""Schema objects for Aion's chunking pipeline.

Chunking is the bridge between raw documents and retrieval-ready AI data.
Embedding models and vector stores such as FAISS do not work directly with
entire PDFs or large note files very well; they work best when documents are
broken into smaller semantic units that can be embedded, indexed, and retrieved
with precision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Chunk:
    """A retrievable semantic unit derived from a normalized document.

    In a RAG pipeline, retrieval usually happens at the chunk level rather than
    the full-document level. Smaller units make it easier for FAISS or other
    vector indexes to surface the exact passage most relevant to a user's
    question, while still carrying enough surrounding context to be useful.

    The ``metadata`` field is especially important in RAG systems because
    retrieval is not only about matching text embeddings. We often need extra
    context such as file name, source type, page hints, chunk position, tags,
    or future filtering attributes. Keeping metadata attached to each chunk
    allows later retrieval and answer-generation stages to trace where the text
    came from and apply richer ranking or filtering logic.
    """

    # Deterministic identifier for the chunk. This lets downstream systems
    # store, update, and reference chunk records consistently.
    chunk_id: str

    # ID of the parent document so we can trace the chunk back to its source.
    document_id: str

    # The semantic text payload that will later be embedded and indexed.
    text: str

    # Stable order within the document. Retrieval systems often need to restore
    # nearby context or sort chunks back into source order.
    chunk_index: int

    # Extensible retrieval context. ``default_factory`` prevents shared mutable
    # state between instances.
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["Chunk"]
