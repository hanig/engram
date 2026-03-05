#!/usr/bin/env python3
"""IdeaSpark daily runner — generates and posts one research idea to Slack.

Required Slack Bot scopes (add in https://api.slack.com/apps):
    - reactions:read    (for feedback collection via emoji reactions)
    - Already granted by engram: chat:write, im:write, im:read, im:history, users:read
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import (
    SLACK_AUTHORIZED_USERS,
    get_user_timezone,
    PROJECT_ROOT,
)
from src.ideaspark.agent import IdeaSparkAgent
from src.ideaspark.memory import IdeaMemory
from src.ideaspark.notion_archive import archive_idea

logger = logging.getLogger(__name__)



def post_to_slack(brief: str, user_id: str | None = None) -> str | None:
    """Post idea brief to Slack DM. Returns message timestamp for reaction tracking."""
    try:
        from src.integrations.slack import SlackClient
        slack = SlackClient()

        if not user_id:
            if SLACK_AUTHORIZED_USERS:
                user_id = SLACK_AUTHORIZED_USERS[0]
            else:
                logger.error("No authorized Slack users configured")
                return None

        # Open DM channel
        response = slack._client.conversations_open(users=[user_id])
        channel_id = response["channel"]["id"]

        # Post the brief as a rich message
        result = slack._client.chat_postMessage(
            channel=channel_id,
            text=brief,
            mrkdwn=True,
        )

        ts = result.get("ts")
        logger.info(f"Posted IdeaSpark to Slack (ts={ts})")
        return ts

    except Exception as e:
        logger.error(f"Error posting to Slack: {e}")
        return None


def collect_reactions(channel_id: str, message_ts: str) -> str | None:
    """Check for emoji reactions on a message. Returns reaction type or None."""
    try:
        from src.integrations.slack import SlackClient
        slack = SlackClient()
        result = slack._client.reactions_get(channel=channel_id, timestamp=message_ts)
        message = result.get("message", {})
        reactions = message.get("reactions", [])

        for r in reactions:
            name = r.get("name", "")
            if name == "fire":
                return "fire"
            elif name == "thinking_face":
                return "thinking"
            elif name in ("-1", "thumbsdown"):
                return "thumbsdown"

        return None
    except Exception as e:
        logger.warning(f"Error collecting reactions: {e}")
        return None


def run_daily():
    """Main daily execution."""
    now = datetime.now(get_user_timezone())
    logger.info(f"IdeaSpark daily run: {now.strftime('%Y-%m-%d %H:%M')}")

    # Generate idea
    agent = IdeaSparkAgent()
    result = agent.generate_idea()

    if result is None:
        logger.info("No idea generated today (below quality threshold or error)")
        return

    # Post to Slack
    brief = result["brief"]
    ts = post_to_slack(brief)

    if ts:
        # Update the idea log with Slack timestamp for reaction tracking
        memory = IdeaMemory()
        for entry in memory.idea_log:
            if entry["id"] == result["idea_number"]:
                entry["slack_ts"] = ts
                memory.save()
                break

    logger.info(
        f"IdeaSpark #{result['idea_number']}: {result['title']} "
        f"[N:{result['scores']['novelty']} F:{result['scores']['feasibility']} "
        f"I:{result['scores']['impact']}]"
    )


def collect_feedback():
    """Scan past ideas for new reactions and update preferences."""
    from src.integrations.slack import SlackClient
    memory = IdeaMemory()
    slack = SlackClient()
    user_id = SLACK_AUTHORIZED_USERS[0] if SLACK_AUTHORIZED_USERS else None

    if not user_id:
        logger.error("No authorized user for feedback collection")
        return

    # Open DM channel
    response = slack._client.conversations_open(users=[user_id])
    channel_id = response["channel"]["id"]

    updated = 0
    for entry in memory.idea_log:
        if entry.get("reaction") is not None:
            continue  # already have feedback
        ts = entry.get("slack_ts")
        if not ts:
            continue

        reaction = collect_reactions(channel_id, ts)
        if reaction:
            memory.record_feedback(entry["id"], reaction)
            logger.info(f"Idea #{entry['id']}: reaction={reaction}")
            updated += 1

            # Archive to Notion if 🔥
            if reaction == "fire":
                archive_idea(
                    idea_number=entry["id"],
                    title=entry.get("title", f"Idea #{entry['id']}"),
                    date_str=entry.get("date", "")[:10],
                    theme=entry.get("theme", ""),
                    strategy=entry.get("strategy", ""),
                    scores=entry.get("scores", {}),
                    brief=entry.get("brief", ""),
                    is_stretch=entry.get("is_stretch", False),
                )

    if updated:
        logger.info(f"Collected {updated} new reactions")

    # Generate meta-summary if threshold reached
    summary = memory.generate_meta_summary()
    if summary:
        logger.info(f"Meta-summary available:\n{summary}")


def main():
    parser = argparse.ArgumentParser(description="IdeaSpark daily research idea generator")
    parser.add_argument("--generate", action="store_true", help="Generate and post today's idea")
    parser.add_argument("--feedback", action="store_true", help="Collect reactions from past ideas")
    parser.add_argument("--dry-run", action="store_true", help="Generate but don't post to Slack")
    parser.add_argument("--status", action="store_true", help="Show idea log stats")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if args.status:
        memory = IdeaMemory()
        print(f"Total ideas: {memory.get_idea_count()}")
        print(f"🔥: {memory.preferences.get('total_fire', 0)}")
        print(f"👎: {memory.preferences.get('total_thumbsdown', 0)}")
        if memory.get_idea_count() > 0:
            hit_rate = memory.preferences.get("total_fire", 0) / memory.get_idea_count() * 100
            print(f"Hit rate: {hit_rate:.0f}%")
        print(f"\nPreferred themes: {memory.get_preferred_themes()}")
        print(f"Preferred strategy: {memory.get_preferred_strategy()}")
        summary = memory.generate_meta_summary()
        if summary:
            print(f"\n{summary}")
        return

    if args.feedback:
        collect_feedback()
        return

    if args.generate or args.dry_run:
        agent = IdeaSparkAgent()
        result = agent.generate_idea()

        if result is None:
            print("No idea generated (below quality threshold)")
            return

        print(result["brief"])
        print(f"\n--- Metadata ---")
        print(f"Title: {result['title']}")
        print(f"Scores: {result['scores']}")
        print(f"Theme: {result['theme']}")
        print(f"Strategy: {result['strategy']}")
        print(f"Stretch: {result['is_stretch']}")

        if not args.dry_run:
            ts = post_to_slack(result["brief"])
            if ts:
                print(f"\nPosted to Slack (ts={ts})")
            else:
                print("\nFailed to post to Slack")
        return

    # Default: run daily pipeline (generate + post + collect feedback)
    run_daily()
    collect_feedback()


if __name__ == "__main__":
    main()
