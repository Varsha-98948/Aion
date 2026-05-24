"""Text file parsing utilities for Aion's ingestion pipeline.

Even simple text formats benefit from a parser layer in AI systems because the
rest of the pipeline should not need to care whether content came from a PDF,
markdown note, or plain text file. This module normalizes .txt and .md inputs
into the same high-level structure used elsewhere in Aion before chunking and
embedding begin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict


class TextMetadata(TypedDict):
    """Metadata captured during plain text and markdown extraction."""

    character_count: int
    file_type: Literal["txt", "md"]


class TextExtractionResult(TypedDict):
    """Normalized extraction result compatible with the Document schema."""

    content: str
    metadata: TextMetadata


def _normalize_text_content(raw_text: str) -> str:
    """Clean text while preserving its original high-level structure.

    Preprocessing consistency matters in RAG pipelines because chunkers and
    embedding models are sensitive to formatting noise. We normalize line
    endings and trim unnecessary whitespace so retrieval quality is more stable
    across documents, while still preserving paragraph and heading boundaries.
    """

    normalized_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [line.rstrip() for line in normalized_text.split("\n")]
    return "\n".join(normalized_lines).strip()


def extract_text_file(file_path: str) -> TextExtractionResult:
    """Extract normalized text from a .txt or .md file.

    Unifying every source format into a single structure gives downstream
    chunking and embedding systems one predictable interface. Raw files on disk
    cannot be embedded directly; they first need to be decoded, cleaned, and
    represented as normalized text plus metadata.
    """

    path = Path(file_path)
    file_type = path.suffix.lower().lstrip(".")

    if file_type not in {"txt", "md"}:
        raise ValueError(
            f"Unsupported text file type: '{path.suffix}'. Expected .txt or .md."
        )

    with path.open("r", encoding="utf-8", errors="replace") as file:
        raw_text = file.read()

    content = _normalize_text_content(raw_text)

    return {
        "content": content,
        "metadata": {
            "character_count": len(content),
            "file_type": file_type,
        },
    }
