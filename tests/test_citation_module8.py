"""Integration tests for Module 8: Cross-Document Retrieval and Citation-Aware Responses.

This test suite validates that citations and source document metadata flow correctly
through the entire RAG pipeline, from retrieval to response generation.
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.chunk_models import Chunk
from core.retrieval_models import RetrievalResult, Citation, SourceDocument
from core.response_models import GeneratedResponse
from core.embedder import EmbeddingEngine
from core.vector_store import VectorStore
from core.retriever import Retriever
from core.rag_pipeline import RAGPipeline
from core.prompt_builder import PromptBuilder


class TestCitationMetadata:
    """Test that citation metadata is properly extracted from RetrievalResult."""

    def test_retrieval_result_source_filename_property(self):
        """Test that RetrievalResult exposes source_filename as a property."""
        result = RetrievalResult(
            chunk_id="test_chunk_1",
            document_id="doc_1",
            text="Sample content",
            similarity_score=0.95,
            metadata={"source_filename": "document.pdf"},
        )
        assert result.source_filename == "document.pdf"

    def test_retrieval_result_source_filename_fallback(self):
        """Test that RetrievalResult returns 'unknown' when source_filename is missing."""
        result = RetrievalResult(
            chunk_id="test_chunk_1",
            document_id="doc_1",
            text="Sample content",
            similarity_score=0.95,
            metadata={},
        )
        assert result.source_filename == "unknown"

    def test_retrieval_result_chunk_index_property(self):
        """Test that RetrievalResult exposes chunk_index as a property."""
        result = RetrievalResult(
            chunk_id="test_chunk_1",
            document_id="doc_1",
            text="Sample content",
            similarity_score=0.95,
            metadata={"chunk_index": 5},
        )
        assert result.chunk_index == 5

    def test_retrieval_result_chunk_index_default(self):
        """Test that RetrievalResult defaults chunk_index to 0 when missing."""
        result = RetrievalResult(
            chunk_id="test_chunk_1",
            document_id="doc_1",
            text="Sample content",
            similarity_score=0.95,
            metadata={},
        )
        assert result.chunk_index == 0


class TestCitationModel:
    """Test Citation model construction and serialization."""

    def test_citation_creation(self):
        """Test creating a Citation object."""
        citation = Citation(
            source_filename="notes.pdf",
            document_id="doc_123",
            chunk_index=2,
            similarity_score=0.87,
            chunk_text="IPv6 is a network protocol...",
        )
        assert citation.source_filename == "notes.pdf"
        assert citation.document_id == "doc_123"
        assert citation.chunk_index == 2
        assert citation.similarity_score == 0.87

    def test_citation_to_dict(self):
        """Test Citation serialization to dictionary."""
        citation = Citation(
            source_filename="notes.pdf",
            document_id="doc_123",
            chunk_index=2,
            similarity_score=0.87,
            chunk_text="IPv6 is a network protocol with 128-bit addresses...",
        )
        citation_dict = citation.to_dict()
        assert citation_dict["source_filename"] == "notes.pdf"
        assert citation_dict["document_id"] == "doc_123"
        assert citation_dict["chunk_index"] == 2
        assert citation_dict["similarity_score"] == 0.87
        # Verify truncation of long text
        assert "..." in citation_dict["chunk_text"]

    def test_citation_truncates_long_text(self):
        """Test that Citation truncates very long chunk text in serialization."""
        long_text = "A" * 500
        citation = Citation(
            source_filename="notes.pdf",
            document_id="doc_123",
            chunk_index=2,
            similarity_score=0.87,
            chunk_text=long_text,
        )
        citation_dict = citation.to_dict()
        assert len(citation_dict["chunk_text"]) < len(long_text)
        assert "..." in citation_dict["chunk_text"]


class TestSourceDocumentModel:
    """Test SourceDocument model construction and serialization."""

    def test_source_document_creation(self):
        """Test creating a SourceDocument object."""
        source_doc = SourceDocument(
            document_id="doc_123",
            source_filename="notes.pdf",
            chunk_count_referenced=3,
            avg_similarity_score=0.85,
        )
        assert source_doc.document_id == "doc_123"
        assert source_doc.source_filename == "notes.pdf"
        assert source_doc.chunk_count_referenced == 3
        assert source_doc.avg_similarity_score == 0.85

    def test_source_document_to_dict(self):
        """Test SourceDocument serialization to dictionary."""
        source_doc = SourceDocument(
            document_id="doc_123",
            source_filename="notes.pdf",
            chunk_count_referenced=3,
            avg_similarity_score=0.8567,
        )
        doc_dict = source_doc.to_dict()
        assert doc_dict["document_id"] == "doc_123"
        assert doc_dict["source_filename"] == "notes.pdf"
        assert doc_dict["chunk_count_referenced"] == 3
        # Verify rounding
        assert doc_dict["avg_similarity_score"] == 0.8567


class TestGeneratedResponseWithCitations:
    """Test GeneratedResponse with citation and source_documents fields."""

    def test_generated_response_with_citations(self):
        """Test creating GeneratedResponse with citations."""
        citations = [
            Citation("doc1.pdf", "doc_1", 0, 0.9, "Sample text 1"),
            Citation("doc2.pdf", "doc_2", 1, 0.85, "Sample text 2"),
        ]
        response = GeneratedResponse(
            query="What is IPv6?",
            response="IPv6 uses 128-bit addresses.",
            retrieved_chunks=[],
            citations=citations,
            source_documents=[],
        )
        assert len(response.citations) == 2
        assert response.citations[0].source_filename == "doc1.pdf"

    def test_generated_response_with_source_documents(self):
        """Test creating GeneratedResponse with source_documents."""
        source_docs = [
            SourceDocument("doc_1", "doc1.pdf", 2, 0.88),
            SourceDocument("doc_2", "doc2.pdf", 1, 0.85),
        ]
        response = GeneratedResponse(
            query="What is IPv6?",
            response="IPv6 uses 128-bit addresses.",
            retrieved_chunks=[],
            citations=[],
            source_documents=source_docs,
        )
        assert len(response.source_documents) == 2
        assert response.source_documents[0].source_filename == "doc1.pdf"

    def test_generated_response_defaults_citations_empty(self):
        """Test that citations and source_documents default to empty lists."""
        response = GeneratedResponse(
            query="What is IPv6?",
            response="IPv6 uses 128-bit addresses.",
            retrieved_chunks=[],
        )
        assert response.citations == []
        assert response.source_documents == []


class TestRAGPipelineCitationExtraction:
    """Test RAGPipeline citation extraction functionality."""

    def test_extract_citations_from_retrieval_results(self):
        """Test extracting citations from RetrievalResult objects."""
        # Create a mock retriever result
        results = [
            RetrievalResult(
                chunk_id="chunk_1",
                document_id="doc_1",
                text="IPv6 is a network protocol...",
                similarity_score=0.95,
                metadata={
                    "source_filename": "notes.pdf",
                    "chunk_index": 0,
                },
            ),
            RetrievalResult(
                chunk_id="chunk_2",
                document_id="doc_2",
                text="128-bit addresses are used...",
                similarity_score=0.87,
                metadata={
                    "source_filename": "network_guide.pdf",
                    "chunk_index": 2,
                },
            ),
        ]

        # Create RAG pipeline
        pipeline = RAGPipeline(retriever=None, prompt_builder=None, llm_client=None)
        citations = pipeline._extract_citations(results)

        assert len(citations) == 2
        assert citations[0].source_filename == "notes.pdf"
        assert citations[0].chunk_index == 0
        assert citations[0].similarity_score == 0.95
        assert citations[1].source_filename == "network_guide.pdf"
        assert citations[1].chunk_index == 2

    def test_aggregate_source_documents_from_citations(self):
        """Test aggregating source documents from citations."""
        citations = [
            Citation("notes.pdf", "doc_1", 0, 0.95, "IPv6 is..."),
            Citation("notes.pdf", "doc_1", 3, 0.92, "128-bit..."),
            Citation("network_guide.pdf", "doc_2", 1, 0.87, "Routing..."),
        ]

        pipeline = RAGPipeline(retriever=None, prompt_builder=None, llm_client=None)
        source_docs = pipeline._aggregate_source_documents(citations)

        assert len(source_docs) == 2
        
        # Find docs by name
        doc1_agg = next((d for d in source_docs if d.document_id == "doc_1"), None)
        doc2_agg = next((d for d in source_docs if d.document_id == "doc_2"), None)

        assert doc1_agg is not None
        assert doc1_agg.source_filename == "notes.pdf"
        assert doc1_agg.chunk_count_referenced == 2
        # Average of 0.95 and 0.92
        assert abs(doc1_agg.avg_similarity_score - 0.935) < 0.001

        assert doc2_agg is not None
        assert doc2_agg.source_filename == "network_guide.pdf"
        assert doc2_agg.chunk_count_referenced == 1
        assert doc2_agg.avg_similarity_score == 0.87

    def test_aggregate_source_documents_sorted_by_similarity(self):
        """Test that source documents are sorted by average similarity (highest first)."""
        citations = [
            Citation("doc1.pdf", "doc_1", 0, 0.70, "Text"),
            Citation("doc2.pdf", "doc_2", 0, 0.95, "Text"),
            Citation("doc3.pdf", "doc_3", 0, 0.80, "Text"),
        ]

        pipeline = RAGPipeline(retriever=None, prompt_builder=None, llm_client=None)
        source_docs = pipeline._aggregate_source_documents(citations)

        # Should be sorted: doc_2 (0.95), doc_3 (0.80), doc_1 (0.70)
        assert source_docs[0].document_id == "doc_2"
        assert source_docs[1].document_id == "doc_3"
        assert source_docs[2].document_id == "doc_1"

    def test_aggregate_source_documents_empty_citations(self):
        """Test aggregating from empty citations list."""
        pipeline = RAGPipeline(retriever=None, prompt_builder=None, llm_client=None)
        source_docs = pipeline._aggregate_source_documents([])

        assert source_docs == []


class TestMetadataFlow:
    """Test that metadata flows correctly through the pipeline."""

    def test_chunk_with_source_filename_metadata(self):
        """Test that chunks created with source_filename metadata preserve it."""
        chunk = Chunk(
            chunk_id="chunk_1",
            document_id="doc_1",
            text="Sample text",
            chunk_index=0,
            metadata={
                "source_filename": "document.pdf",
                "source_file_type": "pdf",
            },
        )
        assert chunk.metadata["source_filename"] == "document.pdf"
        assert chunk.metadata["source_file_type"] == "pdf"

    def test_retrieval_result_preserves_chunk_metadata(self):
        """Test that RetrievalResult preserves all chunk metadata."""
        metadata = {
            "source_filename": "document.pdf",
            "source_file_type": "pdf",
            "chunk_index": 5,
            "word_count": 150,
        }
        result = RetrievalResult(
            chunk_id="chunk_1",
            document_id="doc_1",
            text="Sample text",
            similarity_score=0.9,
            metadata=metadata,
        )
        # Verify all metadata is preserved
        for key, value in metadata.items():
            assert result.metadata[key] == value


def run_tests():
    """Run all tests and print results."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
