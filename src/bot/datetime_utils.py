"""Date and time parsing helpers for bot actions."""

from datetime import datetime, timedelta

from ..config import get_user_timezone


def parse_event_datetime(date_str: str, time_str: str) -> datetime:
    """Parse bot event date/time strings into a timezone-aware datetime."""
    tz = get_user_timezone()
    now = datetime.now(tz)

    date_lower = date_str.lower().strip()
    if date_lower == "today":
        target_date = now.date()
    elif date_lower == "tomorrow":
        target_date = (now + timedelta(days=1)).date()
    elif date_lower == "yesterday":
        target_date = (now - timedelta(days=1)).date()
    else:
        day_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        if date_lower in day_names:
            target_weekday = day_names.index(date_lower)
            days_ahead = target_weekday - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            target_date = (now + timedelta(days=days_ahead)).date()
        else:
            try:
                target_date = datetime.fromisoformat(date_str).date()
            except ValueError as exc:
                raise ValueError(f"Could not parse event date: {date_str}") from exc

    hour, minute = parse_event_time(time_str)

    return datetime(
        year=target_date.year,
        month=target_date.month,
        day=target_date.day,
        hour=hour,
        minute=minute,
        tzinfo=tz,
    )


def parse_event_time(time_str: str) -> tuple[int, int]:
    """Parse a compact event time string into hour/minute."""
    time_lower = time_str.lower().strip()

    if time_lower == "noon":
        return 12, 0
    if time_lower == "midnight":
        return 0, 0

    if ":" in time_lower:
        time_part = time_lower.replace("am", "").replace("pm", "").strip()
        parts = time_part.split(":")
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except ValueError as exc:
            raise ValueError(f"Could not parse event time: {time_str}") from exc
    else:
        time_clean = time_lower.replace("am", "").replace("pm", "").strip()
        try:
            hour = int(time_clean)
            minute = 0
        except ValueError as exc:
            raise ValueError(f"Could not parse event time: {time_str}") from exc

    if "pm" in time_lower and hour < 12:
        hour += 12
    elif "am" in time_lower and hour == 12:
        hour = 0

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Event time out of range: {time_str}")

    return hour, minute
