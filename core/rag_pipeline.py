"""Retrieval-Augmented Generation orchestration for Aion.

RAG separates two jobs: retrieval finds relevant external memory, and generation
uses that retrieved context to answer. This separation is important because it
lets Aion improve retrieval, prompting, and LLM transport independently.

Memory-aware RAG extends this by also retrieving recent conversation history
and injecting it into the prompt. The conversation layer stays independent from
document retrieval, ensuring memory is never embedded into vector search.

Citations connect generated answers back to source chunks, making RAG responses
traceable and verifiable. Each answer includes citations pointing to the specific
chunks that informed the response.
"""

from __future__ import annotations

from collections import defaultdict

from .conversation_manager import ConversationManager
from .llm_client import OllamaClient
from .memory_models import ConversationTurn
from .prompt_builder import PromptBuilder
from .response_models import GeneratedResponse
from .retriever import Retriever
from .retrieval_models import RetrievalResult, Citation, SourceDocument


class RAGPipeline:
    """Coordinate retrieval, prompt construction, and local LLM generation.

    Retrieval-Augmented Generation improves reliability by injecting relevant
    external memory into the prompt. The LLM still generates the answer, but it
    is guided by retrieved chunks rather than relying only on model weights.
    Context windows matter here: only a limited amount of retrieved text can fit
    into a prompt, so the pipeline keeps top-k retrieval configurable.

    Memory-aware RAG additionally retrieves recent conversation history and
    injects it into the prompt before retrieved document context. Conversation
    memory is kept completely separate from vector search.
    """

    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder | None = None,
        llm_client: OllamaClient | None = None,
        conversation_manager: ConversationManager | None = None,
        top_k: int = 5,
        memory_window: int = 5,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")
        if memory_window < 0:
            raise ValueError("memory_window must be non-negative.")

        self.retriever = retriever
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.llm_client = llm_client or OllamaClient()
        self.conversation_manager = conversation_manager
        self.top_k = top_k
        self.memory_window = memory_window

    def ask(self, query: str, top_k: int | None = None) -> GeneratedResponse:
        """Run the full memory-aware RAG flow for a user query.

        Flow:
        1. Retrieve recent conversation turns (if memory manager is available)
        2. Retrieve relevant document chunks
        3. Build prompt with memory history + retrieved context + query
        4. Generate response using LLM
        5. Extract citations from retrieved chunks
        6. Aggregate source documents from citations
        7. Save turn to memory (if memory manager is available)
        """

        cleaned_query = query.strip()
        if not cleaned_query:
            return GeneratedResponse(
                query=query,
                response="Please enter a question.",
                retrieved_chunks=[],
                citations=[],
                source_documents=[],
                metadata={"error": "empty_query"},
            )

        memory_turns = self._retrieve_memory(limit=self.memory_window)
        retrieved_chunks = self.retrieve_context(cleaned_query, top_k=top_k)
        prompt = self.prompt_builder.build_prompt(
            cleaned_query,
            retrieved_chunks,
            memory_turns=memory_turns if memory_turns else None,
        )
        system_prompt = self.prompt_builder.build_system_prompt()
        response = self.generate_response(prompt=prompt, system_prompt=system_prompt)

        if self.conversation_manager:
            self.conversation_manager.add_turn(
                user_message=cleaned_query,
                assistant_message=response,
            )
            self.conversation_manager.save()

        # Extract citations from retrieved chunks
        citations = self._extract_citations(retrieved_chunks)
        # Aggregate source documents
        source_documents = self._aggregate_source_documents(citations)

        return GeneratedResponse(
            query=cleaned_query,
            response=response,
            retrieved_chunks=retrieved_chunks,
            citations=citations,
            source_documents=source_documents,
            metadata={
                "top_k": top_k or self.top_k,
                "retrieved_chunk_count": len(retrieved_chunks),
                "citation_count": len(citations),
                "source_document_count": len(source_documents),
                "memory_turn_count": len(memory_turns),
                "llm_model": self.llm_client.config.model,
                "prompt": prompt,
                "system_prompt": system_prompt,
            },
        )

    def retrieve_context(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        """Retrieve semantic context for a query."""

        return self.retriever.retrieve(query, top_k=top_k or self.top_k)

    def _retrieve_memory(self, limit: int = 5) -> list[ConversationTurn]:
        """Retrieve recent conversation turns from memory.

        Memory retrieval is completely separate from document retrieval.
        Only the most recent turns are returned; no summarization or ranking
        is applied. This remains a simple session-based window into recent chat.
        """

        if not self.conversation_manager:
            return []

        return self.conversation_manager.get_recent_turns(limit=limit)

    def generate_response(self, prompt: str, system_prompt: str) -> str:
        """Generate an answer from a grounded prompt using the LLM client."""

        return self.llm_client.generate(prompt=prompt, system_prompt=system_prompt)

    def _extract_citations(self, retrieved_chunks: list[RetrievalResult]) -> list[Citation]:
        """Extract citation metadata from retrieved chunks.

        Each retrieved chunk becomes a citation, capturing the exact provenance
        of where retrieved information came from. Citations are ordered by
        similarity score (highest first) to prioritize the most relevant sources.
        """

        citations: list[Citation] = []
        for chunk in retrieved_chunks:
            citation = Citation(
                source_filename=chunk.source_filename,
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                similarity_score=chunk.similarity_score,
                chunk_text=chunk.text,
            )
            citations.append(citation)

        return citations

    def _aggregate_source_documents(self, citations: list[Citation]) -> list[SourceDocument]:
        """Aggregate citations by document, creating document-level source metadata.

        When multiple chunks from the same document are cited, this method
        groups them and computes aggregate statistics (average similarity score,
        chunk count) for cleaner answer-level source information.
        """

        if not citations:
            return []

        # Group citations by document_id
        documents_map: dict[str, list[Citation]] = defaultdict(list)
        for citation in citations:
            documents_map[citation.document_id].append(citation)

        # Aggregate to SourceDocument records
        source_documents: list[SourceDocument] = []
        for document_id, doc_citations in documents_map.items():
            if not doc_citations:
                continue

            source_filename = doc_citations[0].source_filename
            chunk_count = len(doc_citations)
            avg_similarity = sum(c.similarity_score for c in doc_citations) / chunk_count

            source_doc = SourceDocument(
                document_id=document_id,
                source_filename=source_filename,
                chunk_count_referenced=chunk_count,
                avg_similarity_score=avg_similarity,
            )
            source_documents.append(source_doc)

        # Sort by average similarity (highest first)
        source_documents.sort(key=lambda s: s.avg_similarity_score, reverse=True)

        return source_documents


__all__ = ["RAGPipeline"]
