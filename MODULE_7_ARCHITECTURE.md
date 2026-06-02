# Module 7 Architecture Diagrams

## System Overview

### Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AION SYSTEM FLOW                             │
└─────────────────────────────────────────────────────────────────────┘

                            ┌──────────────┐
                            │  User Input  │
                            └──────┬───────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Streamlit UI              │
                    │  - File upload              │
                    │  - Mode selector (NEW)      │
                    │  - KB statistics (NEW)      │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Upload Mode Decision      │
                    └────────────┬────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
        ┌────────▼─────────┐          ┌─────────▼────────┐
        │   TEMPORARY      │          │  ADD TO KB       │
        │   MODE           │          │  MODE (NEW)      │
        └────────┬─────────┘          └─────────┬────────┘
                 │                               │
      ┌──────────▼──────────┐         ┌──────────▼──────────────┐
      │ Pipeline.process    │         │ Pipeline.process        │
      │ - Load document     │         │ - Load document         │
      │ - Chunk text        │         │ - Chunk text            │
      │ - Generate embeddings       │ - Generate embeddings   │
      │ - Build FAISS index │         │ - Build FAISS index     │
      └──────────┬──────────┘         └──────────┬──────────────┘
                 │                               │
      ┌──────────▼──────────┐         ┌──────────▼──────────────┐
      │ Searchable this     │         │ KnowledgeBaseManager    │
      │ session ONLY        │         │ .register_document() ◄──┼─── NEW
      │                     │         │ - Store metadata        │
      │ Session ends →      │         │ - Persist to JSON       │
      │ Data lost           │         │ - Update stats          │
      └─────────────────────┘         └──────────┬──────────────┘
                                                  │
                                       ┌──────────▼──────────────┐
                                       │ PERSISTENT              │
                                       │ data/knowledge_base/    │
                                       │ documents_metadata.json │
                                       └─────────────────────────┘
                                                  │
                                       ┌──────────▼──────────────┐
                                       │ Searchable this session │
                                       │ + Future sessions       │
                                       │                         │
                                       │ Session ends →          │
                                       │ Data PERSISTS           │
                                       └─────────────────────────┘
