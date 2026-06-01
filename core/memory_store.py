"""Persistence layer for conversational memory.

MemoryStore is responsible for saving and loading conversation history as
JSON. It is deliberately separate from document retrieval and embedding so
that conversation state can be managed independently.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .memory_models import ConversationTurn


class MemoryStore:
    """A file-backed store for conversation history.

    Conversations are persisted under a configurable directory with
    deterministic JSON serialization.
    """

    def __init__(self, memory_directory: str | Path = "data/memory") -> None:
        self.memory_directory = Path(memory_directory)
        self.memory_directory.mkdir(parents=True, exist_ok=True)

    def _get_memory_file_path(self, session_id: str = "default") -> Path:
        return self.memory_directory / f"{session_id}.json"

    def save(self, turns: Iterable[ConversationTurn], session_id: str = "default") -> Path:
        """Persist conversation turns to a deterministic JSON file."""
        path = self._get_memory_file_path(session_id)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        payload = [asdict(turn) for turn in turns]

        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(path)
        return path

    def load(self, session_id: str = "default") -> list[ConversationTurn]:
        """Load conversation turns from a JSON file."""
        path = self._get_memory_file_path(session_id)
        if not path.exists():
            return []

        raw_data = json.loads(path.read_text(encoding="utf-8"))
        return [ConversationTurn(**entry) for entry in raw_data]

    def exists(self, session_id: str = "default") -> bool:
        """Return True when a memory file exists for the session."""
        return self._get_memory_file_path(session_id).exists()

    def delete(self, session_id: str = "default") -> None:
        """Remove stored memory for the given session."""
        path = self._get_memory_file_path(session_id)
        if path.exists():
            path.unlink()
