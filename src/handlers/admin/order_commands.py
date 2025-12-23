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

            # Check 5-unit limit for target customer
            existing_orders = [o for o in self.db.get_orders_by_customer(target_customer.customer_id) 
                             if o.offer_id == offer_id and o.status != 'cancelled']
            total_existing = sum(order.quantity for order in existing_orders)
            
            if total_existing + quantity > 5:
                message = f"❌ Order exceeds 5-unit limit for {target_customer.first_name or username}\n\n"
                message += f"Their existing orders ({total_existing} units):\n"
                for order in existing_orders:
                    if isinstance(order.created_at, str):
                        from datetime import datetime
                        order_date = datetime.fromisoformat(order.created_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    else:
                        order_date = order.created_at.strftime('%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                remaining_allowed = 5 - total_existing
                if remaining_allowed > 0:
                    message += f"\nMaximum you can order for them: {remaining_allowed} units"
                else:
                    message += f"\nThey have reached the 5-unit limit for this offer"
                
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
            customer_message += f"Refund: €{order.total_price:.2f}"
            self._send_message(customer.telegram_user_id, customer_message)

        # Confirm to admin
        self._send_message(chat_id, 
            f"✅ Order cancelled\n"
            f"Order ID: {order.order_id}\n"
            f"Customer notified\n"
            f"Box quantity updated: {new_quantity}/{box.max_capacity}")
        
        return {'status': 'success'}

    def _find_customer_by_identifier(self, identifier: str):
        """Find customer by username or display name"""
        from models.entities import AuthorizationStatus
        
        # Try by username first (remove @ if present)
        username = identifier.lstrip('@').lower()
        customer = self.db.get_customer_by_username(username)
        if customer:
            return customer
        
        # Try by first name
        customers = self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value)
        for customer in customers:
            if customer.first_name and customer.first_name.lower() == identifier.lower():
                return customer
            # Try first + last name combination
            full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            if full_name.lower() == identifier.lower():
                return customer
        
        return None