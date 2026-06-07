"""Developer-focused Streamlit dashboard for Aion's semantic preprocessing flow.

The UI stays intentionally thin. Its job is to collect input, call the backend
pipeline, and visualize results for debugging. Keeping Streamlit separate from
pipeline orchestration preserves clean layering and keeps the core system
reusable from scripts, tests, or future APIs.
"""

from __future__ import annotations

from pathlib import Path
import json

import streamlit as st

from core.chunker import Chunker
from core.conversation_manager import ConversationManager
from core.embedder import EmbeddingEngine
from core.knowledge_base import KnowledgeBaseClearError, KnowledgeBaseManager
from core.llm_client import OllamaClient
from core.pipeline import ProcessingPipeline, ProcessingResult
from core.prompt_builder import PromptBuilder
from core.rag_pipeline import RAGPipeline
from core.retriever import Retriever
from core.retrieval_models import RetrievalResult
from core.response_models import GeneratedResponse
from core.vector_store import VectorStore

UPLOADS_DIRECTORY = Path("data/uploads")
DEFAULT_OLLAMA_MODELS = ["gemma", "mistral", "llama3"]
KNOWLEDGE_BASE_DIRECTORY = Path("data/knowledge_base")
INDEXES_DIRECTORY = Path("data/indexes")


def _find_vector_index_directory(document_id: str) -> Path | None:
    """Find a persisted FAISS index directory for a given document ID.

    This is robust against folder naming conventions used during index creation.
    It scans all known index directories and checks their metadata for a matching
    document_id.
    """
    if not INDEXES_DIRECTORY.exists():
        return None

    for candidate_dir in INDEXES_DIRECTORY.iterdir():
        if not candidate_dir.is_dir():
            continue

        metadata_path = candidate_dir / VectorStore.METADATA_FILENAME
        if not metadata_path.exists():
            continue

        try:
            with metadata_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except json.JSONDecodeError:
            continue

        for record in payload.get("records", []):
            if record.get("document_id") == document_id:
                return candidate_dir

        if candidate_dir.name.endswith(document_id[:12]):
            return candidate_dir

    return None


def _find_latest_vector_index(kb_manager: KnowledgeBaseManager) -> tuple[str, Path] | None:
    """Find the most recently added document's persisted vector index.
    
    Returns:
        Tuple of (document_id, index_directory) if found, None otherwise.
    """
    documents = kb_manager.list_documents()
    if not documents:
        return None

    for document in reversed(documents):
        index_dir = _find_vector_index_directory(document.document_id)
        if index_dir is not None:
            return document.document_id, index_dir

    return None


def _find_registered_vector_indexes(kb_manager: KnowledgeBaseManager) -> list[tuple[str, Path]]:
    """Find persisted vector indexes for all registered knowledge-base documents."""

    index_entries: list[tuple[str, Path]] = []
    for document in kb_manager.list_documents():
        index_dir = _find_vector_index_directory(document.document_id)
        if index_dir is not None:
            index_entries.append((document.document_id, index_dir))

    return index_entries


def _load_vector_store_from_index(index_directory: Path, embedding_engine: EmbeddingEngine) -> VectorStore | None:
    """Load a vector store from a persisted FAISS index directory.
    
    Args:
        index_directory: Path to directory containing index.faiss and index_metadata.json
        embedding_engine: EmbeddingEngine for query embedding during retrieval
    
    Returns:
        Loaded VectorStore if successful, None if loading fails.
    """
    try:
        vector_store = VectorStore(index_directory=index_directory)
        vector_store.load_index(index_directory=index_directory)
        return vector_store
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        st.warning(f"Could not load vector index: {e}")
        return None


def _load_unified_kb_vector_store(
    kb_manager: KnowledgeBaseManager,
    embedding_engine: EmbeddingEngine,
) -> tuple[VectorStore, list[str]] | None:
    """Load and merge all registered knowledge-base indexes into one search store."""

    index_entries = _find_registered_vector_indexes(kb_manager)
    if not index_entries:
        return None

    unified_store = VectorStore(index_directory=INDEXES_DIRECTORY)
    loaded_document_ids: list[str] = []

    for document_id, index_dir in index_entries:
        document_store = _load_vector_store_from_index(index_dir, embedding_engine)
        if document_store is None:
            continue

        try:
            unified_store.merge_from_store(document_store)
        except ValueError as error:
            st.warning(f"Could not merge vector index for document `{document_id}`: {error}")
            continue

        loaded_document_ids.append(document_id)

    if unified_store.record_count == 0:
        return None

    return unified_store, loaded_document_ids


