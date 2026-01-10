from typing import Dict, Any
from models.entities import AuthorizationStatus, OrderStatus
from .base_order_handler import BaseOrderHandler
from utils.pagination import PaginationUtils

class OrderStatusManagement(BaseOrderHandler):
    """Handles order status management functionality"""
    
    def handle_send_overviews(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /send_overviews command"""
        # Get customers with LABELING_COMPLETED orders
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        customers_with_ready_orders = []
        
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            labeling_completed_orders = [o for o in orders if o.status == OrderStatus.LABELING_COMPLETED.value]
            if labeling_completed_orders:
                customers_with_ready_orders.append((customer, labeling_completed_orders))
        
        if not customers_with_ready_orders:
            self._send_message(chat_id, self._t('no_customers_ready_overview', user_id=None))
            return {'status': 'no_customers'}
        
        total_customers = len(customers_with_ready_orders)
        batches_needed = (total_customers + 49) // 50  # Round up
        
        message = f"📊 Delivery Overview Summary:\n\n👥 Customers to notify: {total_customers}\n📦 Payment link batches needed: {batches_needed}\n\nThis will send delivery overviews and move orders to AWAITING_PAYMENT status."
        
        keyboard = {
            "inline_keyboard": [[
                {"text": self._t('start_sending_overviews', user_id=None), "callback_data": "start_send_overviews"},
                {"text": self._t('cancel', user_id=None), "callback_data": "cancel_action"}
            ]]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'confirmation_shown'}
    
    def handle_mark_paid(self, chat_id: int, args: list, page: int = 1) -> Dict[str, Any]:
        """Handle /mark_paid command with pagination"""
        # Get customers with AWAITING_PAYMENT orders
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        customers_awaiting_payment = []
        
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            awaiting_payment_orders = [o for o in orders if o.status == OrderStatus.AWAITING_PAYMENT.value]
            if awaiting_payment_orders:
                customers_awaiting_payment.append((customer, awaiting_payment_orders))
        
        if not customers_awaiting_payment:
            self._send_message(chat_id, self._t('no_customers_awaiting_payment', user_id=None))
            return {'status': 'no_customers'}
        
        # Paginate results
        page_customers, total_pages = PaginationUtils.paginate_list(customers_awaiting_payment, page, 10)
        
        # Show customers with payment buttons
        message = f"💳 Customers Awaiting Payment - Page {page}/{total_pages}:\n\n"
        keyboard_rows = []
        
        for customer, orders in page_customers:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t('unknown', user_id=None)
            total_amount = sum(order.total_price for order in orders)
            message += f"👤 {customer_name}: €{total_amount:.2f} ({len(orders)} orders)\n"
            keyboard_rows.append([{"text": self._t('mark_customer_paid', user_id=None, customer_name=customer_name), "callback_data": f"mark_paid_{customer.customer_id}"}])
        
        # Add pagination keyboard if needed
        if total_pages > 1:
            pagination_keyboard = PaginationUtils.build_pagination_keyboard(page, total_pages, "mark_paid", enhanced=True)
            keyboard_rows.extend(pagination_keyboard["inline_keyboard"])
        
        keyboard = {"inline_keyboard": keyboard_rows}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'customers_shown'}
    
    def handle_failed_notifications(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /failed_notifications command - show orders that couldn't be notified"""
        # Get customers with LABELING_COMPLETED orders (these should have been notified)
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        failed_notifications = []
        
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            labeling_completed_orders = [o for o in orders if o.status == OrderStatus.LABELING_COMPLETED.value]
            if labeling_completed_orders:
                # These are orders that should have been notified but are still in LABELING_COMPLETED
                failed_notifications.append((customer, labeling_completed_orders))
        
        if not failed_notifications:
            self._send_message(chat_id, self._t('no_failed_notifications', user_id=None))
            return {'status': 'no_failed'}
        
        # Show failed notifications
        message = self._t('failed_delivery_notifications_title', user_id=None) + "\n\n"
        
        for customer, orders in failed_notifications:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t('unknown', user_id=None)
            total_amount = sum(order.total_price for order in orders)
            message += f"👤 {customer_name} (@{customer.username or 'no_username'}):\n"
            message += f"   💰 €{total_amount:.2f} ({len(orders)} orders)\n"
            for order in orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t('unknown', user_id=None)
                message += f"   • {order.quantity}x {offer_name} - €{order.total_price:.2f}\n"
            message += "\n"
        
        message += "\n💡 These customers need to be contacted manually or retry delivery overview sending."
        
        self._send_message(chat_id, message)
        return {'status': 'failed_shown'}