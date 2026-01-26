import logging
from typing import Dict, Any
from handlers.base_handler import BaseHandler
from models.entities import Order, Box, BoxStatus, OfferStatus, OrderStatus
from services.box_status_manager import BoxStatusManager

logger = logging.getLogger()

class CustomerOrderCommands(BaseHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)
    
    def handle_create_order(self, chat_id: int, user_id: int, args: list, skip_duplicate_check: bool = False) -> Dict[str, Any]:
        """Handle /create_order command"""
        error = self._validate_args(args, 1, 'usage_order', chat_id)
        if error:
            return error
        
        offer_id, error = self._parse_int_arg(args[0], 'invalid_format', chat_id)
        if error:
            return error
        
        quantity = 1
        if len(args) > 1:
            quantity, error = self._parse_int_arg(args[1], 'invalid_format', chat_id)
            if error:
                return error
        
        if quantity <= 0:
            return self._send_error(chat_id, 'quantity_must_positive', 'invalid_quantity', user_id=user_id)
        
        # Get and validate offer and customer
        offer, customer = self._get_offer_and_customer(chat_id, user_id, offer_id)
        if not offer or not customer:
            return {'status': 'validation_failed'}
        
        # Check order limits
        if not self._check_order_limits(chat_id, customer.customer_id, offer_id, quantity):
            return {'status': 'limit_exceeded'}
        
        # Check for duplicates
        if not skip_duplicate_check and self._has_duplicate_orders(chat_id, user_id, customer.customer_id, offer_id, quantity, offer.name):
            return {'status': 'confirmation_required'}
        
        return self.execute_order(chat_id, user_id, quantity, offer, customer)

    def handle_confirm_order(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_order command"""
        error = self._validate_args(args, 1, 'usage_confirm_order', chat_id)
        if error:
            return error
        
        return self.handle_create_order(chat_id, user_id, args, skip_duplicate_check=True)

    def execute_order(self, chat_id: int, user_id: int, quantity: int, offer, customer, placed_by_admin: bool = False) -> Dict[str, Any]:
        """Execute order placement"""
        try:
            # Validate quantity
            if quantity > offer.wholesale_box_size:
                self._send_message(chat_id, self._t('quantity_exceeds_box_size', user_id, quantity=quantity, box_size=offer.wholesale_box_size))
                return {'status': 'quantity_too_large'}
            
            # Find or create suitable box
            suitable_box = self._find_or_create_box(chat_id, user_id, offer.offer_id, quantity, offer)
            if not suitable_box:
                return {'status': 'insufficient_space'}
            
            # Create and assign order
            order = self._create_and_assign_order(chat_id, user_id, customer, offer, suitable_box, quantity, placed_by_admin)
            if not order:
                return {'status': 'error'}
            
            # Update offer status and send notifications
            self.box_status_manager.update_offer_status_after_change(offer.offer_id)
            self._send_order_confirmation(chat_id, user_id, order, offer, quantity, placed_by_admin, customer)
            
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error in execute_order: {e}")
            self._send_message(chat_id, self._t('order_processing_failed', user_id))
            return {'status': 'error'}
    
    def _get_offer_and_customer(self, chat_id: int, user_id: int, offer_id: int) -> tuple:
        """Get and validate offer and customer"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t('offer_not_found', user_id))
            return None, None
        
        if offer.status == OfferStatus.SOLD_OUT.value:
            self._send_message(chat_id, self._t('offer_sold_out_named', user_id, offer_name=offer.name))
            return None, None
        
        if offer.status != OfferStatus.ACTIVE.value:
            self._send_message(chat_id, self._t('offer_not_found', user_id))
            return None, None
        
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, self._t('customer_not_found', user_id))
            return None, None
        
        return offer, customer
    
    def _check_order_limits(self, chat_id: int, customer_id: str, offer_id: int, quantity: int) -> bool:
        """Check if order is within limits"""
        valid, limit_message = self.validator.validate_order_limit(customer_id, offer_id, quantity)
        if not valid:
            self._send_message(chat_id, limit_message)
        return valid
    
    def _has_duplicate_orders(self, chat_id: int, user_id: int, customer_id: str, offer_id: int, quantity: int, offer_name: str) -> bool:
        """Check for duplicate orders and prompt confirmation"""
        existing_orders = self.db.get_orders_by_customer_and_offer(customer_id, offer_id)
        if not existing_orders:
            return False
        
        from utils.timezone import to_cet_string
        message = self._t('duplicate_order_warning', user_id, offer_name=offer_name)
        message += "\n\n"
        for order in existing_orders:
            order_date = to_cet_string(order.created_at, '%Y-%m-%d')
            message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
        
        message += self._t('confirm_additional_order', user_id, quantity=quantity)
        
        keyboard = {
            "inline_keyboard": [[
                {"text": self._t('confirm', user_id), "callback_data": f"confirm_order_{offer_id}_{quantity}"},
                {"text": self._t('cancel', user_id), "callback_data": "cancel_confirmation"}
            ]]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return True
    
    def _find_or_create_box(self, chat_id: int, user_id: int, offer_id: int, quantity: int, offer) -> Box:
        """Find existing box with space or create new one"""
        boxes = self.db.get_boxes_by_offer(offer_id)
        
        # Prioritize delivered boxes first
        delivered_boxes = self.box_status_manager.get_delivered_boxes(boxes)
        for box in delivered_boxes:
            available_space = box.max_capacity - box.current_quantity
            if available_space >= quantity:
                return box
        
        # Then try other boxes (open, full, ordered)
        for box in boxes:
            if box.status in [BoxStatus.OPEN.value, BoxStatus.FULL.value, BoxStatus.ORDERED.value]:
                available_space = box.max_capacity - box.current_quantity
                if available_space >= quantity:
                    return box
        
        # Create new box if allowed
        has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes) if boxes else False
        has_delivered_boxes = len(self.box_status_manager.get_delivered_boxes(boxes)) > 0
        
        # Cannot create new boxes if delivered boxes exist
        if offer.status == OfferStatus.ACTIVE.value and not has_ordered_boxes and not has_delivered_boxes:
            new_box = Box(offer_id=offer_id, max_capacity=offer.wholesale_box_size)
            suitable_box = self.db.create_box(new_box)
            if not suitable_box:
                self._send_message(chat_id, self._t('order_processing_failed', user_id))
            return suitable_box
        else:
            self._send_message(chat_id, self._t('order_too_large_for_remaining_space', user_id))
            return None
    
    def _create_and_assign_order(self, chat_id: int, user_id: int, customer, offer, box, quantity: int, placed_by_admin: bool) -> Order:
        """Create order and assign to box"""
        order = Order(
            customer_id=customer.customer_id,
            box_id="",
            offer_id=offer.offer_id,
            quantity=quantity,
            unit_price=offer.price_per_unit,
            total_price=offer.price_per_unit * quantity,
            placed_by_admin=placed_by_admin
        )
        
        created_order = self.db.create_order(order, admin_id=0)  # Customer action
        if not created_order:
            self._send_message(chat_id, self._t('order_failed', user_id))
            return None

        # Note: Order-box assignment is split into separate operations due to DynamoDB's lack of
        # cross-table transactions. Error handling ensures consistency by notifying admin on failures.
        if not self.box_status_manager.update_box_after_order_placement(box.box_id, quantity):
            logger.error(f"Failed to update box {box.box_id}")
            self._send_message(chat_id, self._t('failed_update_box', user_id))
            self._send_message(self.admin_user_id, self._t('admin_box_update_failed', 
                box_id=box.box_id, 
                customer=f"{customer.first_name} {customer.last_name or ''}".strip(),
                offer_name=offer.name,
                quantity=quantity
            ))
            return None
        
        # Update order with box_id and status
        if box.status == BoxStatus.DELIVERED.value:
            final_status = OrderStatus.READY_FOR_LABELING.value
        elif box.status == BoxStatus.ORDERED.value:
            final_status = 'ordered'
        else:
            final_status = 'pending'
        
        self.db.update_order(created_order.order_id, {'box_id': box.box_id, 'status': final_status}, admin_id=0)
        created_order.status = final_status
        
        return created_order
    
    def _send_order_confirmation(self, chat_id: int, user_id: int, order, offer, quantity: int, placed_by_admin: bool, customer):
        """Send order confirmation and notifications"""
        self._send_message(chat_id, self._t('order_placed_single', user_id,
            order_id=order.order_id,
            product=offer.name,
            quantity=quantity,
            total=float(order.total_price),
            status=order.status))
        
        if not placed_by_admin:
            self._notify_channel_order(customer, offer, quantity)
    
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
                return False
            
            # Only send notifications for non-guest orders
            if customer.is_guest:
                logger.info("Skipping message to guest user")
                return False
            
            bot_username = self._get_bot_username()
            
            # Check if offer is now sold out and calculate remaining availability
            updated_offer = self.db.get_offer(offer.offer_id)
            availability_text = ""
            
            if updated_offer and updated_offer.status == OfferStatus.SOLD_OUT.value:
                availability_text = f" - {self._t('status_sold_out', force_group_lang=True)}"
            else:
                # Calculate remaining availability from all boxes under capacity
                boxes = self.db.get_boxes_by_offer(offer.offer_id)
                total_available = self.box_status_manager.get_available_capacity_for_orders(boxes)
                
                if total_available > 6:
                    availability_text = f" ({self._t('sufficient_available', force_group_lang=True)})"
                elif total_available > 0:
                    availability_text = f" ({self._t('units_available', force_group_lang=True, count=total_available)})"
                # If total_available == 0 and not sold out, show nothing
            
            # Format offer name as link
            offer_link = f"<a href='https://t.me/{bot_username}?start=view_offer_{offer.offer_id}'>{self._escape_html(offer.name)}</a>"
            
            customer_name = self._get_public_name(customer)
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
    def handle_delete_cancelled_orders(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /delete_cancelled_orders command - delete all cancelled orders for user"""
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
            logger.error(f"Error in handle_delete_cancelled_orders: {e}")
            self._send_message(chat_id, self._t('failed_delete_cancelled_orders', user_id))
            return {'status': 'error'}
    
    def handle_delete_completed_orders(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /delete_completed_orders command - delete all completed orders for user"""
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
            logger.error(f"Error in handle_delete_completed_orders: {e}")
            self._send_message(chat_id, self._t('failed_delete_completed_orders', user_id))
            return {'status': 'error'}
    
    def handle_payment_info(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /payment_info command - show customer their payment details"""
        try:
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, self._t('customer_not_found', user_id))
                return {'status': 'customer_not_found'}
            
            orders = self.db.get_orders_by_customer(customer.customer_id)
            awaiting_payment_orders = [o for o in orders if o.status == OrderStatus.AWAITING_PAYMENT.value]
            
            if not awaiting_payment_orders:
                self._send_message(chat_id, self._t('no_orders_awaiting_payment', user_id, customer_name=customer.first_name))
                return {'status': 'no_orders'}
            
            payment_link = self.db.get_payment_link()
            if not payment_link:
                self._send_message(chat_id, self._t('no_payment_link_stored', user_id))
                return {'status': 'no_payment_link'}
            
            from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
            delivery_handler = DeliveryOverviewHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
            message = delivery_handler._build_delivery_message(customer, awaiting_payment_orders, [], payment_link, is_reminder=False)
            
            self._send_message(chat_id, message, parse_mode="HTML")
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error in handle_payment_info: {e}")
            self._send_message(chat_id, self._t('order_processing_failed', user_id))
            return {'status': 'error'}