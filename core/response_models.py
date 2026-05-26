"""Schema objects for Aion's generated RAG responses.

Retrieval-Augmented Generation, or RAG, combines external memory with language
model generation. The retriever finds relevant source chunks, and the generator
answers using those chunks as grounded context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .retrieval_models import RetrievalResult


@dataclass(slots=True)
class GeneratedResponse:
    """A generated answer with the retrieval trace that supported it.

    Retrieval traceability matters because RAG answers should be inspectable.
    The final text is only one part of the output; developers also need to see
    which chunks were retrieved, how they scored, which model answered, and what
    prompt settings were used. This helps debug hallucinations, weak retrieval,
    and prompt grounding problems separately.
    """

    query: str
    response: str
    retrieved_chunks: list[RetrievalResult]
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["GeneratedResponse"]
