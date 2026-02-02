"""Text chunking utilities for semantic indexing."""

import re
from dataclasses import dataclass
from typing import Iterator


@dataclass
class Chunk:
    """A chunk of text with metadata."""

    text: str
    start_char: int
    end_char: int
    chunk_index: int
    metadata: dict | None = None


class TextChunker:
    """Splits text into overlapping chunks for embedding."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
    ):
        """Initialize the chunker.

        Args:
            chunk_size: Target size of each chunk in characters.
            chunk_overlap: Number of characters to overlap between chunks.
            min_chunk_size: Minimum chunk size (smaller chunks are merged).
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        """Split text into chunks.

        Args:
            text: Text to chunk.
            metadata: Optional metadata to attach to all chunks.

        Returns:
            List of Chunk objects.
        """
        if not text or len(text) < self.min_chunk_size:
            if text:
                return [
                    Chunk(
                        text=text.strip(),
                        start_char=0,
                        end_char=len(text),
                        chunk_index=0,
                        metadata=metadata,
                    )
                ]
            return []

        chunks = []
        sentences = self._split_into_sentences(text)
        current_chunk = []
        current_start = 0
        current_length = 0
        chunk_index = 0

        for sentence_start, sentence in sentences:
            sentence_length = len(sentence)

            # If adding this sentence would exceed chunk size
            if current_length + sentence_length > self.chunk_size and current_chunk:
                # Create chunk from accumulated sentences
                chunk_text = " ".join(current_chunk)
                chunks.append(
                    Chunk(
                        text=chunk_text.strip(),
                        start_char=current_start,
                        end_char=current_start + len(chunk_text),
                        chunk_index=chunk_index,
                        metadata=metadata,
                    )
                )
                chunk_index += 1

                # Start new chunk with overlap
                overlap_text = self._get_overlap(current_chunk, self.chunk_overlap)
                current_chunk = [overlap_text] if overlap_text else []
                current_length = len(overlap_text) if overlap_text else 0
                current_start = sentence_start - current_length

            current_chunk.append(sentence)
            current_length += sentence_length + 1  # +1 for space

        # Don't forget the last chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append(
                    Chunk(
                        text=chunk_text.strip(),
                        start_char=current_start,
                        end_char=current_start + len(chunk_text),
                        chunk_index=chunk_index,
                        metadata=metadata,
                    )
                )
            elif chunks:
                # Merge with previous chunk if too small
                prev_chunk = chunks[-1]
                merged_text = prev_chunk.text + " " + chunk_text.strip()
                chunks[-1] = Chunk(
                    text=merged_text,
                    start_char=prev_chunk.start_char,
                    end_char=prev_chunk.start_char + len(merged_text),
                    chunk_index=prev_chunk.chunk_index,
                    metadata=metadata,
                )

        return chunks

    def _split_into_sentences(self, text: str) -> list[tuple[int, str]]:
        """Split text into sentences with their start positions.

        Returns:
            List of (start_position, sentence) tuples.
        """
        # Simple sentence splitting on common terminators
        # This is a simplified approach - consider using nltk for better results
        sentence_pattern = r"(?<=[.!?])\s+(?=[A-Z])|(?<=\n)\s*(?=\S)"

        sentences = []
        current_pos = 0

        parts = re.split(sentence_pattern, text)
        for part in parts:
            if part.strip():
                sentences.append((current_pos, part.strip()))
            current_pos += len(part)
            # Account for the split pattern
            if current_pos < len(text):
                while current_pos < len(text) and text[current_pos] in " \n\t":
                    current_pos += 1

        return sentences

    def _get_overlap(self, sentences: list[str], target_length: int) -> str:
        """Get the last N characters worth of sentences for overlap.

        Args:
            sentences: List of sentences.
            target_length: Target overlap length.

        Returns:
            Overlap text.
        """
        if not sentences:
            return ""

        overlap_sentences = []
        overlap_length = 0

        for sentence in reversed(sentences):
            if overlap_length + len(sentence) > target_length:
                break
            overlap_sentences.insert(0, sentence)
            overlap_length += len(sentence) + 1

        return " ".join(overlap_sentences)

    def chunk_document(
        self,
        title: str,
        body: str,
        source_id: str,
        source_type: str,
        metadata: dict | None = None,
    ) -> list[Chunk]:
        """Chunk a document with contextual metadata.

        Prepends title to each chunk for better context.

        Args:
            title: Document title.
            body: Document body.
            source_id: Original document ID.
            source_type: Type of document (email, file, etc.).
            metadata: Additional metadata.

        Returns:
            List of chunks with document metadata.
        """
        base_metadata = {
            "source_id": source_id,
            "source_type": source_type,
            "title": title,
            **(metadata or {}),
        }

        # Prepend title to body for context
        full_text = f"{title}\n\n{body}" if title else body

        chunks = self.chunk(full_text, metadata=base_metadata)

        # Add chunk-specific metadata
        total_chunks = len(chunks)
        for chunk in chunks:
            chunk.metadata = {
                **base_metadata,
                "chunk_index": chunk.chunk_index,
                "total_chunks": total_chunks,
            }

        return chunks


class EmailChunker(TextChunker):
    """Specialized chunker for email messages."""

    def __init__(self):
        """Initialize with email-appropriate settings."""
        # Smaller chunks for emails since they're typically shorter
        # Low min_chunk_size to handle short emails
        super().__init__(chunk_size=800, chunk_overlap=150, min_chunk_size=10)

    def chunk_email(
        self,
        subject: str,
        body: str,
        from_addr: str,
        to_addr: str,
        message_id: str,
        metadata: dict | None = None,
    ) -> list[Chunk]:
        """Chunk an email with header context.

        Args:
            subject: Email subject.
            body: Email body.
            from_addr: Sender address.
            to_addr: Recipient address.
            message_id: Message ID.
            metadata: Additional metadata.

        Returns:
            List of chunks with email metadata.
        """
        # Create context header
        header = f"Subject: {subject}\nFrom: {from_addr}\nTo: {to_addr}"

        base_metadata = {
            "source_id": message_id,
            "source_type": "email",
            "subject": subject,
            "from": from_addr,
            "to": to_addr,
            **(metadata or {}),
        }

        # Combine header and body
        full_text = f"{header}\n\n{body}"

        return self.chunk(full_text, metadata=base_metadata)
