from typing import Dict, Any, Optional
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Order, Box, BoxStatus, OfferStatus

class AdminOrderCommands(BaseHandler):
    def handle_cancel_order(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /cancel_order command"""
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

        # Check if it's an order ID (numeric) or username
        if len(args) == 1 and args[0].isdigit():
            # Legacy behavior - direct order ID
            return self._handle_cancel_order_by_id(chat_id, args[0])
        
        # Username provided - show orders for cancellation
        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "cancel_order_user_select")
        
        if error:
            return error
        
        return self._show_user_orders_for_cancel(chat_id, customer)
    
    def _handle_cancel_order_by_id(self, chat_id: int, order_id: str) -> Dict[str, Any]:
        """Handle cancel order by direct order ID (legacy behavior)"""
        order = self.db.get_order(order_id)
        
        if not order:
            self._send_message(chat_id, self._t('order_not_found'))
            return {'status': 'order_not_found'}
        
        if order.status == 'cancelled':
            self._send_message(chat_id, self._t('order_already_cancelled'))
            return {'status': 'already_cancelled'}

        # Get box info
        box = self.db.get_box(order.box_id)
        if not box:
            self._send_message(chat_id, self._t('box_not_found'))
            return {'status': 'box_not_found'}

        # Get customer and offer info
        customer = self.db.get_customer(order.customer_id)
        offer = self.db.get_offer(order.offer_id)
        customer_name = customer.first_name if customer else self._t('unknown', user_id=None)
        offer_name = offer.name if offer else self._t('unknown', user_id=None)

        # Show confirmation details
        message = self._t('cancel_order_confirmation', user_id=None,
                         order_id=order_id,
                         customer_name=customer_name,
                         offer_name=offer_name,
                         quantity=order.quantity,
                         total=order.total_price)
        
        if box.status == BoxStatus.FULL.value:
            message += "\n" + self._t('cancel_full_box_warning', user_id=None)
        
        # Add inline keyboard for confirmation
        keyboard = {
            "inline_keyboard": [[
                {"text": self._t('confirm_cancel', user_id=None), "callback_data": f"confirm_cancel_order_{order_id}"},
                {"text": self._t('keep_order', user_id=None), "callback_data": "cancel_action"}
            ]]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
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

        return self._execute_cancel(order, box, chat_id)

    def handle_order_for(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /order_for command - admin places order for another user"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_order_for'))
            return {'status': 'invalid_args'}

        try:
            username = args[0]
            offer_id = int(args[1])
            quantity = int(args[2]) if len(args) > 2 else 1

            if quantity <= 0:
                self._send_message(chat_id, self._t('quantity_must_positive'))
                return {'status': 'invalid_quantity'}

            # Find target customer
            target_customer, _ = self._find_customer_with_disambiguation(username, 0, "")
            if not target_customer:
                self._send_message(chat_id, self._t('user_not_found_username', username=username))
                return {'status': 'user_not_found'}

            # Get offer
            offer = self.db.get_offer(offer_id)
            if not offer or offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, self._t('offer_not_found_inactive'))
                return {'status': 'offer_not_found'}

            # Check 10-unit admin limit for target customer
            existing_orders = [o for o in self.db.get_orders_by_customer(target_customer.customer_id) 
                             if o.offer_id == offer_id and o.status in ['pending', 'ordered']]
            total_existing = sum(order.quantity for order in existing_orders)
            
            if total_existing + quantity > 10:
                message = self._t('admin_order_limit_exceeded', user_id=None,
                                customer_name=target_customer.first_name or username,
                                total_existing=total_existing)
                message += "\n\n"
                for order in existing_orders:
                    from utils.timezone import to_cet_string
                    order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                remaining_allowed = 10 - total_existing
                if remaining_allowed > 0:
                    message += self._t('admin_remaining_units_allowed', user_id=None, remaining=remaining_allowed)
                else:
                    message += self._t('admin_limit_reached', user_id=None)
                
                self._send_message(chat_id, message)
                return {'status': 'limit_exceeded'}

            # Execute the order for the target customer
            from handlers.customer.order_commands import CustomerOrderCommands
            order_handler = CustomerOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
            result = order_handler.execute_order(chat_id, target_customer.telegram_user_id, offer_id, quantity, offer, target_customer, placed_by_admin=True)
            
            if result['status'] == 'success':
                # Get the actual order to show correct status
                orders = self.db.get_orders_by_customer(target_customer.customer_id)
                latest_order = max(orders, key=lambda o: o.created_at) if orders else None
                order_status = latest_order.status if latest_order else 'pending'
                
                # Try to notify target customer
                customer_message = self._t('admin_order_placed', target_customer.telegram_user_id,
                                         product=offer.name,
                                         quantity=quantity,
                                         total=offer.price_per_unit * quantity,
                                         status=order_status)
                pm_result = self._send_message(target_customer.telegram_user_id, customer_message)
                
                # Send notification to default group (admin orders don't trigger this automatically)
                order_handler._notify_channel_order(target_customer, offer, quantity)
                
                # Confirm to admin with PM status
                display_name = target_customer.first_name or username
                admin_message = self._t('order_placed_for_user', name=display_name)
                if not pm_result.get('success'):
                    admin_message += "\n" + self._t('pm_notification_failed', user_id=None, name=display_name)
                self._send_message(chat_id, admin_message)
            
            return result

        except ValueError:
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'invalid_format'}

    def _execute_cancel(self, order, box, chat_id: int) -> Dict[str, Any]:
        """Execute order cancellation"""
        # Update order status
        if not self.db.update_order(order.order_id, {'status': 'cancelled'}):
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
        
        # Notify customer
        if customer:
            customer_message = self._t('order_cancelled_by_admin', customer.telegram_user_id,
                                     product=offer.name if offer else 'Unknown',
                                     quantity=order.quantity)
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

        # Group orders by status
        active_orders = [o for o in orders if o.status in ['pending', 'ordered']]
        cancelled_orders = [o for o in orders if o.status == 'cancelled']

        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or "Unknown")
        message = self._t('user_orders_title', user_id=None, name=display_name)
        message += "\n\n"

        if active_orders:
            message += self._t('active_orders_label', user_id=None) + "\n"
            for order in active_orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t('unknown', user_id=None)
                from utils.timezone import to_cet_string
                order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                message += f"• [{order_date}] {order.quantity}x {offer_name} - €{order.total_price:.2f} ({order.status})\n"
                message += f"  ID: {order.order_id}\n"
        
        if cancelled_orders:
            message += "\n" + self._t('cancelled_orders_label', user_id=None) + "\n"
            for order in cancelled_orders[-3:]:  # Show last 3 cancelled
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t('unknown', user_id=None)
                from utils.timezone import to_cet_string
                order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                message += f"• [{order_date}] {order.quantity}x {offer_name} - €{order.total_price:.2f}\n"
        
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
            self._send_message(chat_id, "❌ No customers with orders ready for delivery overview")
            return {'status': 'no_customers'}
        
        total_customers = len(customers_with_ready_orders)
        batches_needed = (total_customers + 49) // 50  # Round up
        
        message = f"📊 Delivery Overview Summary:\n\n👥 Customers to notify: {total_customers}\n📦 Payment link batches needed: {batches_needed}\n\nThis will send delivery overviews and move orders to AWAITING_PAYMENT status."
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Start Sending Overviews", "callback_data": "start_send_overviews"},
                {"text": "❌ Cancel", "callback_data": "cancel_action"}
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
            self._send_message(chat_id, "❌ No customers with orders awaiting payment")
            return {'status': 'no_customers'}
        
        # Show customers with payment buttons
        message = "💳 Customers Awaiting Payment:\n\n"
        keyboard_rows = []
        
        for customer, orders in customers_awaiting_payment[:10]:  # Show first 10
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown"
            total_amount = sum(order.total_price for order in orders)
            message += f"👤 {customer_name}: €{total_amount:.2f} ({len(orders)} orders)\n"
            keyboard_rows.append([{"text": f"✅ Mark {customer_name} Paid", "callback_data": f"mark_paid_{customer.customer_id}"}])
        
        if len(customers_awaiting_payment) > 10:
            message += f"\n... and {len(customers_awaiting_payment) - 10} more customers"
        
        keyboard = {"inline_keyboard": keyboard_rows}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'customers_shown'}
    
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
            self._send_message(chat_id, "✅ No failed notifications - all labeling completed orders have been processed")
            return {'status': 'no_failed'}
        
        # Show failed notifications
        message = "⚠️ Orders with Failed Delivery Notifications:\n\n"
        
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