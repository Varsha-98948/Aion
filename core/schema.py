"""Shared schema objects for Aion's document ingestion pipeline.

This module defines the canonical internal representation for source documents
before they are transformed into chunks, embeddings, or search index records.
Keeping one consistent schema at the ingestion boundary makes it easier to
support many file types (PDF, TXT, MD, and more) without rewriting downstream
pipeline logic for each format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _generate_doc_id() -> str:
    """Return a unique identifier for each ingested document."""
    return str(uuid4())


def _generate_created_at() -> str:
    """Return an ISO 8601 timestamp for when the document entered the system."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Document:
    """Standard internal representation for all ingested document types.

    A unified schema lets the ingestion pipeline normalize PDFs, text files,
    markdown files, and future formats into one predictable object. Downstream
    systems such as chunkers, embedders, retrievers, and metadata filters can
    then work against a single interface instead of format-specific loaders.

    The flexible ``metadata`` field is intentionally left open-ended so we can
    attach future pipeline information such as source path, author, page count,
    chunking hints, embedding status, or custom tags without changing the core
    document structure.
    """

    # Stable internal ID used to track a document across parsing, chunking,
    # embedding, storage, and retrieval steps.
    doc_id: str = field(default_factory=_generate_doc_id)

    # Original file name as seen by the user or loader.
    filename: str = ""

    # Normalized file type label such as "pdf", "txt", or "md".
    file_type: str = ""

    # Plain-text content extracted from the source file. Keeping this unified
    # text field allows later chunking and embedding stages to remain generic.
    content: str = ""

    # Extensible container for extra ingestion data. A default_factory avoids
    # sharing mutable state between instances.
    metadata: dict[str, Any] = field(default_factory=dict)

    # ISO timestamp marking when the document object was created in Aion.
    created_at: str = field(default_factory=_generate_created_at)
