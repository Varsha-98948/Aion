"""Developer-focused Streamlit dashboard for Aion's semantic preprocessing flow.

The UI stays intentionally thin. Its job is to collect input, call the backend
pipeline, and visualize results for debugging. Keeping Streamlit separate from
pipeline orchestration preserves clean layering and keeps the core system
reusable from scripts, tests, or future APIs.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.chunker import Chunker
from core.embedder import EmbeddingEngine
from core.llm_client import OllamaClient
from core.pipeline import ProcessingPipeline, ProcessingResult
from core.prompt_builder import PromptBuilder
from core.rag_pipeline import RAGPipeline
from core.retriever import Retriever
from core.retrieval_models import RetrievalResult
from core.response_models import GeneratedResponse

UPLOADS_DIRECTORY = Path("data/uploads")


def render_app() -> None:
    """Render Aion's preprocessing and embedding dashboard."""

    st.set_page_config(page_title="Aion", layout="wide")
    st.title("Aion")
    st.subheader("Local-First Semantic Memory Dashboard")
    st.write(
        "This dashboard shows Aion's semantic preprocessing layer: document "
        "loading, chunk generation, embedding generation, and developer-focused "
        "vector observability before retrieval and FAISS indexing."
    )

    default_chunker = Chunker()
    default_embedder = EmbeddingEngine()

    with st.sidebar:
        st.header("Chunker Config")
        chunk_size = st.number_input(
            "Chunk Size",
            min_value=100,
            max_value=4000,
            value=default_chunker.chunk_size,
            step=50,
            help="Character target for each chunk. This influences context size and later retrieval precision.",
        )
        overlap = st.number_input(
            "Overlap",
            min_value=0,
            max_value=max(int(chunk_size) - 1, 0),
            value=min(default_chunker.overlap, max(int(chunk_size) - 1, 0)),
            step=10,
            help="Shared context between neighboring chunks to reduce boundary information loss.",
        )

        st.header("Embedding Config")
        embedding_model = st.text_input(
            "Embedding Model",
            value=default_embedder.model_name,
            help="SentenceTransformer model used to convert chunks into semantic vectors.",
        )
        batch_size = st.number_input(
            "Embedding Batch Size",
            min_value=1,
            max_value=256,
            value=default_embedder.batch_size,
            step=1,
            help="How many chunks to embed at once. Larger batches can be faster but use more memory.",
        )
        normalize_embeddings = st.checkbox(
            "Normalize Embeddings",
            value=default_embedder.normalize_embeddings,
            help="Normalized vectors often make cosine similarity behavior more stable for semantic retrieval.",
        )
        top_k = st.number_input(
            "Retrieval Top K",
            min_value=1,
            max_value=20,
            value=5,
            step=1,
            help="Number of nearest chunks to return for semantic search.",
        )
        st.header("Generation Config")
        ollama_model = st.text_input(
            "Ollama Model",
            value="mistral",
            help="Local Ollama model used for grounded answer generation.",
        )
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=0.2,
            step=0.05,
            help="Lower values make answers more deterministic.",
        )
        show_prompt_debug = st.checkbox(
            "Show Prompt Debug",
            value=False,
            help="Display the final grounded prompt sent to Ollama.",
        )

    pipeline = ProcessingPipeline(
        chunker=Chunker(chunk_size=int(chunk_size), overlap=int(overlap)),
        embedder=EmbeddingEngine(
            model_name=embedding_model.strip() or EmbeddingEngine.DEFAULT_MODEL_NAME,
            batch_size=int(batch_size),
            normalize_embeddings=normalize_embeddings,
        ),
    )

    uploaded_file = st.file_uploader(
        "Upload a document",
        type=["pdf", "txt", "md"],
        help="Supported formats match the current ingestion layer.",
    )

    if uploaded_file is None:
        st.info("Upload a PDF, TXT, or Markdown file to inspect chunks and embeddings.")
        return

    saved_file_path = _save_uploaded_file(uploaded_file.name, bytes(uploaded_file.getbuffer()))

    try:
        result = pipeline.process_file(saved_file_path, filename=uploaded_file.name, save_output=True)
    except Exception as error:
        st.error(f"Pipeline execution failed: {error}")
        return

    _render_document_info(result)
    _render_chunk_stats(result)
    _render_embedding_stats(result)
    _render_index_stats(result)
    _render_rag_search(
        result,
        pipeline=pipeline,
        top_k=int(top_k),
        ollama_model=ollama_model.strip() or "mistral",
        temperature=float(temperature),
        show_prompt_debug=show_prompt_debug,
    )
    _render_embedded_chunk_previews(result)


