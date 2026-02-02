"""Base handler class for bot commands."""

from abc import ABC, abstractmethod
from typing import Any

from ..conversation import ConversationContext
from ..intent_router import Intent


class BaseHandler(ABC):
    """Abstract base class for bot command handlers."""

    @abstractmethod
    def handle(self, intent: Intent, context: ConversationContext) -> dict[str, Any]:
        """Handle an intent.

        Args:
            intent: Classified intent with entities.
            context: Conversation context.

        Returns:
            Response dictionary with 'text' and optionally 'blocks'.
        """
        pass

    def can_handle(self, intent: Intent) -> bool:
        """Check if this handler can handle the given intent.

        Args:
            intent: Classified intent.

        Returns:
            True if this handler can handle the intent.
        """
        return True
