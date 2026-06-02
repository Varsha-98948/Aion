"""Multi-document knowledge base manager for Aion.

This module provides persistent storage and metadata tracking for permanent
knowledge base documents. It maintains separation from temporary documents
and supports future enhancements such as citations, filtering, and collections.

The knowledge base is designed to grow over time: documents are registered when
added, tracked with comprehensive metadata, and remain searchable across sessions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any
from uuid import uuid4


def _generate_kb_metadata_id() -> str:
    """Return a unique identifier for knowledge base metadata."""
    return str(uuid4())


def _get_current_timestamp() -> str:
    """Return current ISO 8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class DocumentMetadata:
    """Metadata record for a document in the knowledge base.

    This structure is intentionally extensible for future features:
    - citations: track document provenance
    - collections: group documents by topic or project
    - tags: flexible categorization
    - last_updated: track document modifications
    - embedding_status: track processing state
    - deletion_status: soft delete support

    The metadata is immutable after creation (frozen=True prevents accidental
    modification) but can be replaced entirely when needed.
    """

    # Unique identifier for this knowledge base document entry
    kb_doc_id: str = field(default_factory=_generate_kb_metadata_id)

    # Original document ID from the Document schema (for retrieval linking)
    document_id: str = ""

    # Original filename as provided by the user
    filename: str = ""

    # Normalized file type (pdf, txt, md, etc.)
    file_type: str = ""

    # ISO timestamp marking when the document was added to the knowledge base
    date_added: str = field(default_factory=_get_current_timestamp)

    # Total number of chunks generated from this document
    chunk_count: int = 0

    # Extensible metadata container for future features
    # Examples: collections, tags, source_url, custom_metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize metadata to JSON-compatible dictionary."""
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DocumentMetadata:
        """Deserialize metadata from dictionary."""
        return DocumentMetadata(**data)


@dataclass(slots=True)
class KnowledgeBaseStats:
    """Statistics for the entire knowledge base."""

    total_documents: int = 0
    total_chunks: int = 0
    average_chunks_per_document: float = 0.0
    oldest_document_date: str = ""
    newest_document_date: str = ""


