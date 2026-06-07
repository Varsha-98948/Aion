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
from core.embedding_models import EmbeddedChunk
from core.embedder import EmbeddingEngine
from core.vector_store import VectorStore
from core.retriever import Retriever
from core.rag_pipeline import RAGPipeline
from core.prompt_builder import PromptBuilder
from core.knowledge_base import KnowledgeBaseManager
from ui import app_streamlit


class FakeEmbeddingEngine:
    """Small deterministic query embedder for retrieval tests."""

    def embed_texts(self, texts, batch_size=None):
        return [[1.0, 0.0] for text in texts if text.strip()]


class FakeLLMClient:
    """Small deterministic LLM client for end-to-end RAG tests."""

    def __init__(self):
        self.config = type("Config", (), {"model": "fake-llm"})()

    def generate(self, prompt: str, system_prompt: str) -> str:
        return "IoT connects devices, while cloud computing provides remote computing resources."


def _embedded_chunk(
    chunk_id: str,
    document_id: str,
    filename: str,
    chunk_index: int,
    text: str,
    embedding: list[float],
) -> EmbeddedChunk:
    return EmbeddedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        text=text,
        embedding=embedding,
        metadata={
            "source_filename": filename,
            "source_file_type": "pdf",
            "chunk_index": chunk_index,
        },
    )


def _build_persisted_store(index_directory: Path, chunks: list[EmbeddedChunk]) -> VectorStore:
    store = VectorStore(index_directory=index_directory)
    store.build_index(chunks)
    store.save_index(index_directory)
    return store


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


class TestUnifiedKnowledgeBaseRetrieval:
    """Test cross-document retrieval through a unified knowledge-base vector store."""

    def test_retrieval_across_multiple_documents(self, tmp_path):
        """Test that one retriever can return chunks from multiple documents."""

        iot_chunk = _embedded_chunk(
            "iot_chunk_1",
            "doc_iot",
            "Sample_1.pdf",
            0,
            "IoT means Internet of Things, where connected devices exchange data.",
            [1.0, 0.0],
        )
        cloud_chunk = _embedded_chunk(
            "cloud_chunk_1",
            "doc_cloud",
            "Sample_2.pdf",
            0,
            "Cloud computing provides on-demand servers, storage, and applications.",
            [1.0, 0.0],
        )

        iot_store = _build_persisted_store(tmp_path / "iot_index", [iot_chunk])
        cloud_store = _build_persisted_store(tmp_path / "cloud_index", [cloud_chunk])

        unified_store = VectorStore(index_directory=tmp_path / "unified")
        unified_store.merge_from_store(iot_store)
        unified_store.merge_from_store(cloud_store)

        retriever = Retriever(
            vector_store=unified_store,
            embedding_engine=FakeEmbeddingEngine(),
            top_k=2,
        )
        results = retriever.retrieve("What do you mean by IoT and Cloud Computing?", top_k=2)

        assert len(results) == 2
        assert {result.document_id for result in results} == {"doc_iot", "doc_cloud"}
        assert {result.source_filename for result in results} == {"Sample_1.pdf", "Sample_2.pdf"}
        assert all(result.chunk_index == 0 for result in results)

    def test_unified_kb_retrieval_works_after_restart(self, tmp_path, monkeypatch):
        """Test that persisted per-document indexes reload into one KB store."""

        indexes_directory = tmp_path / "indexes"
        monkeypatch.setattr(app_streamlit, "INDEXES_DIRECTORY", indexes_directory)

        iot_chunk = _embedded_chunk(
            "iot_chunk_1",
            "doc_iot",
            "Sample_1.pdf",
            0,
            "IoT connects physical devices and sensors to networks.",
            [1.0, 0.0],
        )
        cloud_chunk = _embedded_chunk(
            "cloud_chunk_1",
            "doc_cloud",
            "Sample_2.pdf",
            0,
            "Cloud computing offers remote infrastructure and software services.",
            [1.0, 0.0],
        )

        _build_persisted_store(indexes_directory / "sample_1_doc_iot", [iot_chunk])
        _build_persisted_store(indexes_directory / "sample_2_doc_cloud", [cloud_chunk])

        kb_manager = KnowledgeBaseManager(kb_directory=tmp_path / "knowledge_base")
        kb_manager.register_document("doc_iot", "Sample_1.pdf", "pdf", 1)
        kb_manager.register_document("doc_cloud", "Sample_2.pdf", "pdf", 1)

        unified_index_info = app_streamlit._load_unified_kb_vector_store(
            kb_manager,
            FakeEmbeddingEngine(),
        )

        assert unified_index_info is not None
        unified_store, loaded_document_ids = unified_index_info
        assert unified_store.record_count == 2
        assert set(loaded_document_ids) == {"doc_iot", "doc_cloud"}

        retriever = Retriever(
            vector_store=unified_store,
            embedding_engine=FakeEmbeddingEngine(),
            top_k=2,
        )
        results = retriever.retrieve("What do you mean by IoT and Cloud Computing?", top_k=2)

        assert len(results) == 2
        assert {result.document_id for result in results} == {"doc_iot", "doc_cloud"}
        assert {result.metadata["source_filename"] for result in results} == {
            "Sample_1.pdf",
            "Sample_2.pdf",
        }

    def test_citations_survive_end_to_end_generation(self, tmp_path):
        """Test that RAG output includes citations and source summaries."""

        chunks = [
            _embedded_chunk(
                "iot_chunk_1",
                "doc_iot",
                "Sample_1.pdf",
                0,
                "IoT means Internet of Things and connected devices.",
                [1.0, 0.0],
            ),
            _embedded_chunk(
                "cloud_chunk_1",
                "doc_cloud",
                "Sample_2.pdf",
                0,
                "Cloud computing means remote computing resources over a network.",
                [1.0, 0.0],
            ),
        ]
        vector_store = _build_persisted_store(tmp_path / "unified_index", chunks)
        retriever = Retriever(
            vector_store=vector_store,
            embedding_engine=FakeEmbeddingEngine(),
            top_k=2,
        )
        rag_pipeline = RAGPipeline(
            retriever=retriever,
            prompt_builder=PromptBuilder(),
            llm_client=FakeLLMClient(),
            top_k=2,
        )

        generated_response = rag_pipeline.ask(
            "What do you mean by IoT and Cloud Computing?",
            top_k=2,
        )

        assert generated_response.response
        assert len(generated_response.retrieved_chunks) == 2
        assert len(generated_response.citations) == 2
        assert len(generated_response.source_documents) == 2
        assert {citation.source_filename for citation in generated_response.citations} == {
            "Sample_1.pdf",
            "Sample_2.pdf",
        }
        assert {
            source_document.chunk_count_referenced
            for source_document in generated_response.source_documents
        } == {1}
        assert generated_response.metadata["citation_count"] == 2
        assert generated_response.metadata["source_document_count"] == 2


def run_tests():
    """Run all tests and print results."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
