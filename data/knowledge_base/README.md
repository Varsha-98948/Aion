# Knowledge Base Directory

This directory contains metadata for Aion's persistent multi-document knowledge base.

## Structure

- `documents_metadata.json` - Registry of all documents in the knowledge base
- `export_backup.json` - Optional export backups created by users

## Document Metadata Schema

Each registered document contains:

```json
{
  "kb_doc_id": "unique-kb-identifier",
  "document_id": "document-schema-id",
  "filename": "original_filename.pdf",
  "file_type": "pdf",
  "date_added": "2026-06-02T10:30:45.123456+00:00",
  "chunk_count": 42,
  "metadata": {
    "source_path": "data/uploads/...",
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    "chunk_config": {
      "chunk_size": 512,
      "overlap": 50
    },
    "notes": "Custom metadata for future features"
  }
}
```

## Features

- **Registration**: Documents are registered when uploaded in "Add To Knowledge Base" mode
- **Persistence**: Metadata survives across sessions
- **Statistics**: Track document count, chunk count, and dates
- **Export/Import**: Backup and restore knowledge base metadata
- **Future-Ready**: Extensible metadata for citations, collections, tags, and more

## Management

Use the Streamlit UI sidebar to:
- View document count and statistics
- List all registered documents
- Export knowledge base metadata
- Clear the knowledge base (if needed)

## Queries

Knowledge base documents remain searchable alongside temporary documents. Future modules will support:
- Cross-document semantic search
- Document filtering
- Collection-based retrieval
- Citation tracking
