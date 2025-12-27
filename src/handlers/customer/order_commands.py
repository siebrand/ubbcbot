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
            self._send_message(chat_id, self._t('usage_order', user_id))
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            quantity = int(args[1]) if len(args) > 1 else 1

            if quantity <= 0:
                self._send_message(chat_id, self._t('quantity_must_positive', user_id))
                return {'status': 'invalid_quantity'}

            # Get offer
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found', user_id))
                return {'status': 'offer_not_found'}
            
            if offer.status == OfferStatus.SOLD_OUT.value:
                self._send_message(chat_id, self._t('offer_sold_out_named', user_id, offer_name=offer.name))
                return {'status': 'sold_out'}
            
            if offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, self._t('offer_not_found', user_id))
                return {'status': 'offer_not_found'}

            # Get customer
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, self._t('customer_not_found', user_id))
                return {'status': 'customer_not_found'}

            # Check for existing orders and enforce 5-unit limit BEFORE creating boxes
            existing_orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) 
                             if o.offer_id == offer_id and o.status in ['pending', 'ordered']]
            total_existing = sum(order.quantity for order in existing_orders)
            
            if total_existing + quantity > 5:
                message = self._t('order_limit_exceeded', user_id, 
                                offer_name=offer.name, 
                                total_existing=total_existing)
                message += "\n\n"
                for order in existing_orders:
                    from utils.timezone import to_cet_string
                    order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                remaining_allowed = 5 - total_existing
                if remaining_allowed > 0:
                    message += self._t('remaining_units_allowed', user_id, remaining=remaining_allowed)
                else:
                    message += self._t('limit_reached', user_id)
                
                self._send_message(chat_id, message)
                return {'status': 'limit_exceeded'}

            # Check for existing orders for duplicate confirmation
            if existing_orders:
                message = self._t('duplicate_order_warning', user_id, offer_name=offer.name)
                message += "\n\n"
                for order in existing_orders:
                    from utils.timezone import to_cet_string
                    order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                message += self._t('confirm_additional_order', user_id, quantity=quantity)
                
                # Create inline keyboard with Confirm and Cancel buttons
                keyboard = {
                    "inline_keyboard": [[
                        {"text": self._t('confirm', user_id), "callback_data": f"confirm_order_{offer_id}_{quantity}"},
                        {"text": self._t('cancel', user_id), "callback_data": "cancel_confirmation"}
                    ]]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'confirmation_required'}

            # Execute the order
            return self.execute_order(chat_id, user_id, offer_id, quantity, offer, customer)

        except ValueError:
            self._send_message(chat_id, self._t('invalid_format', user_id))
            return {'status': 'invalid_format'}

    def handle_confirm_order(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_order command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_confirm_order', user_id))
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            quantity = int(args[1])
            
            if quantity <= 0:
                self._send_message(chat_id, self._t('quantity_must_positive', user_id))
                return {'status': 'invalid_quantity'}

            # Get offer and customer
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found', user_id))
                return {'status': 'offer_not_found'}
            
            if offer.status == OfferStatus.SOLD_OUT.value:
                self._send_message(chat_id, self._t('offer_sold_out_named', user_id, offer_name=offer.name))
                return {'status': 'sold_out'}
            
            if offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, self._t('offer_not_found_inactive', user_id))
                return {'status': 'offer_not_found'}

            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, self._t('customer_not_found', user_id))
                return {'status': 'customer_not_found'}
            
            # Check 5-unit limit for confirmed orders
            existing_orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) 
                             if o.offer_id == offer_id and o.status in ['pending', 'ordered']]
            total_existing = sum(order.quantity for order in existing_orders)
            
            if total_existing + quantity > 5:
                message = self._t('order_limit_exceeded', user_id, 
                                offer_name=offer.name, 
                                total_existing=total_existing)
                message += "\n\n"
                for order in existing_orders:
                    from utils.timezone import to_cet_string
                    order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                remaining_allowed = 5 - total_existing
                if remaining_allowed > 0:
                    message += self._t('remaining_units_allowed', user_id, remaining=remaining_allowed)
                else:
                    message += self._t('limit_reached', user_id)
                
                self._send_message(chat_id, message)
                return {'status': 'limit_exceeded'}
            
            # Execute the order without duplicate check
            return self.execute_order(chat_id, user_id, offer_id, quantity, offer, customer)
            
        except ValueError:
            self._send_message(chat_id, self._t('invalid_format', user_id))
            return {'status': 'invalid_format'}

    def execute_order(self, chat_id: int, user_id: int, offer_id: int, quantity: int, offer, customer, placed_by_admin: bool = False) -> Dict[str, Any]:
        """Execute order placement"""
        try:
            box_size = int(offer.wholesale_box_size)
            if box_size == 1:
                logger.info(f"DEBUG: Processing order for box size 1 offer {offer_id}, quantity {quantity}, customer {customer.customer_id}")
            
            # Check total available capacity and create new box if needed
            boxes = self.db.get_boxes_by_offer(offer_id)
            total_available = 0
            for box in boxes:
                if box.status in [BoxStatus.OPEN.value, BoxStatus.MINIMUM_REACHED.value, BoxStatus.FULL.value]:
                    # Ensure box capacity values are integers
                    max_cap = int(box.max_capacity) if hasattr(box.max_capacity, '__int__') else box.max_capacity
                    current_qty = int(box.current_quantity) if hasattr(box.current_quantity, '__int__') else box.current_quantity
                    total_available += max_cap - current_qty
            
            if box_size == 1:
                logger.info(f"DEBUG: Box size 1 - Found {len(boxes)} boxes, total_available: {total_available}")
            
            # Create new boxes if insufficient capacity and offer allows it
            if total_available < quantity:
                has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes) if boxes else False
                if offer.status == OfferStatus.ACTIVE.value and not has_ordered_boxes:
                    # Calculate how many new boxes needed
                    needed_capacity = quantity - total_available
                    boxes_needed = (needed_capacity + box_size - 1) // box_size  # Ceiling division
                    
                    if box_size == 1:
                        logger.info(f"DEBUG: Box size 1 - Creating {boxes_needed} new boxes for needed_capacity {needed_capacity}")
                    
                    # Create the required number of boxes
                    for i in range(boxes_needed):
                        new_box = Box(
                            offer_id=offer_id,
                            max_capacity=box_size,
                            min_breakeven=int(offer.min_quantity_breakeven)
                        )
                        created_box = self.db.create_box(new_box)
                        if box_size == 1:
                            logger.info(f"DEBUG: Box size 1 - Created box {i+1}/{boxes_needed}, box_id: {created_box.box_id if created_box else 'FAILED'}")
                        total_available += int(box_size)
                else:
                    if total_available > 0:
                        self._send_message(chat_id, self._t('insufficient_quantity', user_id, 
                                                          requested=quantity, 
                                                          available=total_available))
                    else:
                        self._send_message(chat_id, self._t('sold_out', user_id))
                    return {'status': 'insufficient_capacity'}
            
            # Final capacity check
            if quantity > total_available:
                self._send_message(chat_id, self._t('insufficient_quantity', user_id, 
                                                  requested=quantity, 
                                                  available=total_available))
                return {'status': 'insufficient_capacity'}

            # Create single order
            order = Order(
                customer_id=customer.customer_id,
                box_id="",  # Will be set when assigning to boxes
                offer_id=offer_id,
                quantity=quantity,
                unit_price=offer.price_per_unit,
                total_price=offer.price_per_unit * quantity,
                placed_by_admin=placed_by_admin
            )

            created_order = self.db.create_order(order)
            if not created_order:
                self._send_message(chat_id, self._t('order_failed', user_id))
                return {'status': 'error'}
            
            if box_size == 1:
                logger.info(f"DEBUG: Box size 1 - Created order {created_order.order_id}, quantity {quantity}")

            # Now assign order to boxes and update quantities
            remaining_quantity = quantity
            boxes_used = []
            
            while remaining_quantity > 0:
                # Find available box
                boxes = self.db.get_boxes_by_offer(offer_id)
                available_box = None
                
                for box in boxes:
                    if box.status in [BoxStatus.OPEN.value, BoxStatus.MINIMUM_REACHED.value, BoxStatus.FULL.value]:
                        available_space = box.max_capacity - box.current_quantity
                        if available_space > 0:
                            available_box = box
                            break

                # Should always find a box since we created one if needed
                if not available_box:
                    logger.error(f"No available box found for offer {offer_id} after capacity check")
                    self._send_message(chat_id, self._t('order_processing_failed', user_id))
                    return {'status': 'error'}

                # Calculate how much can fit in this box
                available_space = available_box.max_capacity - available_box.current_quantity
                box_quantity = min(remaining_quantity, available_space)
                
                # Update box quantity and status
                new_quantity = available_box.current_quantity + box_quantity
                updates = {'current_quantity': new_quantity}
                
                # Update box status based on new quantity
                if new_quantity >= available_box.max_capacity:
                    updates['status'] = BoxStatus.FULL.value if available_box.status != BoxStatus.ORDERED.value else BoxStatus.ORDERED.value
                elif new_quantity >= available_box.min_breakeven:
                    updates['status'] = BoxStatus.MINIMUM_REACHED.value if available_box.status != BoxStatus.ORDERED.value else BoxStatus.ORDERED.value

                if not self.db.update_box(available_box.box_id, updates):
                    logger.error(f"Failed to update box {available_box.box_id}")
                    self._send_message(chat_id, self._t('failed_update_box', user_id))
                    return {'status': 'error'}
                
                boxes_used.append(available_box.box_id)
                remaining_quantity -= box_quantity
                logger.info(f"Assigned {box_quantity} units to box, remaining: {remaining_quantity}")

            # Update order with first box_id and appropriate status
            if boxes_used:
                # Get updated box status to determine final order status
                updated_box = self.db.get_box(boxes_used[0])
                final_status = 'ordered' if updated_box.status == BoxStatus.ORDERED.value else 'pending'
                self.db.update_order(order.order_id, {'box_id': boxes_used[0], 'status': final_status})
                
                # Update order object for confirmation message
                order.status = final_status
                
                # Check if offer should be marked as sold out
                self._check_and_update_offer_status(offer_id)

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
            
            # Send notification to default channel for all successful orders (not just private chats)
            if not placed_by_admin:  # Don't notify for admin orders
                if box_size == 1:
                    logger.info(f"DEBUG: Box size 1 - Sending group notification for order {created_order.order_id}")
                notification_result = self._notify_channel_order(customer, offer, quantity)
                if box_size == 1:
                    logger.info(f"DEBUG: Box size 1 - Group notification result: {notification_result}")
            
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error in execute_order: {e}")
            self._send_message(chat_id, self._t('order_processing_failed', user_id))
            return {'status': 'error'}
    
    def _check_and_update_offer_status(self, offer_id: int):
        """Check if offer should be marked as sold out - only if boxes are already ordered"""
        try:
            offer = self.db.get_offer(offer_id)
            if not offer or offer.status != OfferStatus.ACTIVE.value:
                return
            
            boxes = self.db.get_boxes_by_offer(offer_id)
            
            # Only mark as sold out if there are ordered boxes and all capacity is used
            has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes)
            if not has_ordered_boxes:
                return  # Don't mark as sold out if no boxes are ordered yet
            
            total_capacity = sum(box.max_capacity for box in boxes)
            total_ordered = sum(box.current_quantity for box in boxes)
            
            # Check if all units are ordered by customers
            if total_ordered >= total_capacity:
                self.db.update_offer(offer_id, {'status': OfferStatus.SOLD_OUT.value})
                logger.info(f"Offer {offer_id} marked as sold out - all {total_capacity} units ordered")
                
                # Delete notification messages for sold out offer
                self._delete_offer_notifications(offer_id)
        except Exception as e:
            logger.error(f"Error checking offer status: {e}")
    
    def _get_public_name(self, customer):
        """Get customer's public display name (Firstname L)"""
        name_parts = []
        if customer.first_name:
            name_parts.append(customer.first_name)
        if customer.last_name:
            name_parts.append(f"{customer.last_name[0]}")
        
        return ' '.join(name_parts) if name_parts else customer.username or 'Unknown'
    
    def _notify_channel_order(self, customer, offer, quantity):
        """Send order notification to default group"""
        import os
        try:
            group_id = os.environ.get('DEFAULT_GROUP_ID')
            if not group_id:
                box_size = int(offer.wholesale_box_size)
                if box_size == 1:
                    logger.info(f"DEBUG: Box size 1 - No DEFAULT_GROUP_ID configured")
                return False
            
            customer_name = self._get_public_name(customer)
            
            # Check if offer is now sold out and calculate remaining availability
            updated_offer = self.db.get_offer(offer.offer_id)
            availability_text = ""
            
            if updated_offer and updated_offer.status == OfferStatus.SOLD_OUT.value:
                availability_text = " - SOLD OUT"
            else:
                # Calculate remaining availability
                boxes = self.db.get_boxes_by_offer(offer.offer_id)
                total_available = 0
                for box in boxes:
                    if box.status in [BoxStatus.OPEN.value, BoxStatus.MINIMUM_REACHED.value, BoxStatus.FULL.value]:
                        total_available += box.max_capacity - box.current_quantity
                
                if total_available > 6:
                    availability_text = f" ({self._t('sufficient_available', force_group_lang=True)})"
                elif total_available > 0:
                    availability_text = f" ({self._t('units_available', force_group_lang=True, count=total_available)})"
                # If total_available == 0 and not sold out, show nothing
            
            message = f"🍺 {customer_name} ordered {quantity}x {offer.name}{availability_text}"
            box_size = int(offer.wholesale_box_size)
            if box_size == 1:
                logger.info(f"DEBUG: Box size 1 - Sending group message: {message}")
            
            result = self._send_message(int(group_id), message, force_group=True)
            success = result.get('success', False)
            
            if box_size == 1:
                logger.info(f"DEBUG: Box size 1 - Group message send result: {success}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending group notification: {e}")
            return False
    def _delete_offer_notifications(self, offer_id: int):
        """Delete notification messages for sold out offer"""
        try:
            notifications = self.db.get_notification_messages_by_offer(offer_id)
            
            for notification in notifications:
                try:
                    if self._delete_message(notification.chat_id, notification.message_id):
                        self.db.delete_notification_message(notification.notification_id)
                        logger.info(f"Deleted notification message {notification.message_id} for offer {offer_id}")
                except Exception as e:
                    logger.error(f"Failed to delete message {notification.message_id}: {e}")
        except Exception as e:
            logger.error(f"Error deleting offer notifications: {e}")