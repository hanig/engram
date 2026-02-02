"""Calendar handler for calendar-related queries."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..conversation import ConversationContext
from ..formatters import format_availability, format_calendar_events
from ..intent_router import Intent
from .base import BaseHandler

logger = logging.getLogger(__name__)


class CalendarHandler(BaseHandler):
    """Handler for calendar-related queries."""

    def __init__(self):
        """Initialize the calendar handler."""
        self._multi_google = None

    @property
    def multi_google(self):
        """Lazy load multi-Google manager."""
        if self._multi_google is None:
            from ...integrations.google_multi import MultiGoogleManager
            self._multi_google = MultiGoogleManager()
        return self._multi_google

    def handle(self, intent: Intent, context: ConversationContext) -> dict[str, Any]:
        """Handle a calendar intent.

        Args:
            intent: Classified intent with entities.
            context: Conversation context.

        Returns:
            Response dictionary with calendar information.
        """
        if intent.intent == "calendar_availability":
            return self._handle_availability(intent, context)
        else:
            return self._handle_calendar_check(intent, context)

    def _handle_calendar_check(
        self, intent: Intent, context: ConversationContext
    ) -> dict[str, Any]:
        """Handle calendar check intent."""
        date_ref = intent.entities.get("date", "today")
        target_date = self._parse_date_reference(date_ref)

        try:
            events = self.multi_google.get_all_calendars_for_date(target_date)

            return format_calendar_events(events, date_ref)

        except Exception as e:
            logger.error(f"Error getting calendar: {e}")
            return {"text": f"Error getting calendar: {str(e)}"}

    def _handle_availability(
        self, intent: Intent, context: ConversationContext
    ) -> dict[str, Any]:
        """Handle availability check intent."""
        date_ref = intent.entities.get("date", "today")
        target_date = self._parse_date_reference(date_ref)

        try:
            free_slots = self.multi_google.check_availability(
                date=target_date,
                duration_minutes=30,
            )

            return format_availability(free_slots, date_ref)

        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            return {"text": f"Error checking availability: {str(e)}"}

    def _parse_date_reference(self, date_ref: str) -> datetime:
        """Parse a date reference string into a datetime.

        Args:
            date_ref: Date reference like "today", "tomorrow", etc.

        Returns:
            datetime object.
        """
        now = datetime.now(timezone.utc)
        date_ref_lower = date_ref.lower()

        if date_ref_lower == "today":
            return now
        elif date_ref_lower == "tomorrow":
            return now + timedelta(days=1)
        elif date_ref_lower == "yesterday":
            return now - timedelta(days=1)
        elif date_ref_lower == "next week":
            return now + timedelta(days=7)
        elif date_ref_lower == "this week":
            return now
        else:
            # Try to parse as ISO date
            try:
                return datetime.fromisoformat(date_ref)
            except ValueError:
                return now
