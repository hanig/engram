"""Calendar aggregation across multiple Google accounts."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import GOOGLE_ACCOUNTS, GOOGLE_EMAILS
from ..integrations.google_multi import MultiGoogleManager

logger = logging.getLogger(__name__)


class CalendarAggregator:
    """Aggregates and analyzes calendar events across all Google accounts."""

    def __init__(self, multi_google: MultiGoogleManager | None = None):
        """Initialize the calendar aggregator.

        Args:
            multi_google: Multi-Google manager instance.
        """
        self.multi_google = multi_google or MultiGoogleManager()

    def get_events_for_date(
        self,
        date: datetime,
        accounts: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get all events for a specific date.

        Args:
            date: The date to get events for.
            accounts: Specific accounts to check. None for all.

        Returns:
            List of events sorted by start time.
        """
        return self.multi_google.get_all_calendars_for_date(date)

    def get_today_events(self) -> list[dict[str, Any]]:
        """Get all events for today.

        Returns:
            List of today's events.
        """
        return self.multi_google.get_all_calendars_today()

    def get_week_overview(
        self,
        start_date: datetime | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Get a week's worth of events.

        Args:
            start_date: Start of the week. Defaults to today.

        Returns:
            Dictionary mapping date strings to event lists.
        """
        if start_date is None:
            start_date = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        week_events = {}

        for i in range(7):
            date = start_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            week_events[date_str] = self.get_events_for_date(date)

        return week_events

    def check_availability(
        self,
        date: datetime,
        duration_minutes: int = 30,
        working_hours: tuple[int, int] = (9, 18),
    ) -> list[dict[str, Any]]:
        """Find available time slots.

        Args:
            date: The date to check.
            duration_minutes: Minimum slot duration.
            working_hours: (start_hour, end_hour).

        Returns:
            List of available time slots.
        """
        return self.multi_google.check_availability(
            date=date,
            duration_minutes=duration_minutes,
            working_hours=working_hours,
        )

    def find_meeting_time(
        self,
        date: datetime,
        duration_minutes: int = 60,
        preferred_hours: tuple[int, int] | None = None,
    ) -> dict[str, Any] | None:
        """Find the best meeting time for a given date.

        Prefers morning slots, then afternoon.

        Args:
            date: The date to find a slot.
            duration_minutes: Required duration.
            preferred_hours: Preferred time range (start, end).

        Returns:
            Best available slot or None.
        """
        working_hours = preferred_hours or (9, 18)
        slots = self.check_availability(
            date=date,
            duration_minutes=duration_minutes,
            working_hours=working_hours,
        )

        if not slots:
            return None

        # Prefer morning slots (before noon)
        morning_slots = [
            s for s in slots
            if s["start"].hour < 12
        ]

        if morning_slots:
            return morning_slots[0]

        # Otherwise return first available
        return slots[0]

    def get_conflicts(
        self,
        date: datetime,
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Find overlapping events (conflicts).

        Args:
            date: The date to check.

        Returns:
            List of (event1, event2) tuples for conflicting events.
        """
        events = self.get_events_for_date(date)
        conflicts = []

        for i, event1 in enumerate(events):
            if event1.get("is_all_day"):
                continue

            start1 = event1.get("start")
            end1 = event1.get("end")

            if not start1 or not end1:
                continue

            for event2 in events[i + 1:]:
                if event2.get("is_all_day"):
                    continue

                start2 = event2.get("start")
                end2 = event2.get("end")

                if not start2 or not end2:
                    continue

                # Check for overlap
                if start1 < end2 and start2 < end1:
                    conflicts.append((event1, event2))

        return conflicts

    def get_meeting_stats(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, Any]:
        """Get statistics about meetings in a date range.

        Args:
            start_date: Start of range.
            end_date: End of range.

        Returns:
            Statistics dictionary.
        """
        stats = {
            "total_events": 0,
            "total_meetings_hours": 0,
            "meetings_by_account": {},
            "busiest_day": None,
            "busiest_day_count": 0,
        }

        current_date = start_date
        while current_date <= end_date:
            events = self.get_events_for_date(current_date)
            date_str = current_date.strftime("%Y-%m-%d")

            day_count = len(events)
            stats["total_events"] += day_count

            if day_count > stats["busiest_day_count"]:
                stats["busiest_day"] = date_str
                stats["busiest_day_count"] = day_count

            for event in events:
                # Count by account
                account = event.get("account", "unknown")
                if account not in stats["meetings_by_account"]:
                    stats["meetings_by_account"][account] = 0
                stats["meetings_by_account"][account] += 1

                # Calculate duration
                if not event.get("is_all_day"):
                    start = event.get("start")
                    end = event.get("end")
                    if start and end:
                        duration = (end - start).total_seconds() / 3600
                        stats["total_meetings_hours"] += duration

            current_date += timedelta(days=1)

        return stats

    def get_upcoming_with_person(
        self,
        person_email: str,
        days_ahead: int = 14,
    ) -> list[dict[str, Any]]:
        """Find upcoming meetings with a specific person.

        Args:
            person_email: Email address to look for.
            days_ahead: Number of days to look ahead.

        Returns:
            List of events with this person.
        """
        meetings = []
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=days_ahead)

        current_date = start_date
        while current_date <= end_date:
            events = self.get_events_for_date(current_date)

            for event in events:
                # Check if person is in attendees
                attendees = event.get("attendees", [])
                for att in attendees:
                    if att.get("email", "").lower() == person_email.lower():
                        meetings.append(event)
                        break

                # Also check organizer
                organizer = event.get("organizer", {})
                if organizer.get("email", "").lower() == person_email.lower():
                    if event not in meetings:
                        meetings.append(event)

            current_date += timedelta(days=1)

        return meetings