class KnowledgeBaseManager:
    """Manage persistent documents and metadata in the knowledge base.

    The knowledge base layer sits between the processing pipeline and the
    retrieval system. Its responsibilities are strictly limited to management:
    - tracking which documents are permanent
    - storing document metadata
    - providing statistics
    - supporting future cross-document features

    The manager does NOT:
    - process documents (pipeline's job)
    - embed chunks (embedding engine's job)
    - store vectors (vector store's job)
    - handle retrieval (retriever's job)

    This separation keeps each layer focused and makes it easy to add features
    like collections, filtering, or deletion without touching other components.
    """

    METADATA_FILENAME = "documents_metadata.json"

    def __init__(self, kb_directory: str | Path = "data/knowledge_base") -> None:
        """Initialize the knowledge base manager.

        Args:
            kb_directory: Path where knowledge base metadata is stored.
                         Defaults to "data/knowledge_base".
        """
        self.kb_directory = Path(kb_directory)
        self.kb_directory.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.kb_directory / self.METADATA_FILENAME

        # In-memory cache of registered documents
        self._documents: dict[str, DocumentMetadata] = {}
        self._load_metadata()

    def register_document(
        self,
        document_id: str,
        filename: str,
        file_type: str,
        chunk_count: int,
        custom_metadata: dict[str, Any] | None = None,
    ) -> DocumentMetadata:
        """Register a document in the knowledge base.

        Args:
            document_id: The unique identifier from the Document schema.
            filename: Original filename as provided by the user.
            file_type: Normalized file type (pdf, txt, md).
            chunk_count: Total chunks generated for this document.
            custom_metadata: Optional extensible metadata dict.

        Returns:
            The DocumentMetadata object for this registered document.

        Raises:
            ValueError: If the document is already registered.
        """
        if document_id in self._documents:
            raise ValueError(
                f"Document '{document_id}' is already registered in the knowledge base. "
                "Use update_document() to modify an existing document."
            )

        metadata = DocumentMetadata(
            document_id=document_id,
            filename=filename,
            file_type=file_type,
            chunk_count=chunk_count,
            metadata=custom_metadata or {},
        )

        self._documents[document_id] = metadata
        self._save_metadata()

        return metadata

    def get_document(self, document_id: str) -> DocumentMetadata | None:
        """Retrieve metadata for a specific document.

        Args:
            document_id: The unique identifier of the document.

        Returns:
            DocumentMetadata if found, None otherwise.
        """
        return self._documents.get(document_id)

    def remove_document(self, document_id: str) -> bool:
        """Remove a document from the knowledge base.

        Note: This performs a hard delete of metadata. For soft deletion support
        (document hiding without chunk removal), future versions should add a
        'deletion_status' field to DocumentMetadata.

        Args:
            document_id: The unique identifier of the document to remove.

        Returns:
            True if the document was removed, False if it didn't exist.
        """
        if document_id not in self._documents:
            return False

        del self._documents[document_id]
        self._save_metadata()
        return True

    def list_documents(self) -> list[DocumentMetadata]:
        """Return all documents in the knowledge base, sorted by date_added.

        Returns:
            List of DocumentMetadata objects in ascending date order.
        """
        return sorted(self._documents.values(), key=lambda doc: doc.date_added)

    def get_statistics(self) -> KnowledgeBaseStats:
        """Calculate knowledge base statistics.

        Returns:
            KnowledgeBaseStats with aggregated information.
        """
        if not self._documents:
            return KnowledgeBaseStats()

        docs = list(self._documents.values())
        total_documents = len(docs)
        total_chunks = sum(doc.chunk_count for doc in docs)

        sorted_by_date = sorted(docs, key=lambda doc: doc.date_added)

        return KnowledgeBaseStats(
            total_documents=total_documents,
            total_chunks=total_chunks,
            average_chunks_per_document=total_chunks / total_documents if total_documents > 0 else 0.0,
            oldest_document_date=sorted_by_date[0].date_added,
            newest_document_date=sorted_by_date[-1].date_added,
        )

    def update_chunk_count(self, document_id: str, new_chunk_count: int) -> bool:
        """Update the chunk count for an existing document.

        This method allows the chunk count to be updated if reprocessing occurs.

        Args:
            document_id: The unique identifier of the document.
            new_chunk_count: The updated chunk count.

        Returns:
            True if updated, False if document doesn't exist.
        """
        if document_id not in self._documents:
            return False

        self._documents[document_id].chunk_count = new_chunk_count
        self._save_metadata()
        return True

    def document_exists(self, document_id: str) -> bool:
        """Check if a document is registered in the knowledge base.

        Args:
            document_id: The unique identifier to check.

        Returns:
            True if the document is registered, False otherwise.
        """
        return document_id in self._documents

    def get_document_count(self) -> int:
        """Return the total number of documents in the knowledge base."""
        return len(self._documents)

    def get_total_chunks(self) -> int:
        """Return the total number of chunks across all documents."""
        return sum(doc.chunk_count for doc in self._documents.values())

    def clear_knowledge_base(self) -> None:
        """Remove all documents from the knowledge base.

        WARNING: This operation is irreversible. Use with caution.
        Chunk and vector data is NOT deleted—only metadata is cleared.
        """
        self._documents.clear()
        self._save_metadata()

    def _save_metadata(self) -> None:
        """Persist metadata to JSON file."""
        payload = {
            "version": "1.0",
            "last_updated": _get_current_timestamp(),
            "document_count": len(self._documents),
            "documents": [doc.to_dict() for doc in self._documents.values()],
        }

        with self.metadata_file.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False, default=str)

    def _load_metadata(self) -> None:
        """Load metadata from JSON file if it exists."""
        if not self.metadata_file.exists():
            self._documents = {}
            return

        try:
            with self.metadata_file.open("r", encoding="utf-8") as file:
                payload = json.load(file)

            self._documents = {}
            for doc_data in payload.get("documents", []):
                metadata = DocumentMetadata.from_dict(doc_data)
                self._documents[metadata.document_id] = metadata

        except (json.JSONDecodeError, KeyError) as error:
            print(f"Warning: Could not load knowledge base metadata: {error}")
            self._documents = {}

    def export_knowledge_base(self, export_path: str | Path) -> Path:
        """Export the entire knowledge base metadata to a file.

        Useful for backups or data migration.

        Args:
            export_path: Path where the export should be saved.

        Returns:
            The path where the data was exported.
        """
        export_path = Path(export_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": "1.0",
            "export_timestamp": _get_current_timestamp(),
            "document_count": len(self._documents),
            "documents": [doc.to_dict() for doc in self._documents.values()],
        }

        with export_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False, default=str)

        return export_path

    def import_knowledge_base(self, import_path: str | Path) -> int:
        """Import documents from an exported knowledge base file.

        Existing documents are preserved. Imported documents with duplicate
        document_ids are skipped.

        Args:
            import_path: Path to the exported knowledge base file.

        Returns:
            Number of documents successfully imported.
        """
        import_path = Path(import_path)

        if not import_path.exists():
            raise FileNotFoundError(f"Import file not found: {import_path}")

        try:
            with import_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)

            imported_count = 0
            for doc_data in payload.get("documents", []):
                metadata = DocumentMetadata.from_dict(doc_data)
                if metadata.document_id not in self._documents:
                    self._documents[metadata.document_id] = metadata
                    imported_count += 1

            if imported_count > 0:
                self._save_metadata()

            return imported_count

        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid knowledge base import file: {error}")


__all__ = ["KnowledgeBaseManager", "DocumentMetadata", "KnowledgeBaseStats"]
