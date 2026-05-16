"""Tests for multi-account Google manager behavior."""

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.integrations.google_multi import MultiGoogleManager


def test_check_availability_ignores_all_day_events():
    """All-day events should not block the whole working day."""
    tz = ZoneInfo("America/Los_Angeles")
    date = datetime(2026, 5, 18, tzinfo=tz)
    manager = MultiGoogleManager()

    all_day_start = date.replace(hour=0, minute=0)
    timed_start = date.replace(hour=10, minute=0)
    timed_end = timed_start + timedelta(hours=1)

    with patch.object(
        manager,
        "get_all_calendars_for_date",
        return_value=[
            {
                "id": "all-day",
                "summary": "Conference",
                "is_all_day": True,
                "start": all_day_start,
                "end": all_day_start + timedelta(days=1),
            },
            {
                "id": "timed",
                "summary": "Meeting",
                "is_all_day": False,
                "start": timed_start,
                "end": timed_end,
            },
        ],
    ):
        slots = manager.check_availability(
            date=date,
            duration_minutes=30,
            working_hours=(9, 12),
        )

    assert slots == [
        {
            "start": date.replace(hour=9, minute=0),
            "end": timed_start,
            "duration_minutes": 60,
        },
        {
            "start": timed_end,
            "end": date.replace(hour=12, minute=0),
            "duration_minutes": 60,
        },
    ]
