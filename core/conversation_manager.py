"""Conversation memory management for Aion.

This module provides a foundation for session-based conversational memory.
It keeps user/assistant turns in memory and persists them independently of the
document retrieval layer.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable
import uuid

from .memory_models import ConversationTurn
from .memory_store import MemoryStore


class ConversationManager:
    """Manage conversational history independently from retrieval."""

    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        session_id: str = "default",
    ) -> None:
        self.memory_store = memory_store or MemoryStore()
        self.session_id = session_id
        self.turns: list[ConversationTurn] = []

    def add_turn(
        self,
        user_message: str,
        assistant_message: str,
        turn_id: str | None = None,
        timestamp: str | None = None,
    ) -> ConversationTurn:
        """Append a new conversation turn to the current session."""
        turn_id = turn_id or uuid.uuid4().hex
        timestamp = timestamp or self._current_timestamp()
        turn = ConversationTurn(
            turn_id=turn_id,
            user_message=user_message,
            assistant_message=assistant_message,
            timestamp=timestamp,
        )
        self.turns.append(turn)
        return turn

    def get_recent_turns(self, limit: int = 10) -> list[ConversationTurn]:
        """Return the most recent conversation turns."""
        if limit <= 0:
            return []
        return self.turns[-limit:]

    def load(self) -> list[ConversationTurn]:
        """Load history from persistent storage into memory."""
        self.turns = self.memory_store.load(self.session_id)
        return self.turns

    def save(self) -> Path:
        """Save the current conversation history to disk."""
        return self.memory_store.save(self.turns, session_id=self.session_id)

    def clear(self, save_after_clear: bool = False) -> None:
        """Clear the in-memory conversation history."""
        self.turns = []
        if save_after_clear:
            self.save()

    def _current_timestamp(self) -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
