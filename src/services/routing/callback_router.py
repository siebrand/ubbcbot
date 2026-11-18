"""
Callback Router - Decouples callback parsing from execution
Handlers register patterns and the router dispatches to the correct handler
"""

import re
from collections.abc import Callable
from typing import Any, NamedTuple

# What happens to the keyboard of the tapped message after the callback
REMOVE_KEYBOARD = "remove"  # the buttons are gone, so an old message cannot be tapped twice
KEEP_KEYBOARD = "keep"  # navigation (pages, the delivery workflow, order buttons) keeps working
DELETE_MESSAGE = "delete"  # the handler sends a fresh message that replaces this one


class Route(NamedTuple):
    regex: re.Pattern
    handler: Callable
    pattern: str
    # Open to approved customers. Callback data is client-supplied: everything else is admin-only.
    customer: bool = False
    keyboard: str = REMOVE_KEYBOARD


class CallbackRouter:
    """Routes callback queries to registered handlers based on regex patterns. The first match wins."""

    def __init__(self):
        self.routes: list[Route] = []

    def register(
        self,
        pattern: str,
        handler_func: Callable,
        aliases: list[str] | None = None,
        customer: bool = False,
        keyboard: str = REMOVE_KEYBOARD,
    ):
        """
        Register a callback handler.

        Args:
            pattern: Regex pattern (e.g., r"^approve_(\\d+)$")
            handler_func: Function to call when matched (receives match object and context)
            aliases: Optional list of alternative patterns
            customer: Whether approved customers may trigger it (default: admin only)
            keyboard: What happens to the keyboard of the tapped message (REMOVE_KEYBOARD, KEEP_KEYBOARD, ...)
        """
        for each in [pattern, *(aliases or [])]:
            self.routes.append(Route(re.compile(each), handler_func, each, customer, keyboard))

    def match(self, callback_data: str) -> tuple[Route, re.Match] | tuple[None, None]:
        """The first route that matches, with its match; (None, None) when none does"""
        for route in self.routes:
            found = route.regex.match(callback_data)
            if found:
                return route, found
        return None, None

    def dispatch(self, callback_data: str, context: dict[str, Any]) -> bool:
        """
        Match callback_data against registered patterns.

        Args:
            callback_data: The callback query data string
            context: Context dict to pass to handler

        Returns:
            True if handled, False if no pattern matched
        """
        route, found = self.match(callback_data)
        if route is None:
            return False
        route.handler(found, context)
        return True
