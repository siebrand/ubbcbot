from typing import Dict, Any, List, Tuple
from handlers.base_handler import BaseHandler
from models.entities import OrderStatus, AuthorizationStatus
from decimal import Decimal

class DeliveryOverviewHandler(BaseHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.current_batch = 0
        self.customers_data = []
    
    def start_send_overviews(self, chat_id: int) -> Dict[str, Any]:
        """Start the delivery overview sending process"""
        # Get customers with LABELING_COMPLETED orders
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        self.customers_data = []
        
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            labeling_completed_orders = [o for o in orders if o.status == OrderStatus.LABELING_COMPLETED.value]
            if labeling_completed_orders:
                # Separate delivered and delayed items
                delivered_orders = [o for o in labeling_completed_orders if o.received_quantity == o.quantity]
                delayed_orders = [o for o in labeling_completed_orders if o.received_quantity < o.quantity]
                
                self.customers_data.append({
                    'customer': customer,
                    'delivered_orders': delivered_orders,
                    'delayed_orders': delayed_orders
                })
        
        if not self.customers_data:
            self._send_message(chat_id, "❌ No customers with orders ready for delivery overview")
            return {'status': 'no_customers'}
        
        self.current_batch = 0
        return self._request_payment_link(chat_id)
    
    def _request_payment_link(self, chat_id: int) -> Dict[str, Any]:
        """Request payment link for current batch"""
        remaining_customers = len(self.customers_data) - (self.current_batch * 50)
        batch_size = min(50, remaining_customers)
        batch_number = self.current_batch + 1
        total_batches = (len(self.customers_data) + 49) // 50
        
        message = f"💳 Payment Link Request (Batch {batch_number}/{total_batches}):\n\n"
        message += f"👥 Customers in this batch: {batch_size}\n"
        message += f"📧 Please provide the payment link for these {batch_size} customers:"
        
        # Store context for reply handling
        self._store_context(chat_id, 'payment_link_input', str(self.current_batch))
        
        self._send_message(chat_id, message, reply_markup={"force_reply": True, "input_field_placeholder": "Enter payment link"})
        return {'status': 'awaiting_payment_link'}
    
    def handle_payment_link_input(self, chat_id: int, payment_link: str, batch_str: str) -> Dict[str, Any]:
        """Handle payment link input and send overviews"""
        try:
            batch_index = int(batch_str)
            start_idx = batch_index * 50
            end_idx = min(start_idx + 50, len(self.customers_data))
            
            batch_customers = self.customers_data[start_idx:end_idx]
            sent_count = 0
            
            for customer_data in batch_customers:
                if self._send_delivery_overview(customer_data, payment_link):
                    sent_count += 1
            
            # Update batch counter
            self.current_batch += 1
            
            message = f"✅ Batch {batch_index + 1} completed: {sent_count}/{len(batch_customers)} overviews sent\n\n"
            
            # Check if more batches needed
            if self.current_batch * 50 < len(self.customers_data):
                message += "📧 Ready for next batch..."
                self._send_message(chat_id, message)
                return self._request_payment_link(chat_id)
            else:
                message += f"🎉 All delivery overviews sent!\nTotal customers notified: {len(self.customers_data)}"
                self._send_message(chat_id, message)
                return {'status': 'completed'}
                
        except Exception as e:
            self._send_message(chat_id, f"❌ Error processing payment link: {str(e)}")
            return {'status': 'error'}
    
    def _send_delivery_overview(self, customer_data: Dict, payment_link: str) -> bool:
        """Send delivery overview to a customer"""
        try:
            customer = customer_data['customer']
            delivered_orders = customer_data['delivered_orders']
            delayed_orders = customer_data['delayed_orders']
            
            # Calculate totals
            delivered_total = sum(order.total_price for order in delivered_orders)
            
            # Build message
            message = f"📦 Delivery Overview\n\n"
            
            if delivered_orders:
                message += "✅ Ready for Pickup:\n"
                for order in delivered_orders:
                    offer = self.db.get_offer(order.offer_id)
                    offer_name = offer.name if offer else "Unknown"
                    message += f"• {order.quantity}x {offer_name} - €{order.total_price:.2f}\n"
                message += f"\nTotal to pay: €{delivered_total:.2f}\n"
                message += f"Payment: {payment_link}\n\n"
            
            if delayed_orders:
                message += "⏳ Delayed Items (for your information):\n"
                for order in delayed_orders:
                    offer = self.db.get_offer(order.offer_id)
                    offer_name = offer.name if offer else "Unknown"
                    delayed_qty = order.quantity - order.received_quantity
                    message += f"• {delayed_qty}x {offer_name} - will arrive later\n"
            
            # Send message
            result = self._send_message(customer.telegram_user_id, message)
            
            if result.get('success'):
                # Update orders to AWAITING_PAYMENT
                for order in delivered_orders:
                    self.db.update_order(order.order_id, {'status': OrderStatus.AWAITING_PAYMENT.value})
                return True
            else:
                return False
                
        except Exception as e:
            print(f"Error sending delivery overview to customer {customer.customer_id}: {e}")
            return False
    
    def handle_mark_customer_paid(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Mark a customer's orders as paid"""
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, "❌ Customer not found")
            return {'status': 'customer_not_found'}
        
        # Get awaiting payment orders
        orders = self.db.get_orders_by_customer(customer_id)
        awaiting_payment_orders = [o for o in orders if o.status == OrderStatus.AWAITING_PAYMENT.value]
        
        if not awaiting_payment_orders:
            self._send_message(chat_id, f"❌ No orders awaiting payment for {customer.first_name}")
            return {'status': 'no_orders'}
        
        # Update orders to COMPLETED
        updated_count = 0
        for order in awaiting_payment_orders:
            if self.db.update_order(order.order_id, {'status': OrderStatus.COMPLETED.value}):
                updated_count += 1
        
        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown"
        total_amount = sum(order.total_price for order in awaiting_payment_orders)
        
        if updated_count > 0:
            self._send_message(chat_id, f"✅ Payment confirmed for {customer_name}\n{updated_count} orders marked as COMPLETED\nTotal: €{total_amount:.2f}")
            
            # Notify customer
            self._send_message(customer.telegram_user_id, f"✅ Payment received! Your orders are now ready for pickup.\nTotal: €{total_amount:.2f}")
            
            return {'status': 'success', 'updated_count': updated_count}
        else:
            self._send_message(chat_id, f"❌ Failed to update orders for {customer_name}")
            return {'status': 'error'}
    
    def _store_context(self, chat_id: int, context_type: str, data: str):
        """Store context for reply handling"""
        from models.entities import EditContext
        
        # Delete existing context
        existing = self.db.get_edit_context_by_chat_id(chat_id)
        if existing:
            self.db.delete_edit_context(existing.context_id)
        
        # Create new context
        context = EditContext(
            chat_id=chat_id,
            edit_type=context_type,
            entity_id=data
        )
        self.db.create_edit_context(context)