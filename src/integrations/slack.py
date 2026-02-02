"""Slack API client for indexing workspace data."""

import logging
from datetime import datetime
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ..config import SLACK_BOT_TOKEN

logger = logging.getLogger(__name__)


class SlackClient:
    """Client for indexing Slack workspace data."""

    def __init__(self, token: str | None = None):
        """Initialize Slack client.

        Args:
            token: Slack bot token. Defaults to environment variable.
        """
        self.token = token or SLACK_BOT_TOKEN
        if not self.token:
            raise ValueError("Slack bot token is required")

        self._client = WebClient(token=self.token)
        self._user_cache: dict[str, dict] = {}
        self._channel_cache: dict[str, dict] = {}

    def test_connection(self) -> dict[str, Any]:
        """Test the Slack connection and get bot info."""
        try:
            response = self._client.auth_test()
            return {
                "ok": response["ok"],
                "user": response.get("user"),
                "user_id": response.get("user_id"),
                "team": response.get("team"),
                "team_id": response.get("team_id"),
            }
        except SlackApiError as e:
            logger.error(f"Error testing connection: {e}")
            raise

    def list_channels(
        self,
        types: str = "public_channel,private_channel",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """List channels the bot has access to.

        Args:
            types: Channel types (public_channel, private_channel, mpim, im).
            limit: Maximum number of channels.

        Returns:
            List of channel metadata.
        """
        channels = []
        cursor = None

        try:
            while len(channels) < limit:
                response = self._client.conversations_list(
                    types=types,
                    limit=min(limit - len(channels), 200),
                    cursor=cursor,
                )

                for channel in response.get("channels", []):
                    channels.append(self._parse_channel(channel))

                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

        except SlackApiError as e:
            logger.error(f"Error listing channels: {e}")

        return channels

    def get_channel_info(self, channel_id: str) -> dict[str, Any] | None:
        """Get channel information.

        Args:
            channel_id: The channel ID.

        Returns:
            Channel metadata or None if not found.
        """
        if channel_id in self._channel_cache:
            return self._channel_cache[channel_id]

        try:
            response = self._client.conversations_info(channel=channel_id)
            channel = self._parse_channel(response["channel"])
            self._channel_cache[channel_id] = channel
            return channel
        except SlackApiError as e:
            if e.response["error"] == "channel_not_found":
                return None
            logger.error(f"Error getting channel {channel_id}: {e}")
            return None

    def get_channel_history(
        self,
        channel_id: str,
        limit: int = 100,
        oldest: float | None = None,
        latest: float | None = None,
    ) -> list[dict[str, Any]]:
        """Get message history from a channel.

        Args:
            channel_id: The channel ID.
            limit: Maximum number of messages.
            oldest: Unix timestamp for oldest message.
            latest: Unix timestamp for latest message.

        Returns:
            List of message metadata.
        """
        messages = []
        cursor = None

        try:
            while len(messages) < limit:
                params = {
                    "channel": channel_id,
                    "limit": min(limit - len(messages), 200),
                }
                if cursor:
                    params["cursor"] = cursor
                if oldest:
                    params["oldest"] = str(oldest)
                if latest:
                    params["latest"] = str(latest)

                response = self._client.conversations_history(**params)

                for msg in response.get("messages", []):
                    parsed = self._parse_message(msg, channel_id)
                    if parsed:
                        messages.append(parsed)

                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

        except SlackApiError as e:
            logger.error(f"Error getting channel history for {channel_id}: {e}")

        return messages

    def get_thread_replies(
        self,
        channel_id: str,
        thread_ts: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get replies in a thread.

        Args:
            channel_id: The channel ID.
            thread_ts: The thread's parent message timestamp.
            limit: Maximum number of replies.

        Returns:
            List of message metadata.
        """
        try:
            response = self._client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=limit,
            )

            messages = []
            for msg in response.get("messages", []):
                # Skip the parent message
                if msg.get("ts") != thread_ts:
                    parsed = self._parse_message(msg, channel_id)
                    if parsed:
                        messages.append(parsed)

            return messages

        except SlackApiError as e:
            logger.error(f"Error getting thread replies: {e}")
            return []

    def search_messages(
        self,
        query: str,
        count: int = 50,
        sort: str = "timestamp",
        sort_dir: str = "desc",
    ) -> list[dict[str, Any]]:
        """Search messages in the workspace.

        Note: Requires search:read scope.

        Args:
            query: Search query.
            count: Maximum number of results.
            sort: Sort field (timestamp, score).
            sort_dir: Sort direction (asc, desc).

        Returns:
            List of message metadata.
        """
        try:
            response = self._client.search_messages(
                query=query,
                count=count,
                sort=sort,
                sort_dir=sort_dir,
            )

            messages = []
            for match in response.get("messages", {}).get("matches", []):
                messages.append({
                    "id": f"{match['channel']['id']}:{match['ts']}",
                    "text": match.get("text", ""),
                    "user_id": match.get("user"),
                    "channel_id": match["channel"]["id"],
                    "channel_name": match["channel"].get("name"),
                    "timestamp": datetime.fromtimestamp(float(match["ts"])),
                    "permalink": match.get("permalink"),
                })

            return messages

        except SlackApiError as e:
            # search_messages requires specific scopes
            logger.error(f"Error searching messages: {e}")
            return []

    def get_user_info(self, user_id: str) -> dict[str, Any] | None:
        """Get user information.

        Args:
            user_id: The user ID.

        Returns:
            User metadata or None if not found.
        """
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            response = self._client.users_info(user=user_id)
            user = self._parse_user(response["user"])
            self._user_cache[user_id] = user
            return user
        except SlackApiError as e:
            if e.response["error"] == "user_not_found":
                return None
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    def list_users(self, limit: int = 500) -> list[dict[str, Any]]:
        """List all users in the workspace.

        Args:
            limit: Maximum number of users.

        Returns:
            List of user metadata.
        """
        users = []
        cursor = None

        try:
            while len(users) < limit:
                response = self._client.users_list(
                    limit=min(limit - len(users), 200),
                    cursor=cursor,
                )

                for user in response.get("members", []):
                    parsed = self._parse_user(user)
                    users.append(parsed)
                    self._user_cache[user["id"]] = parsed

                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

        except SlackApiError as e:
            logger.error(f"Error listing users: {e}")

        return users

    def get_mentions(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get messages mentioning a user.

        Args:
            user_id: The user ID to find mentions for.
            limit: Maximum number of results.

        Returns:
            List of message metadata.
        """
        # Use search to find mentions
        return self.search_messages(f"<@{user_id}>", count=limit)

    def _parse_channel(self, channel: dict) -> dict[str, Any]:
        """Parse a channel object into a dictionary."""
        return {
            "id": channel["id"],
            "name": channel.get("name", ""),
            "is_private": channel.get("is_private", False),
            "is_archived": channel.get("is_archived", False),
            "is_member": channel.get("is_member", False),
            "topic": channel.get("topic", {}).get("value", ""),
            "purpose": channel.get("purpose", {}).get("value", ""),
            "num_members": channel.get("num_members", 0),
            "created": datetime.fromtimestamp(channel.get("created", 0)),
        }

    def _parse_message(
        self, message: dict, channel_id: str
    ) -> dict[str, Any] | None:
        """Parse a message object into a dictionary."""
        # Skip bot messages and system messages
        if message.get("subtype") in ["bot_message", "channel_join", "channel_leave"]:
            return None

        return {
            "id": f"{channel_id}:{message['ts']}",
            "text": message.get("text", ""),
            "user_id": message.get("user"),
            "channel_id": channel_id,
            "timestamp": datetime.fromtimestamp(float(message["ts"])),
            "thread_ts": message.get("thread_ts"),
            "reply_count": message.get("reply_count", 0),
            "reactions": [
                {"name": r["name"], "count": r["count"]}
                for r in message.get("reactions", [])
            ],
            "has_files": bool(message.get("files")),
        }

    def _parse_user(self, user: dict) -> dict[str, Any]:
        """Parse a user object into a dictionary."""
        profile = user.get("profile", {})
        return {
            "id": user["id"],
            "name": user.get("name", ""),
            "real_name": user.get("real_name", profile.get("real_name", "")),
            "display_name": profile.get("display_name", ""),
            "email": profile.get("email"),
            "title": profile.get("title", ""),
            "is_bot": user.get("is_bot", False),
            "is_admin": user.get("is_admin", False),
            "deleted": user.get("deleted", False),
            "timezone": user.get("tz", ""),
        }
