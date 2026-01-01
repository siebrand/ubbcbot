from typing import Dict, Any, Optional
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Order, Box, BoxStatus, OfferStatus

class AdminOrderCommands(BaseHandler):
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
                return self._handle_cancel_order_by_id(chat_id, arg)
        
        # Username provided - show orders for cancellation
        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "cancel_order_user_select")
        
        if error:
            return error
        
        return self._show_user_orders_for_cancel(chat_id, customer)
    
    def _handle_cancel_order_by_partial_id(self, chat_id: int, partial_order_id: str) -> Dict[str, Any]:
        """Handle cancel order by partial order ID (first 8 characters) with enhanced confirmation"""
        from models.entities import AuthorizationStatus
        
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
                customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Unknown"
                
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
    
    def _handle_cancel_order_by_id(self, chat_id: int, order_id: str) -> Dict[str, Any]:
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
        
        customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Unknown"
        offer_name = offer.name if offer else "Unknown"
        
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
            display_name = f"{customer.first_name} {customer.last_name}" or "Unknown"
            self._send_message(chat_id, self._t('no_active_orders_for_user', chat_id, name=display_name))
            return {'status': 'no_orders'}

        # Paginate orders
        page_orders, total_pages = self._paginate_list(orders, page, 10)
        
        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or "Unknown")
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

    def handle_order_for(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /order_for command - admin places order for another user"""
        if not args:
            # Show button-based UI to ask for username
            message = self._t('enter_username_for_order_for', chat_id)
            keyboard = {
                "inline_keyboard": [[
                    {"text": "📝 Enter Username", "callback_data": "enter_username_order_for"}
                ]]
            }
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'awaiting_input'}

        # Legacy behavior for direct command usage
        if len(args) >= 2:
            return self._execute_order_for_legacy(chat_id, user_id, args)
        
        # Username provided - find customer and show offers
        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "order_for_user_select")
        
        if error:
            return error
        
        return self._show_offers_for_order_for(chat_id, customer)

    def _execute_cancel(self, order, box, chat_id: int, reason: str = "Manual cancellation") -> Dict[str, Any]:
        """Execute order cancellation"""
        from datetime import datetime, UTC
        
        # Update order status and set cancellation date
        if not self.db.update_order(order.order_id, {
            'status': 'cancelled',
            'update_date': datetime.now(UTC).isoformat()
        }):
            self._send_message(chat_id, self._t('failed_cancel_order'))
            return {'status': 'error'}

        # Update box quantity and status
        new_quantity = box.current_quantity - order.quantity
        updates = {'current_quantity': new_quantity}
        
        # Recalculate box status
        if new_quantity == 0:
            updates['status'] = BoxStatus.OPEN.value
        elif new_quantity < box.min_breakeven:
            updates['status'] = BoxStatus.OPEN.value
        elif new_quantity < box.max_capacity:
            updates['status'] = BoxStatus.MINIMUM_REACHED.value
        
        self.db.update_box(box.box_id, updates)

        # Get customer and offer info for notifications
        customer = self.db.get_customer(order.customer_id)
        offer = self.db.get_offer(order.offer_id)
        
        # Notify customer with reason
        if customer:
            customer_message = self._t('order_cancelled_by_admin', customer.telegram_user_id,
                                     product=offer.name if offer else 'Unknown',
                                     quantity=order.quantity,
                                     reason=reason)
            self._send_message(customer.telegram_user_id, customer_message)

        # Confirm to admin
        admin_message = self._t('order_cancelled_success', user_id=None,
                              order_id=order.order_id,
                              new_quantity=new_quantity,
                              max_capacity=box.max_capacity)
        self._send_message(chat_id, admin_message)
        
        return {'status': 'success'}

    def handle_user_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /user_orders command"""
        if not args:
            # Show button-based UI to ask for username
            message = self._t('enter_username_for_orders', chat_id)
            keyboard = {
                "inline_keyboard": [[
                    {"text": "📝 Enter Username", "callback_data": "enter_username_orders"}
                ]]
            }
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'awaiting_input'}

        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "user_orders_select")
        
        if error:
            return error
        
        return self._show_user_orders(chat_id, customer)
    
    def _show_user_orders(self, chat_id: int, customer) -> Dict[str, Any]:
        """Show orders for a specific customer"""
        orders = self.db.get_orders_by_customer(customer.customer_id)
        
        if not orders:
            display_name = f"{customer.first_name} {customer.last_name}" or "Unknown"
            self._send_message(chat_id, self._t('no_orders_for_user', name=display_name))
            return {'status': 'no_orders'}

        # Sort orders by offer_id ascending
        orders.sort(key=lambda x: x.offer_id)
        
        # Aggregate orders by offer, price and status
        aggregated = {}
        for order in orders:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else self._t('unknown', user_id=None)
            
            key = (order.offer_id, order.unit_price, order.status)
            if key not in aggregated:
                aggregated[key] = {
                    'offer_name': offer_name,
                    'unit_price': order.unit_price,
                    'status': order.status,
                    'quantity': 0,
                    'total_price': Decimal('0.0'),
                    'dates': set(),
                    'order_ids': []
                }
            
            aggregated[key]['quantity'] += order.quantity
            aggregated[key]['total_price'] += order.total_price
            aggregated[key]['order_ids'].append(order.order_id)
            
            # Add date
            from utils.timezone import to_cet_string
            aggregated[key]['dates'].add(to_cet_string(order.created_at, '%Y-%m-%d'))

        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or "Unknown")
        message = self._t('user_orders_title', user_id=None, name=display_name)
        message += "\n\n"
        
        # Group by status for totals
        status_groups = {}
        for (offer_id, unit_price, status), data in aggregated.items():
            if status not in status_groups:
                status_groups[status] = {'total_price': Decimal('0.0'), 'items': []}
            status_groups[status]['total_price'] += data['total_price']
            status_groups[status]['items'].append(((offer_id, unit_price, status), data))
        
        # Display orders grouped by status
        open_statuses = ['pending', 'ordered', 'confirmed']
        open_total = Decimal('0.0')
        
        # First show open orders
        for status in ['pending', 'ordered', 'confirmed', 'delivered']:
            if status not in status_groups:
                continue
                
            status_emoji = {
                'pending': '⏳',
                'ordered': '📦',
                'confirmed': '✅',
                'cancelled': '❌',
                'delivered': '🚚'
            }.get(status, '❓')
            
            # Add status header if multiple statuses present
            if len(status_groups) > 1:
                message += f"{status_emoji} {status.upper()}:\n"
            
            line_count = 0
            for (offer_id, unit_price, order_status), data in status_groups[status]['items']:
                # Determine date display
                if len(data['dates']) == 1:
                    date_display = f"[{list(data['dates'])[0]}]"
                else:
                    date_display = f"[{self._t('multiple_days_label')}]"
                
                # Alternate diamond icons for better readability
                line_icon = "🔸" if line_count % 2 == 0 else "🔹"
                
                # Get first 8 characters of first order ID
                short_order_id = data['order_ids'][0][:8] if data['order_ids'] else "unknown"
                
                order_line = f"{line_icon} {date_display} [{offer_id}] {data['offer_name']} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f} - {short_order_id}"
                
                message += order_line + "\n"
                line_count += 1
            
            # Add status total if multiple statuses present
            if len(status_groups) > 1:
                message += "\n" + self._t('subtotal_label', user_id=None, total=status_groups[status]['total_price']) + "\n\n"
            
            # Add to open total if applicable
            if status in open_statuses:
                open_total += status_groups[status]['total_price']
        
        # Add open orders total before cancelled orders
        if open_total > 0 and 'cancelled' in status_groups:
            message += "\n" + self._t('open_orders_total_label', user_id=None, total=open_total) + "\n\n"
        
        # Show cancelled orders last (no total needed)
        if 'cancelled' in status_groups:
            status_emoji = '❌'
            if len(status_groups) > 1:
                message += f"{status_emoji} CANCELLED:\n"
            
            line_count = 0
            for (offer_id, unit_price, order_status), data in status_groups['cancelled']['items']:
                # Determine date display
                if len(data['dates']) == 1:
                    date_display = f"[{list(data['dates'])[0]}]"
                else:
                    date_display = f"[{self._t('multiple_days_label')}]"
                
                # Alternate diamond icons for better readability
                line_icon = "🔸" if line_count % 2 == 0 else "🔹"
                
                # Get first 8 characters of first order ID
                short_order_id = data['order_ids'][0][:8] if data['order_ids'] else "unknown"
                
                order_line = f"{line_icon} {date_display} [{offer_id}] {data['offer_name']} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f} - {short_order_id}"
                
                message += order_line + "\n"
                line_count += 1
        
        # Add open orders total if no cancelled orders
        elif open_total > 0:
            message += "\n" + self._t('open_orders_total_label', user_id=None, total=open_total)
        
        self._send_message(chat_id, message)
        return {'status': 'success'}

    def handle_all_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /all_orders command"""
        if not args:
            # Show status selection buttons
            keyboard = {
                "inline_keyboard": [
                    [{"text": "Ready for Labeling", "callback_data": "export_orders_ready_for_labeling"}],
                    [{"text": "Labeling Completed", "callback_data": "export_orders_labeling_completed"}],
                    [{"text": "Awaiting Payment", "callback_data": "export_orders_awaiting_payment"}],
                    [{"text": "Completed", "callback_data": "export_orders_completed"}],
                    [{"text": "Active", "callback_data": "export_orders_active"}],
                    [{"text": "Cancelled", "callback_data": "export_orders_cancelled"}],
                    [{"text": "All", "callback_data": "export_orders_all"}]
                ]
            }
            self._send_message(chat_id, "📊 Select order status to export:", reply_markup=keyboard)
            return {'status': 'selection_shown'}
        
        # Get filter from args
        status_filter = args[0].lower()
        return self._export_orders_by_status(chat_id, status_filter)
    
    def _export_orders_by_status(self, chat_id: int, status_filter: str) -> Dict[str, Any]:
        """Export orders by status filter"""
        # Get all customers and their orders
        from models.entities import AuthorizationStatus, OrderStatus
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        
        all_orders = []
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            for order in orders:
                if status_filter == 'active' and order.status not in ['pending', 'ordered']:
                    continue
                elif status_filter == 'cancelled' and order.status != 'cancelled':
                    continue
                elif status_filter == 'ordered' and order.status != 'ordered':
                    continue
                elif status_filter == 'ready_for_labeling' and order.status != OrderStatus.READY_FOR_LABELING.value:
                    continue
                elif status_filter == 'labeling_completed' and order.status != OrderStatus.LABELING_COMPLETED.value:
                    continue
                elif status_filter == 'awaiting_payment' and order.status != OrderStatus.AWAITING_PAYMENT.value:
                    continue
                elif status_filter == 'completed' and order.status != OrderStatus.COMPLETED.value:
                    continue
                elif status_filter != 'all' and status_filter not in ['active', 'cancelled', 'ordered', 'ready_for_labeling', 'labeling_completed', 'awaiting_payment', 'completed']:
                    continue
                all_orders.append((customer, order))
        
        if not all_orders:
            self._send_message(chat_id, self._t('no_orders_status', status=status_filter))
            return {'status': 'no_orders'}
        
        # Sort by customer name for grouping
        all_orders.sort(key=lambda x: (x[0].first_name or '', x[0].last_name or ''))
        
        # Generate CSV and upload
        csv_content = self._generate_pick_list_csv(all_orders)
        csv_filename = f"pick_list_{status_filter}_{self.environment}.csv"
        
        # Send CSV file
        caption = self._t('pick_list_csv_caption', user_id=None, 
                         status=status_filter.replace('_', ' ').title(), 
                         count=len(all_orders))
        self._send_document(chat_id, csv_content, csv_filename, caption)
        
        return {'status': 'success'}
    
    def _generate_pick_list_csv(self, orders_data: list) -> str:
        """Generate pick list CSV content grouped by customer"""
        # CSV headers
        headers = [
            'Customer_Name', 'Telegram_Username', 'Offer_Name', 
            'Box_ID', 'Unit_Count', 'Unit_Price', 'Total_Price_to_Charge'
        ]
        
        csv_content = ','.join(headers) + '\n'
        
        # Group by customer and sort
        customer_orders = {}
        for customer, order in orders_data:
            customer_key = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown"
            if customer_key not in customer_orders:
                customer_orders[customer_key] = []
            customer_orders[customer_key].append((customer, order))
        
        # Generate CSV data grouped by customer
        for customer_name in sorted(customer_orders.keys()):
            for customer, order in customer_orders[customer_name]:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else "Unknown"
                username = customer.username or ""
                
                csv_content += f'"{customer_name}","{username}","{offer_name}","{order.box_id}",{order.quantity},{order.unit_price:.2f},{order.total_price:.2f}\n'
        
        return csv_content

    def handle_user_orders_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user selection from disambiguation buttons for user_orders"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}
        
        return self._show_user_orders(chat_id, customer)
    
    def handle_send_overviews(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /send_overviews command"""
        from models.entities import AuthorizationStatus, OrderStatus
        
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
    
    def handle_mark_paid(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /mark_paid command"""
        from models.entities import AuthorizationStatus, OrderStatus
        
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
        
        # Show customers with payment buttons
        message = "💳 Customers Awaiting Payment:\n\n"
        keyboard_rows = []
        
        for customer, orders in customers_awaiting_payment[:10]:  # Show first 10
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown"
            total_amount = sum(order.total_price for order in orders)
            message += f"👤 {customer_name}: €{total_amount:.2f} ({len(orders)} orders)\n"
            keyboard_rows.append([{"text": self._t('mark_customer_paid', user_id=None, customer_name=customer_name), "callback_data": f"mark_paid_{customer.customer_id}"}])
        
        if len(customers_awaiting_payment) > 10:
            message += f"\n... and {len(customers_awaiting_payment) - 10} more customers"
        
        keyboard = {"inline_keyboard": keyboard_rows}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'customers_shown'}
    
    def handle_offer_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /offer_orders command"""
        if not args:
            # Show button-based UI to select offer
            return self._show_offer_selection_for_orders(chat_id)
        
        try:
            offer_id = int(args[0])
            return self._show_orders_for_offer(chat_id, offer_id)
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id', chat_id))
            return {'status': 'invalid_format'}
    
    def _show_offer_selection_for_orders(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Show paginated list of offers for order viewing"""
        from models.entities import OfferStatus
        offers = [o for o in self.db.list_offers() if o.status in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value, OfferStatus.INACTIVE.value]]
        
        if not offers:
            self._send_message(chat_id, self._t('no_offers_available', chat_id))
            return {'status': 'no_offers'}
        
        # Sort by offer_id descending (newest first)
        offers.sort(key=lambda x: x.offer_id, reverse=True)
        
        # Paginate results
        page_offers, total_pages = self._paginate_list(offers, page, 10)
        
        message = self._t('select_offer_for_orders', chat_id, page=page, total_pages=total_pages) + "\n\n"
        keyboard_buttons = []
        
        for offer in page_offers:
            supplier = self.db.get_supplier_by_name(offer.supplier_name)
            supplier_name = supplier.name if supplier else "Unknown"
            
            # Get order count for this offer
            orders = self.db.get_orders_by_offer(offer.offer_id)
            order_count = len(orders)
            
            button_text = f"🍺 {offer.name} - €{offer.price_per_unit:.2f} ({supplier_name}) [{order_count} orders]"
            keyboard_buttons.append([{"text": button_text, "callback_data": f"offer_orders_{offer.offer_id}"}])
        
        # Add pagination if needed
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": self._t('previous', chat_id), "callback_data": f"offer_orders_page_{page - 1}"})
            nav_buttons.append({"text": self._t('page_indicator', chat_id, page=page, total_pages=total_pages), "callback_data": "page_info"})
            if page < total_pages:
                nav_buttons.append({"text": self._t('next', chat_id), "callback_data": f"offer_orders_page_{page + 1}"})
            keyboard_buttons.append(nav_buttons)
        
        # Add cancel button
        keyboard_buttons.append([{"text": self._t('cancel', chat_id), "callback_data": "cancel_action"}])
        
        keyboard = {"inline_keyboard": keyboard_buttons}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def _show_orders_for_offer(self, chat_id: int, offer_id: int, page: int = 1) -> Dict[str, Any]:
        """Show paginated orders for a specific offer"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t('offer_not_found', chat_id))
            return {'status': 'offer_not_found'}
        
        orders = self.db.get_orders_by_offer(offer_id)
        if not orders:
            self._send_message(chat_id, self._t('no_orders_for_offer', chat_id, offer_name=offer.name))
            return {'status': 'no_orders'}
        
        # Sort by creation date (newest first)
        orders.sort(key=lambda x: x.created_at, reverse=True)
        
        # Paginate results
        page_orders, total_pages = self._paginate_list(orders, page, 10)
        
        # Calculate totals
        active_orders = [o for o in orders if o.status in ['pending', 'ordered']]
        total_quantity = sum(o.quantity for o in orders)
        active_quantity = sum(o.quantity for o in active_orders)
        total_value = sum(o.total_price for o in orders)
        active_value = sum(o.total_price for o in active_orders)
        
        message = self._t('offer_orders_header', chat_id,
            offer_name=offer.name,
            offer_id=offer_id,
            page=page,
            total_pages=total_pages,
            total_orders=len(orders),
            active_orders=len(active_orders),
            total_quantity=total_quantity,
            active_quantity=active_quantity,
            total_value=total_value,
            active_value=active_value
        ) + "\n\n"
        
        for i, order in enumerate(page_orders):
            customer = self.db.get_customer(order.customer_id)
            customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Unknown"
            
            from utils.timezone import to_cet_string
            order_date = to_cet_string(order.created_at, '%Y-%m-%d')
            
            status_emoji = {
                'pending': '⏳',
                'ordered': '📦',
                'cancelled': '❌',
                'ready_for_labeling': '🏷️',
                'labeling_completed': '✅',
                'awaiting_payment': '💳',
                'completed': '✅'
            }.get(order.status, '❓')
            
            # Alternate diamond icons for better readability
            line_icon = "🔸" if i % 2 == 0 else "🔹"
            
            message += f"{line_icon} [{order_date}] {customer_name} {order.quantity}x €{order.total_price:.2f} - {order.order_id[:8]}\n"
        
        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": self._t('previous', chat_id), "callback_data": f"offer_orders_detail_{offer_id}_{page - 1}"})
            nav_buttons.append({"text": self._t('page_indicator', chat_id, page=page, total_pages=total_pages), "callback_data": "page_info"})
            if page < total_pages:
                nav_buttons.append({"text": self._t('next', chat_id), "callback_data": f"offer_orders_detail_{offer_id}_{page + 1}"})
            keyboard = {"inline_keyboard": [nav_buttons]}
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_failed_notifications(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /failed_notifications command - show orders that couldn't be notified"""
        from models.entities import AuthorizationStatus, OrderStatus
        
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
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown"
            total_amount = sum(order.total_price for order in orders)
            message += f"👤 {customer_name} (@{customer.username or 'no_username'}):\n"
            message += f"   💰 €{total_amount:.2f} ({len(orders)} orders)\n"
            for order in orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else "Unknown"
                message += f"   • {order.quantity}x {offer_name} - €{order.total_price:.2f}\n"
            message += "\n"
        
        message += "\n💡 These customers need to be contacted manually or retry delivery overview sending."
        
        self._send_message(chat_id, message)
        return {'status': 'failed_shown'}
    
    def handle_offer_orders_page(self, chat_id: int, page: int) -> Dict[str, Any]:
        """Handle pagination for offer selection"""
        return self._show_offer_selection_for_orders(chat_id, page)
    
    def handle_offer_orders_detail_page(self, chat_id: int, offer_id: str, page: int) -> Dict[str, Any]:
        """Handle pagination for offer orders detail"""
        try:
            return self._show_orders_for_offer(chat_id, int(offer_id), page)
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id', chat_id))
            return {'status': 'invalid_format'}
    
    def handle_export_orders_callback(self, chat_id: int, status_filter: str) -> Dict[str, Any]:
        """Handle export orders callback"""
        return self._export_orders_by_status(chat_id, status_filter)
    

    
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
    
    def _execute_order_for_legacy(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Legacy order_for execution for direct command usage"""
        try:
            username = args[0]
            offer_id = int(args[1])
            quantity = int(args[2]) if len(args) > 2 else 1

            if quantity <= 0:
                self._send_message(chat_id, self._t('quantity_must_positive'))
                return {'status': 'invalid_quantity'}

            # Find target customer
            customer, error = self._find_customer_with_disambiguation(username, chat_id, "order_for_user_select")
            if error:
                return error

            return self._execute_order_for_customer(chat_id, customer, offer_id, quantity)

        except ValueError:
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'invalid_format'}
    
    def _show_offers_for_order_for(self, chat_id: int, customer) -> Dict[str, Any]:
        """Show active offers for order_for workflow"""
        from models.entities import OfferStatus
        offers = [o for o in self.db.list_offers() if o.status == OfferStatus.ACTIVE.value]
        
        if not offers:
            self._send_message(chat_id, self._t('no_offers_available'))
            return {'status': 'no_offers'}
        
        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or "Unknown")
        message = f"🍺 Select offer for {display_name}:\n\n"
        
        keyboard_buttons = []
        for offer in offers[:10]:  # Limit to 10 offers
            supplier = self.db.get_supplier_by_name(offer.supplier_name)
            supplier_name = supplier.name if supplier else "Unknown"
            
            button_text = f"🍺 {offer.name} - €{offer.price_per_unit:.2f} ({supplier_name})"
            keyboard_buttons.append([{
                "text": button_text,
                "callback_data": f"order_for_offer_{customer.customer_id}_{offer.offer_id}"
            }])
        
        keyboard_buttons.append([{"text": self._t('cancel', user_id=None), "callback_data": "cancel_action"}])
        keyboard = {"inline_keyboard": keyboard_buttons}
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def _show_quantity_selection_for_order_for(self, chat_id: int, customer, offer) -> Dict[str, Any]:
        """Show quantity selection for order_for workflow"""
        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or "Unknown")
        message = f"📦 Select quantity for {display_name}:\n\n🍺 {offer.name} - €{offer.price_per_unit:.2f}"
        
        keyboard_buttons = [
            [{"text": self._t('order_1', user_id=None), "callback_data": f"order_for_quantity_{customer.customer_id}_{offer.offer_id}_1"}],
            [{"text": self._t('order_2', user_id=None), "callback_data": f"order_for_quantity_{customer.customer_id}_{offer.offer_id}_2"}],
            [{"text": self._t('other_quantity', user_id=None), "callback_data": f"order_for_other_{customer.customer_id}_{offer.offer_id}"}],
            [{"text": self._t('cancel', user_id=None), "callback_data": "cancel_action"}]
        ]
        
        keyboard = {"inline_keyboard": keyboard_buttons}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def _execute_order_for_customer(self, chat_id: int, customer, offer_id: int, quantity: int) -> Dict[str, Any]:
        """Execute order for customer with validation"""
        # Get offer
        offer = self.db.get_offer(offer_id)
        if not offer or offer.status != OfferStatus.ACTIVE.value:
            self._send_message(chat_id, self._t('offer_not_found_inactive'))
            return {'status': 'offer_not_found'}

        # Check 10-unit admin limit for target customer
        valid, limit_message = self.validator.validate_order_limit(customer.customer_id, offer_id, quantity, 10)
        if not valid:
            # Extract existing orders info for admin message
            existing_orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) 
                             if o.offer_id == offer_id and o.status in ['pending', 'ordered']]
            total_existing = sum(order.quantity for order in existing_orders)
            
            display_name = customer.first_name or "Unknown"
            admin_message = self._t('admin_order_limit_exceeded', user_id=None, 
                                  customer_name=display_name, 
                                  total_existing=total_existing)
            
            # Add order details
            admin_message += "\n\n"
            for order in existing_orders:
                from utils.timezone import to_cet_string
                order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                admin_message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
            
            remaining_allowed = 10 - total_existing
            if remaining_allowed > 0:
                admin_message += self._t('admin_remaining_units_allowed', user_id=None, remaining=remaining_allowed)
            else:
                admin_message += self._t('admin_limit_reached', user_id=None, customer_name=display_name)
            
            self._send_message(chat_id, admin_message)
            return {'status': 'limit_exceeded'}

        # Execute the order for the target customer
        from handlers.customer.order_commands import CustomerOrderCommands
        order_handler = CustomerOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        result = order_handler.execute_order(chat_id, customer.telegram_user_id, offer_id, quantity, offer, customer, placed_by_admin=True)
        
        if result['status'] == 'success':
            # Get the actual order to show correct status
            orders = self.db.get_orders_by_customer(customer.customer_id)
            latest_order = max(orders, key=lambda o: o.created_at) if orders else None
            order_status = latest_order.status if latest_order else 'pending'
            
            # Try to notify target customer
            customer_message = self._t('admin_order_placed', customer.telegram_user_id,
                                     product=offer.name,
                                     quantity=quantity,
                                     total=offer.price_per_unit * quantity,
                                     status=order_status)
            pm_result = self._send_message(customer.telegram_user_id, customer_message)
            
            # Send notification to default group (admin orders don't trigger this automatically)
            order_handler._notify_channel_order(customer, offer, quantity)
            
            # Confirm to admin with PM status
            display_name = customer.first_name or "Unknown"
            admin_message = self._t('order_placed_for_user', name=display_name)
            if not pm_result.get('success'):
                admin_message += "\n" + self._t('pm_notification_failed', user_id=None, name=display_name)
            self._send_message(chat_id, admin_message)
        
        return result
    
    def handle_order_for_user_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user selection from disambiguation for order_for"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}
        
        return self._show_offers_for_order_for(chat_id, customer)
    
    def handle_order_for_offer_select(self, chat_id: int, customer_id: str, offer_id: str) -> Dict[str, Any]:
        """Handle offer selection for order_for"""
        import logging
        logger = logging.getLogger()
        logger.info(f"handle_order_for_offer_select called with customer_id: {customer_id}, offer_id: {offer_id}")
        
        customer = self.db.get_customer(customer_id)
        logger.info(f"Customer found: {customer is not None}")
        
        try:
            offer_id_int = int(offer_id)
            logger.info(f"Converted offer_id to int: {offer_id_int}")
            offer = self.db.get_offer(offer_id_int)
            logger.info(f"Offer found: {offer is not None}")
        except ValueError as e:
            logger.error(f"ValueError converting offer_id '{offer_id}' to int: {e}")
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'invalid_format'}
        
        if not customer:
            logger.error(f"Customer not found for ID: {customer_id}")
            self._send_message(chat_id, self._t('invalid_selection'))
            return {'status': 'invalid_selection'}
        
        if not offer:
            logger.error(f"Offer not found for ID: {offer_id_int}")
            self._send_message(chat_id, self._t('invalid_selection'))
            return {'status': 'invalid_selection'}
        
        logger.info(f"Proceeding to quantity selection")
        return self._show_quantity_selection_for_order_for(chat_id, customer, offer)
    
    def handle_order_for_quantity_select(self, chat_id: int, customer_id: str, offer_id: str, quantity: str) -> Dict[str, Any]:
        """Handle quantity selection for order_for"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}
        
        return self._execute_order_for_customer(chat_id, customer, int(offer_id), int(quantity))
    
    def handle_order_for_other_quantity(self, chat_id: int, customer_id: str, offer_id: str) -> Dict[str, Any]:
        """Handle 'Other' quantity selection for order_for"""
        # Store context for text input
        from models.entities import EditContext
        context_data = f"{customer_id}_{offer_id}"
        
        # Store edit context
        context = EditContext(
            chat_id=chat_id,
            edit_type='order_for_quantity_input',
            entity_id=context_data
        )
        self.db.create_edit_context(context)
        
        self._send_message(chat_id, self._t('enter_quantity_1_to_10', chat_id), 
                          reply_markup={"force_reply": True, "input_field_placeholder": "Enter quantity"})
        return {'status': 'awaiting_quantity_input'}
    
    def handle_delete_cancelled(self, chat_id: int) -> Dict[str, Any]:
        """Handle admin /delete_cancelled command - delete cancelled orders older than 7 days"""
        try:
            from datetime import datetime, UTC, timedelta
            
            # Calculate cutoff date (7 days ago)
            cutoff_date = datetime.now(UTC) - timedelta(days=7)
            
            # Get all cancelled orders
            from models.entities import AuthorizationStatus
            customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
            
            old_cancelled_orders = []
            for customer in customers:
                cancelled_orders = self.db.get_orders_by_customer_and_status(customer.customer_id, 'cancelled')
                for order in cancelled_orders:
                    if order.update_date:
                        try:
                            update_date = datetime.fromisoformat(order.update_date.replace('Z', '+00:00'))
                            if update_date <= cutoff_date:
                                old_cancelled_orders.append(order)
                        except (ValueError, AttributeError):
                            # Skip orders with invalid cancellation dates
                            continue
            
            if not old_cancelled_orders:
                self._send_message(chat_id, self._t('no_old_cancelled_orders', chat_id))
                return {'status': 'no_old_cancelled_orders'}
            
            # Delete old cancelled orders
            deleted_count = 0
            for order in old_cancelled_orders:
                if self.db.delete_order(order.order_id):
                    deleted_count += 1
            
            if deleted_count > 0:
                self._send_message(chat_id, self._t('old_cancelled_orders_deleted', chat_id, count=deleted_count))
                return {'status': 'success', 'deleted_count': deleted_count}
            else:
                self._send_message(chat_id, self._t('failed_delete_old_cancelled_orders', chat_id))
                return {'status': 'error'}
                
        except Exception as e:
            import logging
            logger = logging.getLogger()
            logger.error(f"Error in admin handle_delete_cancelled: {e}")
            self._send_message(chat_id, self._t('failed_delete_old_cancelled_orders', chat_id))
            return {'status': 'error'}
    
    def handle_audit_orders(self, chat_id: int) -> Dict[str, Any]:
        """Handle /audit_orders command - add update_date to orders without it"""
        try:
            from datetime import datetime, UTC
            from models.entities import AuthorizationStatus
            
            # Get all customers
            customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
            
            orders_without_update_date = []
            for customer in customers:
                orders = self.db.get_orders_by_customer(customer.customer_id)
                for order in orders:
                    if not order.update_date:
                        orders_without_update_date.append(order)
            
            if not orders_without_update_date:
                self._send_message(chat_id, self._t('no_orders_missing_update_date', chat_id))
                return {'status': 'no_orders_to_audit'}
            
            # Update orders - update_date will be set automatically by update_order
            updated_count = 0
            
            for order in orders_without_update_date:
                if self.db.update_order(order.order_id, {}):
                    updated_count += 1
            
            if updated_count > 0:
                self._send_message(chat_id, self._t('orders_audit_completed', chat_id, count=updated_count))
                return {'status': 'success', 'updated_count': updated_count}
            else:
                self._send_message(chat_id, self._t('failed_audit_orders', chat_id))
                return {'status': 'error'}
                
        except Exception as e:
            import logging
            logger = logging.getLogger()
            logger.error(f"Error in handle_audit_orders: {e}")
            self._send_message(chat_id, self._t('failed_audit_orders', chat_id))
            return {'status': 'error'}