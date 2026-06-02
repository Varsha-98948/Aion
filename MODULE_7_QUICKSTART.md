# Module 7 Quick Start Guide

## What's New

**Multi-Document Knowledge Base Support** — Aion now distinguishes between:
- **Temporary Documents**: Searchable only during this session
- **Knowledge Base Documents**: Registered, tracked, and searchable across all sessions

## Files Created/Modified

### ✅ Created
- `core/knowledge_base.py` — KnowledgeBaseManager for persistent document tracking
- `data/knowledge_base/` — Storage directory for KB metadata
- `MODULE_7_DOCUMENTATION.md` — Complete architecture & design guide
- `tests/test_knowledge_base_module7.py` — Validation test suite

### ✅ Modified
- `ui/app_streamlit.py` — Added upload modes and KB statistics display

## Quick Start

### 1. Via Streamlit UI (Recommended)

```bash
cd c:\Users\Asus\OneDrive\Desktop\Aion
.\venv\Scripts\Activate.ps1
streamlit run ui/app_streamlit.py
```

**In the UI:**
1. You'll see a new **"Upload Mode"** radio button with two options:
   - **Temporary** (default) — process & search only this session
   - **Add To Knowledge Base** — register & persist for future sessions

2. In the **sidebar**, you'll see new Knowledge Base section:
   - Document count & chunk statistics
   - Expandable list of all stored documents
   - Export/clear controls

**Try it:**
- Upload a PDF in "Temporary" mode → no KB registration
- Upload another PDF in "Add To Knowledge Base" mode → see it appear in KB list
- Refresh/restart Streamlit → the KB document persists, temporary one doesn't

### 2. Via Python Script

```python
from core.knowledge_base import KnowledgeBaseManager

# Initialize
kb = KnowledgeBaseManager()

# Register a document (after pipeline processes it)
metadata = kb.register_document(
    document_id="your-doc-id",
    filename="document.pdf",
    file_type="pdf",
    chunk_count=42,
    custom_metadata={
        "source": "important_docs",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2"
    }
)

# Get statistics
stats = kb.get_statistics()
print(f"KB has {stats.total_documents} documents, {stats.total_chunks} chunks")

# List all documents
for doc in kb.list_documents():
    print(f"- {doc.filename} ({doc.chunk_count} chunks)")

# Remove a document
kb.remove_document("your-doc-id")
```

### 3. Run Validation Tests

```bash
cd c:\Users\Asus\OneDrive\Desktop\Aion
.\venv\Scripts\Activate.ps1
python tests/test_knowledge_base_module7.py
```

Expected output: **✓ ALL TESTS PASSED**

## Data Structure

Knowledge base metadata is stored in `data/knowledge_base/documents_metadata.json`:

```json
{
  "version": "1.0",
  "last_updated": "2026-06-02T10:30:45...",
  "document_count": 2,
  "documents": [
    {
      "kb_doc_id": "550e8400-e29b-41d4-a716-...",
      "document_id": "the-doc-id",
      "filename": "research_paper.pdf",
      "file_type": "pdf",
      "date_added": "2026-06-01T09:15:30...",
      "chunk_count": 47,
      "metadata": {...}
    }
  ]
}
```

## Key Differences: Temporary vs. Knowledge Base

| Feature | Temporary | Knowledge Base |
|---------|-----------|----------------|
| **Persistence** | Session only | Across all sessions |
| **Registration** | No metadata stored | Registered with metadata |
| **Retrieval** | Current session only | Available in future sessions |
| **Use Case** | Quick tests | Important reference docs |
| **Data Location** | FAISS index in `data/indexes/` | Metadata in `data/knowledge_base/` |

## Architecture Highlights

The implementation follows **clean architecture** principles:

```
┌──────────────────────┐
│    Streamlit UI      │  ← User selects upload mode
└──────────┬───────────┘
           │
    ┌──────▼──────┐
    │  Pipeline   │  ← Processes document (unchanged)
    └──────┬──────┘
           │
┌──────────▼──────────────────┐
│  KnowledgeBaseManager (NEW) │  ← Manages metadata ONLY
│  - Register documents       │     (No coupling to other components)
│  - Track metadata           │
│  - Persist to JSON          │
└─────────────────────────────┘
```

**Why this design?**
- Each component has ONE responsibility
- Easy to test independently
- Easy to add future features without refactoring
- Prepared for cross-document retrieval, collections, citations, etc.

## What's NOT Included (Future Modules)

These features are PLANNED but NOT YET IMPLEMENTED:

- ❌ Cross-document semantic search (Module 8)
- ❌ Document filtering by collection/tags (Module 9)
- ❌ Citation tracking (Module 10)
- ❌ Semantic memory scoring (Module 11)
- ❌ Remote knowledge base sync (Module 12)

**But the architecture is ready!** The metadata is extensible to support all these features.

## Troubleshooting

### "Document already registered"
You're trying to register the same `document_id` twice. Either:
1. Use a different document ID
2. Call `kb.remove_document()` first
3. Update chunk count with `kb.update_chunk_count()`

### Knowledge base not persisting
Check:
1. `data/knowledge_base/documents_metadata.json` exists (auto-created)
2. File permissions allow writing
3. Upload mode is "Add To Knowledge Base"

### Sidebar KB stats showing 0
Either:
1. No documents have been registered yet (add one!)
2. You've selected "Temporary" mode (won't register)

### Tests fail
Run with full traceback:
```bash
python tests/test_knowledge_base_module7.py 2>&1
```

## For Deep Dive

📖 Read `MODULE_7_DOCUMENTATION.md` for:
- Complete architecture explanation
- JSON schema details
- Example code
- Design rationale
- Future enhancement roadmap

## Next Steps

**Developers:** 
- Review `core/knowledge_base.py` source code
- Check `MODULE_7_DOCUMENTATION.md` for architecture details
- Run validation tests
- Try the UI in both upload modes

**Data:** 
- Documents are stored in `data/uploads/`
- Metadata tracked in `data/knowledge_base/documents_metadata.json`
- Chunks in `data/chunks/`
- Vectors in `data/vectors/`
- FAISS indexes in `data/indexes/`

**Questions?**
See `MODULE_7_DOCUMENTATION.md` FAQ or run validation tests.

---

**Status:** ✅ Module 7 Implementation Complete  
**Date:** June 2, 2026  
**Components:** KnowledgeBaseManager, Streamlit UI Integration, 100+ lines docs
