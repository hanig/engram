"""Base class for actions that require confirmation."""

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..formatters import format_confirmation

# Action timeout in seconds (5 minutes)
ACTION_TIMEOUT = 5 * 60


@dataclass
class PendingAction(ABC):
    """Base class for pending actions that require user confirmation."""

    action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if all required fields are filled.

        Returns:
            True if action is ready for confirmation.
        """
        pass

    @abstractmethod
    def get_next_prompt(self) -> str:
        """Get the prompt for the next required field.

        Returns:
            Prompt string asking for missing information.
        """
        pass

    @abstractmethod
    def update_from_input(self, text: str) -> None:
        """Update action fields from user input.

        Args:
            text: User input text.
        """
        pass

    @abstractmethod
    def get_preview(self) -> str:
        """Get a preview of what the action will do.

        Returns:
            Preview text.
        """
        pass

    @abstractmethod
    def execute(self) -> dict[str, Any]:
        """Execute the action.

        Returns:
            Result dictionary with 'success' and 'message'.
        """
        pass

    @abstractmethod
    def get_action_type(self) -> str:
        """Get the action type name.

        Returns:
            Human-readable action type.
        """
        pass

    def is_expired(self) -> bool:
        """Check if the action has expired.

        Returns:
            True if action is older than timeout.
        """
        return time.time() - self.created_at > ACTION_TIMEOUT

    def get_confirmation_prompt(self) -> dict[str, Any]:
        """Get the confirmation prompt with buttons.

        Returns:
            Response dictionary with blocks.
        """
        return format_confirmation(
            action_type=self.get_action_type(),
            preview=self.get_preview(),
            action_id=self.action_id,
        )


class ConfirmableAction(PendingAction):
    """Generic confirmable action (for simple cases)."""

    def __init__(
        self,
        action_type: str,
        preview: str,
        execute_fn,
    ):
        """Initialize a generic confirmable action.

        Args:
            action_type: Human-readable action type.
            preview: Preview text.
            execute_fn: Function to execute (no args).
        """
        super().__init__()
        self._action_type = action_type
        self._preview = preview
        self._execute_fn = execute_fn

    def is_ready(self) -> bool:
        return True

    def get_next_prompt(self) -> str:
        return ""

    def update_from_input(self, text: str) -> None:
        pass

    def get_preview(self) -> str:
        return self._preview

    def execute(self) -> dict[str, Any]:
        return self._execute_fn()

    def get_action_type(self) -> str:
        return self._action_type
