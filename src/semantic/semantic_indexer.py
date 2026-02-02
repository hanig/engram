"""Orchestrates the semantic indexing pipeline."""

import logging
from typing import Any

from tqdm import tqdm

from ..config import EMBEDDING_BATCH_SIZE
from ..knowledge_graph import KnowledgeGraph
from .chunker import Chunk, EmailChunker, TextChunker
from .embedder import Embedder
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class SemanticIndexer:
    """Orchestrates embedding generation and vector storage."""

    def __init__(
        self,
        kg: KnowledgeGraph | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
    ):
        """Initialize the semantic indexer.

        Args:
            kg: Knowledge graph instance.
            embedder: Embedder instance.
            vector_store: Vector store instance.
        """
        self.kg = kg or KnowledgeGraph()
        self.embedder = embedder or Embedder()
        self.vector_store = vector_store or VectorStore()

        self.text_chunker = TextChunker()
        self.email_chunker = EmailChunker()

    def index_all(
        self,
        content_types: list[str] | None = None,
        batch_size: int = EMBEDDING_BATCH_SIZE,
        show_progress: bool = True,
    ) -> dict[str, Any]:
        """Index all content from the knowledge graph.

        Args:
            content_types: Types of content to index. None for all.
            batch_size: Number of chunks to embed at once.
            show_progress: Whether to show progress bar.

        Returns:
            Statistics about the indexing operation.
        """
        logger.info("Starting semantic indexing")

        stats = {
            "content_processed": 0,
            "chunks_created": 0,
            "embeddings_generated": 0,
            "errors": 0,
        }

        # Get all content from knowledge graph
        content_items = self.kg.search_content(content_type=None, limit=100000)

        if content_types:
            content_items = [c for c in content_items if c["type"] in content_types]

        logger.info(f"Found {len(content_items)} content items to index")

        # Process content by type for better chunking
        content_by_type: dict[str, list[dict]] = {}
        for item in content_items:
            content_type = item["type"]
            if content_type not in content_by_type:
                content_by_type[content_type] = []
            content_by_type[content_type].append(item)

        # Process each content type
        for content_type, items in content_by_type.items():
            logger.info(f"Processing {len(items)} {content_type} items")

            all_chunks = []

            # Generate chunks
            for item in items:
                try:
                    chunks = self._chunk_content(item)
                    all_chunks.extend(chunks)
                    stats["content_processed"] += 1
                except Exception as e:
                    logger.error(f"Error chunking content {item['id']}: {e}")
                    stats["errors"] += 1

            stats["chunks_created"] += len(all_chunks)

            # Embed and store chunks in batches
            if all_chunks:
                self._embed_and_store_chunks(
                    collection=content_type,
                    chunks=all_chunks,
                    batch_size=batch_size,
                    stats=stats,
                    show_progress=show_progress,
                )

        logger.info(f"Semantic indexing complete: {stats}")
        return stats

    def index_content(
        self,
        content_id: str,
        content_type: str,
        title: str | None,
        body: str | None,
        metadata: dict | None = None,
    ) -> int:
        """Index a single piece of content.

        Args:
            content_id: Unique content ID.
            content_type: Type of content (email, file, etc.).
            title: Content title.
            body: Content body.
            metadata: Additional metadata.

        Returns:
            Number of chunks created.
        """
        if not body:
            return 0

        # Create content dict for chunking
        content = {
            "id": content_id,
            "type": content_type,
            "title": title,
            "body": body,
            "metadata": metadata or {},
        }

        chunks = self._chunk_content(content)

        if chunks:
            # Embed
            texts = [c.text for c in chunks]
            embeddings = self.embedder.embed_batch(texts)

            # Store
            ids = [f"{content_id}:chunk:{c.chunk_index}" for c in chunks]
            documents = texts
            metadatas = [c.metadata or {} for c in chunks]

            self.vector_store.add(
                collection=content_type,
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )

        return len(chunks)

    def search(
        self,
        query: str,
        content_types: list[str] | None = None,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar content.

        Args:
            query: Search query.
            content_types: Types of content to search. None for all.
            top_k: Number of results per content type.
            filters: Metadata filters.

        Returns:
            List of search results with scores.
        """
        # Embed query
        query_embedding = self.embedder.embed(query)

        all_results = []

        # Search each collection
        collections = content_types or self.vector_store.list_collections()

        for collection in collections:
            try:
                results = self.vector_store.search(
                    collection=collection,
                    query_embedding=query_embedding,
                    top_k=top_k,
                    where=filters,
                )

                for i, doc_id in enumerate(results["ids"]):
                    all_results.append({
                        "id": doc_id,
                        "collection": collection,
                        "text": results["documents"][i] if results["documents"] else "",
                        "metadata": results["metadatas"][i] if results["metadatas"] else {},
                        "score": 1 - results["distances"][i] if results["distances"] else 0,
                    })

            except Exception as e:
                logger.error(f"Error searching collection '{collection}': {e}")

        # Sort by score and return top results
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:top_k]

    def delete_content(self, content_id: str, content_type: str) -> None:
        """Delete all chunks for a piece of content.

        Args:
            content_id: Content ID.
            content_type: Type of content (collection name).
        """
        # Delete by metadata filter
        self.vector_store.delete(
            collection=content_type,
            where={"source_id": content_id},
        )

    def _chunk_content(self, content: dict) -> list[Chunk]:
        """Chunk content based on its type.

        Args:
            content: Content dictionary from knowledge graph.

        Returns:
            List of chunks.
        """
        content_type = content["type"]
        title = content.get("title") or ""
        body = content.get("body") or ""
        metadata = content.get("metadata") or {}

        if not body:
            return []

        # Add source metadata
        base_metadata = {
            "source_id": content["id"],
            "source_type": content_type,
            "title": title,
            "source_account": content.get("source_account"),
            "timestamp": str(content.get("timestamp")) if content.get("timestamp") else None,
            **metadata,
        }

        # Use appropriate chunker
        if content_type == "email":
            chunks = self.email_chunker.chunk_email(
                subject=title,
                body=body,
                from_addr=metadata.get("from", ""),
                to_addr=metadata.get("to", ""),
                message_id=content["id"],
                metadata=base_metadata,
            )
        else:
            chunks = self.text_chunker.chunk_document(
                title=title,
                body=body,
                source_id=content["id"],
                source_type=content_type,
                metadata=base_metadata,
            )

        return chunks

    def _embed_and_store_chunks(
        self,
        collection: str,
        chunks: list[Chunk],
        batch_size: int,
        stats: dict[str, int],
        show_progress: bool,
    ) -> None:
        """Embed and store chunks in batches.

        Args:
            collection: Collection name.
            chunks: List of chunks to process.
            batch_size: Batch size for embedding.
            stats: Statistics dictionary to update.
            show_progress: Whether to show progress bar.
        """
        iterator = range(0, len(chunks), batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc=f"Embedding {collection}")

        for i in iterator:
            batch_chunks = chunks[i : i + batch_size]

            try:
                # Extract texts
                texts = [c.text for c in batch_chunks]

                # Generate embeddings
                embeddings = self.embedder.embed_batch(texts)

                # Prepare for storage
                ids = []
                documents = []
                metadatas = []

                for chunk, embedding in zip(batch_chunks, embeddings):
                    source_id = chunk.metadata.get("source_id", "unknown")
                    chunk_id = f"{source_id}:chunk:{chunk.chunk_index}"

                    ids.append(chunk_id)
                    documents.append(chunk.text)
                    metadatas.append(chunk.metadata or {})

                # Store in vector store
                self.vector_store.add(
                    collection=collection,
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                )

                stats["embeddings_generated"] += len(embeddings)

            except Exception as e:
                logger.error(f"Error embedding batch: {e}")
                stats["errors"] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the semantic index.

        Returns:
            Statistics dictionary.
        """
        return {
            "vector_store": self.vector_store.get_stats(),
            "knowledge_graph": self.kg.get_stats(),
        }
