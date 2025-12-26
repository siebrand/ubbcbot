from typing import Dict, Any
from handlers.base_handler import BaseHandler
from models.entities import OrderStatus

class LabelingCommands(BaseHandler):
    def handle_finish_labeling(self, chat_id: int, box_id: str) -> Dict[str, Any]:
        """Handle finish labeling for a box"""
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