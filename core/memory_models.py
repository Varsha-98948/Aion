"""Data models for conversational memory.

The memory models in this module are intentionally lightweight so that the
conversation layer can remain independent from retrieval, embedding, and
vector storage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ConversationTurn:
    """Represents a single turn in a conversation.

    Fields:
        turn_id: Unique identifier for the conversation turn.
        user_message: Text sent by the user.
        assistant_message: Text returned by the assistant.
        timestamp: ISO 8601 timestamp when the turn was recorded.
    """

    turn_id: str
    user_message: str
    assistant_message: str
    timestamp: str
