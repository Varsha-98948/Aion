"""Developer-focused Streamlit dashboard for Aion's preprocessing pipeline.

The UI stays intentionally thin. Its job is to collect input, call the backend
pipeline, and visualize results for debugging. Keeping Streamlit separate from
pipeline orchestration preserves clean layering and keeps the core system
reusable from scripts, tests, or future APIs.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.pipeline import ProcessingPipeline, ProcessingResult

UPLOADS_DIRECTORY = Path("data/uploads")


def render_app() -> None:
    """Render Aion's preprocessing dashboard."""

    st.set_page_config(page_title="Aion", layout="wide")
    st.title("Aion")
    st.subheader("Local-First AI Preprocessing Dashboard")
    st.write(
        "This dashboard covers the final preprocessing stage before embeddings: "
        "document loading, chunk generation, chunk serialization, and "
        "developer-focused inspection."
    )

    pipeline = ProcessingPipeline()

    with st.sidebar:
        st.header("Chunker Config")
        chunk_size = st.number_input(
            "Chunk Size",
            min_value=100,
            max_value=4000,
            value=pipeline.chunker.chunk_size,
            step=50,
            help="Character target for each chunk. This influences retrieval precision and context size later.",
        )
        overlap = st.number_input(
            "Overlap",
            min_value=0,
            max_value=max(int(chunk_size) - 1, 0),
            value=min(pipeline.chunker.overlap, max(int(chunk_size) - 1, 0)),
            step=10,
            help="Shared context between neighboring chunks to reduce boundary loss.",
        )

    pipeline.chunker.chunk_size = int(chunk_size)
    pipeline.chunker.overlap = int(overlap)
    pipeline.chunker.min_chunk_size = max(1, pipeline.chunker.chunk_size // 2)

    uploaded_file = st.file_uploader(
        "Upload a document",
        type=["pdf", "txt", "md"],
        help="Supported formats match the current ingestion layer.",
    )

    if uploaded_file is None:
        st.info("Upload a PDF, TXT, or Markdown file to inspect the chunking pipeline.")
        return

    saved_file_path = _save_uploaded_file(uploaded_file.name, bytes(uploaded_file.getbuffer()))
    result = pipeline.process_file(saved_file_path, filename=uploaded_file.name, save_output=True)

    _render_document_info(result)
    _render_chunk_stats(result)
    _render_chunk_previews(result)


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
        "Chunk statistics matter because chunk size distribution directly affects "
        "how useful later embeddings and retrieval will be."
    )
    st.write(
        f"Configured chunk size: `{result.stats.chunk_size}` characters | "
        f"Configured overlap: `{result.stats.overlap}` characters"
    )


def _render_chunk_previews(result: ProcessingResult) -> None:
    """Display chunk previews and chunk-level metadata for inspection."""

    st.header("Chunk Previews")

    if not result.chunks:
        st.warning("No chunks were generated for this document.")
        return

    for chunk in result.chunks:
        preview_title = (
            f"Chunk {chunk.chunk_index} | "
            f"{len(chunk.text)} chars | "
            f"{len(chunk.text.split())} words"
        )
        with st.expander(preview_title, expanded=chunk.chunk_index == 0):
            st.write(chunk.text)
            st.write("**Chunk Metadata:**")
            st.json(chunk.metadata)


def main() -> None:
    """Streamlit entry point."""

    render_app()
