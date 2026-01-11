from typing import Dict, Any
from datetime import datetime, UTC
from models.entities import BoxStatus, AuthorizationStatus
from .base_order_handler import BaseOrderHandler
from services.box_status_manager import BoxStatusManager

class OrderCancellation(BaseOrderHandler):
    """Handles order cancellation functionality"""
    
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)
    
    def handle_cancel_order(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /cancel_order command with enhanced detection"""
        if not args:
            # Show button-based UI to ask for username
            message = self._t('enter_username_for_cancel', chat_id)
            keyboard = {
                "inline_keyboard": [[
                    {"text": "📝 Enter Username", "callback_data": "enter_username_cancel"}
                ]]
            }
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'awaiting_input'}

        if len(args) == 1:
            arg = args[0]
            
            # Enhanced detection logic:
            # 1. If exactly 8 alphanumeric characters -> partial order ID
            # 2. If fully numeric and longer than 8 -> full order ID
            # 3. Otherwise -> username
            
            if len(arg) == 8 and arg.isalnum():
                return self._handle_cancel_order_by_partial_id(chat_id, arg)
            elif arg.isdigit() and len(arg) > 8:
                return self.handle_cancel_order_by_id(chat_id, arg)
        
        # Username provided - show orders for cancellation
        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "cancel_order_user_select")
        
        if error:
            return error
        
        return self._show_user_orders_for_cancel(chat_id, customer)
    
    def _handle_cancel_order_by_partial_id(self, chat_id: int, partial_order_id: str) -> Dict[str, Any]:
        """Handle cancel order by partial order ID (first 8 characters) with enhanced confirmation"""
        # Search for orders that start with the partial ID
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        matching_orders = []
        
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            for order in orders:
                if order.order_id.startswith(partial_order_id) and order.status != 'cancelled':
                    matching_orders.append((order, customer))
        
        if not matching_orders:
            self._send_message(chat_id, self._t('no_orders_found_partial', chat_id, partial_id=partial_order_id))
            return {'status': 'order_not_found'}
        
        if len(matching_orders) > 1:
            # Multiple matches - show enhanced disambiguation with full details
            message = self._t('multiple_orders_found_partial', chat_id, partial_id=partial_order_id) + "\n\n"
            keyboard_buttons = []
            
            for order, customer in matching_orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t('unknown', user_id=None)
                customer_name = f"{customer.first_name} {customer.last_name}" if customer else self._t('unknown', user_id=None)
                
                from utils.timezone import to_cet_string
                order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                
                # Enhanced button text with order ID prefix
                button_text = f"{order.order_id[:8]}: {customer_name} - {order.quantity}x {offer_name} €{order.total_price:.2f}"
                keyboard_buttons.append([{
                    "text": button_text,
                    "callback_data": f"cancel_order_confirm_{order.order_id}"
                }])
            
            keyboard_buttons.append([{"text": self._t('cancel', user_id=None), "callback_data": "cancel_action"}])
            keyboard = {"inline_keyboard": keyboard_buttons}
            
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'disambiguation_shown'}
        
        # Single match - show enhanced confirmation with full details
        order, customer = matching_orders[0]
        return self._show_enhanced_cancel_confirmation(chat_id, order, customer, f"partial ID '{partial_order_id}'")
    
    def handle_cancel_order_by_id(self, chat_id: int, order_id: str) -> Dict[str, Any]:
        """Handle cancel order by direct order ID with enhanced confirmation"""
        order = self.db.get_order(order_id)
        
        if not order:
            self._send_message(chat_id, self._t('order_not_found_full_id', chat_id, order_id=order_id))
            return {'status': 'order_not_found'}
        
        if order.status == 'cancelled':
            self._send_message(chat_id, self._t('order_already_cancelled_full_id', chat_id, order_id=order_id))
            return {'status': 'already_cancelled'}

        # Get customer info
        customer = self.db.get_customer(order.customer_id)
        if not customer:
            self._send_message(chat_id, self._t('customer_not_found_for_order', chat_id, order_id=order_id))
            return {'status': 'customer_not_found'}
        
        return self._show_enhanced_cancel_confirmation(chat_id, order, customer, f"full ID '{order_id}'")
    
    def _show_enhanced_cancel_confirmation(self, chat_id: int, order, customer, detection_method: str) -> Dict[str, Any]:
        """Show enhanced confirmation dialog with full order details"""
        # Get box and offer info
        box = self.db.get_box(order.box_id)
        offer = self.db.get_offer(order.offer_id)
        
        if not box:
            self._send_message(chat_id, self._t('box_not_found_for_order', chat_id, order_id=order.order_id))
            return {'status': 'box_not_found'}
        
        customer_name = f"{customer.first_name} {customer.last_name}" if customer else self._t('unknown', user_id=None)
        offer_name = offer.name if offer else self._t('unknown', user_id=None)
        
        from utils.timezone import to_cet_string
        order_date = to_cet_string(order.created_at, '%Y-%m-%d %H:%M')
        
        # Enhanced confirmation message with all details
        message = f"⚠️ {self._t('cancel_order_confirmation_title', chat_id)}\n\n"
        message += f"🔍 {self._t('cancel_detection_method', chat_id, method=detection_method)}\n"
        message += f"📋 {self._t('cancel_order_id_label', chat_id, order_id=order.order_id)}\n"
        message += f"👤 {self._t('cancel_customer_label', chat_id, customer_name=customer_name)}\n"
        message += f"🍺 {self._t('cancel_product_label', chat_id, offer_name=offer_name)}\n"
        message += f"📦 {self._t('cancel_quantity_label', chat_id, quantity=order.quantity)}\n"
        message += f"💰 {self._t('cancel_total_label', chat_id, total=order.total_price)}\n"
        message += f"📅 {self._t('cancel_order_date_label', chat_id, order_date=order_date)}\n"
        message += f"📊 {self._t('cancel_status_label', chat_id, status=order.status)}\n"
        message += f"📦 {self._t('cancel_box_label', chat_id, box_id=order.box_id, current_quantity=box.current_quantity, max_capacity=box.max_capacity)}\n\n"
        
        if box.status == BoxStatus.FULL.value:
            message += f"⚠️ {self._t('cancel_full_box_warning_enhanced', chat_id)}\n\n"
        
        message += f"❓ {self._t('cancel_confirmation_question', chat_id)}"
        
        # Add inline keyboard for confirmation
        keyboard = {
            "inline_keyboard": [[
                {"text": self._t('confirm_cancel_enhanced', chat_id), "callback_data": f"request_cancel_reason_{order.order_id}"},
                {"text": self._t('keep_order_enhanced', chat_id), "callback_data": "cancel_action"}
            ]]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard, parse_mode='HTML')
        return {'status': 'confirmation_required'}
    
    def _show_user_orders_for_cancel(self, chat_id: int, customer, page: int = 1) -> Dict[str, Any]:
        """Show user's active orders with cancel buttons"""
        orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) 
                 if o.status in ['pending', 'ordered']]
        
        if not orders:
            display_name = f"{customer.first_name} {customer.last_name}" or self._t('unknown', user_id=None)
            self._send_message(chat_id, self._t('no_active_orders_for_user', chat_id, name=display_name))
            return {'status': 'no_orders'}

        # Paginate orders
        page_orders, total_pages = self._paginate_list(orders, page, 10)
        
        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or self._t('unknown', user_id=None))
        message = f"❌ Cancel Order for {display_name} (Page {page}/{total_pages}):\n\n"
        
        keyboard_buttons = []
        for order in page_orders:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else self._t('unknown', user_id=None)
            from utils.timezone import to_cet_string
            order_date = to_cet_string(order.created_at, '%Y-%m-%d')
            
            button_text = f"❌ [{order_date}] {order.quantity}x {offer_name} - €{order.total_price:.2f}"
            keyboard_buttons.append([{
                "text": button_text,
                "callback_data": f"cancel_order_confirm_{order.order_id}"
            }])
        
        # Add pagination if needed
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": "◀️ Previous", "callback_data": f"cancel_orders_page_{customer.customer_id}_{page - 1}"})
            nav_buttons.append({"text": f"Page {page}/{total_pages}", "callback_data": "page_info"})
            if page < total_pages:
                nav_buttons.append({"text": "Next ▶️", "callback_data": f"cancel_orders_page_{customer.customer_id}_{page + 1}"})
            keyboard_buttons.append(nav_buttons)
        
        # Add cancel option at the bottom
        keyboard_buttons.append([{"text": self._t('cancel', user_id=None), "callback_data": "cancel_action"}])
        
        keyboard = {"inline_keyboard": keyboard_buttons}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}

    def handle_confirm_cancel(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_cancel command - now called from button callback"""
        error = self._validate_args(args, 1, 'usage_confirm_cancel', chat_id)
        if error:
            return error

        order_id = args[0]
        order = self.db.get_order(order_id)
        
        if not order:
            self._send_message(chat_id, self._t('order_not_found'))
            return {'status': 'order_not_found'}

        box = self.db.get_box(order.box_id)
        if not box:
            self._send_message(chat_id, self._t('box_not_found'))
            return {'status': 'box_not_found'}

    def handle_confirm_cancel_with_reason(self, chat_id: int, order_id: str, reason: str) -> Dict[str, Any]:
        """Handle order cancellation with reason"""
        order = self.db.get_order(order_id)
        
        if not order:
            self._send_message(chat_id, self._t('order_not_found'))
            return {'status': 'order_not_found'}

        box = self.db.get_box(order.box_id)
        if not box:
            self._send_message(chat_id, self._t('box_not_found'))
            return {'status': 'box_not_found'}

        return self._execute_cancel(order, box, chat_id, reason)

    def _execute_cancel(self, order, box, chat_id: int, reason: str = "Manual cancellation") -> Dict[str, Any]:
        """Execute order cancellation"""
        # Update order status and set cancellation date
        if not self.db.update_order(order.order_id, {
            'status': 'cancelled',
            'update_date': datetime.now(UTC).isoformat()
        }):
            self._send_message(chat_id, self._t('failed_cancel_order'))
            return {'status': 'error'}

        # Update box quantity and status
        if not self.box_status_manager.update_box_after_order_cancellation(box.box_id, order.quantity):
            logger.error(f"Failed to update box {box.box_id} after cancellation")

        # Check if offer status should change after cancellation
        self.box_status_manager.update_offer_status_after_change(order.offer_id)

        # Get customer and offer info for notifications
        customer = self.db.get_customer(order.customer_id)
        offer = self.db.get_offer(order.offer_id)
        
        # Notify customer with reason
        if customer:
            customer_message = self._t('order_cancelled_by_admin', customer.telegram_user_id,
                                     name=offer.name if offer else self._t('unknown', user_id=None),
                                     quantity=order.quantity,
                                     total=float(order.total_price),
                                     reason=reason)
            self._send_message(customer.telegram_user_id, customer_message)

        # Confirm to admin
        box = self.db.get_box(order.box_id)  # Refresh box data
        admin_message = self._t('order_cancelled_success', user_id=None,
                              order_id=order.order_id,
                              new_quantity=box.current_quantity if box else 0,
                              max_capacity=box.max_capacity if box else 0)
        self._send_message(chat_id, admin_message)
        
        return {'status': 'success'}

    def handle_cancel_order_user_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user selection from disambiguation for cancel order"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}
        
        return self._show_user_orders_for_cancel(chat_id, customer)
    
    def handle_cancel_orders_page(self, chat_id: int, customer_id: str, page: int) -> Dict[str, Any]:
        """Handle pagination for cancel orders list"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}
        
        return self._show_user_orders_for_cancel(chat_id, customer, page)