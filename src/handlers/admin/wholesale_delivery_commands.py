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

    def handle_supplier_selection(self, chat_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle supplier selection"""
        return self.delivery_handler.handle_supplier_selection(chat_id, supplier_id)

    def handle_offer_selection(self, chat_id: int, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle offer selection"""
        return self.delivery_handler.handle_offer_selection(chat_id, offer_id, supplier_id)

    def handle_box_selection(self, chat_id: int, box_id: str, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle box selection"""
        return self.delivery_handler.handle_box_selection(chat_id, box_id, offer_id, supplier_id)

    def handle_delivery_action(self, chat_id: int, action: str, box_id: str, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle delivery action"""
        return self.delivery_handler.handle_delivery_action(chat_id, action, box_id, offer_id, supplier_id)

    def handle_partial_action(self, chat_id: int, action: str, box_id: str, received_units: int) -> Dict[str, Any]:
        """Handle partial delivery action"""
        return self.delivery_handler.handle_partial_action(chat_id, action, box_id, received_units)

    def handle_back_navigation(self, chat_id: int, target: str, *args) -> Dict[str, Any]:
        """Handle back navigation"""
        return self.delivery_handler.handle_back_navigation(chat_id, target, *args)

    def handle_complete_delivery(self, chat_id: int, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle complete delivery"""
        return self.delivery_handler.handle_complete_delivery(chat_id, offer_id, supplier_id)

    def handle_confirm_complete_delivery(self, chat_id: int, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle confirm complete delivery"""
        return self.delivery_handler.handle_confirm_complete_delivery(chat_id, offer_id, supplier_id)