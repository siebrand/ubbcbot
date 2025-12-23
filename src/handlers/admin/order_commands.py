from typing import Dict, Any, Optional
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Order, Box, BoxStatus, OfferStatus

class AdminOrderCommands(BaseHandler):
    def handle_cancel_order(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /cancel_order command"""
        if not args:
            self._send_message(chat_id, "Usage: /cancel_order <order_id>")
            return {'status': 'invalid_args'}

        order_id = args[0]
        order = self.db.get_order(order_id)
        
        if not order:
            self._send_message(chat_id, "❌ Order not found")
            return {'status': 'order_not_found'}
        
        if order.status == 'cancelled':
            self._send_message(chat_id, "❌ Order already cancelled")
            return {'status': 'already_cancelled'}

        # Get box info
        box = self.db.get_box(order.box_id)
        if not box:
            self._send_message(chat_id, "❌ Box not found")
            return {'status': 'box_not_found'}

        # Check if box is full - require confirmation
        if box.status == BoxStatus.FULL.value:
            self._send_message(chat_id, 
                f"⚠️ WARNING: This order is from a FULL box!\n"
                f"Order: {order_id}\n"
                f"Quantity: {order.quantity}\n"
                f"Cancelling will affect box status.\n\n"
                f"Confirm with: /confirm_cancel {order_id}")
            return {'status': 'confirmation_required'}

        # Cancel directly for non-full boxes
        return self._execute_cancel(order, box, chat_id)

    def handle_confirm_cancel(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_cancel command"""
        if not args:
            self._send_message(chat_id, "Usage: /confirm_cancel <order_id>")
            return {'status': 'invalid_args'}

        order_id = args[0]
        order = self.db.get_order(order_id)
        
        if not order:
            self._send_message(chat_id, "❌ Order not found")
            return {'status': 'order_not_found'}

        box = self.db.get_box(order.box_id)
        if not box:
            self._send_message(chat_id, "❌ Box not found")
            return {'status': 'box_not_found'}

        return self._execute_cancel(order, box, chat_id)

    def handle_order_for(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /order_for command - admin places order for another user"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /order_for <username> <offer_id> [quantity]")
            return {'status': 'invalid_args'}

        try:
            username = args[0]
            offer_id = int(args[1])
            quantity = int(args[2]) if len(args) > 2 else 1

            if quantity <= 0:
                self._send_message(chat_id, "❌ Quantity must be positive")
                return {'status': 'invalid_quantity'}

            # Find target customer
            target_customer = self._find_customer_by_identifier(username)
            if not target_customer:
                self._send_message(chat_id, f"❌ User '{username}' not found")
                return {'status': 'user_not_found'}

            # Get offer
            offer = self.db.get_offer(offer_id)
            if not offer or offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, "❌ Offer not found or inactive")
                return {'status': 'offer_not_found'}

            # Check 10-unit admin limit for target customer
            existing_orders = [o for o in self.db.get_orders_by_customer(target_customer.customer_id) 
                             if o.offer_id == offer_id and o.status != 'cancelled']
            total_existing = sum(order.quantity for order in existing_orders)
            
            if total_existing + quantity > 10:
                message = f"❌ Order exceeds 10-unit admin limit for {target_customer.first_name or username}\n\n"
                message += f"Their existing orders ({total_existing} units):\n"
                for order in existing_orders:
                    from utils.timezone import to_cet_string
                    order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                remaining_allowed = 10 - total_existing
                if remaining_allowed > 0:
                    message += f"\nMaximum you can order for them: {remaining_allowed} units"
                else:
                    message += f"\nThey have reached the 10-unit admin limit for this offer"
                
                self._send_message(chat_id, message)
                return {'status': 'limit_exceeded'}

            # Execute the order for the target customer
            from handlers.customer.order_commands import CustomerOrderCommands
            order_handler = CustomerOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
            result = order_handler.execute_order(chat_id, user_id, offer_id, quantity, offer, target_customer, placed_by_admin=True)
            
            if result['status'] == 'success':
                # Notify target customer
                customer_message = f"🍺 An order has been placed for you by admin\n\n"
                customer_message += f"Product: {offer.name}\n"
                customer_message += f"Quantity: {quantity}\n"
                customer_message += f"Total: €{offer.price_per_unit * quantity:.2f}\n"
                customer_message += f"Status: pending"
                self._send_message(target_customer.telegram_user_id, customer_message)
                
                # Confirm to admin
                display_name = target_customer.first_name or username
                self._send_message(chat_id, f"✅ Order placed for {display_name}")
            
            return result

        except ValueError:
            self._send_message(chat_id, "❌ Invalid format")
            return {'status': 'invalid_format'}

    def _execute_cancel(self, order, box, chat_id: int) -> Dict[str, Any]:
        """Execute order cancellation"""
        # Update order status
        if not self.db.update_order(order.order_id, {'status': 'cancelled'}):
            self._send_message(chat_id, "❌ Failed to cancel order")
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
            customer_message = f"❌ Your order has been cancelled by admin\n"
            customer_message += f"Product: {offer.name if offer else 'Unknown'}\n"
            customer_message += f"Quantity: {order.quantity}\n"
            self._send_message(customer.telegram_user_id, customer_message)

        # Confirm to admin
        self._send_message(chat_id, 
            f"✅ Order cancelled\n"
            f"Order ID: {order.order_id}\n"
            f"Customer notified\n"
            f"Box quantity updated: {new_quantity}/{box.max_capacity}")
        
        return {'status': 'success'}

    def handle_user_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /user_orders command"""
        if not args:
            self._send_message(chat_id, "Usage: /user_orders <username>")
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer = self._find_customer_by_identifier(identifier)
        
        if not customer:
            self._send_message(chat_id, f"❌ User '{identifier}' not found")
            return {'status': 'user_not_found'}

        orders = self.db.get_orders_by_customer(customer.customer_id)
        
        if not orders:
            display_name = customer.first_name or identifier
            self._send_message(chat_id, f"📋 No orders found for {display_name}")
            return {'status': 'no_orders'}

        # Group orders by status
        active_orders = [o for o in orders if o.status != 'cancelled']
        cancelled_orders = [o for o in orders if o.status == 'cancelled']
        
        display_name = self._escape_html(customer.first_name or identifier)
        message = f"📋 Orders for {display_name}:\n\n"
        
        if active_orders:
            message += "🟢 Active Orders:\n"
            for order in active_orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else "Unknown"
                from utils.timezone import to_cet_string
                order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                message += f"• [{order_date}] {order.quantity}x {offer_name} - €{order.total_price:.2f} ({order.status})\n"
                message += f"  ID: {order.order_id}\n"
        
        if cancelled_orders:
            message += "\n❌ Cancelled Orders:\n"
            for order in cancelled_orders[-3:]:  # Show last 3 cancelled
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else "Unknown"
                from utils.timezone import to_cet_string
                order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                message += f"• [{order_date}] {order.quantity}x {offer_name} - €{order.total_price:.2f}\n"
        
        self._send_message(chat_id, message)
        return {'status': 'success'}

    def handle_all_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /all_orders command"""
        # Get filter from args (active, cancelled, ordered, or all)
        status_filter = args[0].lower() if args else 'active'
        
        if status_filter not in ['active', 'cancelled', 'ordered', 'all']:
            self._send_message(chat_id, "Usage: /all_orders [active|cancelled|ordered|all]")
            return {'status': 'invalid_args'}

        # Get all customers and their orders
        from models.entities import AuthorizationStatus
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        
        all_orders = []
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            for order in orders:
                if status_filter == 'active' and order.status == 'cancelled':
                    continue
                elif status_filter == 'cancelled' and order.status != 'cancelled':
                    continue
                elif status_filter == 'ordered' and order.status != 'ordered':
                    continue
                all_orders.append((customer, order))
        
        if not all_orders:
            self._send_message(chat_id, f"📋 No {status_filter} orders found")
            return {'status': 'no_orders'}
        
        # Sort by date (newest first)
        all_orders.sort(key=lambda x: x[1].created_at, reverse=True)
        
        # Generate CSV and upload
        csv_content = self._generate_orders_csv(all_orders)
        csv_filename = f"orders_{status_filter}_{self.environment}.csv"
        
        # Send CSV file
        self._send_document(chat_id, csv_content, csv_filename, f"📊 {status_filter.title()} Orders CSV ({len(all_orders)} orders)")
        
        return {'status': 'success'}
    
    def _generate_orders_csv(self, orders_data: list) -> str:
        """Generate CSV content from orders data"""
        import csv
        from io import StringIO
        from datetime import datetime
        
        output = StringIO()
        writer = csv.writer(output)
        
        # CSV headers
        writer.writerow([
            'Order ID', 'Date', 'Customer Name', 'Username', 'Product', 
            'Quantity', 'Unit Price', 'Total Price', 'Status', 'Box ID'
        ])
        
        # CSV data
        for customer, order in orders_data:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else "Unknown"
            unit_price = offer.price_per_unit if offer else 0
            
            from utils.timezone import to_cet_string
            order_date = to_cet_string(order.created_at, '%Y-%m-%d %H:%M')
            
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown"
            username = customer.username or ""
            
            writer.writerow([
                order.order_id,
                order_date,
                customer_name,
                username,
                offer_name,
                order.quantity,
                f"{unit_price:.2f}",
                f"{order.total_price:.2f}",
                order.status,
                order.box_id
            ])
        
        return output.getvalue()

    def _find_customer_by_identifier(self, identifier: str):
        """Find customer by username or display name"""
        from models.entities import AuthorizationStatus
        
        # Try by username first (remove @ if present)
        username = identifier.lstrip('@').lower()
        customer = self.db.get_customer_by_username(username)
        if customer:
            return customer
        
        # Try by first name across all customers (not just unauthorized)
        all_customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        for customer in all_customers:
            if customer.first_name and customer.first_name.lower() == identifier.lower():
                return customer
            # Try first + last name combination
            full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            if full_name.lower() == identifier.lower():
                return customer
        
        return None