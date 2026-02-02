"""Slack event handlers for the bot."""

import logging
import re
from typing import Any

from slack_bolt import App

from ..config import SLACK_AUTHORIZED_USERS
from .conversation import ConversationManager
from .formatters import format_error_message, format_help_message
from .intent_router import IntentRouter, Intent

logger = logging.getLogger(__name__)


def register_event_handlers(app: App, conversation_manager: ConversationManager) -> None:
    """Register all event handlers with the app.

    Args:
        app: Slack App instance.
        conversation_manager: Conversation manager instance.
    """
    # Initialize intent router
    intent_router = IntentRouter()

    # Import handlers
    from .handlers.search import SearchHandler
    from .handlers.calendar import CalendarHandler
    from .handlers.email import EmailHandler
    from .handlers.github import GitHubHandler
    from .handlers.briefing import BriefingHandler

    # Initialize handlers (lazy - they'll load resources when needed)
    handlers = {
        "search": SearchHandler(),
        "calendar": CalendarHandler(),
        "email": EmailHandler(),
        "github": GitHubHandler(),
        "briefing": BriefingHandler(),
    }

    @app.event("app_mention")
    def handle_mention(event: dict, say, client) -> None:
        """Handle @mentions of the bot."""
        _handle_message(event, say, client, is_dm=False)

    @app.event("message")
    def handle_dm(event: dict, say, client) -> None:
        """Handle direct messages to the bot."""
        # Only handle DMs (channel type "im")
        if event.get("channel_type") == "im":
            # Ignore bot's own messages
            if event.get("bot_id"):
                return
            _handle_message(event, say, client, is_dm=True)

    @app.action(re.compile(r"^confirm_action:.*"))
    def handle_confirm(ack, body, client) -> None:
        """Handle action confirmation buttons."""
        ack()
        _handle_action_confirmation(body, client, confirmed=True)

    @app.action(re.compile(r"^cancel_action:.*"))
    def handle_cancel(ack, body, client) -> None:
        """Handle action cancellation buttons."""
        ack()
        _handle_action_confirmation(body, client, confirmed=False)

    def _handle_message(event: dict, say, client, is_dm: bool) -> None:
        """Common message handling logic."""
        user_id = event.get("user")
        channel_id = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")
        text = event.get("text", "")

        # Check authorization
        if not _is_authorized(user_id):
            say(
                text="Sorry, you're not authorized to use this bot.",
                thread_ts=thread_ts,
            )
            logger.warning(f"Unauthorized access attempt by user {user_id}")
            return

        # Strip bot mention from text
        text = _strip_bot_mention(text, client)

        if not text.strip():
            say(text=format_help_message(), thread_ts=thread_ts)
            return

        # Get or create conversation context
        context = conversation_manager.get_or_create(
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
        )

        # Add user message to history
        context.add_message("user", text)

        try:
            # Check for pending action that needs input
            if context.pending_action:
                response = _handle_pending_action_input(context, text, handlers)
            else:
                # Route to appropriate handler
                response = _route_message(
                    text=text,
                    context=context,
                    intent_router=intent_router,
                    handlers=handlers,
                )

            # Add assistant response to history
            if response:
                context.add_message("assistant", response.get("text", ""))

            # Send response
            if response:
                _send_response(say, response, thread_ts)
            else:
                say(
                    text="I'm not sure how to help with that. Try asking about your calendar, emails, or searching for information.",
                    thread_ts=thread_ts,
                )

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            say(text=format_error_message(str(e)), thread_ts=thread_ts)

    def _handle_action_confirmation(body: dict, client, confirmed: bool) -> None:
        """Handle action confirmation or cancellation."""
        user_id = body.get("user", {}).get("id")
        action_id = body.get("actions", [{}])[0].get("action_id", "")
        channel_id = body.get("channel", {}).get("id")
        message_ts = body.get("message", {}).get("ts")

        # Extract action key from action_id (e.g., "confirm_action:abc123")
        action_key = action_id.split(":", 1)[1] if ":" in action_id else ""

        # Get conversation context
        context = conversation_manager.get(user_id, channel_id)

        if not context or not context.pending_action:
            # Update message to show expired
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text="This action has expired.",
                blocks=[],
            )
            return

        pending = context.pending_action

        if confirmed:
            try:
                # Execute the action
                result = pending.execute()

                # Update message with success
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text=f"Action completed: {result.get('message', 'Success')}",
                    blocks=[],
                )

            except Exception as e:
                logger.error(f"Error executing action: {e}")
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text=f"Error executing action: {str(e)}",
                    blocks=[],
                )
        else:
            # Update message with cancellation
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text="Action cancelled.",
                blocks=[],
            )

        # Clear pending action
        context.pending_action = None


def _is_authorized(user_id: str) -> bool:
    """Check if a user is authorized to use the bot."""
    # If no authorized users configured, allow all
    if not SLACK_AUTHORIZED_USERS:
        return True
    return user_id in SLACK_AUTHORIZED_USERS


def _strip_bot_mention(text: str, client) -> str:
    """Remove bot mention from message text."""
    # Get bot user ID
    try:
        auth_response = client.auth_test()
        bot_user_id = auth_response.get("user_id", "")
        # Remove <@BOT_ID> pattern
        text = re.sub(f"<@{bot_user_id}>", "", text)
    except Exception:
        pass
    return text.strip()


def _route_message(
    text: str,
    context,
    intent_router: IntentRouter,
    handlers: dict,
) -> dict[str, Any] | None:
    """Route message to appropriate handler based on intent.

    Returns:
        Response dictionary with 'text' and optionally 'blocks'.
    """
    # Classify intent
    intent = intent_router.classify(text, context.history)

    logger.info(f"Classified intent: {intent.intent} with entities: {intent.entities}")

    # Map intent to handler
    intent_to_handler = {
        "search": "search",
        "calendar_check": "calendar",
        "calendar_availability": "calendar",
        "email_search": "email",
        "email_draft": "email",
        "github_search": "github",
        "github_create_issue": "github",
        "github_list_prs": "github",
        "briefing": "briefing",
        "help": None,  # Handled specially
    }

    handler_name = intent_to_handler.get(intent.intent)

    if handler_name is None:
        if intent.intent == "help":
            return {"text": format_help_message()}
        return None

    handler = handlers.get(handler_name)
    if not handler:
        return {"text": f"Handler '{handler_name}' not available."}

    # Execute handler
    return handler.handle(intent, context)


def _handle_pending_action_input(context, text: str, handlers: dict) -> dict[str, Any]:
    """Handle input for a pending action that needs more information."""
    pending = context.pending_action

    # Update action with new input
    pending.update_from_input(text)

    # Check if action is ready
    if pending.is_ready():
        # Return confirmation prompt
        return pending.get_confirmation_prompt()
    else:
        # Ask for next required input
        return {"text": pending.get_next_prompt()}


def _send_response(say, response: dict, thread_ts: str) -> None:
    """Send response to Slack."""
    kwargs = {"thread_ts": thread_ts}

    if "blocks" in response:
        kwargs["blocks"] = response["blocks"]
        kwargs["text"] = response.get("text", "")
    else:
        kwargs["text"] = response.get("text", "")

    say(**kwargs)
