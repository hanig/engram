"""Main Slack bot application using Socket Mode."""

import logging
from typing import Callable

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from ..config import SLACK_APP_TOKEN, SLACK_BOT_TOKEN
from .conversation import ConversationManager
from .event_handlers import register_event_handlers
from .formatters import format_error_message

logger = logging.getLogger(__name__)


def create_bot_app(
    bot_token: str | None = None,
    app_token: str | None = None,
) -> tuple[App, SocketModeHandler]:
    """Create and configure the Slack bot application.

    Args:
        bot_token: Slack bot token. Defaults to environment variable.
        app_token: Slack app token for Socket Mode. Defaults to environment variable.

    Returns:
        Tuple of (App, SocketModeHandler).
    """
    bot_token = bot_token or SLACK_BOT_TOKEN
    app_token = app_token or SLACK_APP_TOKEN

    if not bot_token:
        raise ValueError("SLACK_BOT_TOKEN is required")
    if not app_token:
        raise ValueError("SLACK_APP_TOKEN is required for Socket Mode")

    # Create the app
    app = App(token=bot_token)

    # Initialize conversation manager
    conversation_manager = ConversationManager()

    # Register event handlers
    register_event_handlers(app, conversation_manager)

    # Add global error handler
    @app.error
    def global_error_handler(error, body, logger):
        logger.error(f"Error: {error}")
        logger.error(f"Request body: {body}")

    # Create Socket Mode handler
    handler = SocketModeHandler(app, app_token)

    logger.info("Slack bot app created successfully")
    return app, handler


def run_bot(
    bot_token: str | None = None,
    app_token: str | None = None,
) -> None:
    """Run the Slack bot.

    Args:
        bot_token: Slack bot token.
        app_token: Slack app token for Socket Mode.
    """
    app, handler = create_bot_app(bot_token, app_token)

    logger.info("Starting Slack bot in Socket Mode...")
    print("Bot is running! Press Ctrl+C to stop.")

    try:
        handler.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise


class BotContext:
    """Context object passed to handlers."""

    def __init__(
        self,
        app: App,
        conversation_manager: ConversationManager,
    ):
        """Initialize bot context.

        Args:
            app: Slack App instance.
            conversation_manager: Conversation manager instance.
        """
        self.app = app
        self.conversations = conversation_manager

        # Lazy-loaded components
        self._query_engine = None
        self._semantic_indexer = None
        self._multi_google = None
        self._github_client = None

    @property
    def query_engine(self):
        """Get query engine (lazy loaded)."""
        if self._query_engine is None:
            from ..query.engine import QueryEngine
            self._query_engine = QueryEngine()
        return self._query_engine

    @property
    def semantic_indexer(self):
        """Get semantic indexer (lazy loaded)."""
        if self._semantic_indexer is None:
            from ..semantic.semantic_indexer import SemanticIndexer
            self._semantic_indexer = SemanticIndexer()
        return self._semantic_indexer

    @property
    def multi_google(self):
        """Get multi-Google manager (lazy loaded)."""
        if self._multi_google is None:
            from ..integrations.google_multi import MultiGoogleManager
            self._multi_google = MultiGoogleManager()
        return self._multi_google

    @property
    def github_client(self):
        """Get GitHub client (lazy loaded)."""
        if self._github_client is None:
            from ..integrations.github_client import GitHubClient
            self._github_client = GitHubClient()
        return self._github_client
