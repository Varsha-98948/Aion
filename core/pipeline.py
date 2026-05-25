"""Orchestration layer for Aion's preprocessing and embedding pipeline.

This module keeps workflow orchestration separate from transformation logic.
That separation matters in scalable AI systems because loading, chunking,
serialization, embedding, and later indexing are distinct stages with
different responsibilities.

Example usage:
    >>> from core.pipeline import ProcessingPipeline
    >>> pipeline = ProcessingPipeline()
    >>> result = pipeline.process_file("documents/notes.txt")
    >>> result.stats.chunk_count
    4
    >>> result.embedding_stats.total_embeddings
    4

Sample serialized vector JSON:
    {
      "document": {
        "doc_id": "8af8c4...",
        "filename": "notes.txt",
        "file_type": "txt"
      },
      "embedding_stats": {
        "total_embeddings": 4,
        "embedding_dimension": 384,
        "model_name": "sentence-transformers/all-MiniLM-L6-v2"
      },
      "embeddings": [
        {
          "chunk_id": "8af8c4...-chunk-0000-a1b2c3d4e5f6",
          "document_id": "8af8c4...",
          "text": "A retrievable semantic passage...",
          "embedding": [0.0123, -0.0841, 0.1944],
          "metadata": {
            "source_filename": "notes.txt",
            "embedding_dimension": 384
          }
        }
      ]
    }

Expected output flow:
    upload/file path -> DocumentLoader -> Document -> Chunker -> Chunk list
    -> JSON chunk persistence -> EmbeddingEngine -> EmbeddedChunk list
    -> JSON vector persistence -> UI/debug inspection
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

from .chunk_models import Chunk
from .chunker import Chunker
from .document_loader import DocumentLoader
from .embedder import EmbeddingEngine
from .embedding_models import EmbeddedChunk
from .schema import Document
from .vector_utils import serialize_embedding, validate_embedding_dimensions, vector_norm


@dataclass(slots=True)
class PipelineStats:
    """Debugging statistics for one document's chunking run.

    Chunk statistics matter because chunk quality strongly influences later
    embeddings. If chunks are too large, too small, or too uneven, semantic
    retrieval will usually become less precise once vector search is added.
    """

    chunk_count: int
    average_chunk_size: float
    smallest_chunk_size: int
    largest_chunk_size: int
    chunk_size: int
    overlap: int


@dataclass(slots=True)
class EmbeddingStats:
    """Debugging statistics for one embedding run.

    Vector observability matters in AI systems because embeddings are expensive
    to generate and hard to reason about if they remain invisible. These stats
    help confirm that vectors were produced consistently and with the expected
    dimensionality.
    """

    total_embeddings: int
    embedding_dimension: int
    model_name: str
    batch_size: int
    average_vector_norm: float
    smallest_vector_norm: float
    largest_vector_norm: float
    normalized_embeddings: bool


@dataclass(slots=True)
class ProcessingResult:
    """Structured result returned by the preprocessing pipeline."""

    document: Document
    chunks: list[Chunk]
    embedded_chunks: list[EmbeddedChunk]
    stats: PipelineStats
    embedding_stats: EmbeddingStats
    chunk_file_path: Path | None = None
    vector_file_path: Path | None = None


class ProcessingPipeline:
    """Coordinate document loading, chunking, embedding, and persistence.

    Preprocessing pipelines are the bridge between ingestion and retrieval
    infrastructure. Keeping this layer modular makes it easier to add FAISS,
    caching, reranking, or evaluation later without changing the lower-level
    document, chunk, and embedding components.
    """

    def __init__(
        self,
        loader: DocumentLoader | None = None,
        chunker: Chunker | None = None,
        embedder: EmbeddingEngine | None = None,
        chunks_directory: str | Path = "data/chunks",
        vectors_directory: str | Path = "data/vectors",
    ) -> None:
        self.loader = loader or DocumentLoader()
        self.chunker = chunker or Chunker()
        self.embedder = embedder or EmbeddingEngine()
        self.chunks_directory = Path(chunks_directory)
        self.vectors_directory = Path(vectors_directory)
        self.chunks_directory.mkdir(parents=True, exist_ok=True)
        self.vectors_directory.mkdir(parents=True, exist_ok=True)

    def process_file(
        self,
        file_path: str | Path,
        filename: str | None = None,
        save_output: bool = True,
        generate_embeddings: bool = True,
    ) -> ProcessingResult:
        """Run the document-to-vector flow for a single file."""

        document = self.loader.load(str(file_path), filename=filename)
        chunks = self.chunker.chunk_document(document)
        stats = self.get_pipeline_stats(chunks)

        chunk_file_path: Path | None = None
        if save_output:
            chunk_file_path = self.save_chunks(document=document, chunks=chunks, stats=stats)

        embedded_chunks: list[EmbeddedChunk] = []
        if generate_embeddings:
            embedded_chunks = self.embedder.embed_chunks(chunks)

        embedding_stats = self.get_embedding_stats(embedded_chunks)

        vector_file_path: Path | None = None
        if save_output and generate_embeddings:
            vector_file_path = self.save_embeddings(
                document=document,
                embedded_chunks=embedded_chunks,
                stats=embedding_stats,
            )

        return ProcessingResult(
            document=document,
            chunks=chunks,
            embedded_chunks=embedded_chunks,
            stats=stats,
            embedding_stats=embedding_stats,
            chunk_file_path=chunk_file_path,
            vector_file_path=vector_file_path,
        )

    def save_chunks(
        self,
        document: Document,
        chunks: list[Chunk],
        stats: PipelineStats,
    ) -> Path:
        """Serialize chunks to JSON for debugging and future embedding stages.

        Serialized chunks are useful in RAG debugging because they let us
        inspect the exact text units that will later be embedded. Observability
        matters in AI systems: when retrieval quality is poor, developers need
        readable intermediate artifacts to trace where degradation began.
        """

        output_path = self.chunks_directory / self._build_chunk_filename(document)
        payload = {
            "document": self._serialize_document(document),
            "stats": asdict(stats),
            "chunks": [self._serialize_chunk(chunk) for chunk in chunks],
        }

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False, default=str)

        return output_path

    def save_embeddings(
        self,
        document: Document,
        embedded_chunks: list[EmbeddedChunk],
        stats: EmbeddingStats,
    ) -> Path:
        """Serialize embedded chunks to JSON for debugging and reuse.

        Embedding persistence improves performance because embedding generation
        is one of the more expensive stages in a local AI pipeline. Persisting
        vectors means later FAISS indexing or retrieval experiments can reuse
        existing embeddings instead of recomputing them every run.
        """

        output_path = self.vectors_directory / self._build_vector_filename(document)
        payload = {
            "document": self._serialize_document(document),
            "embedding_stats": asdict(stats),
            "embeddings": [
                self._serialize_embedded_chunk(embedded_chunk)
                for embedded_chunk in embedded_chunks
            ],
        }

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False, default=str)

        return output_path

    def get_pipeline_stats(self, chunks: list[Chunk]) -> PipelineStats:
        """Return chunking metrics useful for retrieval debugging."""

        chunk_lengths = [len(chunk.text) for chunk in chunks]
        if not chunk_lengths:
            return PipelineStats(
                chunk_count=0,
                average_chunk_size=0.0,
                smallest_chunk_size=0,
                largest_chunk_size=0,
                chunk_size=self.chunker.chunk_size,
                overlap=self.chunker.overlap,
            )

        return PipelineStats(
            chunk_count=len(chunks),
            average_chunk_size=sum(chunk_lengths) / len(chunk_lengths),
            smallest_chunk_size=min(chunk_lengths),
            largest_chunk_size=max(chunk_lengths),
            chunk_size=self.chunker.chunk_size,
            overlap=self.chunker.overlap,
        )

    def get_embedding_stats(self, embedded_chunks: list[EmbeddedChunk]) -> EmbeddingStats:
        """Return embedding metrics useful for semantic retrieval debugging.

        These metrics help validate the semantic memory layer before retrieval is
        added. Consistent dimension and sensible vector norms are early signals
        that chunks are being embedded into one coherent vector space.
        """

        if not embedded_chunks:
            return EmbeddingStats(
                total_embeddings=0,
                embedding_dimension=0,
                model_name=self.embedder.model_name,
                batch_size=self.embedder.batch_size,
                average_vector_norm=0.0,
                smallest_vector_norm=0.0,
                largest_vector_norm=0.0,
                normalized_embeddings=self.embedder.normalize_embeddings,
            )

        embeddings = [embedded_chunk.embedding for embedded_chunk in embedded_chunks]
        embedding_dimension = validate_embedding_dimensions(embeddings)
        norms = [vector_norm(embedding) for embedding in embeddings]

        return EmbeddingStats(
            total_embeddings=len(embedded_chunks),
            embedding_dimension=embedding_dimension,
            model_name=self.embedder.model_name,
            batch_size=self.embedder.batch_size,
            average_vector_norm=sum(norms) / len(norms),
            smallest_vector_norm=min(norms),
            largest_vector_norm=max(norms),
            normalized_embeddings=self.embedder.normalize_embeddings,
        )

    @staticmethod
    def _serialize_document(document: Document) -> dict[str, Any]:
        """Convert a document object into a JSON-friendly dictionary."""

        return {
            "doc_id": document.doc_id,
            "filename": document.filename,
            "file_type": document.file_type,
            "created_at": document.created_at,
            "metadata": document.metadata,
        }

    @staticmethod
    def _serialize_chunk(chunk: Chunk) -> dict[str, Any]:
        """Convert a ``Chunk`` object into a JSON-friendly dictionary."""

        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "metadata": chunk.metadata,
        }

    @staticmethod
    def _serialize_embedded_chunk(embedded_chunk: EmbeddedChunk) -> dict[str, Any]:
        """Convert an ``EmbeddedChunk`` object into a JSON-friendly dictionary."""

        return {
            "chunk_id": embedded_chunk.chunk_id,
            "document_id": embedded_chunk.document_id,
            "text": embedded_chunk.text,
            "embedding": serialize_embedding(embedded_chunk.embedding),
            "metadata": embedded_chunk.metadata,
        }

    def _build_chunk_filename(self, document: Document) -> str:
        """Build a deterministic, human-readable filename for saved chunks."""

        safe_stem = self._slugify_filename(Path(document.filename).stem)
        return f"{safe_stem}_{document.doc_id[:12]}_chunks.json"

    def _build_vector_filename(self, document: Document) -> str:
        """Build a deterministic, human-readable filename for saved vectors."""

        safe_stem = self._slugify_filename(Path(document.filename).stem)
        return f"{safe_stem}_{document.doc_id[:12]}_vectors.json"

    @staticmethod
    def _slugify_filename(filename_stem: str) -> str:
        """Convert a filename into a filesystem-friendly stem."""

        lowered = filename_stem.strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
        return slug or "document"


__all__ = ["EmbeddingStats", "PipelineStats", "ProcessingPipeline", "ProcessingResult"]
