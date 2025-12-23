from typing import Dict, Any
from handlers.base_handler import BaseHandler

class AuthCommands(BaseHandler):
    def handle_unauthorized_start(self, chat_id: int) -> Dict[str, Any]:
        """Handle /start for unauthorized users"""
        message = "🍺 Welcome to UBBC Bot!\n\n"
        message += "⚠️ Your access is pending admin approval.\n"
        message += "Please wait for approval to use the bot.\n\n"
        message += "Contact admin if you need immediate access."
        
        self._send_message(chat_id, message)
        return {'status': 'unauthorized'}