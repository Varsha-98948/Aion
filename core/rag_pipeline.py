"""Retrieval-Augmented Generation orchestration for Aion.

RAG separates two jobs: retrieval finds relevant external memory, and generation
uses that retrieved context to answer. This separation is important because it
lets Aion improve retrieval, prompting, and LLM transport independently.
"""

from __future__ import annotations

from .llm_client import OllamaClient
from .prompt_builder import PromptBuilder
from .response_models import GeneratedResponse
from .retriever import Retriever
from .retrieval_models import RetrievalResult


class RAGPipeline:
    """Coordinate retrieval, prompt construction, and local LLM generation.

    Retrieval-Augmented Generation improves reliability by injecting relevant
    external memory into the prompt. The LLM still generates the answer, but it
    is guided by retrieved chunks rather than relying only on model weights.
    Context windows matter here: only a limited amount of retrieved text can fit
    into a prompt, so the pipeline keeps top-k retrieval configurable.
    """

    def __init__(
        self,
        retriever: Retriever,
        prompt_builder: PromptBuilder | None = None,
        llm_client: OllamaClient | None = None,
        top_k: int = 5,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")

        self.retriever = retriever
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.llm_client = llm_client or OllamaClient()
        self.top_k = top_k

    def ask(self, query: str, top_k: int | None = None) -> GeneratedResponse:
        """Run the full RAG flow for a user query."""

        cleaned_query = query.strip()
        if not cleaned_query:
            return GeneratedResponse(
                query=query,
                response="Please enter a question.",
                retrieved_chunks=[],
                metadata={"error": "empty_query"},
            )

        retrieved_chunks = self.retrieve_context(cleaned_query, top_k=top_k)
        prompt = self.prompt_builder.build_prompt(cleaned_query, retrieved_chunks)
        system_prompt = self.prompt_builder.build_system_prompt()
        response = self.generate_response(prompt=prompt, system_prompt=system_prompt)

        return GeneratedResponse(
            query=cleaned_query,
            response=response,
            retrieved_chunks=retrieved_chunks,
            metadata={
                "top_k": top_k or self.top_k,
                "retrieved_chunk_count": len(retrieved_chunks),
                "llm_model": self.llm_client.config.model,
                "prompt": prompt,
                "system_prompt": system_prompt,
            },
        )

    def retrieve_context(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        """Retrieve semantic context for a query."""

        return self.retriever.retrieve(query, top_k=top_k or self.top_k)

    def generate_response(self, prompt: str, system_prompt: str) -> str:
        """Generate an answer from a grounded prompt using the LLM client."""

        return self.llm_client.generate(prompt=prompt, system_prompt=system_prompt)


__all__ = ["RAGPipeline"]