def _get_kb_index_stats(vector_store: VectorStore) -> dict:
    """Extract index statistics from a loaded vector store."""
    return {
        "indexed_vectors": vector_store.record_count,
        "embedding_dimension": vector_store.embedding_dimension,
        "index_type": "IndexFlatIP",
        "metric": "cosine_similarity_via_normalized_inner_product",
        "index_directory": str(vector_store.index_directory),
    }


def _render_knowledge_base_sidebar(kb_manager: KnowledgeBaseManager) -> None:
    """Display knowledge base statistics and management in sidebar."""

    with st.sidebar:
        st.divider()
        st.header("📚 Knowledge Base")

        stats = kb_manager.get_statistics()
        
        col1, col2 = st.columns(2)
        col1.metric("Documents", stats.total_documents)
        col2.metric("Total Chunks", stats.total_chunks)

        if stats.total_documents > 0:
            col3, col4 = st.columns(2)
            col3.metric("Avg Chunks/Doc", f"{stats.average_chunks_per_document:.1f}")
            col4.metric("Total Chunks", stats.total_chunks)

            with st.expander("📖 Stored Documents", expanded=False):
                documents = kb_manager.list_documents()
                for idx, doc_meta in enumerate(documents, start=1):
                    st.write(
                        f"{idx}. **{doc_meta.filename}** "
                        f"({doc_meta.file_type.upper()}) "
                        f"| {doc_meta.chunk_count} chunks"
                    )
                    st.caption(f"Added: {doc_meta.date_added[:10]}")

            with st.expander("⚙️ Knowledge Base Controls", expanded=False):
                if st.button("Export Knowledge Base", use_container_width=True):
                    try:
                        export_path = kb_manager.export_knowledge_base(
                            "data/knowledge_base/export_backup.json"
                        )
                        st.success(f"✓ Exported to {export_path}")
                    except Exception as e:
                        st.error(f"Export failed: {e}")

                if st.button("Clear Knowledge Base", use_container_width=True):
                    if st.checkbox("I understand this will delete all metadata", key="confirm_clear_kb"):
                        kb_manager.clear_knowledge_base()
                        st.success("✓ Knowledge Base cleared")
                        st.rerun()


