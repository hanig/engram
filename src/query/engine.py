"""Unified query engine combining knowledge graph and semantic search."""

import logging
from datetime import datetime
from typing import Any

from ..knowledge_graph import KnowledgeGraph
from ..semantic.embedder import Embedder
from ..semantic.vector_store import VectorStore

logger = logging.getLogger(__name__)


class QueryEngine:
    """Unified query engine for the knowledge graph."""

    def __init__(
        self,
        kg: KnowledgeGraph | None = None,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
    ):
        """Initialize the query engine.

        Args:
            kg: Knowledge graph instance.
            vector_store: Vector store instance.
            embedder: Embedder instance.
        """
        self.kg = kg or KnowledgeGraph()
        self.vector_store = vector_store or VectorStore()
        self._embedder = embedder

    @property
    def embedder(self):
        """Lazy load embedder."""
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    def search(
        self,
        query: str,
        content_types: list[str] | None = None,
        sources: list[str] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        top_k: int = 10,
        use_semantic: bool = True,
        use_keyword: bool = True,
    ) -> list[dict[str, Any]]:
        """Perform a unified search across all data.

        Args:
            query: Search query.
            content_types: Filter by content types (email, file, event, etc.).
            sources: Filter by sources (gmail, drive, calendar, github, slack).
            since: Only content after this date.
            until: Only content before this date.
            top_k: Maximum number of results.
            use_semantic: Include semantic search results.
            use_keyword: Include keyword search results.

        Returns:
            List of search results with scores.
        """
        results = []
        seen_ids = set()

        # Semantic search
        if use_semantic:
            try:
                semantic_results = self._semantic_search(
                    query=query,
                    content_types=content_types,
                    top_k=top_k * 2,  # Get more to merge
                )
                for r in semantic_results:
                    if r["id"] not in seen_ids:
                        results.append(r)
                        seen_ids.add(r["id"])
            except Exception as e:
                logger.error(f"Semantic search error: {e}")

        # Keyword search
        if use_keyword:
            try:
                keyword_results = self._keyword_search(
                    query=query,
                    content_types=content_types,
                    sources=sources,
                    since=since,
                    until=until,
                    limit=top_k * 2,
                )
                for r in keyword_results:
                    if r["id"] not in seen_ids:
                        results.append(r)
                        seen_ids.add(r["id"])
            except Exception as e:
                logger.error(f"Keyword search error: {e}")

        # Sort by score
        results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return results[:top_k]

    def _semantic_search(
        self,
        query: str,
        content_types: list[str] | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Perform semantic search using embeddings.

        Args:
            query: Search query.
            content_types: Filter by content types.
            top_k: Maximum results.

        Returns:
            List of results with semantic scores.
        """
        # Embed query
        query_embedding = self.embedder.embed(query)

        results = []
        collections = content_types or self.vector_store.list_collections()

        for collection in collections:
            try:
                coll_results = self.vector_store.search(
                    collection=collection,
                    query_embedding=query_embedding,
                    top_k=top_k,
                )

                for i, doc_id in enumerate(coll_results["ids"]):
                    # Get source content ID from chunk ID
                    source_id = doc_id.rsplit(":chunk:", 1)[0] if ":chunk:" in doc_id else doc_id

                    results.append({
                        "id": source_id,
                        "chunk_id": doc_id,
                        "type": collection,
                        "text": coll_results["documents"][i] if coll_results["documents"] else "",
                        "metadata": coll_results["metadatas"][i] if coll_results["metadatas"] else {},
                        "score": 1 - coll_results["distances"][i] if coll_results["distances"] else 0,
                        "search_type": "semantic",
                    })

            except Exception as e:
                logger.warning(f"Error searching collection {collection}: {e}")

        return results

    def _keyword_search(
        self,
        query: str,
        content_types: list[str] | None = None,
        sources: list[str] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Perform keyword search on knowledge graph.

        Args:
            query: Search query.
            content_types: Filter by content types.
            sources: Filter by sources.
            since: Only content after this date.
            until: Only content before this date.
            limit: Maximum results.

        Returns:
            List of results with relevance scores.
        """
        results = []

        # Search for each content type
        if content_types:
            for content_type in content_types:
                kg_results = self.kg.search_content(
                    query=query,
                    content_type=content_type,
                    since=since,
                    until=until,
                    limit=limit,
                )
                results.extend(kg_results)
        else:
            kg_results = self.kg.search_content(
                query=query,
                since=since,
                until=until,
                limit=limit,
            )
            results.extend(kg_results)

        # Filter by source if specified
        if sources:
            results = [r for r in results if r.get("source") in sources]

        # Calculate basic relevance score based on query match
        query_lower = query.lower()
        for r in results:
            title = (r.get("title") or "").lower()
            body = (r.get("body") or "").lower()

            # Simple TF-based scoring
            title_matches = title.count(query_lower)
            body_matches = body.count(query_lower)

            # Title matches are worth more
            r["score"] = min((title_matches * 3 + body_matches) * 0.1, 0.8)
            r["search_type"] = "keyword"

        return results

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Get an entity by ID.

        Args:
            entity_id: Entity ID.

        Returns:
            Entity data or None.
        """
        return self.kg.get_entity(entity_id)

    def get_content(self, content_id: str) -> dict[str, Any] | None:
        """Get content by ID.

        Args:
            content_id: Content ID.

        Returns:
            Content data or None.
        """
        return self.kg.get_content(content_id)

    def find_person(self, query: str) -> list[dict[str, Any]]:
        """Find people matching a query.

        Args:
            query: Name or email to search for.

        Returns:
            List of matching person entities.
        """
        return self.kg.search_entities(
            query=query,
            entity_type="person",
            limit=20,
        )

    def get_person_activity(
        self,
        person_id: str,
        content_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get activity involving a person.

        Args:
            person_id: Person entity ID.
            content_types: Filter by content types.
            limit: Maximum results.

        Returns:
            List of content items involving the person.
        """
        # Get relationships
        relationships = self.kg.get_relationships(
            entity_id=person_id,
            direction="incoming",
        )

        # Get content for each relationship
        content_ids = [r["from_id"] for r in relationships]
        activity = []

        for content_id in content_ids[:limit]:
            content = self.kg.get_content(content_id)
            if content:
                if content_types is None or content.get("type") in content_types:
                    activity.append(content)

        # Sort by timestamp
        activity.sort(
            key=lambda x: x.get("timestamp") or "",
            reverse=True,
        )

        return activity[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the query engine data.

        Returns:
            Statistics dictionary.
        """
        return {
            "knowledge_graph": self.kg.get_stats(),
            "vector_store": self.vector_store.get_stats(),
        }
