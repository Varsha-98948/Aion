"""Central document ingestion router for Aion.

This module is the single entry point for loading source documents into Aion's
internal ``Document`` schema. Routing logic is intentionally separated from
format-specific parsing logic so individual parsers can stay focused on text
extraction while this loader handles orchestration and normalization.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .pdf_parser import extract_pdf_text
from .schema import Document
from .text_parser import extract_text_file


ParserResult = dict[str, object]
ParserFunction = Callable[[str], ParserResult]


class DocumentLoader:
    """Load supported files into Aion's unified ``Document`` representation.

    Central ingestion control is important in AI systems because every document
    should pass through one predictable normalization path before chunking,
    embedding, and vector indexing. That makes downstream FAISS pipelines
    easier to extend, debug, and keep consistent across file types.
    """

    def __init__(self) -> None:
        # Keeping extension-to-parser routing in one place makes it easy to add
        # future formats such as DOCX or HTML without mixing that logic into
        # the parser implementations themselves.
        self._parsers: dict[str, ParserFunction] = {
            "pdf": extract_pdf_text,
            "txt": extract_text_file,
            "md": extract_text_file,
        }

    def load(self, file_path: str, filename: str | None = None) -> Document:
        """Load a file and return a normalized ``Document`` object."""

        path = Path(file_path)
        file_type = path.suffix.lower().lstrip(".")
        parser = self._get_parser(file_type)
        parsed_document = parser(str(path))

        return Document(
            filename=filename or path.name,
            file_type=file_type,
            content=self._extract_content(parsed_document),
            metadata=self._extract_metadata(parsed_document),
        )

    def _get_parser(self, file_type: str) -> ParserFunction:
        """Return the parser registered for a supported file type."""

        parser = self._parsers.get(file_type)
        if parser is None:
            raise ValueError(
                f"Unsupported file type: '{file_type}'. "
                "Supported types are: pdf, txt, md."
            )

        return parser

    @staticmethod
    def _extract_content(parsed_document: ParserResult) -> str:
        """Pull normalized text content from a parser result."""

        content = parsed_document.get("content", "")
        if not isinstance(content, str):
            raise TypeError("Parser output 'content' must be a string.")

        return content

    @staticmethod
    def _extract_metadata(parsed_document: ParserResult) -> dict[str, object]:
        """Pull metadata from a parser result in a schema-friendly form."""

        metadata = parsed_document.get("metadata", {})
        if not isinstance(metadata, dict):
            raise TypeError("Parser output 'metadata' must be a dictionary.")

        return metadata
