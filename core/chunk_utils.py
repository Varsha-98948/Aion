"""Reusable helpers for Aion's document-to-chunk transformation.

Keeping chunk-related text utilities in a dedicated module avoids repeating
string-processing logic inside the main ``Chunker`` class. This separation also
keeps the architecture easier to understand: the chunker orchestrates the
workflow, while these helpers focus on low-level text operations.
"""

from __future__ import annotations

import re

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def clean_text_for_chunking(text: str) -> str:
    """Normalize text while preserving paragraph boundaries.

    Chunking quality in RAG depends on clean and predictable input. Excess
    whitespace noise can create awkward fragments, while preserving paragraph
    breaks helps the chunker keep related ideas together before embeddings are
    generated.
    """

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized_text.split("\n")]
    cleaned_text = "\n".join(normalized_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
    return cleaned_text.strip()


def split_into_paragraphs(text: str) -> list[str]:
    """Split normalized text into paragraph blocks.

    Paragraph-aware chunking is a strong default for RAG because paragraphs
    often already represent human-authored idea boundaries. Respecting those
    boundaries usually produces more meaningful embeddings than fixed-size cuts.
    """

    if not text.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    return [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]


def split_into_sentences(text: str) -> list[str]:
    """Split a text block into sentence-like units.

    This is a lightweight fallback used when a paragraph is too large to fit
    inside a target chunk. Sentence-aware splitting is valuable because it
    preserves semantic continuity better than cutting at arbitrary character
    positions.
    """

    stripped_text = text.strip()
    if not stripped_text:
        return []

    sentences = SENTENCE_SPLIT_PATTERN.split(stripped_text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def join_segments(segments: list[str], separator: str = " ") -> str:
    """Join text segments while ignoring empty values."""

    return separator.join(segment for segment in segments if segment.strip()).strip()


def joined_length(segments: list[str], separator: str = " ") -> int:
    """Return the character length of joined segments.

    Measuring joined length centrally keeps chunk-size logic deterministic and
    avoids repeated ad hoc calculations inside the main chunker.
    """

    return len(join_segments(segments, separator=separator))


def split_long_text_by_words(text: str, max_length: int) -> list[str]:
    """Split very long text into word-preserving fragments.

    This is the final safety net for unusually long sentences or paragraphs.
    We still prefer semantic boundaries first, but word-aware fallback splitting
    is better than truncation because it preserves all source content.
    """

    stripped_text = text.strip()
    if not stripped_text:
        return []

    if max_length <= 0:
        raise ValueError("max_length must be greater than zero.")

    if len(stripped_text) <= max_length:
        return [stripped_text]

    words = stripped_text.split()
    fragments: list[str] = []
    current_words: list[str] = []

    for word in words:
        if len(word) > max_length:
            if current_words:
                fragments.append(join_segments(current_words, separator=" "))
                current_words = []

            for start_index in range(0, len(word), max_length):
                fragments.append(word[start_index : start_index + max_length])
            continue

        candidate_words = current_words + [word]
        if joined_length(candidate_words, separator=" ") <= max_length or not current_words:
            current_words = candidate_words
            continue

        fragments.append(join_segments(current_words, separator=" "))
        current_words = [word]

    if current_words:
        fragments.append(join_segments(current_words, separator=" "))

    return _rebalance_trailing_fragment(fragments, max_length=max_length)


def _rebalance_trailing_fragment(fragments: list[str], max_length: int) -> list[str]:
    """Reduce extremely small final fragments created by fallback splitting."""

    if len(fragments) < 2:
        return fragments

    minimum_tail_length = max(20, max_length // 4)
    if len(fragments[-1]) >= minimum_tail_length:
        return fragments

    previous_words = fragments[-2].split()
    trailing_words = fragments[-1].split()

    while previous_words:
        moved_word = previous_words[-1]
        candidate_trailing_words = [moved_word] + trailing_words
        if joined_length(candidate_trailing_words, separator=" ") > max_length:
            break

        previous_words.pop()
        trailing_words = candidate_trailing_words

        if len(join_segments(trailing_words, separator=" ")) >= minimum_tail_length:
            break

    rebalanced_fragments = fragments[:-2]
    if previous_words:
        rebalanced_fragments.append(join_segments(previous_words, separator=" "))
    rebalanced_fragments.append(join_segments(trailing_words, separator=" "))
    return rebalanced_fragments


def group_sentences_by_size(sentences: list[str], max_length: int) -> list[str]:
    """Group sentences into chunk-sized text units.

    Grouping multiple neighboring sentences keeps local context together while
    still respecting chunk-size limits. This prepares the document for
    embedding-ready chunks without forcing the main chunker to juggle the
    sentence assembly details itself.
    """

    if max_length <= 0:
        raise ValueError("max_length must be greater than zero.")

    grouped_sentences: list[str] = []
    current_group: list[str] = []

    for sentence in sentences:
        stripped_sentence = sentence.strip()
        if not stripped_sentence:
            continue

        if len(stripped_sentence) > max_length:
            if current_group:
                grouped_sentences.append(join_segments(current_group, separator=" "))
                current_group = []

            grouped_sentences.extend(split_long_text_by_words(stripped_sentence, max_length))
            continue

        candidate_group = current_group + [stripped_sentence]
        if joined_length(candidate_group, separator=" ") <= max_length or not current_group:
            current_group = candidate_group
            continue

        grouped_sentences.append(join_segments(current_group, separator=" "))
        current_group = [stripped_sentence]

    if current_group:
        grouped_sentences.append(join_segments(current_group, separator=" "))

    return grouped_sentences


def build_overlap_segments(
    segments: list[str],
    target_overlap: int,
    separator: str = " ",
) -> list[str]:
    """Return trailing segments that should be repeated into the next chunk.

    Overlap improves retrieval quality because many ideas span boundaries. By
    repeating a small amount of trailing context in the next chunk, we reduce
    the chance that a relevant fact gets isolated away from the sentence that
    explains it.
    """

    if target_overlap <= 0 or len(segments) <= 1:
        return []

    overlap_segments: list[str] = []

    for segment in reversed(segments):
        candidate_segments = [segment] + overlap_segments
        if joined_length(candidate_segments, separator=separator) > target_overlap and overlap_segments:
            break

        overlap_segments = candidate_segments

    if len(overlap_segments) >= len(segments):
        return overlap_segments[1:]

    return overlap_segments


def is_valid_chunk_text(text: str, min_length: int = 1) -> bool:
    """Return ``True`` when chunk text is meaningful enough to keep.

    Validation matters because empty or tiny noise fragments dilute a vector
    index and waste embedding work. Good chunk hygiene leads to cleaner
    retrieval later when FAISS searches over the stored vectors.
    """

    stripped_text = text.strip()
    if len(stripped_text) < min_length:
        return False

    return any(character.isalnum() for character in stripped_text)


__all__ = [
    "build_overlap_segments",
    "clean_text_for_chunking",
    "group_sentences_by_size",
    "is_valid_chunk_text",
    "join_segments",
    "joined_length",
    "split_into_paragraphs",
    "split_into_sentences",
    "split_long_text_by_words",
]