def render_app() -> None:
    """Render Aion's preprocessing and embedding dashboard with KB-first initialization."""

    st.set_page_config(page_title="Aion", layout="wide")
    st.title("Aion")
    st.subheader("Local-First Semantic Memory Dashboard")

    # Initialize configuration
    default_chunker = Chunker()
    default_embedder = EmbeddingEngine()
    ollama_discovery_client = OllamaClient(model="gemma")
    installed_ollama_models = ollama_discovery_client.list_models()
    ollama_model_options = _build_ollama_model_options(installed_ollama_models)

    # Configuration sidebar (unchanged)
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
        ollama_model = st.selectbox(
            "Ollama Model",
            options=ollama_model_options,
            index=_get_default_ollama_model_index(ollama_model_options),
            help="Local Ollama model used for grounded answer generation.",
        )
        if installed_ollama_models:
            st.caption(f"Installed models detected: {', '.join(installed_ollama_models)}")
        else:
            st.caption("No installed Ollama models detected. Choose a model, then install it if needed.")
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

    # Initialize pipeline and conversation manager
    pipeline = ProcessingPipeline(
        chunker=Chunker(chunk_size=int(chunk_size), overlap=int(overlap)),
        embedder=EmbeddingEngine(
            model_name=embedding_model.strip() or EmbeddingEngine.DEFAULT_MODEL_NAME,
            batch_size=int(batch_size),
            normalize_embeddings=normalize_embeddings,
        ),
    )

    if "conversation_session_id" not in st.session_state:
        st.session_state["conversation_session_id"] = "default"

    conversation_manager = _get_conversation_manager(st.session_state["conversation_session_id"])

    # Initialize and load knowledge base
    kb_manager = KnowledgeBaseManager(kb_directory=KNOWLEDGE_BASE_DIRECTORY)
    _render_knowledge_base_sidebar(kb_manager)

    # Try to load existing knowledge base index
    kb_has_documents = kb_manager.get_document_count() > 0
    loaded_vector_store = None
    loaded_document_ids: list[str] = []

    if kb_has_documents:
        unified_index_info = _load_unified_kb_vector_store(kb_manager, pipeline.embedder)
        if unified_index_info:
            loaded_vector_store, loaded_document_ids = unified_index_info

    # Show description
    st.write(
        "This dashboard shows Aion's semantic preprocessing layer: document "
        "loading, chunk generation, embedding generation, and developer-focused "
        "vector observability before retrieval and FAISS indexing."
    )

    if loaded_vector_store is not None:
        st.success(
            "Knowledge Base Ready: "
            f"{loaded_vector_store.record_count} chunks across "
            f"{len(loaded_document_ids)} indexed documents"
        )
    else:
        st.info("No indexed knowledge available yet.")

    # ========================================================================
    # SECTION 1: Ask Aion from Knowledge Base (always visible if KB has content)
    # ========================================================================
    if loaded_vector_store is not None:
        st.divider()
        _render_ask_aion_from_kb(
            vector_store=loaded_vector_store,
            pipeline=pipeline,
            conversation_manager=conversation_manager,
            document_ids=loaded_document_ids,
            top_k=int(top_k),
            ollama_model=ollama_model,
            installed_ollama_models=installed_ollama_models,
            temperature=float(temperature),
            show_prompt_debug=show_prompt_debug,
        )
        st.divider()

    # ========================================================================
    # SECTION 2: Upload New Document
    # ========================================================================
    if kb_has_documents:
        st.header("Add Document to Knowledge Base")
        st.caption("Upload a new document to add to your knowledge base")
    else:
        st.header("Get Started - Upload Your First Document")
        if not loaded_vector_store:
            st.warning("📚 Your Knowledge Base is empty. Upload a document to get started.")

    upload_mode = st.radio(
        "Upload Mode",
        options=["Temporary", "Add To Knowledge Base"],
        help=(
            "Temporary: Process and search only during this session. "
            "Add To Knowledge Base: Process, register, and persist for future sessions."
        ),
    )

    uploaded_file = st.file_uploader(
        "Upload a document",
        type=["pdf", "txt", "md"],
        help="Supported formats match the current ingestion layer.",
    )

    if uploaded_file is not None:
        saved_file_path = _save_uploaded_file(uploaded_file.name, bytes(uploaded_file.getbuffer()))

        try:
            result = pipeline.process_file(saved_file_path, filename=uploaded_file.name, save_output=True)
        except Exception as error:
            st.error(f"Pipeline execution failed: {error}")
            return

        # Handle upload mode: register in knowledge base if needed
        if upload_mode == "Add To Knowledge Base":
            try:
                kb_manager.register_document(
                    document_id=result.document.doc_id,
                    filename=result.document.filename,
                    file_type=result.document.file_type,
                    chunk_count=result.stats.chunk_count,
                    custom_metadata={
                        "source_path": str(saved_file_path),
                        "embedding_model": result.embedding_stats.model_name,
                        "chunk_config": {
                            "chunk_size": result.stats.chunk_size,
                            "overlap": result.stats.overlap,
                        },
                    },
                )
                st.success(f"✓ Document registered in Knowledge Base (ID: `{result.document.doc_id}`)")
            except ValueError as error:
                st.warning(f"Document already in Knowledge Base: {error}")
        else:
            st.info(f"ℹ️ Document processed in temporary mode (not persisted to Knowledge Base)")

        # ====================================================================
        # SECTION 3: Display newly uploaded document details and statistics
        # ====================================================================
        st.divider()
        st.header("Uploaded Document Details")

        _render_document_info(result)
        _render_chunk_stats(result)
        _render_embedded_chunk_previews(result)
        _render_embedding_stats(result)
        _render_index_stats(result)

        # ====================================================================
        # SECTION 4: Ask Aion about newly uploaded document
        # ====================================================================
        st.divider()
        _render_ask_aion(
            result,
            pipeline=pipeline,
            conversation_manager=conversation_manager,
            top_k=int(top_k),
            ollama_model=ollama_model,
            installed_ollama_models=installed_ollama_models,
            temperature=float(temperature),
            show_prompt_debug=show_prompt_debug,
        )

    # ========================================================================
    # SECTION 5: Conversation Memory (always visible)
    # ========================================================================
    st.divider()
    _render_conversation_memory_debug(conversation_manager)


