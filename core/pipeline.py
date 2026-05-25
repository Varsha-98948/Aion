"""Orchestration layer for Aion's preprocessing pipeline.

This module keeps workflow orchestration separate from transformation logic.
That separation matters in scalable AI systems because loading, chunking,
serialization, observability, and later embedding/indexing are distinct stages
with different responsibilities.

Example usage:
    >>> from core.pipeline import ProcessingPipeline
    >>> pipeline = ProcessingPipeline()
    >>> result = pipeline.process_file("documents/notes.txt")
    >>> result.stats.chunk_count
    4

Sample serialized chunk JSON:
    {
      "document": {
        "doc_id": "8af8c4...",
        "filename": "notes.txt",
        "file_type": "txt",
        "created_at": "2026-05-25T09:00:00+00:00"
      },
      "stats": {
        "chunk_count": 4,
        "average_chunk_size": 612.5,
        "smallest_chunk_size": 418,
        "largest_chunk_size": 781,
        "chunk_size": 800,
        "overlap": 120
      },
      "chunks": [
        {
          "chunk_id": "8af8c4...-chunk-0000-a1b2c3d4e5f6",
          "document_id": "8af8c4...",
          "chunk_index": 0,
          "text": "A retrievable semantic passage...",
          "metadata": {
            "source_filename": "notes.txt",
            "source_file_type": "txt"
          }
        }
      ]
    }

Expected output flow:
    upload/file path -> DocumentLoader -> Document -> Chunker -> Chunk list
    -> JSON persistence in data/chunks -> UI/debug inspection
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
from .schema import Document


@dataclass(slots=True)
class PipelineStats:
    """Debugging statistics for one document's chunking run.

    These metrics matter because chunk quality directly shapes later embedding
    and retrieval quality. Uneven or overly large chunks can reduce retrieval
    precision once vectors are introduced.
    """

    chunk_count: int
    average_chunk_size: float
    smallest_chunk_size: int
    largest_chunk_size: int
    chunk_size: int
    overlap: int


@dataclass(slots=True)
class ProcessingResult:
    """Structured result returned by the preprocessing pipeline."""

    document: Document
    chunks: list[Chunk]
    stats: PipelineStats
    chunk_file_path: Path | None = None


class ProcessingPipeline:
    """Coordinate document loading, chunking, persistence, and debug output.

    Preprocessing pipelines are the bridge between ingestion and later
    retrieval infrastructure. Keeping this layer modular makes it easier to add
    embeddings, vector indexing, caching, or evaluation later without changing
    the lower-level document and chunk transformation code.
    """

    def __init__(
        self,
        loader: DocumentLoader | None = None,
        chunker: Chunker | None = None,
        chunks_directory: str | Path = "data/chunks",
    ) -> None:
        self.loader = loader or DocumentLoader()
        self.chunker = chunker or Chunker()
        self.chunks_directory = Path(chunks_directory)
        self.chunks_directory.mkdir(parents=True, exist_ok=True)

    def process_file(
        self,
        file_path: str | Path,
        filename: str | None = None,
        save_output: bool = True,
    ) -> ProcessingResult:
        """Run the document-to-chunk flow for a single file."""

        document = self.loader.load(str(file_path), filename=filename)
        chunks = self.chunker.chunk_document(document)
        stats = self.get_pipeline_stats(chunks)

        chunk_file_path: Path | None = None
        if save_output:
            chunk_file_path = self.save_chunks(document=document, chunks=chunks, stats=stats)

        return ProcessingResult(
            document=document,
            chunks=chunks,
            stats=stats,
            chunk_file_path=chunk_file_path,
        )

    def save_chunks(
        self,
        document: Document,
        chunks: list[Chunk],
        stats: PipelineStats,
    ) -> Path:
        """Serialize chunks to JSON for debugging and future embedding stages.

        Serialized chunks are useful in RAG debugging because they let us
        inspect the exact units that will later be embedded. Observability
        matters in AI systems: when retrieval quality is poor, we need readable
        intermediate artifacts to trace where degradation began.
        """

        output_path = self.chunks_directory / self._build_chunk_filename(document)
        payload = {
            "document": {
                "doc_id": document.doc_id,
                "filename": document.filename,
                "file_type": document.file_type,
                "created_at": document.created_at,
                "metadata": document.metadata,
            },
            "stats": asdict(stats),
            "chunks": [self._serialize_chunk(chunk) for chunk in chunks],
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

    def _build_chunk_filename(self, document: Document) -> str:
        """Build a deterministic, human-readable filename for saved chunks."""

        safe_stem = self._slugify_filename(Path(document.filename).stem)
        return f"{safe_stem}_{document.doc_id[:12]}_chunks.json"

    @staticmethod
    def _slugify_filename(filename_stem: str) -> str:
        """Convert a filename into a filesystem-friendly stem."""

        lowered = filename_stem.strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
        return slug or "document"


__all__ = ["PipelineStats", "ProcessingPipeline", "ProcessingResult"]
