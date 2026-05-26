"""Schema objects for Aion's semantic retrieval layer.

Semantic retrieval means searching by meaning instead of only matching exact
keywords. Once chunks have embeddings, Aion can compare a query vector against
stored chunk vectors and return the nearest chunks as retrieval results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RetrievalResult:
    """A ranked chunk returned from semantic search.

    Retrieval metadata matters because a similarity score alone is not enough
    to make a result useful. Aion needs source details, chunk position, file
    information, and future filtering attributes so retrieved text can be
    inspected, cited, ranked, or excluded by later RAG components.
    """

    chunk_id: str
    document_id: str
    text: str
    similarity_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["RetrievalResult"]
