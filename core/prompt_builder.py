"""Prompt construction utilities for Aion's RAG layer.

Prompt grounding means giving the model retrieved source context and clear
instructions about how to use it. This reduces hallucinations because the LLM
does not need to rely only on parametric memory, which is knowledge stored in
model weights. Instead, it can answer from Aion's external memory: the retrieved
chunks produced by the semantic search layer.

Memory-aware prompting includes recent conversation history so the model can
build on previous turns in the same session while remaining grounded in
retrieved documents.
"""

from __future__ import annotations

from .memory_models import ConversationTurn
from .retrieval_models import RetrievalResult


class PromptBuilder:
    """Build deterministic prompts from a query and retrieved chunks.

    Prompt structure matters because language models are sensitive to how
    context and instructions are framed. Keeping prompt construction in its own
    module makes it easier to iterate on grounding rules without changing
    retrieval or Ollama request code.
    """

    DEFAULT_SYSTEM_PROMPT = (
        "You are Aion, a local-first AI companion. Answer using only the "
        "provided retrieved context. If the context is insufficient, say what "
        "is missing instead of inventing details. Keep the answer concise, "
        "clear, and grounded in the source chunks."
    )

    DEFAULT_USER_TEMPLATE = (
        "Retrieved document context:\n"
        "{context}\n\n"
        "User question:\n"
        "{query}\n\n"
        "Answer:"
    )

    MEMORY_AWARE_USER_TEMPLATE = (
        "Conversation history:\n"
        "{memory}\n\n"
        "Retrieved document context:\n"
        "{context}\n\n"
        "Current question:\n"
        "{query}\n\n"
        "Answer:"
    )

    def __init__(
        self,
        system_prompt: str | None = None,
        user_template: str | None = None,
        max_context_characters: int = 6000,
    ) -> None:
        if max_context_characters <= 0:
            raise ValueError("max_context_characters must be greater than zero.")

        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.user_template = user_template or self.DEFAULT_USER_TEMPLATE
        self.max_context_characters = max_context_characters

    def build_system_prompt(self) -> str:
        """Return the system-level grounding instructions for the LLM."""

        return self.system_prompt.strip()



    def format_context(self, retrieved_chunks: list[RetrievalResult]) -> str:
        """Format retrieved chunks as visible, ranked prompt context.

        Keeping retrieved context visible in the prompt makes grounding explicit:
        the model can distinguish source material from the user's question, and
        developers can inspect exactly what evidence was given to the LLM.
        """

        if not retrieved_chunks:
            return "No retrieved context was found."

        formatted_blocks: list[str] = []
        used_characters = 0

        for rank, chunk in enumerate(retrieved_chunks, start=1):
            source_name = chunk.metadata.get("source_filename", "unknown source")
            chunk_index = chunk.metadata.get("chunk_index", "unknown")
            block = (
                f"[Chunk {rank} | score={chunk.similarity_score:.4f} | "
                f"source={source_name} | chunk_index={chunk_index}]\n"
                f"{chunk.text.strip()}"
            )

            remaining_characters = self.max_context_characters - used_characters
            if remaining_characters <= 0:
                break

            if len(block) > remaining_characters:
                block = block[:remaining_characters].rstrip() + "\n[Context truncated]"

            formatted_blocks.append(block)
            used_characters += len(block)

        return "\n\n".join(formatted_blocks)

    def format_memory_history(self, memory_turns: list[ConversationTurn]) -> str:
        """Format recent conversation turns for prompt injection.

        Conversation history is shown explicitly so the model knows what was
        discussed previously in this session. The history is separate from
        retrieved document context, so the model can distinguish between
        what was said before and what the documents contain.
        """

        if not memory_turns:
            return "[No previous conversation history]"

        formatted_turns: list[str] = []
        for turn in memory_turns:
            turn_text = (
                f"User: {turn.user_message}\n"
                f"Assistant: {turn.assistant_message}"
            )
            formatted_turns.append(turn_text)

        return "\n\n".join(formatted_turns)

    def build_prompt(
        self,
        query: str,
        retrieved_chunks: list[RetrievalResult],
        memory_turns: list[ConversationTurn] | None = None,
    ) -> str:
        """Build the final user prompt with memory and retrieved context injected."""

        context = self.format_context(retrieved_chunks)

        if memory_turns:
            memory = self.format_memory_history(memory_turns)
            return self.MEMORY_AWARE_USER_TEMPLATE.format(
                memory=memory,
                context=context,
                query=query.strip(),
            ).strip()
        else:
            return self.user_template.format(
                context=context,
                query=query.strip(),
            ).strip()


__all__ = ["PromptBuilder", "ConversationTurn"]
