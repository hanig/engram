"""GitHub handler for GitHub-related queries."""

import logging
from typing import Any

from ..actions.github_actions import CreateIssueAction
from ..conversation import ConversationContext
from ..formatters import format_github_issues, format_github_prs, format_search_results
from ..intent_router import Intent
from .base import BaseHandler

logger = logging.getLogger(__name__)


class GitHubHandler(BaseHandler):
    """Handler for GitHub-related queries."""

    def __init__(self):
        """Initialize the GitHub handler."""
        self._github_client = None

    @property
    def github_client(self):
        """Lazy load GitHub client."""
        if self._github_client is None:
            from ...integrations.github_client import GitHubClient
            self._github_client = GitHubClient()
        return self._github_client

    def handle(self, intent: Intent, context: ConversationContext) -> dict[str, Any]:
        """Handle a GitHub intent.

        Args:
            intent: Classified intent with entities.
            context: Conversation context.

        Returns:
            Response dictionary with GitHub information.
        """
        if intent.intent == "github_list_prs":
            return self._handle_list_prs(intent, context)
        elif intent.intent == "github_create_issue":
            return self._handle_create_issue(intent, context)
        else:
            return self._handle_search(intent, context)

    def _handle_list_prs(
        self, intent: Intent, context: ConversationContext
    ) -> dict[str, Any]:
        """Handle list PRs intent."""
        try:
            prs = self.github_client.get_my_prs(state="open", max_results=20)
            return format_github_prs(prs)

        except Exception as e:
            logger.error(f"Error listing PRs: {e}")
            return {"text": f"Error listing pull requests: {str(e)}"}

    def _handle_search(
        self, intent: Intent, context: ConversationContext
    ) -> dict[str, Any]:
        """Handle GitHub search intent."""
        query = intent.entities.get("query", "")
        repo = intent.entities.get("repo", "")

        if not query:
            return {"text": "What would you like to search for on GitHub?"}

        try:
            # Try searching issues first
            issues = self.github_client.get_my_issues(state="all", max_results=10)

            # Filter by query
            filtered_issues = [
                i for i in issues
                if query.lower() in (i.get("title", "") + i.get("body", "")).lower()
            ]

            if filtered_issues:
                return format_github_issues(filtered_issues, query)

            # Fall back to code search
            code_results = self.github_client.search_code(
                query=query,
                repo=repo or None,
                max_results=10,
            )

            if code_results:
                # Format as search results
                results = [
                    {
                        "text": f"{r['path']} in {r['repo']}",
                        "metadata": {
                            "title": r["name"],
                            "source_type": "code",
                        },
                        "score": 1.0,
                    }
                    for r in code_results
                ]
                return format_search_results(results, query)

            return {"text": f"No GitHub results found for '{query}'"}

        except Exception as e:
            logger.error(f"Error searching GitHub: {e}")
            return {"text": f"Error searching GitHub: {str(e)}"}

    def _handle_create_issue(
        self, intent: Intent, context: ConversationContext
    ) -> dict[str, Any]:
        """Handle create issue intent."""
        repo = intent.entities.get("repo", "")
        title = intent.entities.get("title", "")
        body = intent.entities.get("body", "")
        labels = intent.entities.get("labels", "")

        # Parse labels
        label_list = []
        if labels:
            label_list = [l.strip() for l in labels.split(",")]

        # Create pending action
        action = CreateIssueAction(
            repo=repo,
            title=title,
            body=body,
            labels=label_list,
        )

        # Check what we need
        if not action.is_ready():
            context.pending_action = action
            return {"text": action.get_next_prompt()}

        # If we have enough info, show confirmation
        context.pending_action = action
        return action.get_confirmation_prompt()
