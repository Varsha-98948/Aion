"""Embedding engine for converting chunks into semantic vectors.

Embeddings represent meaning as numbers. Instead of comparing text only through
exact keywords, we transform each chunk into a dense vector so later retrieval
systems can search for conceptually related content. That is why embeddings are
foundational in RAG pipelines: they let us retrieve relevant passages even when
the query uses different words than the source document.

Example usage:
    >>> from core.embedder import EmbeddingEngine
    >>> from core.chunk_models import Chunk
    >>> engine = EmbeddingEngine()
    >>> chunks = [
    ...     Chunk(
    ...         chunk_id="chunk-1",
    ...         document_id="doc-1",
    ...         text="Aion is a local-first AI companion.",
    ...         chunk_index=0,
    ...         metadata={},
    ...     )
    ... ]
    >>> embedded_chunks = engine.embed_chunks(chunks)
    >>> len(embedded_chunks[0].embedding) > 0
    True
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from .chunk_models import Chunk
from .embedding_models import EmbeddedChunk
from .vector_utils import serialize_embedding, validate_embedding_dimensions

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


@dataclass(slots=True)
class _EmbeddingBatch:
    """Internal batch container used to keep chunk order explicit."""

    chunks: list[Chunk]
    texts: list[str]


class EmbeddingEngine:
    """Generate semantic embeddings from chunk objects.

    Embedding models compress text meaning into fixed-size vectors. This makes
    semantic retrieval possible because we can compare vectors numerically using
    similarity measures instead of relying only on exact keyword overlap.

    Model size is a practical engineering tradeoff:
    - Smaller models are faster and lighter for local-first systems.
    - Larger models may capture nuance better but cost more memory and time.

    ``all-MiniLM-L6-v2`` is a strong default for learning-oriented RAG systems
    because it is small, widely used, and fast enough for local experimentation.
    """

    DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        prefer_local_files: bool = True,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")

        self.model_name = model_name
        self.batch_size = batch_size
        self.normalize_embeddings = normalize_embeddings
        self.prefer_local_files = prefer_local_files
        self._model: SentenceTransformer | None = None

    def embed_chunks(self, chunks: list[Chunk], batch_size: int | None = None) -> list[EmbeddedChunk]:
        """Generate embeddings for chunks in deterministic order.

        Deterministic ordering matters because later vector indexes and metadata
        files should stay aligned with the chunk order produced earlier in the
        preprocessing pipeline.
        """

        if not chunks:
            return []

        embedding_batch = self._prepare_batch(chunks)
        embedding_matrix = self._encode_texts(
            texts=embedding_batch.texts,
            batch_size=batch_size or self.batch_size,
        )
        embedding_dimension = validate_embedding_dimensions(embedding_matrix)

        embedded_chunks: list[EmbeddedChunk] = []
        for chunk, embedding_vector in zip(embedding_batch.chunks, embedding_matrix, strict=True):
            embedded_chunks.append(
                EmbeddedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    embedding=serialize_embedding(embedding_vector),
                    metadata=self._build_embedding_metadata(
                        chunk=chunk,
                        embedding_dimension=embedding_dimension,
                    ),
                )
            )

        return embedded_chunks

    def embed_texts(self, texts: list[str], batch_size: int | None = None) -> list[list[float]]:
        """Generate embeddings for plain text inputs such as search queries.

        Query embeddings must come from the same model as chunk embeddings so
        both live in the same semantic vector space. That shared space is what
        lets FAISS compare a natural-language question against stored chunks.
        """

        cleaned_texts = [text.strip() for text in texts if text.strip()]
        if not cleaned_texts:
            return []

        embedding_matrix = self._encode_texts(
            texts=cleaned_texts,
            batch_size=batch_size or self.batch_size,
        )
        validate_embedding_dimensions(embedding_matrix)
        return [serialize_embedding(embedding_vector) for embedding_vector in embedding_matrix]

    def _prepare_batch(self, chunks: list[Chunk]) -> _EmbeddingBatch:
        """Create a stable batch representation from chunk objects."""

        ordered_chunks = sorted(
            chunks,
            key=lambda chunk: (chunk.document_id, chunk.chunk_index, chunk.chunk_id),
        )
        return _EmbeddingBatch(
            chunks=ordered_chunks,
            texts=[chunk.text for chunk in ordered_chunks],
        )

    def _encode_texts(self, texts: list[str], batch_size: int) -> np.ndarray:
        """Encode text strings into a 2D embedding matrix."""

        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")

        model = self._get_model()
        embedding_matrix = model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )

        if embedding_matrix.ndim != 2:
            raise ValueError("Embedding model must return a 2D embedding matrix.")

        return np.asarray(embedding_matrix, dtype=np.float32)

    def _get_model(self) -> SentenceTransformer:
        """Load the embedding model lazily.

        Lazy loading keeps startup light for modules that inspect pipeline state
        without always generating embeddings immediately.
        """

        if self._model is None:
            from sentence_transformers import SentenceTransformer

            if self.prefer_local_files:
                try:
                    self._model = SentenceTransformer(self.model_name, local_files_only=True)
                except Exception:
                    self._model = SentenceTransformer(self.model_name)
            else:
                self._model = SentenceTransformer(self.model_name)

        return self._model

    def _build_embedding_metadata(self, chunk: Chunk, embedding_dimension: int) -> dict[str, Any]:
        """Attach embedding provenance to the original chunk metadata."""

        metadata = dict(chunk.metadata)
        metadata["chunk_index"] = chunk.chunk_index
        metadata["embedding_model"] = self.model_name
        metadata["embedding_dimension"] = embedding_dimension
        metadata["normalized_embedding"] = self.normalize_embeddings
        metadata["prefer_local_files"] = self.prefer_local_files
        return metadata


__all__ = ["EmbeddingEngine"]
