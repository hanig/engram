"""Bot actions that modify data (require confirmation)."""

from .confirmable import ConfirmableAction, PendingAction
from .github_actions import CreateIssueAction, CommentOnIssueAction
from .email_actions import CreateDraftAction

__all__ = [
    "ConfirmableAction",
    "PendingAction",
    "CreateIssueAction",
    "CommentOnIssueAction",
    "CreateDraftAction",
]
