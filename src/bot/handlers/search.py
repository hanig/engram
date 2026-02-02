"""Search handler for semantic search queries."""

import logging
from typing import Any

from ..conversation import ConversationContext
from ..formatters import format_search_results
from ..intent_router import Intent
from .base import BaseHandler

logger = logging.getLogger(__name__)


class SearchHandler(BaseHandler):
    """Handler for general semantic search queries."""

    def __init__(self):
        """Initialize the search handler."""
        self._semantic_indexer = None

    @property
    def semantic_indexer(self):
        """Lazy load semantic indexer."""
        if self._semantic_indexer is None:
            from ...semantic.semantic_indexer import SemanticIndexer
            self._semantic_indexer = SemanticIndexer()
        return self._semantic_indexer

    def handle(self, intent: Intent, context: ConversationContext) -> dict[str, Any]:
        """Handle a search intent.

        Args:
            intent: Classified intent with entities.
            context: Conversation context.

        Returns:
            Response dictionary with search results.
        """
        query = intent.entities.get("query", "")

        if not query:
            return {"text": "What would you like to search for?"}

        try:
            # Perform semantic search
            results = self.semantic_indexer.search(
                query=query,
                top_k=10,
            )

            return format_search_results(results, query)

        except Exception as e:
            logger.error(f"Error performing search: {e}")
            return {"text": f"Error searching: {str(e)}"}
