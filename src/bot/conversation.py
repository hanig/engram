"""Conversation state management for the Slack bot."""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Conversation TTL in seconds (30 minutes)
CONVERSATION_TTL = 30 * 60

# Maximum history length
MAX_HISTORY_LENGTH = 20


@dataclass
class ConversationContext:
    """State for a single conversation."""

    user_id: str
    channel_id: str
    thread_ts: str | None = None
    history: list[dict] = field(default_factory=list)
    pending_action: Any = None  # PendingAction instance
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history.

        Args:
            role: Message role ('user' or 'assistant').
            content: Message content.
        """
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })

        # Trim history if too long
        if len(self.history) > MAX_HISTORY_LENGTH:
            self.history = self.history[-MAX_HISTORY_LENGTH:]

        self.last_activity = time.time()

    def get_recent_history(self, count: int = 6) -> list[dict]:
        """Get recent conversation history.

        Args:
            count: Number of recent messages to return.

        Returns:
            List of recent messages.
        """
        return self.history[-count:]

    def is_expired(self) -> bool:
        """Check if the conversation has expired.

        Returns:
            True if conversation is older than TTL.
        """
        return time.time() - self.last_activity > CONVERSATION_TTL

    def clear_pending_action(self) -> None:
        """Clear any pending action."""
        self.pending_action = None

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a metadata value.

        Args:
            key: Metadata key.
            value: Metadata value.
        """
        self.metadata[key] = value
        self.last_activity = time.time()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value.

        Args:
            key: Metadata key.
            default: Default value if key not found.

        Returns:
            Metadata value or default.
        """
        return self.metadata.get(key, default)

    @property
    def key(self) -> str:
        """Get the unique key for this conversation."""
        return f"{self.user_id}:{self.channel_id}:{self.thread_ts or 'main'}"


class ConversationManager:
    """Manages conversation contexts across users and channels."""

    def __init__(self, ttl: int = CONVERSATION_TTL):
        """Initialize the conversation manager.

        Args:
            ttl: Time-to-live for conversations in seconds.
        """
        self.ttl = ttl
        self._conversations: dict[str, ConversationContext] = {}
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes

    def get(
        self,
        user_id: str,
        channel_id: str,
        thread_ts: str | None = None,
    ) -> ConversationContext | None:
        """Get a conversation context if it exists.

        Args:
            user_id: Slack user ID.
            channel_id: Slack channel ID.
            thread_ts: Thread timestamp (optional).

        Returns:
            ConversationContext or None if not found/expired.
        """
        self._maybe_cleanup()

        key = self._make_key(user_id, channel_id, thread_ts)
        context = self._conversations.get(key)

        if context and not context.is_expired():
            context.last_activity = time.time()
            return context

        # Remove expired context
        if context:
            del self._conversations[key]

        return None

    def get_or_create(
        self,
        user_id: str,
        channel_id: str,
        thread_ts: str | None = None,
    ) -> ConversationContext:
        """Get or create a conversation context.

        Args:
            user_id: Slack user ID.
            channel_id: Slack channel ID.
            thread_ts: Thread timestamp (optional).

        Returns:
            ConversationContext instance.
        """
        context = self.get(user_id, channel_id, thread_ts)

        if context is None:
            context = ConversationContext(
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )
            self._conversations[context.key] = context
            logger.debug(f"Created new conversation: {context.key}")

        return context

    def delete(
        self,
        user_id: str,
        channel_id: str,
        thread_ts: str | None = None,
    ) -> bool:
        """Delete a conversation context.

        Args:
            user_id: Slack user ID.
            channel_id: Slack channel ID.
            thread_ts: Thread timestamp (optional).

        Returns:
            True if deleted, False if not found.
        """
        key = self._make_key(user_id, channel_id, thread_ts)
        if key in self._conversations:
            del self._conversations[key]
            return True
        return False

    def _make_key(
        self,
        user_id: str,
        channel_id: str,
        thread_ts: str | None,
    ) -> str:
        """Create a unique key for a conversation.

        Args:
            user_id: Slack user ID.
            channel_id: Slack channel ID.
            thread_ts: Thread timestamp (optional).

        Returns:
            Unique key string.
        """
        return f"{user_id}:{channel_id}:{thread_ts or 'main'}"

    def _maybe_cleanup(self) -> None:
        """Periodically clean up expired conversations."""
        if time.time() - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = time.time()
        expired = []

        for key, context in self._conversations.items():
            if context.is_expired():
                expired.append(key)

        for key in expired:
            del self._conversations[key]

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired conversations")

    def get_stats(self) -> dict:
        """Get statistics about active conversations.

        Returns:
            Dictionary with conversation stats.
        """
        self._maybe_cleanup()

        return {
            "active_conversations": len(self._conversations),
            "ttl_seconds": self.ttl,
        }
