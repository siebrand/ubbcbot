import os
from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Offer, Box, Order, BoxStatus, OfferStatus

class OfferCommands(BaseHandler):
    def handle_create_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /create_offer command"""
        if len(args) < 4:
            self._send_message(chat_id, "Usage: /create_offer <supplier_name> <name> <price> <box_size>")
            return {'status': 'invalid_args'}

        try:
            supplier_name = args[0]
            price = float(args[-2])
            box_size = int(args[-1])
            
            # Validate and sanitize name
            name = ' '.join(args[1:-2]).strip()
            if len(name) > 100:
                self._send_message(chat_id, "❌ Product name too long (max 100 characters)")
                return {'status': 'invalid_name'}
            
            if '<' in name or '>' in name:
                self._send_message(chat_id, "❌ Product name cannot contain < or > characters")
                return {'status': 'invalid_name'}

            # Validate box size
            valid_sizes = [1, 2, 6, 8, 10, 12, 15, 16, 18, 20, 24]
            if box_size not in valid_sizes:
                self._send_message(chat_id, f"❌ Invalid box size. Valid sizes: {valid_sizes}")
                return {'status': 'invalid_box_size'}

            # Check supplier exists
            supplier = self.db.get_supplier_by_name(supplier_name)
            if not supplier:
                self._send_message(chat_id, "❌ Supplier not found")
                return {'status': 'supplier_not_found'}

            # Create offer
            offer = Offer(
                supplier_name=supplier_name,
                name=name,
                price_per_unit=Decimal(str(price)),
                wholesale_box_size=box_size,
                min_quantity_breakeven=max(1, int(box_size * 0.8))
            )

            if self.db.create_offer(offer):
                # Create initial box
                box = Box(
                    offer_id=offer.offer_id,
                    max_capacity=box_size,
                    min_breakeven=offer.min_quantity_breakeven
                )
                self.db.create_box(box)

                # Auto-order 1 unit for admin
                admin_customer = self.db.get_customer_by_telegram_id(self.admin_user_id)
                if admin_customer:
                    admin_order = Order(
                        customer_id=admin_customer.customer_id,
                        box_id=box.box_id,
                        offer_id=offer.offer_id,
                        quantity=1,
                        unit_price=Decimal(str(price)),
                        total_price=Decimal(str(price))
                    )
                    self.db.create_order(admin_order)
                    
                    # Update box quantity
                    updates = {'current_quantity': 1}
                    if 1 >= box.max_capacity:
                        updates['status'] = BoxStatus.FULL.value
                    elif 1 >= box.min_breakeven:
                        updates['status'] = BoxStatus.MINIMUM_REACHED.value
                    
                    if not self.db.update_box(box.box_id, updates):
                        self._send_message(chat_id, "⚠️ Auto-order placed but box update failed")
                    else:
                        self._send_message(chat_id, f"✅ Auto-ordered 1 unit for you. Order ID: {admin_order.order_id}")

                # Announce new offer to default group
                self._announce_offer(offer)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to create offer")
                return {'status': 'error'}

        except (ValueError, IndexError) as e:
            self._send_message(chat_id, f"❌ Invalid format. Error: {str(e)}")
            return {'status': 'invalid_format'}

    def handle_fulfill_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /fulfill_offer command"""
        if not args:
            self._send_message(chat_id, "Usage: /fulfill_offer <offer_id>")
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            if offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, "❌ Offer is not active")
                return {'status': 'offer_not_active'}
            
            # Get all pending orders for this offer, sorted by date ascending
            all_orders = self.db.get_orders_by_offer(offer_id)
            pending_orders = [o for o in all_orders if o.status == 'pending']
            pending_orders.sort(key=lambda x: x.created_at)
            
            if not pending_orders:
                self._send_message(chat_id, "❌ No pending orders for this offer")
                return {'status': 'no_pending_orders'}
            
            # Calculate boxes needed
            total_units = sum(order.quantity for order in pending_orders)
            boxes_needed = (total_units + offer.wholesale_box_size - 1) // offer.wholesale_box_size  # Ceiling division
            
            # Show order summary
            message = f"📋 Fulfillment Summary for Offer {offer_id}:\n"
            message += f"🍺 {offer.name} - €{offer.price_per_unit:.2f}\n"
            message += f"📦 Box size: {offer.wholesale_box_size} units\n\n"
            message += f"📈 Total pending units: {total_units}\n"
            message += f"📦 Boxes needed: {boxes_needed}\n\n"
            message += f"📋 Pending Orders ({len(pending_orders)}):"\n"
            
            for i, order in enumerate(pending_orders[:10], 1):  # Show first 10
                customer = self.db.get_customer(order.customer_id)
                customer_name = customer.first_name if customer else "Unknown"
                if isinstance(order.created_at, str):
                    from datetime import datetime
                    order_date = datetime.fromisoformat(order.created_at.replace('Z', '+00:00')).strftime('%m-%d %H:%M')
                else:
                    order_date = order.created_at.strftime('%m-%d %H:%M')
                message += f"{i}. {customer_name}: {order.quantity}x [{order_date}]\n"
            
            if len(pending_orders) > 10:
                message += f"... and {len(pending_orders) - 10} more orders\n"
            
            message += f"\nReply with: /confirm_fulfill {offer_id} <boxes_ordered>\n"
            message += f"Suggested: /confirm_fulfill {offer_id} {boxes_needed}"
            
            self._send_message(chat_id, message)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}
    
    def handle_confirm_fulfill(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_fulfill command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /confirm_fulfill <offer_id> <boxes_ordered>")
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            boxes_ordered = int(args[1])
            
            if boxes_ordered <= 0:
                self._send_message(chat_id, "❌ Boxes ordered must be positive")
                return {'status': 'invalid_quantity'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            # Get pending orders sorted by date ascending (oldest first)
            all_orders = self.db.get_orders_by_offer(offer_id)
            pending_orders = [o for o in all_orders if o.status == 'pending']
            pending_orders.sort(key=lambda x: x.created_at)
            
            units_available = boxes_ordered * offer.wholesale_box_size
            units_allocated = 0
            fulfilled_orders = []
            cancelled_orders = []
            updated_orders = []
            
            # Process orders from oldest to newest
            for order in pending_orders:
                remaining_capacity = units_available - units_allocated
                
                if remaining_capacity <= 0:
                    # No more capacity - cancel this order
                    cancelled_orders.append(order)
                elif order.quantity <= remaining_capacity:
                    # Order fits completely
                    fulfilled_orders.append(order)
                    units_allocated += order.quantity
                else:
                    # Partial fulfillment - reduce order size
                    old_quantity = order.quantity
                    new_quantity = remaining_capacity
                    updated_orders.append((order, old_quantity, new_quantity))
                    units_allocated += new_quantity
            
            # Execute the fulfillment
            # Update fulfilled orders to 'ordered'
            for order in fulfilled_orders:
                self.db.update_order(order.order_id, {'status': 'ordered'})
            
            # Update partially fulfilled orders
            for order, old_qty, new_qty in updated_orders:
                new_total_price = new_qty * order.unit_price
                self.db.update_order(order.order_id, {
                    'quantity': new_qty,
                    'total_price': new_total_price,
                    'status': 'ordered'
                })
                
                # Notify customer of quantity reduction
                customer = self.db.get_customer(order.customer_id)
                if customer:
                    msg = f"⚠️ Your order has been updated due to limited availability:\n\n"
                    msg += f"🍺 {offer.name}\n"
                    msg += f"Original: {old_qty} units\n"
                    msg += f"Updated: {new_qty} units\n"
                    msg += f"New total: €{new_total_price:.2f}\n\n"
                    msg += f"Your order is confirmed and will be delivered."
                    self._send_message(customer.telegram_user_id, msg)
            
            # Cancel remaining orders
            for order in cancelled_orders:
                self.db.update_order(order.order_id, {'status': 'cancelled'})
                
                # Notify customer of cancellation
                customer = self.db.get_customer(order.customer_id)
                if customer:
                    msg = f"❌ Your order has been cancelled due to insufficient availability:\n\n"
                    msg += f"🍺 {offer.name}\n"
                    msg += f"Quantity: {order.quantity} units\n"
                    msg += f"Amount: €{order.total_price:.2f}\n\n"
                    msg += f"We apologize for the inconvenience."
                    self._send_message(customer.telegram_user_id, msg)
            
            # Update offer status to ordered
            self.db.update_offer(offer_id, {'status': 'ordered'})
            
            # Send summary to admin
            summary = f"✅ Offer {offer_id} fulfilled with {boxes_ordered} boxes:\n\n"
            summary += f"✅ Fulfilled: {len(fulfilled_orders)} orders\n"
            if updated_orders:
                summary += f"⚠️ Updated: {len(updated_orders)} orders (quantity reduced)\n"
            if cancelled_orders:
                summary += f"❌ Cancelled: {len(cancelled_orders)} orders\n"
            summary += f"\n📦 Total units allocated: {units_allocated}/{units_available}"
            
            self._send_message(chat_id, summary)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid format")
            return {'status': 'invalid_format'}
        """Handle /box_status command"""
        offers = self.db.list_offers()
        
        message = "📦 Box Status:\n\n"
        for offer in offers:
            if offer.status == OfferStatus.ACTIVE.value:
                boxes = self.db.get_boxes_by_offer(offer.offer_id)
                boxes.sort(key=lambda x: x.box_id)
                
                for box in boxes:
                    status_emoji = {
                        BoxStatus.OPEN.value: "🟢",
                        BoxStatus.MINIMUM_REACHED.value: "🟡",
                        BoxStatus.FULL.value: "🔴",
                        BoxStatus.ORDERED.value: "📦",
                        BoxStatus.DELIVERED.value: "✅"
                    }.get(box.status, "❓")
                    
                    message += f"🍺 {offer.name} €{offer.price_per_unit:.2f}\n   {status_emoji} Box {box.box_id[:8]}: {box.current_quantity}/{box.max_capacity} ({box.status})\n\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}

    def _announce_offer(self, offer):
        """Announce new offer to default group and subscribers"""
        default_group_id = os.environ.get('DEFAULT_GROUP_ID')
        
        announcement = f"🍺 New offer available!\n\n"
        announcement += f"[{offer.offer_id}] {offer.name}\n"
        announcement += f"Price: €{offer.price_per_unit:.2f} per unit\n"
        announcement += f"Box size: {offer.wholesale_box_size} units\n\n"
        announcement += f"Order with: /order {offer.offer_id} [quantity]"
        
        # Create inline keyboard with order buttons
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🍺 Order 1", "callback_data": f"order_{offer.offer_id}_1"},
                    {"text": "🍺🍺 Order 2", "callback_data": f"order_{offer.offer_id}_2"}
                ]
            ]
        }
        
        # Send to default group
        if default_group_id:
            self._send_message(int(default_group_id), announcement, reply_markup=reply_markup, force_group=True)
        
        # Send to subscribers in batches
        self._notify_subscribers(announcement, reply_markup)
    
    def _notify_subscribers(self, message: str, reply_markup: dict):
        """Send offer notification to all subscribers in batches"""
        import time
        from models.entities import AuthorizationStatus
        
        # Get all approved customers
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        subscribers = [c for c in customers if getattr(c, 'subscribed_to_offers', False)]
        
        # Send in batches to avoid rate limits (30 messages per second max)
        batch_size = 25
        for i in range(0, len(subscribers), batch_size):
            batch = subscribers[i:i + batch_size]
            
            for customer in batch:
                try:
                    self._send_message(customer.telegram_user_id, message, reply_markup=reply_markup)
                except Exception as e:
                    # Log error but continue with other subscribers
                    import logging
                    logging.error(f"Failed to notify subscriber {customer.customer_id}: {e}")
            
            # Rate limiting: wait 1 second between batches
            if i + batch_size < len(subscribers):
                time.sleep(1)