def _save_uploaded_file(filename: str, file_bytes: bytes) -> Path:
    """Persist uploaded files so backend processing works with real paths."""

    UPLOADS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    output_path = UPLOADS_DIRECTORY / filename

    with output_path.open("wb") as file:
        file.write(file_bytes)

    return output_path


def _build_ollama_model_options(installed_models: list[str]) -> list[str]:
    """Return dropdown options with discovered local models first."""

    options: list[str] = []
    for model_name in [*installed_models, *DEFAULT_OLLAMA_MODELS]:
        if model_name not in options:
            options.append(model_name)

    return options


def _get_default_ollama_model_index(model_options: list[str]) -> int:
    """Prefer gemma as the default visible model when available."""

    if "gemma" in model_options:
        return model_options.index("gemma")

    for option_index, model_name in enumerate(model_options):
        if _normalize_ollama_model_name(model_name) == "gemma":
            return option_index

    return 0


def _normalize_ollama_model_name(model_name: str) -> str:
    """Normalize Ollama tags so gemma and gemma:latest compare cleanly."""

    return model_name.split(":", maxsplit=1)[0].strip().lower()


def _is_ollama_model_installed(selected_model: str, installed_models: list[str]) -> bool:
    """Return True when the selected model exists in local Ollama models."""

    selected_model_normalized = _normalize_ollama_model_name(selected_model)
    return any(
        installed_model == selected_model
        or _normalize_ollama_model_name(installed_model) == selected_model_normalized
        for installed_model in installed_models
    )


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


def _render_ask_aion_from_kb(
    vector_store: VectorStore,
    pipeline: ProcessingPipeline,
    conversation_manager: ConversationManager,
    document_ids: list[str],
    top_k: int,
    ollama_model: str,
    installed_ollama_models: list[str],
    temperature: float,
    show_prompt_debug: bool,
) -> None:
    """Render the RAG interaction for a document loaded from the knowledge base.
    
    This allows querying previously indexed KB documents without uploading a new file.
    """

    st.header("Ask Aion")
    st.caption(
        "Querying entire Knowledge Base "
        f"({len(document_ids)} indexed documents, {vector_store.record_count} chunks)"
    )
    st.caption("USER QUERY -> SEMANTIC RETRIEVAL -> CONTEXT INJECTION -> OLLAMA RESPONSE GENERATION")

    query = st.text_area(
        "User Query",
        placeholder=(
            "What does this document say about semantic search?\n"
            "Summarize the key concepts"
        ),
        height=120,
        key="kb_query",
    )
    generate_response = st.button("Generate Response", type="primary", key="kb_generate")

    if not generate_response:
        return

    if not query.strip():
        st.warning("Enter a query before generating a response.")
        return

    if vector_store.record_count == 0:
        st.warning("No vectors available in the knowledge base index.")
        return

    if not _is_ollama_model_installed(ollama_model, installed_ollama_models):
        st.error(
            "Selected Ollama model is not installed locally.\n\n"
            f"Run:\nollama pull {ollama_model}"
        )
        return

    retriever = Retriever(
        vector_store=vector_store,
        embedding_engine=pipeline.embedder,
        top_k=top_k,
    )

    try:
        prompt_builder = PromptBuilder()
        rag_pipeline = RAGPipeline(
            retriever=retriever,
            prompt_builder=prompt_builder,
            llm_client=OllamaClient(model=ollama_model, temperature=temperature),
            conversation_manager=conversation_manager,
            top_k=top_k,
            memory_window=5,
        )
        generated_response = rag_pipeline.ask(query, top_k=top_k)
    except Exception as error:
        st.error(f"RAG generation failed: {error}")
        return

    st.subheader("Response Metrics")
    metric_col_1, metric_col_2, metric_col_3 = st.columns(3)
    metric_col_1.metric("Memory Turns Used", generated_response.metadata.get("memory_turn_count", 0))
    metric_col_2.metric("Retrieved Chunks", generated_response.metadata.get("retrieved_chunk_count", 0))
    metric_col_3.metric("Vector Index Size", vector_store.record_count)

    _render_generated_response(
        generated_response,
        prompt_builder=prompt_builder,
        show_prompt_debug=show_prompt_debug,
    )
    _render_retrieval_results(generated_response.retrieved_chunks)


