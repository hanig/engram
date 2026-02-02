"""Slack workspace content indexer."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import SLACK_WORKSPACE
from ..integrations.slack import SlackClient
from ..knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


class SlackIndexer:
    """Indexer for Slack workspace messages and users."""

    def __init__(self, kg: KnowledgeGraph | None = None):
        """Initialize the Slack indexer.

        Args:
            kg: Knowledge graph instance. Creates new one if not provided.
        """
        self.kg = kg or KnowledgeGraph()

    def index_all(
        self,
        max_messages_per_channel: int = 1000,
        max_channels: int = 50,
        days_back: int = 90,
    ) -> dict[str, Any]:
        """Index all accessible Slack content.

        Args:
            max_messages_per_channel: Maximum messages to index per channel.
            max_channels: Maximum number of channels to index.
            days_back: How many days of history to index.

        Returns:
            Statistics about the indexing operation.
        """
        logger.info("Starting full Slack index")

        client = SlackClient()
        stats = {
            "channels_indexed": 0,
            "messages_indexed": 0,
            "users_indexed": 0,
            "errors": 0,
        }

        # Calculate oldest timestamp
        oldest = (datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp()

        try:
            # Index users first (for resolving user IDs in messages)
            users = client.list_users()
            for user in users:
                self._index_user(user, stats)
            logger.info(f"Indexed {stats['users_indexed']} users")

            # Get accessible channels
            channels = client.list_channels()[:max_channels]

            for channel in channels:
                if channel.get("is_archived"):
                    continue

                try:
                    self._index_channel(channel, stats)

                    # Get channel messages
                    messages = client.get_channel_history(
                        channel_id=channel["id"],
                        limit=max_messages_per_channel,
                        oldest=oldest,
                    )

                    for message in messages:
                        self._index_message(message, channel, stats)

                    stats["channels_indexed"] += 1
                    logger.info(
                        f"Indexed channel #{channel['name']}: "
                        f"{len(messages)} messages"
                    )

                except Exception as e:
                    logger.error(f"Error indexing channel {channel['name']}: {e}")
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"Error in Slack indexing: {e}")
            stats["errors"] += 1

        self.kg.set_last_sync(
            source="slack",
            account=SLACK_WORKSPACE,
            last_sync=datetime.now(timezone.utc),
            metadata={"type": "full", "stats": stats},
        )

        logger.info(f"Slack indexing complete: {stats}")
        return stats

    def index_delta(self, days_back: int = 1) -> dict[str, Any]:
        """Index recent Slack messages.

        Args:
            days_back: Number of days to look back.

        Returns:
            Statistics about the indexing operation.
        """
        logger.info(f"Starting delta Slack sync (last {days_back} days)")

        client = SlackClient()
        stats = {
            "channels_checked": 0,
            "messages_indexed": 0,
            "errors": 0,
        }

        oldest = (datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp()

        try:
            channels = client.list_channels()

            for channel in channels:
                if channel.get("is_archived"):
                    continue

                try:
                    messages = client.get_channel_history(
                        channel_id=channel["id"],
                        limit=100,
                        oldest=oldest,
                    )

                    for message in messages:
                        self._index_message(message, channel, stats)

                    stats["channels_checked"] += 1

                except Exception as e:
                    logger.error(f"Error checking channel {channel['name']}: {e}")
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"Error in Slack delta sync: {e}")
            stats["errors"] += 1

        self.kg.set_last_sync(
            source="slack",
            account=SLACK_WORKSPACE,
            last_sync=datetime.now(timezone.utc),
            metadata={"type": "delta", "stats": stats},
        )

        logger.info(f"Slack delta sync complete: {stats}")
        return stats

    def _index_user(self, user: dict, stats: dict[str, int]) -> None:
        """Index a Slack user as a person entity."""
        if user.get("is_bot") or user.get("deleted"):
            return

        person_id = f"person:slack:{user['id']}"

        self.kg.upsert_entity(
            entity_id=person_id,
            entity_type="person",
            name=user.get("real_name") or user.get("display_name") or user["name"],
            email=user.get("email"),
            source="slack",
            source_account=SLACK_WORKSPACE,
            metadata={
                "slack_id": user["id"],
                "slack_name": user["name"],
                "title": user.get("title"),
                "timezone": user.get("timezone"),
            },
        )

        stats["users_indexed"] += 1

    def _index_channel(self, channel: dict, stats: dict[str, int]) -> None:
        """Index a Slack channel as an entity."""
        entity_id = f"slack:channel:{channel['id']}"

        self.kg.upsert_entity(
            entity_id=entity_id,
            entity_type="channel",
            name=channel["name"],
            source="slack",
            source_account=SLACK_WORKSPACE,
            metadata={
                "slack_id": channel["id"],
                "topic": channel.get("topic"),
                "purpose": channel.get("purpose"),
                "is_private": channel.get("is_private", False),
                "num_members": channel.get("num_members", 0),
            },
        )

    def _index_message(
        self,
        message: dict,
        channel: dict,
        stats: dict[str, int],
    ) -> None:
        """Index a Slack message."""
        if not message.get("text"):
            return

        content_id = f"slack:message:{message['id']}"

        # Link to user
        if message.get("user_id"):
            self.kg.add_relationship(
                from_id=content_id,
                from_type="message",
                to_id=f"person:slack:{message['user_id']}",
                to_type="person",
                relation="author",
            )

        # Link to channel
        self.kg.add_relationship(
            from_id=content_id,
            from_type="message",
            to_id=f"slack:channel:{channel['id']}",
            to_type="channel",
            relation="posted_in",
        )

        self.kg.upsert_content(
            content_id=content_id,
            content_type="message",
            source="slack",
            source_account=SLACK_WORKSPACE,
            title=f"#{channel['name']} message",
            body=message["text"][:5000],
            source_id=message["id"],
            timestamp=message.get("timestamp"),
            metadata={
                "channel_id": channel["id"],
                "channel_name": channel["name"],
                "user_id": message.get("user_id"),
                "thread_ts": message.get("thread_ts"),
                "reply_count": message.get("reply_count", 0),
                "has_reactions": bool(message.get("reactions")),
            },
        )

        stats["messages_indexed"] += 1
