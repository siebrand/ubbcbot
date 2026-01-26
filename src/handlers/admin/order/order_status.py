from typing import Dict, Any
import os
import json
import boto3
from models.entities import AuthorizationStatus, OrderStatus
from .base_order_handler import BaseOrderHandler
from utils.pagination import PaginationUtils

class OrderStatusManagement(BaseOrderHandler):
    """Handles order status management functionality"""
    
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.lambda_client = boto3.client('lambda')
        self.message_sender_lambda = os.environ.get('MESSAGE_SENDER_LAMBDA_NAME')
    
    def handle_send_delivery_overviews(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /send_delivery_overviews command"""
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
    
    def handle_process_payment(self, chat_id: int, args: list, page: int = 1) -> Dict[str, Any]:
        """Handle /process_payment command with pagination"""
        # Get customers with AWAITING_PAYMENT orders
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        customers_awaiting_payment = []
        
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            awaiting_payment_orders = [o for o in orders if o.status == OrderStatus.AWAITING_PAYMENT.value]
            if awaiting_payment_orders:
                customers_awaiting_payment.append((customer, awaiting_payment_orders))
        
        if not customers_awaiting_payment:
            self._send_message(
                chat_id, 
                self._t('no_customers_awaiting_payment', user_id=None),
                reply_markup=self._build_admin_menu_keyboard()
            )
            return {'status': 'no_customers'}
        
        # Sort alphabetically by last name, then first name
        customers_awaiting_payment.sort(key=lambda x: (x[0].last_name or '', x[0].first_name or ''))
        
        # Paginate results
        page_customers, total_pages = PaginationUtils.paginate_list(customers_awaiting_payment, page, 10)
        
        # Show customers with payment buttons
        message = f"💳 Customers Awaiting Payment - Page {page}/{total_pages}:\n\n"
        keyboard_rows = []
        
        for customer, orders in page_customers:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t('unknown', user_id=None)
            total_amount = sum(order.total_price for order in orders)
            message += f"👤 {customer_name}: €{total_amount:.2f} ({len(orders)} orders)\n"
            
            # Button text: ✓ Last, First €amount
            last_name = customer.last_name or ''
            first_name = customer.first_name or self._t('unknown', user_id=None)
            button_text = f"✓ {last_name}, {first_name} €{total_amount:.2f}".strip()
            keyboard_rows.append([{"text": button_text, "callback_data": f"process_payment_{customer.customer_id}"}])
        
        # Add pagination keyboard if needed
        if total_pages > 1:
            pagination_keyboard = PaginationUtils.build_pagination_keyboard(page, total_pages, "process_payment", enhanced=True)
            keyboard_rows.extend(pagination_keyboard["inline_keyboard"])
        
        # Add Done button
        keyboard_rows.append([{"text": self._t('done_general', user_id=None), "callback_data": "cancel_action"}])
        
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
            keyboard = {"inline_keyboard": [[{"text": self._t('back_to_admin'), "callback_data": "admin:main"}]]}
            self._send_message(chat_id, self._t('no_failed_notifications', user_id=None), reply_markup=keyboard)
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
        
        keyboard = {"inline_keyboard": [[{"text": self._t('back_to_admin'), "callback_data": "admin:main"}]]}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'failed_shown'}
    
    def handle_send_payment_reminder(self, chat_id: int, args: list, page: int = 1) -> Dict[str, Any]:
        """Handle /send_payment_reminder command with pagination"""
        # Get customers with AWAITING_PAYMENT orders
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        customers_awaiting_payment = []
        
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            awaiting_payment_orders = [o for o in orders if o.status == OrderStatus.AWAITING_PAYMENT.value]
            if awaiting_payment_orders:
                customers_awaiting_payment.append((customer, awaiting_payment_orders))
        
        if not customers_awaiting_payment:
            self._send_message(
                chat_id, 
                self._t('no_customers_awaiting_payment', user_id=None),
                reply_markup=self._build_admin_menu_keyboard()
            )
            return {'status': 'no_customers'}
        
        # Sort alphabetically by last name, then first name
        customers_awaiting_payment.sort(key=lambda x: (x[0].last_name or '', x[0].first_name or ''))
        
        # Paginate results
        page_customers, total_pages = PaginationUtils.paginate_list(customers_awaiting_payment, page, 10)
        
        # Show customers with reminder buttons
        message = f"🔔 Payment Reminders - Page {page}/{total_pages}:\n\n"
        keyboard_rows = []
        
        for customer, orders in page_customers:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t('unknown', user_id=None)
            total_amount = sum(order.total_price for order in orders)
            message += f"👤 {customer_name}: €{total_amount:.2f} ({len(orders)} orders)\n"
            
            # Button text: 🔔 Last, First €amount
            last_name = customer.last_name or ''
            first_name = customer.first_name or self._t('unknown', user_id=None)
            button_text = f"🔔 {last_name}, {first_name} €{total_amount:.2f}".strip()
            keyboard_rows.append([{"text": button_text, "callback_data": f"remind_payment_{customer.customer_id}"}])
        
        # Add pagination keyboard if needed
        if total_pages > 1:
            pagination_keyboard = PaginationUtils.build_pagination_keyboard(page, total_pages, "remind_payment", enhanced=True)
            keyboard_rows.extend(pagination_keyboard["inline_keyboard"])
        
        # Add Done button
        keyboard_rows.append([{"text": self._t('done_general', user_id=None), "callback_data": "cancel_action"}])
        
        keyboard = {"inline_keyboard": keyboard_rows}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'customers_shown'}
    
    def handle_send_payment_reminder_to_customer(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Send payment reminder to a specific customer"""
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
        
        # Get stored payment link
        payment_link = self.db.get_payment_link()
        if not payment_link:
            self._send_message(chat_id, self._t('no_payment_link_stored', user_id=None))
            return {'status': 'no_payment_link'}
        
        # Build reminder message using delivery overview helper
        from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
        delivery_handler = DeliveryOverviewHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t('unknown', user_id=None)
        message = delivery_handler._build_delivery_message(customer, awaiting_payment_orders, [], payment_link, is_reminder=True)
        
        # Ensure message is a plain string (convert any Decimal formatting)
        message = str(message)
        
        # Send from admin account (not bot) for regular customers
        if customer.is_guest:
            # For guests, send to admin with customer context
            admin_message = f"🔔 {self._t('payment_reminder_for', user_id=None, customer_name=customer_name)}\n\n{message}"
            result = self._send_message(self.admin_user_id, admin_message, parse_mode="HTML")
        else:
            # For regular customers, send directly from admin account
            result = self._send_user_message(customer.telegram_user_id, message)
        
        if result.get('success'):
            self._send_message(chat_id, self._t('payment_reminder_sent', user_id=None, customer_name=customer_name))
            return self.handle_send_payment_reminder(chat_id, [], 1)
        else:
            error = result.get('error', 'Unknown error')
            self._send_message(chat_id, self._t('payment_reminder_failed', user_id=None, customer_name=customer_name) + f" ({error})")
            return {'status': 'error'}
    
    def _send_user_message(self, user_id: int, message: str, parse_mode: str = 'HTML', disable_web_page_preview: bool = True) -> Dict[str, Any]:
        """Send message from admin account via MessageSender Lambda"""
        try:
            payload = {
                'messages': [{
                    'user_id': int(user_id),
                    'message': str(message),
                    'from_admin': True,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': disable_web_page_preview
                }],
                'environment': self.environment
            }
            
            response = self.lambda_client.invoke(
                FunctionName=self.message_sender_lambda,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            result = json.loads(response['Payload'].read())
            body = json.loads(result.get('body', '{}'))
            
            if body.get('success_count', 0) > 0:
                return {'success': True}
            else:
                error = body.get('results', [{}])[0].get('error', 'Unknown error')
                return {'success': False, 'error': error}
        except Exception as e:
            return {'success': False, 'error': str(e)}