def _save_uploaded_file(filename: str, file_bytes: bytes) -> Path:
    """Persist uploaded files so backend processing works with real paths."""

    UPLOADS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    output_path = UPLOADS_DIRECTORY / filename

    with output_path.open("wb") as file:
        file.write(file_bytes)

    return output_path


def _render_document_info(result: ProcessingResult) -> None:
    """Display basic information about the loaded document."""

    st.header("Document Info")
    left_column, right_column = st.columns(2)

    with left_column:
        st.write(f"**Filename:** `{result.document.filename}`")
        st.write(f"**Document ID:** `{result.document.doc_id}`")
        st.write(f"**File Type:** `{result.document.file_type}`")
        st.write(f"**Created At:** `{result.document.created_at}`")

    with right_column:
        st.write(f"**Character Count:** `{len(result.document.content)}`")
        st.write(f"**Serialized Chunks:** `{result.chunk_file_path}`")
        st.write(f"**Serialized Vectors:** `{result.vector_file_path}`")
        st.write(f"**FAISS Index:** `{result.index_file_path}`")
        st.write("**Document Metadata:**")
        st.json(result.document.metadata)


def _render_chunk_stats(result: ProcessingResult) -> None:
    """Display debugging metrics for the generated chunks."""

    st.header("Chunking Statistics")
    first_metric, second_metric, third_metric, fourth_metric = st.columns(4)

    first_metric.metric("Total Chunks", result.stats.chunk_count)
    second_metric.metric("Average Chunk Size", f"{result.stats.average_chunk_size:.1f}")
    third_metric.metric("Smallest Chunk", result.stats.smallest_chunk_size)
    fourth_metric.metric("Largest Chunk", result.stats.largest_chunk_size)

    st.caption(
        "Chunk statistics matter because chunk size distribution affects later "
        "embedding quality and semantic retrieval precision."
    )
    st.write(
        f"Configured chunk size: `{result.stats.chunk_size}` characters | "
        f"Configured overlap: `{result.stats.overlap}` characters"
    )


def _render_embedding_stats(result: ProcessingResult) -> None:
    """Display debugging metrics for generated embeddings."""

    st.header("Embedding Statistics")
    first_metric, second_metric, third_metric, fourth_metric = st.columns(4)

    first_metric.metric("Embeddings Generated", result.embedding_stats.total_embeddings)
    second_metric.metric("Embedding Dimension", result.embedding_stats.embedding_dimension)
    third_metric.metric("Average Vector Norm", f"{result.embedding_stats.average_vector_norm:.4f}")
    fourth_metric.metric("Largest Vector Norm", f"{result.embedding_stats.largest_vector_norm:.4f}")

    st.write(f"**Embedding Model:** `{result.embedding_stats.model_name}`")
    st.write(
        f"**Batch Size:** `{result.embedding_stats.batch_size}` | "
        f"**Normalized:** `{result.embedding_stats.normalized_embeddings}` | "
        f"**Smallest Vector Norm:** `{result.embedding_stats.smallest_vector_norm:.4f}`"
    )
    st.caption(
        "Embeddings turn meaning into vectors. Keyword search looks for exact "
        "terms, while vector search looks for nearby meanings in embedding space."
    )


def _render_index_stats(result: ProcessingResult) -> None:
    """Display FAISS index metrics for retrieval debugging."""

    st.header("Vector Index Statistics")
    first_metric, second_metric, third_metric = st.columns(3)

    first_metric.metric("Indexed Vectors", result.index_stats.indexed_vectors)
    second_metric.metric("Index Dimension", result.index_stats.embedding_dimension)
    third_metric.metric("Index Type", result.index_stats.index_type)

    st.write(f"**Metric:** `{result.index_stats.metric}`")
    st.write(f"**Index Metadata:** `{result.index_metadata_file_path}`")
    st.caption(
        "FAISS searches nearest vectors. With normalized embeddings, inner "
        "product behaves like cosine similarity for semantic retrieval."
    )


