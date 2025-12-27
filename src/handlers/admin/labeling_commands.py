from typing import Dict, Any, List
from handlers.base_handler import BaseHandler
from handlers.admin.labeling_completion_handler import LabelingCompletionHandler
from models.entities import OrderStatus

class LabelingCommands(BaseHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.completion_handler = LabelingCompletionHandler(db, admin_user_id, environment, telegram_token)

    def handle_labeling_completed(self, chat_id: int, user_id: int, args: List[str]) -> Dict[str, Any]:
        """Handle /labeling_completed command"""
        if not self._is_admin(user_id):
            return self._send_message(chat_id, self._t('admin_only', user_id))
        
        return self.completion_handler.handle_labeling_completed(chat_id, user_id, args)

    def handle_supplier_selection(self, chat_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Handle supplier selection"""
        return self.completion_handler.handle_supplier_selection(chat_id, supplier_id_short)

    def handle_offer_selection(self, chat_id: int, offer_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Handle offer selection"""
        return self.completion_handler.handle_offer_selection(chat_id, offer_id, supplier_id_short)

    def handle_box_selection(self, chat_id: int, box_id_short: str, offer_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Handle box selection"""
        return self.completion_handler.handle_box_selection(chat_id, box_id_short, offer_id, supplier_id_short)

    def handle_labeling_action(self, chat_id: int, action: str, box_id_short: str, offer_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Handle labeling completion action"""
        return self.completion_handler.handle_labeling_action(chat_id, action, box_id_short, offer_id, supplier_id_short)

    def handle_back_navigation(self, chat_id: int, target: str, *args) -> Dict[str, Any]:
        """Handle back navigation"""
        return self.completion_handler.handle_back_navigation(chat_id, target, *args)

    def handle_finish_labeling(self, chat_id: int, box_id: str) -> Dict[str, Any]:
        """Handle finish labeling for a box (legacy method)"""
        # Get all orders for this box that are in READY_FOR_LABELING status
        orders = self.db.get_orders_by_box(box_id)
        ready_orders = [o for o in orders if o.status == OrderStatus.READY_FOR_LABELING.value]
        
        if not ready_orders:
            self._send_message(chat_id, f"❌ No orders in READY_FOR_LABELING status found for box {box_id[:8]}")
            return {'status': 'no_orders'}
        
        # Update all ready orders to LABELING_COMPLETED
        updated_count = 0
        for order in ready_orders:
            if self.db.update_order(order.order_id, {'status': OrderStatus.LABELING_COMPLETED.value}):
                updated_count += 1
        
        if updated_count > 0:
            self._send_message(chat_id, f"✅ Labeling completed for box {box_id[:8]}\n{updated_count} orders moved to LABELING_COMPLETED status")
            return {'status': 'success', 'updated_count': updated_count}
        else:
            self._send_message(chat_id, f"❌ Failed to update orders for box {box_id[:8]}")
            return {'status': 'error'}