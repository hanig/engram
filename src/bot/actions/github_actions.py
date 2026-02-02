"""GitHub actions that require confirmation."""

import logging
from dataclasses import dataclass, field
from typing import Any

from .confirmable import PendingAction

logger = logging.getLogger(__name__)


@dataclass
class CreateIssueAction(PendingAction):
    """Action to create a GitHub issue."""

    repo: str = ""
    title: str = ""
    body: str = ""
    labels: list[str] = field(default_factory=list)
    _state: str = "repo"  # What we're asking for: repo, title, body

    def is_ready(self) -> bool:
        """Check if we have enough info to create the issue."""
        return bool(self.repo and self.title)

    def get_next_prompt(self) -> str:
        """Get the prompt for the next required field."""
        if not self.repo:
            return "Which repository should I create the issue in?"
        if not self.title:
            return "What should the issue title be?"
        if not self.body:
            return "What should the issue description be? (or say 'skip' for no description)"
        return ""

    def update_from_input(self, text: str) -> None:
        """Update action fields from user input."""
        text = text.strip()

        if not self.repo:
            self.repo = text
            self._state = "title"
        elif not self.title:
            self.title = text
            self._state = "body"
        elif not self.body:
            if text.lower() != "skip":
                self.body = text
            self._state = "done"

    def get_preview(self) -> str:
        """Get a preview of the issue."""
        preview = f"*Repository:* {self.repo}\n*Title:* {self.title}"
        if self.body:
            body_preview = self.body[:200]
            if len(self.body) > 200:
                body_preview += "..."
            preview += f"\n*Description:* {body_preview}"
        if self.labels:
            preview += f"\n*Labels:* {', '.join(self.labels)}"
        return preview

    def execute(self) -> dict[str, Any]:
        """Create the GitHub issue."""
        from ...integrations.github_client import GitHubClient

        try:
            client = GitHubClient()
            issue = client.create_issue(
                repo_name=self.repo,
                title=self.title,
                body=self.body,
                labels=self.labels,
            )

            return {
                "success": True,
                "message": f"Created issue #{issue['number']}: {issue['url']}",
                "issue": issue,
            }

        except Exception as e:
            logger.error(f"Error creating issue: {e}")
            return {
                "success": False,
                "message": f"Failed to create issue: {str(e)}",
            }

    def get_action_type(self) -> str:
        return "Create GitHub Issue"


@dataclass
class CommentOnIssueAction(PendingAction):
    """Action to comment on a GitHub issue."""

    repo: str = ""
    issue_number: int = 0
    body: str = ""
    _state: str = "body"

    def is_ready(self) -> bool:
        """Check if we have enough info to comment."""
        return bool(self.repo and self.issue_number and self.body)

    def get_next_prompt(self) -> str:
        """Get the prompt for the next required field."""
        if not self.body:
            return "What should the comment say?"
        return ""

    def update_from_input(self, text: str) -> None:
        """Update action fields from user input."""
        if not self.body:
            self.body = text.strip()
            self._state = "done"

    def get_preview(self) -> str:
        """Get a preview of the comment."""
        body_preview = self.body[:200]
        if len(self.body) > 200:
            body_preview += "..."
        return f"*Issue:* {self.repo}#{self.issue_number}\n*Comment:* {body_preview}"

    def execute(self) -> dict[str, Any]:
        """Add the comment to the issue."""
        from ...integrations.github_client import GitHubClient

        try:
            client = GitHubClient()
            comment = client.add_issue_comment(
                repo_name=self.repo,
                issue_number=self.issue_number,
                body=self.body,
            )

            return {
                "success": True,
                "message": f"Added comment: {comment['url']}",
                "comment": comment,
            }

        except Exception as e:
            logger.error(f"Error adding comment: {e}")
            return {
                "success": False,
                "message": f"Failed to add comment: {str(e)}",
            }

    def get_action_type(self) -> str:
        return "Comment on GitHub Issue"
