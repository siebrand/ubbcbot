import logging
from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Order, Box, BoxStatus, OfferStatus

logger = logging.getLogger()

class CustomerOrderCommands(BaseHandler):
    def handle_order(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /order command"""
        if len(args) < 1:
            self._send_message(chat_id, "Usage: /order <offer_id> [quantity]")
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            quantity = int(args[1]) if len(args) > 1 else 1

            if quantity <= 0:
                self._send_message(chat_id, "❌ Quantity must be positive")
                return {'status': 'invalid_quantity'}

            # Get offer
            offer = self.db.get_offer(offer_id)
            if not offer or offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, "❌ Offer not found or inactive")
                return {'status': 'offer_not_found'}

            # Get customer
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, "❌ Customer not found")
                return {'status': 'customer_not_found'}

            # Check for existing orders and enforce 5-unit limit
            existing_orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) 
                             if o.offer_id == offer_id and o.status != 'cancelled']
            total_existing = sum(order.quantity for order in existing_orders)
            
            if total_existing + quantity > 5:
                message = f"❌ Order exceeds 5-unit limit for {offer.name}\n\n"
                message += f"Your existing orders ({total_existing} units):\n"
                for order in existing_orders:
                    if isinstance(order.created_at, str):
                        from datetime import datetime
                        order_date = datetime.fromisoformat(order.created_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    else:
                        order_date = order.created_at.strftime('%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                remaining_allowed = 5 - total_existing
                if remaining_allowed > 0:
                    message += f"\nMaximum you can still order: {remaining_allowed} units"
                else:
                    message += f"\nYou have reached the 5-unit limit for this offer"
                
                self._send_message(chat_id, message)
                return {'status': 'limit_exceeded'}
            
            # Check for existing orders for duplicate confirmation
            if existing_orders:
                message = f"⚠️ You already have orders for {offer.name}:\n\n"
                for order in existing_orders:
                    if isinstance(order.created_at, str):
                        from datetime import datetime
                        order_date = datetime.fromisoformat(order.created_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    else:
                        order_date = order.created_at.strftime('%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                message += f"\nAre you sure you want to order {quantity}x more?\n"
                message += f"[Confirm order](https://t.me/{self._get_bot_username()}?start=confirm_{offer_id}_{quantity})"
                
                self._send_message(chat_id, message, 'Markdown')
                return {'status': 'confirmation_required'}

            # Execute the order
            return self.execute_order(chat_id, user_id, offer_id, quantity, offer, customer)

        except ValueError:
            self._send_message(chat_id, "❌ Invalid quantity format")
            return {'status': 'invalid_format'}

    def handle_confirm_order(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_order command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /confirm_order <offer_id> <quantity>")
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            quantity = int(args[1])
            
            if quantity <= 0:
                self._send_message(chat_id, "❌ Quantity must be positive")
                return {'status': 'invalid_quantity'}

            # Get offer and customer
            offer = self.db.get_offer(offer_id)
            if not offer or offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, "❌ Offer not found or inactive")
                return {'status': 'offer_not_found'}

            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, "❌ Customer not found")
                return {'status': 'customer_not_found'}
            
            # Check 5-unit limit for confirmed orders
            existing_orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) 
                             if o.offer_id == offer_id and o.status != 'cancelled']
            total_existing = sum(order.quantity for order in existing_orders)
            
            if total_existing + quantity > 5:
                message = f"❌ Order exceeds 5-unit limit for {offer.name}\n\n"
                message += f"Your existing orders ({total_existing} units):\n"
                for order in existing_orders:
                    if isinstance(order.created_at, str):
                        from datetime import datetime
                        order_date = datetime.fromisoformat(order.created_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    else:
                        order_date = order.created_at.strftime('%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                remaining_allowed = 5 - total_existing
                if remaining_allowed > 0:
                    message += f"\nMaximum you can still order: {remaining_allowed} units"
                else:
                    message += f"\nYou have reached the 5-unit limit for this offer"
                
                self._send_message(chat_id, message)
                return {'status': 'limit_exceeded'}
            
            # Execute the order without duplicate check
            return self.execute_order(chat_id, user_id, offer_id, quantity, offer, customer)
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid format")
            return {'status': 'invalid_format'}

    def execute_order(self, chat_id: int, user_id: int, offer_id: int, quantity: int, offer, customer, placed_by_admin: bool = False) -> Dict[str, Any]:
        """Execute order placement"""
        try:
            # Create single order
            order = Order(
                customer_id=customer.customer_id,
                box_id="",  # Will be set when assigning to boxes
                offer_id=offer_id,
                quantity=quantity,
                unit_price=Decimal(str(offer.price_per_unit)),
                total_price=Decimal(str(offer.price_per_unit)) * quantity,
                placed_by_admin=placed_by_admin
            )

            if not self.db.create_order(order):
                self._send_message(chat_id, "❌ Failed to place order")
                return {'status': 'error'}

            # Now assign order to boxes and update quantities
            remaining_quantity = quantity
            boxes_used = []
            
            while remaining_quantity > 0:
                # Find available box
                boxes = self.db.get_boxes_by_offer(offer_id)
                available_box = None
                
                for box in boxes:
                    if box.status in [BoxStatus.OPEN.value, BoxStatus.MINIMUM_REACHED.value]:
                        available_space = box.max_capacity - box.current_quantity
                        if available_space > 0:
                            available_box = box
                            break

                # Create new box if needed
                if not available_box:
                    available_box = Box(
                        offer_id=offer_id,
                        max_capacity=offer.wholesale_box_size,
                        min_breakeven=offer.min_quantity_breakeven
                    )
                    self.db.create_box(available_box)

                # Calculate how much can fit in this box
                available_space = available_box.max_capacity - available_box.current_quantity
                box_quantity = min(remaining_quantity, available_space)
                
                # Update box quantity and status
                new_quantity = available_box.current_quantity + box_quantity
                updates = {'current_quantity': new_quantity}
                
                if new_quantity >= available_box.max_capacity:
                    updates['status'] = BoxStatus.FULL.value
                elif new_quantity >= available_box.min_breakeven:
                    updates['status'] = BoxStatus.MINIMUM_REACHED.value

                if not self.db.update_box(available_box.box_id, updates):
                    logger.error(f"Failed to update box {available_box.box_id}")
                    self._send_message(chat_id, "❌ Failed to update box")
                    return {'status': 'error'}
                
                boxes_used.append(available_box.box_id)
                remaining_quantity -= box_quantity
                logger.info(f"Assigned {box_quantity} units to box, remaining: {remaining_quantity}")

            # Update order with first box_id (for reference)
            if boxes_used:
                self.db.update_order(order.order_id, {'box_id': boxes_used[0]})

            # Send confirmation message
            if len(boxes_used) == 1:
                self._send_message(chat_id, 
                    f"✅ Order placed!\n"
                    f"Order ID : {order.order_id}\n"
                    f"Product  : {offer.name}\n"
                    f"Quantity : {quantity}\n"
                    f"Total    : €{order.total_price:.2f}\n"
                    f"Status   : {order.status}")
            else:
                self._send_message(chat_id, 
                    f"✅ Order placed across {len(boxes_used)} boxes!\n"
                    f"Product  : {offer.name}\n"
                    f"Quantity : {quantity}\n"
                    f"Total    : €{order.total_price:.2f}\n"
                    f"Status   : pending")
            
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error in execute_order: {e}")
            self._send_message(chat_id, "❌ Order processing failed")
            return {'status': 'error'}