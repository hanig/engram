"""ChromaDB vector store wrapper."""

import logging
from typing import Any

import chromadb
from chromadb.config import Settings

from ..config import CHROMA_DB_PATH

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB-based vector store for semantic search."""

    def __init__(self, path: str | None = None):
        """Initialize the vector store.

        Args:
            path: Path to ChromaDB storage. Defaults to config value.
        """
        self.path = path or str(CHROMA_DB_PATH)

        # Initialize ChromaDB with persistence
        self._client = chromadb.PersistentClient(
            path=self.path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # Collection names by content type
        self._collections: dict[str, chromadb.Collection] = {}

    def get_collection(self, name: str) -> chromadb.Collection:
        """Get or create a collection.

        Args:
            name: Collection name.

        Returns:
            ChromaDB collection.
        """
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[name]

    def add(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str] | None = None,
        metadatas: list[dict] | None = None,
    ) -> None:
        """Add vectors to a collection.

        Args:
            collection: Collection name.
            ids: Unique IDs for each vector.
            embeddings: Embedding vectors.
            documents: Original text documents (optional).
            metadatas: Metadata for each document (optional).
        """
        coll = self.get_collection(collection)

        # ChromaDB upserts by default
        coll.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        logger.debug(f"Added {len(ids)} vectors to collection '{collection}'")

    def search(
        self,
        collection: str,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict | None = None,
        where_document: dict | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search for similar vectors.

        Args:
            collection: Collection name.
            query_embedding: Query vector.
            top_k: Number of results to return.
            where: Metadata filter.
            where_document: Document content filter.
            include: What to include in results (documents, metadatas, distances).

        Returns:
            Dictionary with ids, distances, documents, metadatas.
        """
        coll = self.get_collection(collection)

        if include is None:
            include = ["documents", "metadatas", "distances"]

        try:
            results = coll.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                where_document=where_document,
                include=include,
            )

            # Flatten results (ChromaDB returns nested lists)
            return {
                "ids": results["ids"][0] if results["ids"] else [],
                "distances": results["distances"][0] if results.get("distances") else [],
                "documents": results["documents"][0] if results.get("documents") else [],
                "metadatas": results["metadatas"][0] if results.get("metadatas") else [],
            }

        except Exception as e:
            logger.error(f"Error searching collection '{collection}': {e}")
            return {"ids": [], "distances": [], "documents": [], "metadatas": []}

    def search_text(
        self,
        collection: str,
        query: str,
        embedder,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Search using text query (embeds query first).

        Args:
            collection: Collection name.
            query: Text query.
            embedder: Embedder instance to generate query embedding.
            top_k: Number of results.
            filters: Metadata filters.

        Returns:
            List of result dictionaries with id, text, metadata, score.
        """
        # Generate query embedding
        query_embedding = embedder.embed(query)

        # Search
        results = self.search(
            collection=collection,
            query_embedding=query_embedding,
            top_k=top_k,
            where=filters,
        )

        # Format results
        formatted = []
        for i, doc_id in enumerate(results["ids"]):
            result = {
                "id": doc_id,
                "text": results["documents"][i] if results["documents"] else None,
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
                "score": 1 - results["distances"][i] if results["distances"] else 0,
            }
            formatted.append(result)

        return formatted

    def delete(
        self,
        collection: str,
        ids: list[str] | None = None,
        where: dict | None = None,
    ) -> None:
        """Delete vectors from a collection.

        Args:
            collection: Collection name.
            ids: IDs to delete.
            where: Metadata filter for deletion.
        """
        coll = self.get_collection(collection)

        if ids:
            coll.delete(ids=ids)
            logger.debug(f"Deleted {len(ids)} vectors from '{collection}'")
        elif where:
            coll.delete(where=where)
            logger.debug(f"Deleted vectors matching filter from '{collection}'")

    def get(
        self,
        collection: str,
        ids: list[str],
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get vectors by ID.

        Args:
            collection: Collection name.
            ids: IDs to retrieve.
            include: What to include in results.

        Returns:
            Dictionary with ids, documents, metadatas, embeddings.
        """
        coll = self.get_collection(collection)

        if include is None:
            include = ["documents", "metadatas"]

        results = coll.get(ids=ids, include=include)
        return results

    def count(self, collection: str) -> int:
        """Get the number of vectors in a collection.

        Args:
            collection: Collection name.

        Returns:
            Number of vectors.
        """
        coll = self.get_collection(collection)
        return coll.count()

    def list_collections(self) -> list[str]:
        """List all collection names.

        Returns:
            List of collection names.
        """
        collections = self._client.list_collections()
        return [c.name for c in collections]

    def delete_collection(self, name: str) -> bool:
        """Delete a collection.

        Args:
            name: Collection name.

        Returns:
            True if deleted, False if not found.
        """
        try:
            self._client.delete_collection(name)
            if name in self._collections:
                del self._collections[name]
            return True
        except Exception:
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about all collections.

        Returns:
            Dictionary with collection counts and totals.
        """
        stats = {"collections": {}, "total_vectors": 0}

        for name in self.list_collections():
            count = self.count(name)
            stats["collections"][name] = count
            stats["total_vectors"] += count

        return stats

    def reset(self) -> None:
        """Reset the entire vector store (delete all data)."""
        logger.warning("Resetting vector store - all data will be deleted")
        self._client.reset()
        self._collections.clear()
