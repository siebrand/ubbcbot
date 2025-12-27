from typing import Dict, Any, List
from handlers.base_handler import BaseHandler
from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler

class WholesaleDeliveryCommands(BaseHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.delivery_handler = WholesaleDeliveryHandler(db, admin_user_id, environment, telegram_token)

    def handle_wholesale_delivery(self, chat_id: int, user_id: int, args: List[str]) -> Dict[str, Any]:
        """Handle /wholesale_delivery command"""
        if not self._is_admin(user_id):
            return self._send_message(chat_id, self._t('admin_only', user_id))
        
        return self.delivery_handler.handle_wholesale_delivery(chat_id, user_id, args)

    def handle_incomplete_delivery_reply(self, chat_id: int, user_id: int, text: str, context_data: str) -> Dict[str, Any]:
        """Handle reply for incomplete delivery quantity input"""
        if not self._is_admin(user_id):
            return self._send_message(chat_id, self._t('admin_only', user_id))
        
        return self.delivery_handler.handle_incomplete_delivery_reply(chat_id, text, context_data)