def _render_rag_search(
    result: ProcessingResult,
    pipeline: ProcessingPipeline,
    top_k: int,
    ollama_model: str,
    temperature: float,
    show_prompt_debug: bool,
) -> None:
    """Render RAG query controls, retrieved context, and generated answers."""

    st.header("RAG Response Generation")
    query = st.text_input("User Query", placeholder="Ask a question about the uploaded document")

    if not query.strip():
        st.info("Enter a query to retrieve context and generate a grounded answer.")
        return

    if result.index_stats.indexed_vectors == 0:
        st.warning("No vector index is available for this document.")
        return

    retriever = Retriever(
        vector_store=pipeline.vector_store,
        embedding_engine=pipeline.embedder,
        top_k=top_k,
    )

    try:
        rag_pipeline = RAGPipeline(
            retriever=retriever,
            prompt_builder=PromptBuilder(),
            llm_client=OllamaClient(model=ollama_model, temperature=temperature),
            top_k=top_k,
        )
        generated_response = rag_pipeline.ask(query, top_k=top_k)
    except Exception as error:
        st.error(f"RAG generation failed: {error}")
        return

    _render_generated_response(generated_response, show_prompt_debug=show_prompt_debug)
    _render_retrieval_results(generated_response.retrieved_chunks)


def _render_generated_response(
    generated_response: GeneratedResponse,
    show_prompt_debug: bool,
) -> None:
    """Display the generated answer and optional prompt debugging details."""

    st.subheader("Generated Response")
    st.write(generated_response.response)
    st.caption(
        f"Model: `{generated_response.metadata.get('llm_model')}` | "
        f"Retrieved chunks: `{generated_response.metadata.get('retrieved_chunk_count')}`"
    )

    if show_prompt_debug:
        with st.expander("Prompt Debug", expanded=False):
            st.write("**System Prompt:**")
            st.code(str(generated_response.metadata.get("system_prompt", "")), language="text")
            st.write("**User Prompt:**")
            st.code(str(generated_response.metadata.get("prompt", "")), language="text")


def _render_retrieval_results(results: list[RetrievalResult]) -> None:
    """Display ranked retrieval results with similarity scores."""

    if not results:
        st.warning("No matching chunks were retrieved.")
        return

    for rank, result in enumerate(results, start=1):
        title = f"Rank {rank} | Score {result.similarity_score:.4f}"
        with st.expander(title, expanded=rank == 1):
            st.progress(max(0.0, min(1.0, result.similarity_score)))
            st.write(result.text)
            st.write("**Source Metadata:**")
            st.json(result.metadata)


def _render_embedded_chunk_previews(result: ProcessingResult) -> None:
    """Display chunk text plus embedding previews for inspection."""

    st.header("Chunk and Embedding Previews")

    if not result.embedded_chunks:
        st.warning("No embeddings were generated for this document.")
        return

    for embedded_chunk in result.embedded_chunks:
        embedding_preview = _format_embedding_preview(embedded_chunk.embedding)
        preview_title = (
            f"Chunk {embedded_chunk.metadata.get('chunk_index', '?')} | "
            f"{len(embedded_chunk.text)} chars | "
            f"{len(embedded_chunk.embedding)} dims"
        )
        with st.expander(preview_title, expanded=embedded_chunk.metadata.get("chunk_index") == 0):
            st.write(embedded_chunk.text)
            st.write("**Embedding Preview:**")
            st.code(embedding_preview, language="text")
            st.write("**Embedding Metadata:**")
            st.json(embedded_chunk.metadata)


def _format_embedding_preview(embedding: list[float], limit: int = 8) -> str:
    """Return a short readable preview of an embedding vector."""

    preview_values = ", ".join(f"{value:.4f}" for value in embedding[:limit])
    suffix = ", ..." if len(embedding) > limit else ""
    return f"[{preview_values}{suffix}]"


def main() -> None:
    """Streamlit entry point."""

    render_app()
