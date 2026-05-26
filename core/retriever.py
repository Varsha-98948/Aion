"""Semantic retriever for Aion.

Retrieval is the step that turns a natural-language query into ranked context.
The query is embedded into the same vector space as stored chunks, then FAISS
returns the nearest chunk vectors. This is different from keyword search: the
query can use different words while still finding related meaning.
"""

from __future__ import annotations

from .embedder import EmbeddingEngine
from .retrieval_models import RetrievalResult
from .vector_store import VectorStore, VectorSearchMatch


class Retriever:
    """Embed user queries and return ranked semantic retrieval results."""

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_engine: EmbeddingEngine | None = None,
        top_k: int = 5,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")

        self.vector_store = vector_store
        self.embedding_engine = embedding_engine or EmbeddingEngine()
        self.top_k = top_k

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        """Return the most semantically relevant chunks for a query."""

        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        query_embedding = self.embed_query(cleaned_query)
        matches = self.vector_store.search(query_embedding, top_k=top_k or self.top_k)
        return self.format_results(matches)

    def embed_query(self, query: str) -> list[float]:
        """Embed a natural-language query into the chunk vector space."""

        return self.embedding_engine.embed_texts([query])[0]

    def format_results(self, matches: list[VectorSearchMatch]) -> list[RetrievalResult]:
        """Convert vector-store matches into retrieval result objects."""

        results: list[RetrievalResult] = []
        for match in matches:
            results.append(
                RetrievalResult(
                    chunk_id=match.record.chunk_id,
                    document_id=match.record.document_id,
                    text=match.record.text,
                    similarity_score=match.similarity_score,
                    metadata={
                        **match.record.metadata,
                        "rank_index_position": match.index_position,
                    },
                )
            )

        return results


__all__ = ["Retriever"]
