"""Tests for text chunking."""

import pytest

from src.semantic.chunker import Chunk, EmailChunker, TextChunker


class TestTextChunker:
    """Tests for TextChunker class."""

    def test_chunk_short_text(self):
        """Test that short text produces single chunk."""
        chunker = TextChunker(chunk_size=1000)
        chunks = chunker.chunk("Hello world")

        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"

    def test_chunk_long_text(self):
        """Test that long text is split into multiple chunks."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=20, min_chunk_size=10)
        text = "This is a test sentence. " * 20

        chunks = chunker.chunk(text)

        assert len(chunks) > 1

    def test_chunk_metadata(self):
        """Test that metadata is attached to chunks."""
        chunker = TextChunker()
        metadata = {"source": "test"}

        chunks = chunker.chunk("Hello world", metadata=metadata)

        assert chunks[0].metadata["source"] == "test"

    def test_chunk_indices(self):
        """Test that chunk indices are sequential."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=20, min_chunk_size=10)
        text = "This is a test. " * 50

        chunks = chunker.chunk(text)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_empty_text(self):
        """Test that empty text produces no chunks."""
        chunker = TextChunker()
        chunks = chunker.chunk("")

        assert len(chunks) == 0

    def test_chunk_document(self):
        """Test document chunking with title."""
        chunker = TextChunker(chunk_size=500)

        chunks = chunker.chunk_document(
            title="Test Document",
            body="This is the body content. " * 10,
            source_id="doc123",
            source_type="file",
        )

        assert len(chunks) >= 1
        assert "Test Document" in chunks[0].text
        assert chunks[0].metadata["source_id"] == "doc123"


class TestEmailChunker:
    """Tests for EmailChunker class."""

    def test_chunk_email(self):
        """Test email chunking."""
        chunker = EmailChunker()

        chunks = chunker.chunk_email(
            subject="Test Subject",
            body="This is the email body.",
            from_addr="sender@example.com",
            to_addr="recipient@example.com",
            message_id="msg123",
        )

        assert len(chunks) >= 1
        assert "Test Subject" in chunks[0].text
        assert chunks[0].metadata["subject"] == "Test Subject"
        assert chunks[0].metadata["from"] == "sender@example.com"

    def test_chunk_email_metadata(self):
        """Test that email metadata is included."""
        chunker = EmailChunker()

        chunks = chunker.chunk_email(
            subject="Test",
            body="Body text",
            from_addr="a@b.com",
            to_addr="c@d.com",
            message_id="123",
            metadata={"extra": "data"},
        )

        assert chunks[0].metadata["extra"] == "data"
        assert chunks[0].metadata["source_type"] == "email"
