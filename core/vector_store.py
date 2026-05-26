"""FAISS-backed vector store for Aion semantic retrieval.

Vector indexes matter because comparing a query against every stored embedding
with plain Python loops does not scale as a memory system grows. FAISS provides
optimized nearest-neighbor search over dense vectors, making semantic retrieval
fast enough for larger local-first document collections.

This implementation uses ``IndexFlatIP``. With normalized vectors, inner
product is equivalent to cosine similarity, which is a common choice for text
embeddings because it compares vector direction rather than raw magnitude.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from .embedding_models import EmbeddedChunk
from .vector_utils import serialize_embedding, validate_embedding_dimensions


@dataclass(slots=True)
class VectorRecord:
    """Metadata record aligned with a FAISS row position."""

    chunk_id: str
    document_id: str
    text: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class VectorSearchMatch:
    """Raw vector-store match returned before retrieval formatting."""

    record: VectorRecord
    similarity_score: float
    index_position: int


class VectorStore:
    """Create, persist, load, and search a FAISS vector index.

    FAISS accelerates nearest-neighbor search: given a query vector, it finds
    stored vectors that are closest in embedding space. ``IndexFlatIP`` is an
    exact index, which is simple and reliable for learning. Approximate indexes
    can be faster at very large scale, but they introduce recall tradeoffs.
    """

    INDEX_FILENAME = "index.faiss"
    METADATA_FILENAME = "index_metadata.json"

    def __init__(self, index_directory: str | Path = "data/indexes") -> None:
        self.index_directory = Path(index_directory)
        self.index_directory.mkdir(parents=True, exist_ok=True)
        self.index: faiss.IndexFlatIP | None = None
        self.records: list[VectorRecord] = []
        self.embedding_dimension: int = 0

    def build_index(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        """Create a fresh FAISS index from embedded chunks."""

        self.index = None
        self.records = []
        self.embedding_dimension = 0
        self.add_embeddings(embedded_chunks)

    def add_embeddings(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        """Add embedded chunks to the current index in deterministic order."""

        if not embedded_chunks:
            return

        ordered_chunks = sorted(
            embedded_chunks,
            key=lambda chunk: (
                chunk.document_id,
                chunk.metadata.get("chunk_index", 0),
                chunk.chunk_id,
            ),
        )
        embedding_matrix = self._build_embedding_matrix(ordered_chunks)

        if self.index is None:
            self.embedding_dimension = embedding_matrix.shape[1]
            self.index = faiss.IndexFlatIP(self.embedding_dimension)
        elif embedding_matrix.shape[1] != self.embedding_dimension:
            raise ValueError(
                f"Index dimension mismatch. Expected {self.embedding_dimension}, "
                f"received {embedding_matrix.shape[1]}."
            )

        self.index.add(embedding_matrix)
        self.records.extend(self._build_records(ordered_chunks))

    def save_index(self, index_directory: str | Path | None = None) -> tuple[Path, Path]:
        """Persist the FAISS index plus row-aligned metadata files."""

        if self.index is None:
            raise ValueError("Cannot save an empty vector index.")

        target_directory = Path(index_directory) if index_directory is not None else self.index_directory
        target_directory.mkdir(parents=True, exist_ok=True)
        index_path = target_directory / self.INDEX_FILENAME
        metadata_path = target_directory / self.METADATA_FILENAME

        faiss.write_index(self.index, str(index_path))
        metadata_payload = {
            "embedding_dimension": self.embedding_dimension,
            "index_type": "IndexFlatIP",
            "distance_metric": "cosine_similarity_via_normalized_inner_product",
            "record_count": len(self.records),
            "records": [asdict(record) for record in self.records],
        }

        with metadata_path.open("w", encoding="utf-8") as file:
            json.dump(metadata_payload, file, indent=2, ensure_ascii=False, default=str)

        return index_path, metadata_path

    def load_index(self, index_directory: str | Path | None = None) -> None:
        """Load a previously persisted FAISS index and metadata."""

        target_directory = Path(index_directory) if index_directory is not None else self.index_directory
        index_path = target_directory / self.INDEX_FILENAME
        metadata_path = target_directory / self.METADATA_FILENAME

        if not index_path.exists() or not metadata_path.exists():
            raise FileNotFoundError("Both FAISS index and metadata files are required.")

        self.index = faiss.read_index(str(index_path))
        with metadata_path.open("r", encoding="utf-8") as file:
            metadata_payload = json.load(file)

        self.embedding_dimension = int(metadata_payload["embedding_dimension"])
        self.records = [
            VectorRecord(
                chunk_id=record["chunk_id"],
                document_id=record["document_id"],
                text=record["text"],
                metadata=record.get("metadata", {}),
            )
            for record in metadata_payload.get("records", [])
        ]

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[VectorSearchMatch]:
        """Search the index for vectors nearest to the query embedding."""

        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")
        if self.index is None:
            raise ValueError("Vector index has not been built or loaded.")
        if not self.records:
            return []

        query_matrix = self._normalize_matrix(np.asarray([query_embedding], dtype=np.float32))
        if query_matrix.shape[1] != self.embedding_dimension:
            raise ValueError(
                f"Query dimension mismatch. Expected {self.embedding_dimension}, "
                f"received {query_matrix.shape[1]}."
            )

        search_limit = min(top_k, len(self.records))
        scores, positions = self.index.search(query_matrix, search_limit)

        matches: list[VectorSearchMatch] = []
        for score, position in zip(scores[0], positions[0], strict=True):
            if position < 0:
                continue

            matches.append(
                VectorSearchMatch(
                    record=self.records[int(position)],
                    similarity_score=float(score),
                    index_position=int(position),
                )
            )

        return sorted(
            matches,
            key=lambda match: (-match.similarity_score, match.index_position, match.record.chunk_id),
        )

    @property
    def record_count(self) -> int:
        """Return the number of vectors currently tracked by the store."""

        return len(self.records)

    def _build_embedding_matrix(self, embedded_chunks: list[EmbeddedChunk]) -> np.ndarray:
        """Create a normalized matrix suitable for FAISS inner-product search."""

        validate_embedding_dimensions([chunk.embedding for chunk in embedded_chunks])
        matrix = np.asarray(
            [serialize_embedding(chunk.embedding) for chunk in embedded_chunks],
            dtype=np.float32,
        )
        return self._normalize_matrix(matrix)

    @staticmethod
    def _normalize_matrix(matrix: np.ndarray) -> np.ndarray:
        """Normalize vectors so inner product behaves like cosine similarity."""

        if matrix.ndim != 2:
            raise ValueError("FAISS expects a 2D matrix of vectors.")
        if matrix.shape[0] == 0 or matrix.shape[1] == 0:
            raise ValueError("Vector matrix cannot be empty.")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("Vector matrix must contain only finite values.")

        normalized_matrix = np.ascontiguousarray(matrix.astype(np.float32))
        faiss.normalize_L2(normalized_matrix)
        return normalized_matrix

    @staticmethod
    def _build_records(embedded_chunks: list[EmbeddedChunk]) -> list[VectorRecord]:
        """Build row-aligned metadata records for embedded chunks."""

        return [
            VectorRecord(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                text=chunk.text,
                metadata=chunk.metadata,
            )
            for chunk in embedded_chunks
        ]


__all__ = ["VectorRecord", "VectorSearchMatch", "VectorStore"]
