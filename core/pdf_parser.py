"""PDF parsing utilities for Aion's ingestion pipeline.

This module converts raw PDF files into normalized plain text so the rest of
the AI pipeline can work with a consistent representation. PDF binaries contain
layout instructions, fonts, and positional data rather than clean semantic
text, so they must be normalized before chunking and embedding.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import fitz


class PageText(TypedDict):
    """Structured page-level text used for future citations and retrieval."""

    page_number: int
    text: str


class PDFMetadata(TypedDict):
    """Metadata captured during PDF extraction for downstream AI systems."""

    number_of_pages: int
    page_texts: list[PageText]


class PDFExtractionResult(TypedDict):
    """Normalized extraction result compatible with the Document schema."""

    content: str
    metadata: PDFMetadata


def _extract_page_text(page: fitz.Page) -> str:
    """Extract and lightly normalize text from a single PDF page.

    PDFs often store text in layout-oriented fragments, so we normalize each
    page into a plain-text string here before later chunking stages operate on
    it. Raw PDF page objects cannot be embedded directly because embedding
    models require textual input, not document rendering instructions.
    """

    return page.get_text("text").strip()


def extract_pdf_text(file_path: str) -> PDFExtractionResult:
    """Extract full text and page-level text from a PDF file.

    Page-level extraction is preserved because retrieval systems often need to
    point back to the exact page that supported an answer. Keeping a list of
    per-page text blocks now makes future chunk-to-page mapping, citations, and
    answer grounding much easier.

    The returned structure is intentionally aligned with Aion's ``Document``
    schema: the combined text can populate ``Document.content`` and the page
    details can live inside ``Document.metadata`` before chunking begins.
    """

    pdf_path = Path(file_path)
    page_texts: list[PageText] = []

    with fitz.open(pdf_path) as pdf_document:
        for page_index, page in enumerate(pdf_document, start=1):
            page_text = _extract_page_text(page)
            page_texts.append(
                {
                    "page_number": page_index,
                    "text": page_text,
                }
            )

        # Chunkers and embedders work best on normalized text, not raw PDF
        # binaries. Joining pages here creates the canonical full-document view
        # while still preserving page boundaries separately in metadata.
        full_text = "\n\n".join(page_entry["text"] for page_entry in page_texts)

        return {
            "content": full_text,
            "metadata": {
                "number_of_pages": len(pdf_document),
                "page_texts": page_texts,
            },
        }
