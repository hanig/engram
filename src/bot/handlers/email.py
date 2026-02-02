"""Email handler for email-related queries."""

import logging
from typing import Any

from ..actions.email_actions import CreateDraftAction
from ..conversation import ConversationContext
from ..formatters import format_confirmation, format_email_results
from ..intent_router import Intent
from .base import BaseHandler

logger = logging.getLogger(__name__)


class EmailHandler(BaseHandler):
    """Handler for email-related queries."""

    def __init__(self):
        """Initialize the email handler."""
        self._multi_google = None

    @property
    def multi_google(self):
        """Lazy load multi-Google manager."""
        if self._multi_google is None:
            from ...integrations.google_multi import MultiGoogleManager
            self._multi_google = MultiGoogleManager()
        return self._multi_google

    def handle(self, intent: Intent, context: ConversationContext) -> dict[str, Any]:
        """Handle an email intent.

        Args:
            intent: Classified intent with entities.
            context: Conversation context.

        Returns:
            Response dictionary with email information.
        """
        if intent.intent == "email_draft":
            return self._handle_draft(intent, context)
        else:
            return self._handle_search(intent, context)

    def _handle_search(
        self, intent: Intent, context: ConversationContext
    ) -> dict[str, Any]:
        """Handle email search intent."""
        query = intent.entities.get("query", "")
        person = intent.entities.get("person", "")

        if not query and not person:
            return {"text": "What would you like to search for in emails?"}

        # Build search query
        search_query = query
        if person:
            search_query = f"from:{person} OR to:{person} {query}".strip()

        try:
            results = self.multi_google.search_mail_tiered(
                query=search_query,
                max_results=10,
            )

            return format_email_results(results, query or person)

        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            return {"text": f"Error searching emails: {str(e)}"}

    def _handle_draft(
        self, intent: Intent, context: ConversationContext
    ) -> dict[str, Any]:
        """Handle email draft creation intent."""
        person = intent.entities.get("person", "")
        query = intent.entities.get("query", "")  # Used as subject hint

        # Create pending action
        action = CreateDraftAction(
            to=person,
            subject_hint=query,
        )

        # Check what we need
        if not action.is_ready():
            context.pending_action = action
            return {"text": action.get_next_prompt()}

        # If we have enough info, show confirmation
        context.pending_action = action
        return action.get_confirmation_prompt()
