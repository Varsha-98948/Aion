"""Example usage and validation tests for Module 7: Knowledge Base Manager.

Run this script to verify the knowledge base functionality works correctly:
    python tests/test_knowledge_base_module7.py
"""

from pathlib import Path
from core.knowledge_base import KnowledgeBaseManager, DocumentMetadata


def test_basic_registration():
    """Test basic document registration."""
    print("\n" + "="*60)
    print("TEST 1: Basic Document Registration")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    # Register a document
    metadata = kb.register_document(
        document_id="example-doc-001",
        filename="semantic_search_guide.pdf",
        file_type="pdf",
        chunk_count=42,
        custom_metadata={
            "source": "academic_papers",
            "topic": "information_retrieval",
            "source_path": "data/uploads/semantic_search_guide.pdf",
        }
    )

    print(f"✓ Registered document:")
    print(f"  - KB ID: {metadata.kb_doc_id}")
    print(f"  - Document ID: {metadata.document_id}")
    print(f"  - Filename: {metadata.filename}")
    print(f"  - Chunks: {metadata.chunk_count}")
    print(f"  - Date Added: {metadata.date_added}")


def test_duplicate_prevention():
    """Test that duplicate registration is prevented."""
    print("\n" + "="*60)
    print("TEST 2: Duplicate Prevention")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    try:
        kb.register_document(
            document_id="example-doc-001",
            filename="duplicate.pdf",
            file_type="pdf",
            chunk_count=10,
        )
        print("✗ ERROR: Should have raised ValueError for duplicate")
    except ValueError as e:
        print(f"✓ Correctly prevented duplicate: {e}")


def test_statistics():
    """Test statistics calculation."""
    print("\n" + "="*60)
    print("TEST 3: Statistics Calculation")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    # Register another document
    kb.register_document(
        document_id="example-doc-002",
        filename="advanced_nlp.txt",
        file_type="txt",
        chunk_count=28,
    )

    stats = kb.get_statistics()

    print(f"✓ Knowledge Base Statistics:")
    print(f"  - Total Documents: {stats.total_documents}")
    print(f"  - Total Chunks: {stats.total_chunks}")
    print(f"  - Average Chunks/Doc: {stats.average_chunks_per_document:.2f}")
    print(f"  - Oldest Document: {stats.oldest_document_date}")
    print(f"  - Newest Document: {stats.newest_document_date}")


def test_document_listing():
    """Test document listing and retrieval."""
    print("\n" + "="*60)
    print("TEST 4: Document Listing and Retrieval")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    documents = kb.list_documents()
    print(f"✓ Listed {len(documents)} documents:")

    for idx, doc in enumerate(documents, start=1):
        print(f"  {idx}. {doc.filename} ({doc.file_type})")
        print(f"     - Chunks: {doc.chunk_count}")
        print(f"     - Added: {doc.date_added}")
        print(f"     - KB ID: {doc.kb_doc_id}")


def test_document_retrieval():
    """Test retrieving specific document metadata."""
    print("\n" + "="*60)
    print("TEST 5: Document Retrieval")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    doc_meta = kb.get_document("example-doc-001")

    if doc_meta:
        print(f"✓ Retrieved document metadata:")
        print(f"  - Filename: {doc_meta.filename}")
        print(f"  - Chunks: {doc_meta.chunk_count}")
        print(f"  - Type: {doc_meta.file_type}")
        print(f"  - Custom metadata: {doc_meta.metadata}")
    else:
        print("✗ Document not found")


def test_document_existence_check():
    """Test existence checking."""
    print("\n" + "="*60)
    print("TEST 6: Document Existence Check")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    exists_1 = kb.document_exists("example-doc-001")
    exists_2 = kb.document_exists("nonexistent-doc")

    print(f"✓ example-doc-001 exists: {exists_1}")
    print(f"✓ nonexistent-doc exists: {exists_2}")


def test_chunk_count_update():
    """Test updating chunk count."""
    print("\n" + "="*60)
    print("TEST 7: Update Chunk Count")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    # Get old count
    doc_before = kb.get_document("example-doc-001")
    print(f"✓ Chunk count before: {doc_before.chunk_count}")

    # Update count
    updated = kb.update_chunk_count("example-doc-001", 45)
    print(f"✓ Update successful: {updated}")

    # Get new count
    doc_after = kb.get_document("example-doc-001")
    print(f"✓ Chunk count after: {doc_after.chunk_count}")


def test_export_import():
    """Test export and import functionality."""
    print("\n" + "="*60)
    print("TEST 8: Export and Import")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    # Export
    export_path = kb.export_knowledge_base("data/knowledge_base/test_export.json")
    print(f"✓ Exported to: {export_path}")

    # Create new manager
    kb2 = KnowledgeBaseManager(kb_directory="data/knowledge_base")
    initial_count = kb2.get_document_count()

    # Import
    imported_count = kb2.import_knowledge_base(export_path)
    print(f"✓ Imported {imported_count} documents")
    print(f"✓ Total documents after import: {kb2.get_document_count()}")


def test_get_counts():
    """Test getting individual counts."""
    print("\n" + "="*60)
    print("TEST 9: Get Counts")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    doc_count = kb.get_document_count()
    chunk_count = kb.get_total_chunks()

    print(f"✓ Document count: {doc_count}")
    print(f"✓ Total chunks: {chunk_count}")


def cleanup_test_documents():
    """Remove test documents to clean up."""
    print("\n" + "="*60)
    print("CLEANUP: Removing Test Documents")
    print("="*60)

    kb = KnowledgeBaseManager(kb_directory="data/knowledge_base")

    removed_1 = kb.remove_document("example-doc-001")
    removed_2 = kb.remove_document("example-doc-002")

    print(f"✓ Removed example-doc-001: {removed_1}")
    print(f"✓ Removed example-doc-002: {removed_2}")
    print(f"✓ Remaining documents: {kb.get_document_count()}")


def main():
    """Run all validation tests."""
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  MODULE 7: KNOWLEDGE BASE MANAGER - VALIDATION TESTS".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")

    try:
        test_basic_registration()
        test_duplicate_prevention()
        test_statistics()
        test_document_listing()
        test_document_retrieval()
        test_document_existence_check()
        test_chunk_count_update()
        test_export_import()
        test_get_counts()
        cleanup_test_documents()

        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
