"""
Callback Router - Decouples callback parsing from execution
Handlers register patterns and the router dispatches to the correct handler
"""

import re
from collections.abc import Callable
from typing import Any


class CallbackRouter:
    """Routes callback queries to registered handlers based on regex patterns"""

    def __init__(self):
        self.routes = []  # List of (compiled_regex, handler_func, pattern_str)

    def register(self, pattern: str, handler_func: Callable, aliases: list[str] | None = None):
        """
        Register a callback handler.

        Args:
            pattern: Regex pattern (e.g., r"^approve_(\\d+)$")
            handler_func: Function to call when matched (receives match object and context)
            aliases: Optional list of alternative patterns
        """
        compiled = re.compile(pattern)
        self.routes.append((compiled, handler_func, pattern))

        # Register aliases pointing to same handler
        if aliases:
            for alias in aliases:
                compiled_alias = re.compile(alias)
                self.routes.append((compiled_alias, handler_func, alias))

    def dispatch(self, callback_data: str, context: dict[str, Any]) -> bool:
        """
        Match callback_data against registered patterns.

        Args:
            callback_data: The callback query data string
            context: Context dict to pass to handler

        Returns:
            True if handled, False if no pattern matched
        """
        for regex, handler, _pattern_str in self.routes:
            match = regex.match(callback_data)
            if match:
                handler(match, context)
                return True
        return False