def _render_ask_aion(
    result: ProcessingResult,
    pipeline: ProcessingPipeline,
    conversation_manager: ConversationManager,
    top_k: int,
    ollama_model: str,
    installed_ollama_models: list[str],
    temperature: float,
    show_prompt_debug: bool,
) -> None:
    """Render the visible user-facing RAG interaction flow."""

    st.header("Ask Aion")
    st.caption("USER QUERY -> SEMANTIC RETRIEVAL -> CONTEXT INJECTION -> OLLAMA RESPONSE GENERATION")
    query = st.text_area(
        "User Query",
        placeholder=(
            "What does this document say about semantic search?\n"
            "Summarize the memory architecture"
        ),
        height=120,
    )
    generate_response = st.button("Generate Response", type="primary")

    if not generate_response:
        return

    if not query.strip():
        st.warning("Enter a query before generating a response.")
        return

    if result.index_stats.indexed_vectors == 0:
        st.warning("No vector index is available for this document.")
        return

    if not _is_ollama_model_installed(ollama_model, installed_ollama_models):
        st.error(
            "Selected Ollama model is not installed locally.\n\n"
            f"Run:\nollama pull {ollama_model}"
        )
        return

    retriever = Retriever(
        vector_store=pipeline.vector_store,
        embedding_engine=pipeline.embedder,
        top_k=top_k,
    )

    try:
        prompt_builder = PromptBuilder()
        rag_pipeline = RAGPipeline(
            retriever=retriever,
            prompt_builder=prompt_builder,
            llm_client=OllamaClient(model=ollama_model, temperature=temperature),
            conversation_manager=conversation_manager,
            top_k=top_k,
            memory_window=5,
        )
        generated_response = rag_pipeline.ask(query, top_k=top_k)
    except Exception as error:
        st.error(f"RAG generation failed: {error}")
        return

    st.subheader("Response Metrics")
    metric_col_1, metric_col_2 = st.columns(2)
    metric_col_1.metric("Memory Turns Used", generated_response.metadata.get("memory_turn_count", 0))
    metric_col_2.metric("Retrieved Chunks", generated_response.metadata.get("retrieved_chunk_count", 0))

    _render_generated_response(
        generated_response,
        prompt_builder=prompt_builder,
        show_prompt_debug=show_prompt_debug,
    )
    _render_retrieval_results(generated_response.retrieved_chunks)


def _get_conversation_manager(session_id: str) -> ConversationManager:
    """Return or initialize a conversation manager for the current session."""
    manager = st.session_state.get("conversation_manager")
    if manager is None or manager.session_id != session_id:
        manager = ConversationManager(session_id=session_id)
        manager.load()
        st.session_state["conversation_manager"] = manager
    return manager


def _render_conversation_memory_debug(manager: ConversationManager) -> None:
    """Display conversational memory diagnostics and controls."""
    st.header("Conversation Memory Debug")

    current_session_id = st.text_input(
        "Session ID",
        value=manager.session_id,
        key="conversation_session_id",
        help="Identifier used to persist conversation history on disk.",
    )

    if current_session_id != manager.session_id:
        manager = ConversationManager(session_id=current_session_id)
        manager.load()
        st.session_state["conversation_manager"] = manager

    session_file = manager.memory_store.memory_directory / f"{manager.session_id}.json"
    memory_exists = session_file.exists()

    session_info_col, turn_count_col = st.columns(2)
    session_info_col.write("**Session Information**")
    session_info_col.write(f"- Current session ID: `{manager.session_id}`")
    turn_count_col.write("**Stored Turns**")
    turn_count_col.write(f"- Number of stored turns: `{len(manager.turns)}`")

    with st.expander("Recent Conversation Turns", expanded=True):
        recent_turns = manager.get_recent_turns(limit=5)
        if not recent_turns:
            st.info("No conversation turns are currently stored for this session.")
        else:
            for index, turn in enumerate(recent_turns, start=1):
                with st.expander(f"Turn {index} — {turn.timestamp}", expanded=False):
                    st.write(f"**User:** {turn.user_message}")
                    st.write(f"**Assistant:** {turn.assistant_message}")
                    st.write(f"**Timestamp:** {turn.timestamp}")

    control_col_1, control_col_2, control_col_3 = st.columns(3)
    load_memory = control_col_1.button("Load Memory")
    save_memory = control_col_2.button("Save Memory")
    clear_memory = control_col_3.button("Clear Memory")

    if load_memory:
        manager.load()
        st.session_state["conversation_manager"] = manager
        st.success("Loaded memory from disk.")

    if save_memory:
        saved_path = manager.save()
        st.session_state["conversation_manager"] = manager
        st.success(f"Saved memory to disk at `{saved_path}`.")

    if clear_memory:
        manager.clear()
        st.session_state["conversation_manager"] = manager
        st.warning("Cleared in-memory conversation history. Use Save Memory to persist the cleared state.")

    st.write("**Memory File Information**")
    st.write(f"- Memory file path: `{session_file}`")
    st.write(f"- Exists on disk: `{memory_exists}`")


