"""Notion archiving — push 🔥-rated ideas to the existing Project ideas database."""

import logging
from datetime import datetime

from src.config import NOTION_API_KEY

logger = logging.getLogger(__name__)

# Existing "Project ideas" database on Notion
# https://www.notion.so/arcinstitute/Project-ideas-1e6062f5e0e8809598d8f4775fd6aa59
NOTION_DB_ID = "202062f5-e0e8-8089-9e81-c3e2fe2edd87"

# Data source (collection) ID for direct API calls
NOTION_DATA_SOURCE_ID = "202062f5-e0e8-800c-8374-000ba5b9424e"


def _get_notion_client():
    """Lazy import and init of Notion client."""
    try:
        from notion_client import Client
        if not NOTION_API_KEY:
            logger.warning("NOTION_API_KEY not set — archiving disabled")
            return None
        return Client(auth=NOTION_API_KEY)
    except ImportError:
        logger.warning("notion-client not installed — archiving disabled")
        return None


def _chunk_rich_text(text: str, limit: int = 2000) -> list[dict]:
    """Split text into Notion rich_text blocks of ≤ limit characters each."""
    blocks = []
    for i in range(0, len(text), limit):
        blocks.append({"text": {"content": text[i : i + limit]}})
    return blocks


def _score_to_priority(scores: dict) -> str:
    """Map average score to priority level."""
    avg = sum(scores.values()) / max(len(scores), 1)
    if avg >= 4:
        return "High"
    elif avg >= 3:
        return "Medium"
    return "Low"


def _build_notes(
    brief: str,
    theme: str,
    strategy: str,
    scores: dict,
    is_stretch: bool,
    idea_number: int,
    date_str: str,
) -> str:
    """Pack IdeaSpark metadata into the Notes field."""
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
    database_id: str = NOTION_DB_ID,
) -> str | None:
    """Archive a 🔥-rated idea to the Project ideas Notion database.

    Maps to existing schema:
        Name    → idea title
        Notes   → full brief + metadata (theme, strategy, scores)
        Wet/Dry → "Dry" (or "Hybrid" for stretch)
        priority → High/Medium/Low from avg score
        Lead    → empty (user assigns)
    """
    notion = _get_notion_client()
    if not notion:
        return None

    notes_text = _build_notes(
        brief=brief,
        theme=theme,
        strategy=strategy,
        scores=scores,
        is_stretch=is_stretch,
        idea_number=idea_number,
        date_str=date_str,
    )

    wet_dry = "Hybrid" if is_stretch else "Dry"
    priority = _score_to_priority(scores)

    try:
        page = notion.pages.create(
            parent={"database_id": database_id},
            properties={
                "Name": {"title": [{"text": {"content": title}}]},
                "Notes": {"rich_text": _chunk_rich_text(notes_text)},
                "Wet/Dry": {"select": {"name": wet_dry}},
                "priority": {"select": {"name": priority}},
            },
        )
        logger.info(f"Archived idea #{idea_number} to Notion: {page['id']}")
        return page["id"]
    except Exception as e:
        logger.error(f"Failed to archive idea to Notion: {e}")
        return None
