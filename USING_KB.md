# Using Aion's Knowledge Base (Phase 2)

## Quick Start - You're Ready Now! 🚀

### First Time Users
1. Open Aion
2. Upload your first document in **"Add To Knowledge Base"** mode
3. Wait for processing
4. Ask Aion questions about it
5. **Next time you open Aion, the document is already there!**

### Returning Users with KB Documents
1. Open Aion
2. **You can immediately ask Aion questions** (no upload needed!)
3. KB stats show in sidebar
4. Click "Ask Aion" section
5. Type your question
6. Get answers from your persisted documents

### Adding More Documents
1. Open Aion (existing KB already loaded)
2. Scroll to **"Add Document to Knowledge Base"**
3. Upload new document
4. It auto-registers to KB
5. Next time you load, new doc is ready to query

---

## How It Works

### Persistent Knowledge Base
```
Before (Phase 1):
- Upload → Process → Query → Close → Lost on refresh

After (Phase 2):
- Upload → Register → Persist → Query → Close →
  Reopen → Query Again! (no re-upload needed)
```

### Upload Modes
| Mode | When | Result |
|------|------|--------|
| **Temporary** | Testing/quick questions | Searchable this session only |
| **Add To KB** | Important documents | Persistent, searchable always |

### What Happens on Startup
1. Aion loads KB metadata from disk
2. Finds latest document's FAISS index
3. Auto-loads the index into memory
4. Shows "Ask Aion" section immediately
5. You can start querying right away!

---

## Commands You'll See

### On First Open (Empty KB)
```
⚠️ Your Knowledge Base is empty
📚 Upload your first document to get started
```
→ Upload a document in "Add To Knowledge Base" mode

### On Return Visit (With KB)
```
📚 Knowledge Base
  Documents: 2
  Total Chunks: 95
  
📖 Stored Documents (expandable)
  1. document1.pdf (45 chunks) - Added 2026-06-01
  2. document2.md (50 chunks) - Added 2026-06-02
```
→ Scroll down to "Ask Aion" section
→ Start asking questions immediately!

### After Uploading New Document
```
✓ Document registered in Knowledge Base (ID: abc123...)
📚 Knowledge Base stats updated
  Documents: 3
  Total Chunks: 142
```
→ Can query new document in same session
→ Persists for next session automatically

---

## Example Workflow

### Session 1: Build Your KB
```
Step 1: Open Aion
  → KB is empty, see upload section

Step 2: Upload "research_notes.pdf"
  → Select "Add To Knowledge Base"
  → Process completes
  → Registered to KB ✓

Step 3: Upload "technical_guide.md"
  → Select "Add To Knowledge Base"
  → Process completes
  → Registered to KB ✓

Step 4: Ask Aion
  → Query → Get answers from both docs
  → Session ends
```

### Session 2: Use Your KB
```
Step 1: Open Aion
  → KB loads automatically
  → See: "Documents: 2, Chunks: 95"

Step 2: Ask Aion (immediately!)
  → No upload needed!
  → Query: "What are the key concepts?"
  → Get answers from your docs

Step 3: Optional - Add More
  → Upload new document if needed
  → Adds to existing KB

Step 4: Close
  → Everything persists
```

---

## Where Things Are Stored

### Your Documents
- Chunks: `data/chunks/`
- Vectors: `data/vectors/`
- FAISS Indexes: `data/indexes/`

### KB Metadata
- **Knowledge Base:** `data/knowledge_base/documents_metadata.json`
- Shows which documents you've registered

### Conversation History
- **Memory:** `data/memory/{session_id}.json`
- Keeps chat history within Aion

---

## Tips & Tricks

### ✨ Pro Tips
1. **Use "Add To KB" for important docs** → They persist
2. **Use "Temporary" for testing** → Try things without clutter
3. **Check sidebar stats** → Know how much content you have
4. **Expand "Stored Documents"** → See all your docs with dates
5. **Use meaningful file names** → Helps identify docs later

### 🔧 Maintenance
- **Export KB:** Sidebar → "Export Knowledge Base" → Backup your metadata
- **View all docs:** Sidebar → "Stored Documents" (expandable)
- **Check KB size:** Sidebar metrics show count and chunks

### ⚡ Fast Access
1. Open Aion
2. See KB stats immediately
3. Scroll to "Ask Aion"
4. Start querying (no upload!)

---

## Troubleshooting

### Q: "Ask Aion" section not showing
**A:** Your KB is empty. Upload your first document.

### Q: Can't query after uploading
**A:** Make sure you selected "Add To Knowledge Base" mode.

### Q: Document not showing in sidebar
**A:** Try refreshing Streamlit (Ctrl+R or rerun).

### Q: Need to query a specific document
**A:** Currently queries all KB docs. Future versions will have filtering.

### Q: How do I delete a document?
**A:** Sidebar → Knowledge Base Controls → Clear Knowledge Base
  *(Note: Use Export first to backup!)*

### Q: My KB disappeared!
**A:** Check if `data/knowledge_base/documents_metadata.json` exists.
   Files might have been deleted. Use export backup if available.

---

## What's New in Phase 2

✅ **KB-First Startup**
- KB loads automatically on app start
- No need to upload again

✅ **Immediate Querying**
- Ask Aion section shows right away
- Query persisted documents instantly

✅ **Better UX**
- Conditional upload section
- Warnings only when KB empty
- Clear document listing

✅ **Same Performance**
- Query same documents as before
- Just without redundant uploads
- Faster interactions overall

---

## Under the Hood (Developers)

### What Changed
1. `render_app()` - Refactored for KB-first flow
2. Added `_find_latest_vector_index()` - Auto-find latest doc
3. Added `_load_vector_store_from_index()` - Load from disk
4. Added `_render_ask_aion_from_kb()` - Query KB docs

### What Didn't Change
- Vector store loading ✓ (already worked)
- Retriever logic ✓ (unchanged)
- RAG pipeline ✓ (unchanged)
- Ollama integration ✓ (unchanged)
- Upload functionality ✓ (unchanged)
- Architecture ✓ (preserved)

### Zero Breaking Changes
- Backward compatible ✓
- All KB data safe ✓
- Upload still works ✓
- Conversations preserved ✓

---

## Future Enhancements

Coming soon:
- 📚 Query multiple KB docs at once (cross-document)
- 🏷️ Filter documents by collection/tags
- 📖 See which document provided each answer
- 📊 Document importance scoring
- 🔗 Citation tracking

---

## Summary

**Aion is now a fully functional persistent knowledge base system!**

- ✅ **Persistent:** Documents stay between sessions
- ✅ **Smart:** Auto-loads KB on startup  
- ✅ **Fast:** Query without re-uploading
- ✅ **Simple:** Just upload once, query always
- ✅ **Safe:** Everything stored locally

Start using your knowledge base today! 🎉

Questions? See `MODULE_7_DOCUMENTATION.md` or `MODULE_7_PHASE2_REFACTORING.md`
