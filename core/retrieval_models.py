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

    @property
    def source_filename(self) -> str:
        """Extract source filename from metadata for easier citation access."""
        return self.metadata.get("source_filename", "unknown")

    @property
    def chunk_index(self) -> int:
        """Extract chunk index from metadata for ordering."""
        # This might be in metadata if stored there during chunking
        return self.metadata.get("chunk_index", 0)


@dataclass(slots=True)
class Citation:
    """Citation metadata extracted from a retrieved chunk.

    Citations provide traceable provenance for RAG-generated answers. Each
    citation points to a specific chunk and document, enabling users to
    verify where the answer came from and explore related content.
    """

    source_filename: str
    document_id: str
    chunk_index: int
    similarity_score: float
    chunk_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize citation to JSON-compatible dictionary."""
        return {
            "source_filename": self.source_filename,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "similarity_score": round(self.similarity_score, 4),
            "chunk_text": self.chunk_text[:200] + "..." if len(self.chunk_text) > 200 else self.chunk_text,
        }


@dataclass(slots=True)
class SourceDocument:
    """Aggregated metadata for a unique source document referenced in citations.

    When multiple chunks come from the same document, this record represents
    the document as a whole, allowing answers to expose which documents were
    consulted without repeating all metadata for each chunk citation.
    """

    document_id: str
    source_filename: str
    chunk_count_referenced: int = 0
    avg_similarity_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize source document to JSON-compatible dictionary."""
        return {
            "document_id": self.document_id,
            "source_filename": self.source_filename,
            "chunk_count_referenced": self.chunk_count_referenced,
            "avg_similarity_score": round(self.avg_similarity_score, 4),
        }


__all__ = ["RetrievalResult", "Citation", "SourceDocument"]
