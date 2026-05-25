"""Document chunking pipeline for Aion.

This module turns normalized ``Document`` objects into retrieval-ready
``Chunk`` objects. In a RAG architecture, chunking is the preparation stage
between ingestion and embeddings: it converts long source text into smaller
semantic units that are better suited for SentenceTransformers, FAISS indexing,
and future memory retrieval workflows.

Example usage:
    >>> from core.chunker import Chunker
    >>> from core.schema import Document
    >>> document = Document(
    ...     filename="notes.txt",
    ...     file_type="txt",
    ...     content=(
    ...         "Aion is a local-first AI system. It values privacy and modularity.\\n\\n"
    ...         "Chunking prepares text for embeddings. Overlap preserves context."
    ...     ),
    ... )
    >>> chunker = Chunker(chunk_size=120, overlap=40)
    >>> chunks = chunker.chunk_document(document)
    >>> chunks[0].text
    'Aion is a local-first AI system. It values privacy and modularity.'
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .chunk_models import Chunk
from .chunk_utils import (
    build_overlap_segments,
    clean_text_for_chunking,
    group_sentences_by_size,
    is_valid_chunk_text,
    join_segments,
    split_into_paragraphs,
    split_into_sentences,
)
from .schema import Document


@dataclass(slots=True)
class _SemanticUnit:
    """Internal text unit used to preserve structure during chunk assembly."""

    text: str
    prefix: str


@dataclass(slots=True)
class _ChunkWindow:
    """Internal chunk window that keeps text plus source-unit boundaries."""

    start_unit_index: int
    end_unit_index: int
    text: str


class Chunker:
    """Transform normalized documents into semantic chunks.

    The chunker exists so the rest of the RAG pipeline can work with retrievable
    units instead of entire documents. Embedding a whole document usually makes
    retrieval less precise because many unrelated topics are compressed into one
    vector. Chunking trades some global context for much better local retrieval.

    Chunk size is configurable because there is always a tradeoff:
    - Smaller chunks improve retrieval precision but may lose context.
    - Larger chunks preserve context but may mix multiple ideas together.

    Overlap is configurable because neighboring chunks often need a shared
    bridge of context. A small overlap helps retrieval and answer grounding when
    a relevant concept sits near a chunk boundary.
    """

    def __init__(self, chunk_size: int = 800, overlap: int = 120) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero.")
        if overlap < 0:
            raise ValueError("overlap cannot be negative.")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size.")

        self.chunk_size = chunk_size
        self.overlap = overlap
        # Tiny chunks are usually poor retrieval units. This threshold gives the
        # assembly logic a chance to keep nearby context together.
        self.min_chunk_size = max(1, chunk_size // 2)

    def chunk_document(self, document: Document) -> list[Chunk]:
        """Convert one ``Document`` into an ordered list of ``Chunk`` objects."""

        cleaned_text = clean_text_for_chunking(document.content)
        if not cleaned_text:
            return []

        semantic_units = self._build_semantic_units(cleaned_text)
        chunk_windows = self._assemble_chunk_windows(semantic_units)

        chunks: list[Chunk] = []
        for chunk_index, chunk_window in enumerate(chunk_windows):
            chunk_id = self._build_chunk_id(
                document_id=document.doc_id,
                chunk_index=chunk_index,
                chunk_text=chunk_window.text,
            )
            metadata = self._build_chunk_metadata(document=document, chunk_window=chunk_window)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=document.doc_id,
                    text=chunk_window.text,
                    chunk_index=chunk_index,
                    metadata=metadata,
                )
            )

        return chunks

    def _build_semantic_units(self, text: str) -> list[_SemanticUnit]:
        """Create ordered semantic units from paragraphs and sentences.

        We prefer paragraph boundaries first because they often align with a
        complete idea. If a paragraph is too large, we recursively fall back to
        sentence grouping so the output remains embedding-friendly.
        """

        paragraphs = split_into_paragraphs(text)
        semantic_units: list[_SemanticUnit] = []

        for paragraph_index, paragraph in enumerate(paragraphs):
            is_new_paragraph = paragraph_index > 0
            prefix_for_first_unit = "\n\n" if is_new_paragraph else ""

            if len(paragraph) <= self.chunk_size:
                semantic_units.append(_SemanticUnit(text=paragraph, prefix=prefix_for_first_unit))
                continue

            sentence_groups = self._split_large_paragraph(paragraph)
            for sentence_group_index, sentence_group in enumerate(sentence_groups):
                prefix = prefix_for_first_unit if sentence_group_index == 0 else " "
                semantic_units.append(_SemanticUnit(text=sentence_group, prefix=prefix))

        return semantic_units

    def _split_large_paragraph(self, paragraph: str) -> list[str]:
        """Break an oversized paragraph into sentence-aware units."""

        sentences = split_into_sentences(paragraph)
        if not sentences:
            return [paragraph]

        sentence_groups = group_sentences_by_size(sentences, max_length=self.chunk_size)
        return [group for group in sentence_groups if group.strip()]

    def _assemble_chunk_windows(self, semantic_units: list[_SemanticUnit]) -> list[_ChunkWindow]:
        """Assemble final chunk windows with overlap-aware progression."""

        if not semantic_units:
            return []

        chunk_windows: list[_ChunkWindow] = []
        start_index = 0

        while start_index < len(semantic_units):
            current_units, next_index = self._collect_chunk_units(semantic_units, start_index)
            chunk_text = self._join_units(current_units)

            should_keep_chunk = (
                is_valid_chunk_text(chunk_text, min_length=self.min_chunk_size)
                or len(current_units) == 1
                or next_index >= len(semantic_units)
            )
            if should_keep_chunk and is_valid_chunk_text(chunk_text):
                chunk_windows.append(
                    _ChunkWindow(
                        start_unit_index=start_index,
                        end_unit_index=next_index,
                        text=chunk_text,
                    )
                )

            if next_index >= len(semantic_units):
                break

            next_start = self._calculate_next_start(start_index, current_units)
            if next_start <= start_index:
                start_index = next_index
                continue

            start_index = next_start

        return self._merge_small_chunk_windows(chunk_windows)

    def _collect_chunk_units(
        self,
        semantic_units: list[_SemanticUnit],
        start_index: int,
    ) -> tuple[list[_SemanticUnit], int]:
        """Collect as many neighboring semantic units as fit the chunk target."""

        collected_units: list[_SemanticUnit] = []
        next_index = start_index

        while next_index < len(semantic_units):
            candidate_units = collected_units + [semantic_units[next_index]]
            candidate_text = self._join_units(candidate_units)

            if (
                collected_units
                and len(candidate_text) > self.chunk_size
                and len(self._join_units(collected_units)) >= self.min_chunk_size
            ):
                break

            collected_units = candidate_units
            next_index += 1

        if not collected_units:
            collected_units = [semantic_units[start_index]]
            next_index = start_index + 1

        return collected_units, next_index

    def _calculate_next_start(self, start_index: int, current_units: list[_SemanticUnit]) -> int:
        """Calculate where the next chunk should begin after overlap."""

        if self.overlap <= 0 or len(current_units) <= 1:
            return start_index + len(current_units)

        overlap_segments = build_overlap_segments(
            [unit.text for unit in current_units],
            target_overlap=self.overlap,
            separator=" ",
        )
        overlap_count = min(len(overlap_segments), len(current_units) - 1)

        return start_index + len(current_units) - overlap_count

    def _join_units(self, units: list[_SemanticUnit]) -> str:
        """Join internal semantic units into final chunk text."""

        if not units:
            return ""

        parts: list[str] = [units[0].text]
        for unit in units[1:]:
            parts.append(f"{unit.prefix}{unit.text}")

        return join_segments(parts, separator="")

    def _merge_small_chunk_windows(self, chunk_windows: list[_ChunkWindow]) -> list[_ChunkWindow]:
        """Merge safe tiny chunks back into the previous chunk when helpful."""

        if len(chunk_windows) < 2:
            return chunk_windows

        merged_windows: list[_ChunkWindow] = [chunk_windows[0]]

        for window in chunk_windows[1:]:
            previous_window = merged_windows[-1]
            has_overlap_with_previous = window.start_unit_index < previous_window.end_unit_index

            if len(window.text) < self.min_chunk_size and not has_overlap_with_previous:
                merged_windows[-1] = _ChunkWindow(
                    start_unit_index=previous_window.start_unit_index,
                    end_unit_index=window.end_unit_index,
                    text=join_segments([previous_window.text, window.text], separator="\n\n"),
                )
                continue

            merged_windows.append(window)

        return merged_windows

    def _build_chunk_id(self, document_id: str, chunk_index: int, chunk_text: str) -> str:
        """Build a deterministic chunk ID from stable chunk inputs."""

        digest_input = f"{document_id}:{chunk_index}:{chunk_text}".encode("utf-8")
        digest = hashlib.sha1(digest_input).hexdigest()
        return f"{document_id}-chunk-{chunk_index:04d}-{digest[:12]}"

    def _build_chunk_metadata(
        self,
        document: Document,
        chunk_window: _ChunkWindow,
    ) -> dict[str, Any]:
        """Create retrieval-friendly metadata for a chunk.

        Chunk metadata matters because vector similarity alone is not enough for
        a complete retrieval system. We often need to surface file names, source
        types, ordering information, or future page references alongside the
        chunk text so answers can be grounded back to the original document.
        """

        source_metadata = dict(document.metadata)
        return {
            "source_filename": document.filename,
            "source_file_type": document.file_type,
            "document_created_at": document.created_at,
            "character_count": len(chunk_window.text),
            "word_count": len(chunk_window.text.split()),
            "chunk_size": self.chunk_size,
            "overlap": self.overlap,
            "start_unit_index": chunk_window.start_unit_index,
            "end_unit_index": chunk_window.end_unit_index - 1,
            "source_metadata": source_metadata,
        }


__all__ = ["Chunker"]
