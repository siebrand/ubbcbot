from typing import Dict, Any, List, Tuple
import os
import json
import boto3
from handlers.base_handler import BaseHandler
from models.entities import OrderStatus, AuthorizationStatus
from decimal import Decimal

class DeliveryOverviewHandler(BaseHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.lambda_client = boto3.client('lambda')
        self.message_sender_lambda = os.environ.get('MESSAGE_SENDER_LAMBDA_NAME')
    
    def start_send_overviews(self, chat_id: int) -> Dict[str, Any]:
        """Start the delivery overview sending process"""
        # Get customers with LABELING_COMPLETED orders
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        customers_data = []
        
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            labeling_completed_orders = [o for o in orders if o.status == OrderStatus.LABELING_COMPLETED.value]
            if labeling_completed_orders:
                # Separate delivered and delayed items
                delivered_orders = [o for o in labeling_completed_orders if (o.received_quantity or 0) >= o.quantity]
                delayed_orders = [o for o in labeling_completed_orders if (o.received_quantity or 0) < o.quantity]
                
                customers_data.append({
                    'customer_id': customer.customer_id,
                    'delivered_order_ids': [o.order_id for o in delivered_orders],
                    'delayed_order_ids': [o.order_id for o in delayed_orders],
                    'is_guest': customer.is_guest
                })
        
        if not customers_data:
            return self._send_message(chat_id, self._t('no_customers_ready_overview', user_id=None))
        
        # Sort: regular customers first, guest users last
        customers_data.sort(key=lambda x: x['is_guest'])
        
        # Store customers data in context for later use
        import json
        context_data = {
            'customers_data': customers_data,
            'current_batch': 0
        }
        self._store_context(chat_id, 'payment_link_input', json.dumps(context_data))
        
        return self._request_payment_link(chat_id, customers_data, 0)
    
    def _request_payment_link(self, chat_id: int, customers_data: list, current_batch: int) -> Dict[str, Any]:
        """Request payment link for current batch"""
        remaining_customers = len(customers_data) - (current_batch * 50)
        batch_size = min(50, remaining_customers)
        batch_number = current_batch + 1
        total_batches = (len(customers_data) + 49) // 50
        
        message = self._t('payment_link_request', user_id=None,
                         batch_number=batch_number,
                         total_batches=total_batches,
                         batch_size=batch_size)
        
        # Store context for reply handling
        import json
        context_data = {
            'customers_data': customers_data,
            'current_batch': current_batch
        }
        self._store_context(chat_id, 'payment_link_input', json.dumps(context_data))
        
        self._send_message(chat_id, message, reply_markup={"force_reply": True, "input_field_placeholder": "Enter payment link"})
        return {'status': 'awaiting_payment_link'}
    
    def handle_payment_link_input(self, chat_id: int, payment_link: str, batch_str: str) -> Dict[str, Any]:
        """Handle payment link input and invoke async message sender"""
        try:
            # Store payment link for later use
            self._store_payment_link(payment_link)
            
            # Get stored customers data from context
            import json
            context_data = json.loads(batch_str)
            customers_data = context_data['customers_data']
            
            batch_index = context_data['current_batch']
            start_idx = batch_index * 50
            end_idx = min(start_idx + 50, len(customers_data))
            
            batch_customers = customers_data[start_idx:end_idx]
            
            # Build messages for async sending
            messages = []
            for customer_data in batch_customers:
                msg = self._build_delivery_message_payload(customer_data, payment_link)
                if msg:
                    messages.append(msg)
            
            # Invoke message sender Lambda
            payload = {
                'messages': messages,
                'environment': self.environment
            }
            
            response = self.lambda_client.invoke(
                FunctionName=self.message_sender_lambda,
                InvocationType='Event',  # Async invocation
                Payload=json.dumps(payload)
            )
            
            # Update orders to AWAITING_PAYMENT immediately
            for customer_data in batch_customers:
                for order_id in customer_data['delivered_order_ids']:
                    self.db.update_order(order_id, {'status': OrderStatus.AWAITING_PAYMENT.value}, admin_id=self.admin_user_id, reason="Delivery overview queued")
            
            # Update batch counter
            current_batch = batch_index + 1
            
            message = self._t('batch_queued', user_id=None, 
                            batch_number=batch_index + 1, 
                            batch_size=len(batch_customers))
            
            # Check if more batches needed
            if current_batch * 50 < len(customers_data):
                message += "\n📧 Ready for next batch..."
                self._send_message(chat_id, message)
                
                # Update context with new batch number
                context_data['current_batch'] = current_batch
                
                return self._request_payment_link(chat_id, customers_data, current_batch)
            else:
                message += self._t('all_overviews_queued', user_id=None, total_customers=len(customers_data))
                self._send_message(chat_id, message)
                
                return {'status': 'completed'}
                
        except Exception as e:
            self._send_message(chat_id, self._t('error_processing_payment_link', user_id=None, error=str(e)))
            return {'status': 'error'}
    
    def _build_delivery_message_payload(self, customer_data: Dict, payment_link: str) -> Dict:
        """Build message payload for async sending"""
        try:
            customer = self.db.get_customer(customer_data['customer_id'])
            if not customer:
                return None
            
            delivered_orders = [self.db.get_order(order_id) for order_id in customer_data['delivered_order_ids']]
            delayed_orders = [self.db.get_order(order_id) for order_id in customer_data['delayed_order_ids']]
            
            delivered_orders = [o for o in delivered_orders if o]
            delayed_orders = [o for o in delayed_orders if o]
            
            message = self._build_delivery_message(customer, delivered_orders, delayed_orders, payment_link)
            
            # Build customer name
            name_parts = []
            if customer.first_name:
                name_parts.append(customer.first_name)
            if customer.last_name:
                name_parts.append(customer.last_name)
            customer_name = " ".join(name_parts) or self._t('unknown', user_id=None)
            
            # For guests, send to admin; for regular customers, send from admin account
            if customer.is_guest:
                admin_message = f"📋 {self._t('delivery_overview_for', user_id=None, customer_name=customer_name)}\n\n{message}"
                return {
                    'user_id': int(self.admin_user_id),
                    'message': str(admin_message),
                    'from_admin': False,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True,
                    'customer_name': str(customer_name)
                }
            else:
                return {
                    'user_id': int(customer.telegram_user_id),
                    'message': str(message),
                    'from_admin': True,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True,
                    'customer_name': str(customer_name)
                }
        except Exception as e:
            print(f"Error building message for customer {customer_data['customer_id']}: {e}")
            return None
    
    def _build_delivery_message(self, customer, delivered_orders: List, delayed_orders: List, payment_link: str, is_reminder: bool = False) -> str:
        """Build delivery/reminder message for customer"""
        delivered_total = sum(order.total_price for order in delivered_orders)
        
        # Add title based on message type
        if is_reminder:
            message = self._t('payment_reminder_title', user_id=customer.telegram_user_id) + "\n\n"
            message += self._t('payment_reminder_intro', user_id=customer.telegram_user_id) + "\n\n"
        else:
            message = self._t('delivery_ready_title', user_id=customer.telegram_user_id) + "\n\n"
            message += self._t('delivery_ready_intro', user_id=customer.telegram_user_id) + "\n\n"
        
        if delivered_orders:
            message += self._t('order_summary_title', user_id=customer.telegram_user_id) + "\n\n"
            for order in delivered_orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t('unknown', user_id=None)
                message += f"- {order.quantity}x {offer_name} — €{order.total_price:.2f}\n"
            
            message += "\n" + self._t('total_amount_bold', user_id=customer.telegram_user_id, total=delivered_total) + "\n\n"
            message += self._t('pay_via_tikkie', user_id=customer.telegram_user_id, link=payment_link, total=delivered_total) + "\n"
            message += "━━━━━━━━━━━━━━━━━━━━\n"
            message += self._t('pickup_location_bold', user_id=customer.telegram_user_id, location=customer.location) + "\n"
            message += "━━━━━━━━━━━━━━━━━━━━\n"
            message += self._t('questions_contact', user_id=customer.telegram_user_id) + "\n\n"
        
        if delayed_orders:
            message += self._t('delayed_items_info', user_id=customer.telegram_user_id) + "\n"
            for order in delayed_orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t('unknown', user_id=None)
                delayed_qty = order.quantity - (order.received_quantity or 0)
                message += f"• {delayed_qty}x {offer_name} - " + self._t('will_arrive_later', user_id=customer.telegram_user_id) + "\n"
        
        return message
    
    def _send_admin_notification(self, customer, delivered_orders: List, delayed_orders: List, message: str, success: bool, customer_name: str, delivered_total):
        """Send admin notification about delivery overview"""
        if customer.is_guest:
            admin_message = f"📋 {self._t('delivery_overview_for', user_id=None, customer_name=customer_name)}\n\n{message}"
        else:
            admin_message = f"✅ {customer_name}\n"
            for order in delivered_orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t('unknown', user_id=None)
                admin_message += f"{order.quantity}x {offer_name} - €{order.total_price:.2f}\n"
            admin_message += f"Total: €{delivered_total:.2f}"
        
        if success:
            self._send_message(self.admin_user_id, self._t('admin_overview_sent_success', user_id=None, message=admin_message), parse_mode="HTML")
        else:
            error_msg = self._t('unknown', user_id=None)
            self._send_message(self.admin_user_id, self._t('admin_overview_sent_failed', user_id=None, customer_name=customer_name, error=error_msg, message=admin_message))
    
    def handle_process_customer_paid(self, chat_id: int, customer_id: str, current_page: int = 1) -> Dict[str, Any]:
        """Set a customer's orders as paid"""
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t('customer_not_found', user_id=None))
            return {'status': 'customer_not_found'}
        
        # Get awaiting payment orders
        orders = self.db.get_orders_by_customer(customer_id)
        awaiting_payment_orders = [o for o in orders if o.status == OrderStatus.AWAITING_PAYMENT.value]
        
        if not awaiting_payment_orders:
            self._send_message(chat_id, self._t('no_orders_awaiting_payment', user_id=None, customer_name=customer.first_name))
            return {'status': 'no_orders'}
        
        # Update orders to COMPLETED using transaction method
        updated_count = 0
        for order in awaiting_payment_orders:
            if self.db.mark_order_paid_with_audit(order.order_id, self.admin_user_id):
                updated_count += 1
        
        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t('unknown', user_id=None)
        total_amount = sum(order.total_price for order in awaiting_payment_orders)
        
        if updated_count > 0:
            self._send_message(chat_id, self._t('payment_confirmed', user_id=None, customer_name=customer_name, updated_count=updated_count, total_amount=total_amount))
            
            # Notify customer via message sender (from admin)
            payload = {
                'messages': [{
                    'user_id': int(customer.telegram_user_id),
                    'message': self._t('payment_received_notification', customer.telegram_user_id, total_amount=total_amount, location=customer.location),
                    'from_admin': True,
                    'parse_mode': 'HTML'
                }],
                'environment': self.environment
            }
            self.lambda_client.invoke(
                FunctionName=self.message_sender_lambda,
                InvocationType='Event',
                Payload=json.dumps(payload)
            )
            
            # Return to process_payment list
            from handlers.admin.order_commands import AdminOrderCommands
            order_commands = AdminOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
            return order_commands.handle_process_payment(chat_id, [], current_page)
        else:
            self._send_message(chat_id, self._t('failed_update_orders_customer', user_id=None, customer_name=customer_name))
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
    
    def _store_payment_link(self, payment_url: str):
        """Store payment link for later use"""
        self.db.store_payment_link(payment_url)