```

## Component Interaction Diagram

```
┌───────────────────────────────────────────────────────────────┐
│                   AION COMPONENT ARCHITECTURE                 │
└───────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────┐
                    │   Streamlit UI          │
                    │  (ui/app_streamlit.py)  │
                    └──────────────┬──────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  ProcessingPipeline         │
                    │  (core/pipeline.py)         │
                    │  - Orchestrates flow        │
                    │  - Calls all components     │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────┴─────────────────────┐
                    │                                    │
        ┌───────────▼──────────┐      ┌────────────────▼──────┐
        │  DocumentLoader      │      │  EmbeddingEngine      │
        │  (core/document_...  │      │  (core/embedder.py)   │
        │  - Load files        │      │  - Generate vectors   │
        │  - Extract text      │      │  - Normalize vecs     │
        └───────────┬──────────┘      └────────────────┬──────┘
                    │                                  │
        ┌───────────▼──────────┐      ┌────────────────▼──────┐
        │  Chunker             │      │  VectorStore          │
        │  (core/chunker.py)   │      │  (core/vector_...     │
        │  - Split text        │      │  - FAISS index        │
        │  - Create chunks     │      │  - Semantic search    │
        └───────────┬──────────┘      └────────────────┬──────┘
                    │                                  │
                    │         ┌──────────────────────┐ │
                    │         │  Retriever           │ │
                    │         │  (core/retriever.py) │ │
                    └────────►│  - Query embedding   │ │
                              │  - Return top-k      │ │
                              └──────────────────────┘ │
                                                       │
                              ┌────────────────────────▼────┐
                              │  RAGPipeline                 │
                              │  (core/rag_pipeline.py)      │
                              │  - Build prompt              │
                              │  - Call Ollama               │
                              │  - Generate response         │
                              └──────────────────────────────┘

                    ┌──────────────────────────┐
                    │  KnowledgeBaseManager    │◄── NEW
                    │  (core/knowledge_base.py)│
                    │  - Register documents    │
                    │  - Track metadata        │
                    │  - Persist to JSON       │
                    │                          │
                    │  NO COUPLING to:         │
                    │  ✓ Pipeline              │
                    │  ✓ VectorStore           │
                    │  ✓ Retriever             │
                    │  ✓ EmbeddingEngine       │
                    └──────────────────────────┘
                              │
                              │ (read metadata only)
                              │
                    ┌─────────▼──────────────┐
                    │  data/knowledge_base/  │
                    │  documents_metadata.json
                    └────────────────────────┘
```

## Knowledge Base Manager - Detailed Operations

```
┌─────────────────────────────────────────────────────────────┐
│         KNOWLEDGE BASE MANAGER OPERATIONS                   │
└─────────────────────────────────────────────────────────────┘

OPERATION 1: Register Document
─────────────────────────────────
    Input: document_id, filename, file_type, chunk_count, metadata
                              │
                              ▼
                    ┌─────────────────────┐
                    │ Check if exists?    │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼────────────┐
                    │ No? Create record    │
                    └─────────┬────────────┘
                              │
                    ┌─────────▼────────────────┐
                    │ Add to in-memory cache   │
                    └─────────┬────────────────┘
                              │
                    ┌─────────▼────────────────┐
                    │ Persist to JSON file     │
                    └─────────┬────────────────┘
                              │
                    Output: DocumentMetadata


OPERATION 2: Get Statistics
──────────────────────────────
    Input: (none, queries in-memory cache)
                              │
                              ▼
                    ┌──────────────────────┐
                    │ Count documents      │
                    │ Sum chunks           │
                    │ Find date range      │
                    │ Calculate averages   │
                    └──────────┬───────────┘
                              │
                    Output: KnowledgeBaseStats


OPERATION 3: List Documents
────────────────────────────
    Input: (none, queries in-memory cache)
                              │
                              ▼
                    ┌──────────────────────┐
                    │ Get all documents    │
                    │ Sort by date_added   │
                    └──────────┬───────────┘
                              │
                    Output: list[DocumentMetadata]


OPERATION 4: Persist Metadata
─────────────────────────────
    In-Memory Cache
    (documents dict)
                              │
                              ▼
                    ┌──────────────────────────┐
                    │ Serialize to JSON format │
                    └──────────┬───────────────┘
                              │
                              ▼
                    ┌──────────────────────────────────┐
                    │ Write to documents_metadata.json  │
                    │ (UTF-8, 2-space indent, sorted)  │
                    └──────────────────────────────────┘
```

## Data Persistence Format

```
BEFORE REGISTRATION:
────────────────────
    (No file exists)


AFTER FIRST REGISTRATION:
─────────────────────────

data/knowledge_base/documents_metadata.json
│
└─ {
     "version": "1.0",
     "last_updated": "2026-06-02T10:30:45.123456+00:00",
     "document_count": 1,
     "documents": [
       {
         "kb_doc_id": "550e8400-e29b-41d4-a716-446655440000",
         "document_id": "8af8c4bf7f-doc-id",
         "filename": "document.pdf",
         "file_type": "pdf",
         "date_added": "2026-06-02T10:30:45.000000+00:00",
         "chunk_count": 42,
         "metadata": {
           "source_path": "data/uploads/document.pdf",
           "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
           "chunk_config": {
             "chunk_size": 512,
             "overlap": 50
           }
         }
       }
     ]
   }


AFTER SECOND REGISTRATION:
──────────────────────────
   Same file structure, now with 2 documents in "documents" array


MEMORY DURING SESSION:
─────────────────────
   _documents = {
     "8af8c4bf7f-doc-id": DocumentMetadata(...),
     "9bf9d5cg8g-doc-id": DocumentMetadata(...),
   }
   
   (Allows O(1) lookups and updates)
```

## Retrieval Preparation (Future)

```
CURRENT STATE (Module 7):
─────────────────────────
    
    ┌──────────────────┐
    │ Document Uploaded│
    │  in KB Mode      │
    └────────┬─────────┘
             │
    ┌────────▼─────────────┐
    │ KnowledgeBaseManager │
    │ Register metadata    │
    └────────┬─────────────┘
             │
    ┌────────▼──────────────┐
    │ Metadata persisted    │
    │ (JSON file)           │
    └────────┬──────────────┘
             │
    ┌────────▼──────────────┐
    │ Document searchable   │
    │ via Retriever (FAISS) │
    └───────────────────────┘


FUTURE STATE (Module 8+):
─────────────────────────

    ┌──────────────────┐
    │ Multiple docs    │
    │  in KB           │
    └────────┬─────────┘
             │
    ┌────────▼──────────────────────┐
    │ Retriever.retrieve()           │
    │ - Load KB metadata             │
    │ - Search ACROSS all documents  │
    │ - Rank results                 │
    │ - Include document source      │
    └────────┬──────────────────────┘
             │
    ┌────────▼──────────────────────┐
    │ Results with citations         │
    │ - Which document?              │
    │ - Which chunk?                 │
    │ - Similarity score             │
    └────────────────────────────────┘
```

## Session Lifecycle

```
SESSION 1: Upload & Register
──────────────────────────────
    1. Start Streamlit
    2. Upload doc1.pdf in "Add to KB" mode
       → Registers doc1 in KB ✓
    3. Upload doc2.txt in "Temporary" mode
       → NO registration
    4. Close Streamlit
    
    RESULT: doc1 persists, doc2 lost


SESSION 2: KB Persists
─────────────────────
    1. Start Streamlit
    2. Initialize KnowledgeBaseManager
       → Loads metadata.json
       → doc1 is available ✓
       → doc2 is gone (expected)
    3. KB sidebar shows: "1 document, X chunks"
    4. Can search doc1 ✓
    5. Close Streamlit
    
    RESULT: doc1 still available next session


BATCH OPERATION: Export/Import
──────────────────────────────
    Session 1:
    - Register doc1, doc2, doc3
    - Click "Export" → backup_2026_06_02.json
    
    Session 2:
    - Load new Aion setup
    - Click "Import" → select backup_2026_06_02.json
    - All 3 documents restored ✓
```

## Error Handling Flow

```
DUPLICATE REGISTRATION:
──────────────────────

    kb.register_document(
        document_id="doc-123",
        ...
    )
    
    First call: ✓ Success, registered
    
    Second call with same doc_id:
        │
        ├─ Check: is doc_id in _documents?
        │   └─ YES → Raise ValueError
        │
        └─ Error message:
             "Document 'doc-123' is already registered in 
              the knowledge base. Use update_document() to 
              modify an existing document."


UPDATE NONEXISTENT DOCUMENT:
────────────────────────────

    kb.update_chunk_count("nonexistent-id", 100)
    
        │
        ├─ Check: is doc_id in _documents?
        │   └─ NO → Return False
        │
        └─ No error raised, just returns False


REMOVE NONEXISTENT DOCUMENT:
────────────────────────────

    kb.remove_document("nonexistent-id")
    
        │
        ├─ Check: is doc_id in _documents?
        │   └─ NO → Return False
        │
        └─ No error raised, just returns False
```

---

**Visual Legend:**
```
┌─────┐  = Component or data store
│     │
└─────┘

   ▼   = Flow direction

◄──┄   = Data read (from)

   →   = Data write (to)

   ✓   = Success

   ✗   = Error/Failure

(NEW) = Added in Module 7
```

See `MODULE_7_DOCUMENTATION.md` for detailed text explanations.
