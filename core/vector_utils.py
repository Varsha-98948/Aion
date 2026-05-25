"""Utility helpers for working with semantic vectors in Aion.

These helpers stay separate from the embedding engine because vector math,
validation, and serialization are reusable concerns. Retrieval systems often
need these utilities in multiple places: during embedding generation, during
index insertion, and later when comparing vectors for semantic similarity.

Example cosine similarity usage:
    >>> from core.vector_utils import cosine_similarity
    >>> cosine_similarity([1.0, 0.0], [0.5, 0.5])
    0.7071067811865475
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import SupportsFloat

import numpy as np

NumericSequence = Sequence[SupportsFloat]


def serialize_embedding(vector: NumericSequence) -> list[float]:
    """Convert an embedding vector into a JSON-friendly float list.

    JSON is not the most storage-efficient vector format, but it is excellent
    for debugging and learning because it makes semantic data observable. That
    matters in AI systems: if embeddings look wrong, developers need an easy
    way to inspect the actual numbers being persisted.
    """

    normalized_vector = _to_numpy_vector(vector)
    return normalized_vector.astype(float).tolist()


def validate_embedding_vector(
    vector: NumericSequence,
    expected_dimension: int | None = None,
) -> list[float]:
    """Validate one embedding vector and return it as a float list."""

    serialized_vector = serialize_embedding(vector)

    if expected_dimension is not None and len(serialized_vector) != expected_dimension:
        raise ValueError(
            f"Embedding dimension mismatch. Expected {expected_dimension}, "
            f"received {len(serialized_vector)}."
        )

    return serialized_vector


def get_embedding_dimension(vector: NumericSequence) -> int:
    """Return the dimensionality of a single embedding vector."""

    return len(validate_embedding_vector(vector))


def validate_embedding_dimensions(
    vectors: Sequence[NumericSequence],
    expected_dimension: int | None = None,
) -> int:
    """Ensure a collection of vectors all shares the same dimensionality.

    Vector dimensionality matters because similarity search and vector indexes
    require consistent shapes. FAISS, cosine similarity, and nearest-neighbor
    search all assume every embedding lives in the same vector space.
    """

    if len(vectors) == 0:
        return expected_dimension or 0

    discovered_dimensions = {get_embedding_dimension(vector) for vector in vectors}
    if len(discovered_dimensions) != 1:
        raise ValueError("All embeddings must share the same dimension.")

    embedding_dimension = discovered_dimensions.pop()
    if expected_dimension is not None and embedding_dimension != expected_dimension:
        raise ValueError(
            f"Embedding dimension mismatch. Expected {expected_dimension}, "
            f"received {embedding_dimension}."
        )

    return embedding_dimension


def cosine_similarity(left_vector: NumericSequence, right_vector: NumericSequence) -> float:
    """Return cosine similarity between two embedding vectors.

    Semantic similarity works because embedding models map related meanings into
    nearby regions of vector space. Cosine similarity compares the angle between
    vectors, which gives a useful measure of conceptual closeness even when the
    raw text does not share many exact keywords.
    """

    left = _to_numpy_vector(left_vector)
    right = _to_numpy_vector(right_vector)

    if left.shape != right.shape:
        raise ValueError("Cosine similarity requires vectors with matching dimensions.")

    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0.0:
        raise ValueError("Cosine similarity is undefined for zero-length vectors.")

    return float(np.dot(left, right) / denominator)


def vector_norm(vector: NumericSequence) -> float:
    """Return the Euclidean norm of an embedding vector."""

    normalized_vector = _to_numpy_vector(vector)
    return float(np.linalg.norm(normalized_vector))


def _to_numpy_vector(vector: NumericSequence) -> np.ndarray:
    """Convert a supported vector input into a validated 1D numpy array."""

    normalized_vector = np.asarray(vector, dtype=np.float32)
    if normalized_vector.ndim != 1:
        raise ValueError("Embedding vectors must be one-dimensional.")
    if normalized_vector.size == 0:
        raise ValueError("Embedding vectors cannot be empty.")
    if not np.all(np.isfinite(normalized_vector)):
        raise ValueError("Embedding vectors must contain only finite numeric values.")

    return normalized_vector


__all__ = [
    "cosine_similarity",
    "get_embedding_dimension",
    "serialize_embedding",
    "validate_embedding_dimensions",
    "validate_embedding_vector",
    "vector_norm",
]
