"""Todoist archiving — push 🔥-rated ideas to the 'Project ideas' project."""

import logging

import requests

from src.config import TODOIST_API_KEY

logger = logging.getLogger(__name__)

TODOIST_API_BASE = "https://api.todoist.com/api/v1"

# Set via TODOIST_PROJECT_ID env var (see config.py)
from src.config import TODOIST_PROJECT_ID


def _get_headers() -> dict | None:
    """Return auth headers, or None if key missing."""
    if not TODOIST_API_KEY:
        logger.warning("TODOIST_API_KEY not set — archiving disabled")
        return None
    return {
        "Authorization": f"Bearer {TODOIST_API_KEY}",
        "Content-Type": "application/json",
    }


def _score_to_priority(scores: dict) -> int:
    """Map average score to Todoist priority (4=urgent, 1=low).

    Todoist priorities are inverted: 4 is highest, 1 is lowest.
    """
    avg = sum(scores.values()) / max(len(scores), 1)
    if avg >= 4:
        return 4  # urgent
    elif avg >= 3:
        return 3  # high
    elif avg >= 2:
        return 2  # medium
    return 1  # low


def _build_description(
    brief: str,
    theme: str,
    strategy: str,
    scores: dict,
    is_stretch: bool,
    idea_number: int,
    date_str: str,
) -> str:
    """Pack IdeaSpark metadata into the task description."""
    strategy_label = "A: papers × new lit" if strategy == "A" else "B: papers × trends"
    stretch_tag = " [STRETCH]" if is_stretch else ""
    header = (
        f"IdeaSpark #{idea_number} — {date_str}{stretch_tag}\n"
        f"Theme: {theme}\n"
        f"Strategy: {strategy_label}\n"
        f"Scores: N={scores.get('novelty', '?')}/5 · "
        f"F={scores.get('feasibility', '?')}/5 · "
        f"I={scores.get('impact', '?')}/5\n"
        f"{'━' * 40}\n\n"
    )
    return header + brief


def archive_idea(
    idea_number: int,
    title: str,
    date_str: str,
    theme: str,
    strategy: str,
    scores: dict,
    brief: str,
    is_stretch: bool = False,
) -> str | None:
    """Archive a 🔥-rated idea to the 'Project ideas' Todoist project.

    Returns the task ID on success, None on failure.
    """
    headers = _get_headers()
    if not headers:
        return None

    if not TODOIST_PROJECT_ID:
        logger.warning("TODOIST_PROJECT_ID not set — archiving disabled")
        return None

    description = _build_description(
        brief=brief,
        theme=theme,
        strategy=strategy,
        scores=scores,
        is_stretch=is_stretch,
        idea_number=idea_number,
        date_str=date_str,
    )

    priority = _score_to_priority(scores)

    # Labels for filtering
    labels = ["ideaspark", theme.lower().replace(" ", "-")]
    if is_stretch:
        labels.append("stretch")

    payload = {
        "content": title,
        "description": description,
        "project_id": TODOIST_PROJECT_ID,
        "priority": priority,
        "labels": labels,
    }

    try:
        resp = requests.post(
            f"{TODOIST_API_BASE}/tasks",
            headers=headers,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        task = resp.json()
        task_id = task["id"]
        logger.info(f"Archived idea #{idea_number} to Todoist: {task_id}")
        return task_id
    except requests.RequestException as e:
        logger.error(f"Failed to archive idea to Todoist: {e}")
        return None