def _render_generated_response(
    generated_response: GeneratedResponse,
    prompt_builder: PromptBuilder,
    show_prompt_debug: bool,
) -> None:
    """Display the generated answer and optional prompt debugging details."""

    st.subheader("Generated Response")
    st.write(generated_response.response)
    st.caption(
        f"Model: `{generated_response.metadata.get('llm_model')}` | "
        f"Retrieved chunks: `{generated_response.metadata.get('retrieved_chunk_count')}`"
    )

    _render_citations(generated_response)
    _render_source_documents(generated_response)

    if show_prompt_debug:
        injected_context = prompt_builder.format_context(generated_response.retrieved_chunks)
        with st.expander("Prompt Debug", expanded=False):
            st.write("**Injected Context:**")
            st.code(injected_context, language="text")
            st.write("**System Prompt:**")
            st.code(str(generated_response.metadata.get("system_prompt", "")), language="text")
            st.write("**Final Prompt:**")
            st.code(str(generated_response.metadata.get("prompt", "")), language="text")


def _render_citations(generated_response: GeneratedResponse) -> None:
    """Display chunk-level citations used by the generated response."""

    st.subheader("Sources Used")

    if not generated_response.citations:
        st.info("No citations were produced for this response.")
        return

    for citation_index, citation in enumerate(generated_response.citations, start=1):
        preview = citation.chunk_text.strip() or "No chunk preview available."
        title = (
            f"{citation_index}. {citation.source_filename} | "
            f"chunk {citation.chunk_index} | score {citation.similarity_score:.4f}"
        )
        with st.expander(title, expanded=citation_index == 1):
            filename_col, chunk_col, score_col = st.columns(3)
            filename_col.write(f"**Filename:** `{citation.source_filename}`")
            chunk_col.write(f"**Chunk Index:** `{citation.chunk_index}`")
            score_col.write(f"**Similarity Score:** `{citation.similarity_score:.4f}`")
            st.write("**Chunk Preview:**")
            st.write(preview)


def _render_source_documents(generated_response: GeneratedResponse) -> None:
    """Display document-level source aggregation for a generated response."""

    st.subheader("Source Documents")

    if not generated_response.source_documents:
        st.info("No source document summaries were produced for this response.")
        return

    st.table(
        [
            {
                "filename": source_document.source_filename,
                "chunks_used": source_document.chunk_count_referenced,
                "average_similarity_score": f"{source_document.avg_similarity_score:.4f}",
            }
            for source_document in generated_response.source_documents
        ]
    )


def _render_retrieval_results(results: list[RetrievalResult]) -> None:
    """Display a developer-facing retrieval trace with full provenance."""

    st.subheader("Retrieval Inspector")

    if not results:
        st.warning("No matching chunks were retrieved.")
        return

    for rank, result in enumerate(results, start=1):
        title = (
            f"Rank {rank} | {result.source_filename} | "
            f"chunk {result.chunk_index} | score {result.similarity_score:.4f}"
        )
        with st.expander(title, expanded=rank == 1):
            rank_col, filename_col, chunk_col, score_col = st.columns(4)
            rank_col.write(f"**Rank:** `{rank}`")
            filename_col.write(f"**Source Filename:** `{result.source_filename}`")
            chunk_col.write(f"**Chunk Index:** `{result.chunk_index}`")
            score_col.write(f"**Similarity Score:** `{result.similarity_score:.4f}`")

            st.write(f"**Document ID:** `{result.document_id}`")
            st.progress(max(0.0, min(1.0, result.similarity_score)))
            st.write("**Chunk Preview:**")
            st.write(result.text)
            st.write("**Raw Metadata:**")
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
