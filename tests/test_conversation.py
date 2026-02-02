"""Tests for conversation management."""

import time

import pytest

from src.bot.conversation import ConversationContext, ConversationManager


class TestConversationContext:
    """Tests for ConversationContext class."""

    def test_create_context(self):
        """Test creating a conversation context."""
        context = ConversationContext(
            user_id="U123",
            channel_id="C456",
            thread_ts="123.456",
        )

        assert context.user_id == "U123"
        assert context.channel_id == "C456"
        assert context.thread_ts == "123.456"

    def test_add_message(self):
        """Test adding messages to history."""
        context = ConversationContext("U1", "C1")

        context.add_message("user", "Hello")
        context.add_message("assistant", "Hi there!")

        assert len(context.history) == 2
        assert context.history[0]["role"] == "user"
        assert context.history[1]["role"] == "assistant"

    def test_history_trimming(self):
        """Test that history is trimmed when too long."""
        context = ConversationContext("U1", "C1")

        # Add more than MAX_HISTORY_LENGTH messages
        for i in range(30):
            context.add_message("user", f"Message {i}")

        assert len(context.history) <= 20  # MAX_HISTORY_LENGTH

    def test_get_recent_history(self):
        """Test getting recent history."""
        context = ConversationContext("U1", "C1")

        for i in range(10):
            context.add_message("user", f"Message {i}")

        recent = context.get_recent_history(3)

        assert len(recent) == 3
        assert recent[-1]["content"] == "Message 9"

    def test_context_key(self):
        """Test context key generation."""
        context = ConversationContext("U1", "C1", "123.456")

        assert context.key == "U1:C1:123.456"

    def test_context_key_no_thread(self):
        """Test context key without thread."""
        context = ConversationContext("U1", "C1")

        assert context.key == "U1:C1:main"

    def test_metadata(self):
        """Test metadata storage."""
        context = ConversationContext("U1", "C1")

        context.set_metadata("key", "value")
        assert context.get_metadata("key") == "value"
        assert context.get_metadata("missing", "default") == "default"


class TestConversationManager:
    """Tests for ConversationManager class."""

    def test_get_or_create(self):
        """Test getting or creating a conversation."""
        manager = ConversationManager()

        context = manager.get_or_create("U1", "C1")

        assert context is not None
        assert context.user_id == "U1"

    def test_get_existing(self):
        """Test getting an existing conversation."""
        manager = ConversationManager()

        ctx1 = manager.get_or_create("U1", "C1")
        ctx1.add_message("user", "Hello")

        ctx2 = manager.get_or_create("U1", "C1")

        assert ctx1 is ctx2
        assert len(ctx2.history) == 1

    def test_get_nonexistent(self):
        """Test getting a non-existent conversation."""
        manager = ConversationManager()

        context = manager.get("U1", "C1")

        assert context is None

    def test_delete(self):
        """Test deleting a conversation."""
        manager = ConversationManager()

        manager.get_or_create("U1", "C1")
        deleted = manager.delete("U1", "C1")

        assert deleted is True
        assert manager.get("U1", "C1") is None

    def test_delete_nonexistent(self):
        """Test deleting non-existent conversation."""
        manager = ConversationManager()

        deleted = manager.delete("U1", "C1")

        assert deleted is False

    def test_different_threads(self):
        """Test that different threads have separate contexts."""
        manager = ConversationManager()

        ctx1 = manager.get_or_create("U1", "C1", "thread1")
        ctx2 = manager.get_or_create("U1", "C1", "thread2")

        assert ctx1 is not ctx2

    def test_get_stats(self):
        """Test getting manager statistics."""
        manager = ConversationManager()

        manager.get_or_create("U1", "C1")
        manager.get_or_create("U2", "C2")

        stats = manager.get_stats()

        assert stats["active_conversations"] == 2
