from typing import Dict, Any
from handlers.base_handler import BaseHandler
from .order.order_cancellation import OrderCancellation
from .order.order_placement import OrderPlacement
from .order.order_viewing import OrderViewing
from .order.order_status import OrderStatusManagement
from .order.order_maintenance import OrderMaintenance

class AdminOrderCommands(BaseHandler):
    """Main coordinator for admin order commands - delegates to specialized modules"""
    
    def __init__(self, db, admin_user_id, environment, telegram_token):
        super().__init__(db, admin_user_id, environment, telegram_token)
        
        # Initialize specialized handlers
        self.cancellation = OrderCancellation(db, admin_user_id, environment, telegram_token)
        self.placement = OrderPlacement(db, admin_user_id, environment, telegram_token)
        self.viewing = OrderViewing(db, admin_user_id, environment, telegram_token)
        self.status_mgmt = OrderStatusManagement(db, admin_user_id, environment, telegram_token)
        self.maintenance = OrderMaintenance(db, admin_user_id, environment, telegram_token)
    
    # Order Cancellation Methods
    def handle_cancel_order(self, chat_id: int, args: list) -> Dict[str, Any]:
        return self.cancellation.handle_cancel_order(chat_id, args)
    
    def handle_confirm_cancel(self, chat_id: int, args: list) -> Dict[str, Any]:
        return self.cancellation.handle_confirm_cancel(chat_id, args)
    
    def handle_confirm_cancel_with_reason(self, chat_id: int, order_id: str, reason: str) -> Dict[str, Any]:
        return self.cancellation.handle_confirm_cancel_with_reason(chat_id, order_id, reason)
    
    def handle_cancel_order_user_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        return self.cancellation.handle_cancel_order_user_select(chat_id, customer_id)
    
    def handle_cancel_orders_page(self, chat_id: int, customer_id: str, page: int) -> Dict[str, Any]:
        return self.cancellation.handle_cancel_orders_page(chat_id, customer_id, page)
    
    # Order Placement Methods
    def handle_create_order_for(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        return self.placement.handle_create_order_for(chat_id, user_id, args)
    
    def handle_order_for_user_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        return self.placement.handle_order_for_user_select(chat_id, customer_id)
    
    def handle_order_for_offer_select(self, chat_id: int, customer_id: str, offer_id: str) -> Dict[str, Any]:
        return self.placement.handle_order_for_offer_select(chat_id, customer_id, offer_id)
    
    def handle_order_for_quantity_select(self, chat_id: int, customer_id: str, offer_id: str, quantity: str) -> Dict[str, Any]:
        return self.placement.handle_order_for_quantity_select(chat_id, customer_id, offer_id, quantity)
    
    def handle_order_for_other_quantity(self, chat_id: int, customer_id: str, offer_id: str) -> Dict[str, Any]:
        return self.placement.handle_order_for_other_quantity(chat_id, customer_id, offer_id)
    
    # Order Viewing Methods
    def handle_user_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        return self.viewing.handle_user_orders(chat_id, args)
    
    def handle_all_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        return self.viewing.handle_all_orders(chat_id, args)
    
    def handle_offer_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        return self.viewing.handle_offer_orders(chat_id, args)
    
    def handle_user_orders_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        return self.viewing.handle_user_orders_select(chat_id, customer_id)
    
    def handle_offer_orders_page(self, chat_id: int, page: int) -> Dict[str, Any]:
        return self.viewing.handle_offer_orders_page(chat_id, page)
    
    def handle_offer_orders_detail_page(self, chat_id: int, offer_id: str, page: int) -> Dict[str, Any]:
        return self.viewing.handle_offer_orders_detail_page(chat_id, offer_id, page)
    
    def handle_export_orders_callback(self, chat_id: int, status_filter: str) -> Dict[str, Any]:
        return self.viewing.handle_export_orders_callback(chat_id, status_filter)
    
    # Order Status Management Methods
    def handle_send_overviews(self, chat_id: int, args: list) -> Dict[str, Any]:
        return self.status_mgmt.handle_send_overviews(chat_id, args)
    
    def handle_mark_paid(self, chat_id: int, args: list, page: int = 1) -> Dict[str, Any]:
        return self.status_mgmt.handle_mark_paid(chat_id, args, page)
    
    def handle_failed_notifications(self, chat_id: int, args: list) -> Dict[str, Any]:
        return self.status_mgmt.handle_failed_notifications(chat_id, args)
    
    # Order Maintenance Methods
    def handle_delete_old_orders(self, chat_id: int) -> Dict[str, Any]:
        return self.maintenance.handle_delete_old_orders(chat_id)
    
    def handle_audit_orders(self, chat_id: int) -> Dict[str, Any]:
        return self.maintenance.handle_audit_orders(chat_id)
