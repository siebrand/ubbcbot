from typing import Any

from handlers.base_handler import BaseHandler


class AuthCommands(BaseHandler):
    def handle_unauthorized_start(self, chat_id: int) -> dict[str, Any]:
        """Handle /start for unauthorized users"""
        self._send_message(chat_id, self._t("unauthorized", None))
        return {"status": "unauthorized"}
