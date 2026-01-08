import logging
from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Order, Box, BoxStatus, OfferStatus

logger = logging.getLogger()

class CustomerOrderCommands(BaseHandler):
    def handle_order(self, chat_id: int, user_id: int, args: list, skip_duplicate_check: bool = False) -> Dict[str, Any]:
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
            valid, limit_message = self.validator.validate_order_limit(customer.customer_id, offer_id, quantity)
            if not valid:
                self._send_message(chat_id, limit_message)
                return {'status': 'limit_exceeded'}

            # Check for existing orders for duplicate confirmation
            if not skip_duplicate_check:
                existing_orders = self.db.get_orders_by_customer_and_offer(customer.customer_id, offer_id)
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
        if len(args) < 1:
            self._send_message(chat_id, self._t('usage_confirm_order', user_id))
            return {'status': 'invalid_args'}
        
        # Reuse handle_order with skip_duplicate_check=True
        return self.handle_order(chat_id, user_id, args, skip_duplicate_check=True)

    def execute_order(self, chat_id: int, user_id: int, offer_id: int, quantity: int, offer, customer, placed_by_admin: bool = False) -> Dict[str, Any]:
        """Execute order placement"""
        try:
            box_size = offer.wholesale_box_size

            # Validate order quantity doesn't exceed box size
            if quantity > box_size:
                self._send_message(chat_id, self._t('quantity_exceeds_box_size', user_id, quantity=quantity, box_size=box_size))
                return {'status': 'quantity_too_large'}
            
            # ATOMIC CAPACITY CHECK: Find a box that can fit the entire order
            boxes = self.db.get_boxes_by_offer(offer_id)
            suitable_box = None
            
            # Look for existing box that can fit the entire order
            for box in boxes:
                if box.status in [BoxStatus.OPEN.value, BoxStatus.FULL.value, BoxStatus.ORDERED.value]:
                    available_space = box.max_capacity - box.current_quantity
                    if available_space >= quantity:
                        suitable_box = box
                        break
            
            # If no suitable box found, create a new one (if allowed)
            if not suitable_box:
                has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes) if boxes else False
                
                if offer.status == OfferStatus.ACTIVE.value and not has_ordered_boxes:
                    # Create new box
                    new_box = Box(
                        offer_id=offer_id,
                        max_capacity=box_size
                    )
                    suitable_box = self.db.create_box(new_box)
                    if not suitable_box:
                        self._send_message(chat_id, self._t('order_processing_failed', user_id))
                        return {'status': 'error'}
                else:
                    # Cannot create boxes - reject order
                    self._send_message(chat_id, self._t('order_too_large_for_remaining_space', user_id))
                    return {'status': 'insufficient_space'}

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
            
            # Assign order to the suitable box
            new_quantity = suitable_box.current_quantity + quantity
            updates = {'current_quantity': new_quantity}
            
            # Update box status based on new quantity (don't change status if already ORDERED)
            if suitable_box.status != BoxStatus.ORDERED.value:
                if new_quantity >= suitable_box.max_capacity:
                    updates['status'] = BoxStatus.FULL.value

            if not self.db.update_box(suitable_box.box_id, updates):
                logger.error(f"Failed to update box {suitable_box.box_id}")
                self._send_message(chat_id, self._t('failed_update_box', user_id))
                return {'status': 'error'}
            
            # Update order with box_id and status
            final_status = 'ordered' if suitable_box.status == BoxStatus.ORDERED.value else 'pending'
            self.db.update_order(order.order_id, {'box_id': suitable_box.box_id, 'status': final_status})
            order.status = final_status

            # Check if offer should be marked as sold out
            self._check_offer_status_after_change(offer_id)
            
            # Send confirmation message - always single box now
            self._send_message(chat_id, self._t('order_placed_single', user_id,
                order_id=order.order_id,
                product=offer.name,
                quantity=quantity,
                total=float(order.total_price),
                status=order.status))
            
            # Send notification to default channel for all successful orders (not just private chats)
            if not placed_by_admin:  # Don't notify for admin orders
                notification_result = self._notify_channel_order(customer, offer, quantity)

            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error in execute_order: {e}")
            self._send_message(chat_id, self._t('order_processing_failed', user_id))
            return {'status': 'error'}
    
    def _get_public_name(self, customer):
        """Get customer's public display name (Firstname L)"""
        name_parts = []
        if customer.first_name:
            name_parts.append(customer.first_name)
        if customer.last_name:
            name_parts.append(f"{customer.last_name[0]}")
        
        return ' '.join(name_parts) if name_parts else customer.username or self._t('unknown', user_id=None)
    
    def _notify_channel_order(self, customer, offer, quantity):
        """Send order notification to default group"""
        import os
        try:
            group_id = os.environ.get('DEFAULT_GROUP_ID')
            if not group_id:
                box_size = offer.wholesale_box_size
                return False
            
            customer_name = self._get_public_name(customer)
            bot_username = self._get_bot_username()
            
            # Check if offer is now sold out and calculate remaining availability
            updated_offer = self.db.get_offer(offer.offer_id)
            availability_text = ""
            
            if updated_offer and updated_offer.status == OfferStatus.SOLD_OUT.value:
                availability_text = f" - {self._t('status_sold_out', force_group_lang=True)}"
            else:
                # Calculate remaining availability
                boxes = self.db.get_boxes_by_offer(offer.offer_id)
                total_available = 0
                for box in boxes:
                    if box.current_quantity < box.max_capacity:
                        total_available += box.max_capacity - box.current_quantity
                
                if total_available > 6:
                    availability_text = f" ({self._t('sufficient_available', force_group_lang=True)})"
                elif total_available > 0:
                    availability_text = f" ({self._t('units_available', force_group_lang=True, count=total_available)})"
                # If total_available == 0 and not sold out, show nothing
            
            # Format offer name as link
            offer_link = f"<a href='https://t.me/{bot_username}?start=offer_details_{offer.offer_id}'>{self._escape_html(offer.name)}</a>"
            
            message = self._t('order_notification', force_group_lang=True, 
                            customer_name=customer_name, 
                            quantity=quantity, 
                            offer_name=offer_link, 
                            availability=availability_text)
            result = self._send_message(int(group_id), message, parse_mode="HTML", force_group=True)
            success = result.get('success', False)
            return success
            
        except Exception as e:
            logger.error(f"Error sending group notification: {e}")
            return False
    def handle_delete_cancelled(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /delete_cancelled command - delete all cancelled orders for user"""
        try:
            # Get customer
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, self._t('customer_not_found', user_id))
                return {'status': 'customer_not_found'}
            
            # Get all cancelled orders for the customer
            cancelled_orders = self.db.get_orders_by_customer_and_status(customer.customer_id, 'cancelled')
            
            if not cancelled_orders:
                self._send_message(chat_id, self._t('no_cancelled_orders', user_id))
                return {'status': 'no_cancelled_orders'}
            
            # Delete all cancelled orders
            deleted_count = 0
            for order in cancelled_orders:
                if self.db.delete_order(order.order_id):
                    deleted_count += 1
            
            if deleted_count > 0:
                self._send_message(chat_id, self._t('cancelled_orders_deleted', user_id, count=deleted_count))
                return {'status': 'success', 'deleted_count': deleted_count}
            else:
                self._send_message(chat_id, self._t('failed_delete_cancelled_orders', user_id))
                return {'status': 'error'}
                
        except Exception as e:
            logger.error(f"Error in handle_delete_cancelled: {e}")
            self._send_message(chat_id, self._t('failed_delete_cancelled_orders', user_id))
            return {'status': 'error'}
    
    def handle_delete_completed(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /delete_completed command - delete all completed orders for user"""
        try:
            # Get customer
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, self._t('customer_not_found', user_id))
                return {'status': 'customer_not_found'}
            
            # Get all completed orders for the customer
            completed_orders = self.db.get_orders_by_customer_and_status(customer.customer_id, 'completed')
            
            if not completed_orders:
                self._send_message(chat_id, self._t('no_completed_orders', user_id))
                return {'status': 'no_completed_orders'}
            
            # Delete all completed orders
            deleted_count = 0
            for order in completed_orders:
                if self.db.delete_order(order.order_id):
                    deleted_count += 1
            
            if deleted_count > 0:
                self._send_message(chat_id, self._t('completed_orders_deleted', user_id, count=deleted_count))
                return {'status': 'success', 'deleted_count': deleted_count}
            else:
                self._send_message(chat_id, self._t('failed_delete_completed_orders', user_id))
                return {'status': 'error'}
                
        except Exception as e:
            logger.error(f"Error in handle_delete_completed: {e}")
            self._send_message(chat_id, self._t('failed_delete_completed_orders', user_id))
            return {'status': 'error'}