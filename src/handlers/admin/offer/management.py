from typing import Dict, Any
from models.entities import OfferStatus, OrderStatus, BoxStatus
from .base import OfferBaseHandler

class OfferManagementHandler(OfferBaseHandler):
    """Handler for offer management operations"""
    
    def handle_fulfill_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /fulfill_offer command"""
        if not args:
            self._send_message(chat_id, self._t('usage_fulfill_offer'))
            return {'status': 'invalid_args'}

        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error
            
        if offer.status not in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value]:
            self._send_message(chat_id, self._t('offer_not_active'))
            return {'status': 'offer_not_active'}
        
        # Get all pending orders for this offer, sorted by date ascending
        all_orders = self.db.get_orders_by_offer(offer.offer_id)
        pending_orders = [o for o in all_orders if o.status == 'pending']
        pending_orders.sort(key=lambda x: x.created_at)
        
        if not pending_orders:
            self._send_message(chat_id, self._t('no_pending_orders'))
            return {'status': 'no_pending_orders'}
        
        # Calculate boxes needed
        total_units = sum(order.quantity for order in pending_orders)
        boxes_needed = (total_units + offer.wholesale_box_size - 1) // offer.wholesale_box_size  # Ceiling division
        
        # Show order summary
        message = self._t('fulfillment_summary',
            offer_id=offer.offer_id,
            name=offer.name,
            price=offer.price_per_unit,
            box_size=offer.wholesale_box_size,
            total_units=total_units,
            boxes_needed=boxes_needed,
            order_count=len(pending_orders)
        )
        
        for i, order in enumerate(pending_orders[:10], 1):  # Show first 10
            customer = self.db.get_customer(order.customer_id)
            customer_name = customer.first_name if customer else "Unknown"
            from utils.timezone import to_cet_string
            order_date = to_cet_string(order.created_at, '%m-%d %H:%M')
            message += f"{i}. {customer_name}: {order.quantity} units [{order_date}]\n"
        
        if len(pending_orders) > 10:
            message += f"... and {len(pending_orders) - 10} more orders\n"
        
        # Add inline keyboard for confirmation
        keyboard = {
            "inline_keyboard": [[
                {"text": self._t('fulfill_with_boxes', boxes=boxes_needed), "callback_data": f"confirm_fulfill_{offer.offer_id}_{boxes_needed}"},
                {"text": self._t('cancel'), "callback_data": "cancel_action"}
            ]]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_confirm_fulfill(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_fulfill command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_confirm_fulfill'))
            return {'status': 'invalid_args'}
        
        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error
            
        boxes_ordered, error = self._parse_int_arg(args[1], 'invalid_format', chat_id)
        if error:
            return error
            
        if boxes_ordered <= 0:
            self._send_message(chat_id, self._t('boxes_must_positive'))
            return {'status': 'invalid_quantity'}
        
        # Get pending orders sorted by date ascending (oldest first)
        all_orders = self.db.get_orders_by_offer(offer.offer_id)
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
                msg = self._t('order_updated_limited',
                    name=offer.name,
                    old_qty=old_qty,
                    new_qty=new_qty,
                    total=new_total_price
                )
                self._send_message(customer.telegram_user_id, msg)
            
            # Update all boxes for this offer to 'ordered' status
            boxes = self.db.get_boxes_by_offer(offer_id)
            for box in boxes:
                self.db.update_box(box.box_id, {'status': BoxStatus.ORDERED.value})
            
            # Cancel remaining orders
            for order in cancelled_orders:
                self.db.update_order(order.order_id, {'status': 'cancelled'})
                
                # Notify customer of cancellation
                customer = self.db.get_customer(order.customer_id)
                if customer:
                    msg = self._t('order_cancelled_insufficient',
                        name=offer.name,
                        quantity=order.quantity,
                        total=order.total_price
                    )
                    self._send_message(customer.telegram_user_id, msg)
            
            # Update offer status - keep active if there's remaining capacity or pending orders
            # Refresh the orders list to get current status after updates
            updated_orders_list = self.db.get_orders_by_offer(offer_id)
            remaining_pending = [o for o in updated_orders_list if o.status == 'pending']
            
            # Check if there's remaining capacity
            remaining_capacity = units_available - units_allocated
            
            if not remaining_pending and remaining_capacity == 0:
                self.db.update_offer(offer_id, {'status': 'sold_out'})
                offer_status_msg = "Offer marked as SOLD OUT (no capacity remaining)"
            elif not remaining_pending:
                offer_status_msg = f"Offer remains ACTIVE ({remaining_capacity} units capacity remaining)"
            else:
                offer_status_msg = f"Offer remains ACTIVE ({len(remaining_pending)} pending orders remaining)"
            
            # Create additional empty boxes if needed to match ordered capacity
            current_boxes = self.db.get_boxes_by_offer(offer_id)
            current_capacity = sum(box.max_capacity for box in current_boxes)
            ordered_capacity = boxes_ordered * offer.wholesale_box_size
            
            if ordered_capacity > current_capacity:
                boxes_to_create = boxes_ordered - len(current_boxes)
                for _ in range(boxes_to_create):
                    from models.entities import Box
                    new_box = Box(
                        offer_id=offer_id,
                        max_capacity=offer.wholesale_box_size,
                        min_breakeven=offer.min_quantity_breakeven,
                        status=BoxStatus.ORDERED.value
                    )
                    self.db.create_box(new_box)
            
            # Clean up empty boxes (delete boxes with 0 orders)
            boxes = self.db.get_boxes_by_offer(offer_id)
            empty_boxes = [box for box in boxes if box.current_quantity == 0]
            deleted_boxes = 0
            for box in empty_boxes:
                if self.db.delete_box(box.box_id):
                    deleted_boxes += 1
            
            # Send summary to admin
            fulfilled_units = sum(order.quantity for order in fulfilled_orders)
            summary = self._t('offer_fulfilled_summary',
                offer_id=offer.offer_id,
                boxes=boxes_ordered,
                fulfilled_orders=len(fulfilled_orders),
                fulfilled_units=fulfilled_units
            )
            
            if updated_orders:
                order, old_qty, new_qty = updated_orders[0]
                customer = self.db.get_customer(order.customer_id)
                customer_name = customer.first_name if customer else "Unknown"
                summary += "\n" + self._t('order_reduced',
                    customer=customer_name,
                    old_qty=old_qty,
                    new_qty=new_qty
                )
            
            if cancelled_orders:
                cancelled_details = []
                cancelled_units = 0
                for order in cancelled_orders:
                    customer = self.db.get_customer(order.customer_id)
                    customer_name = customer.first_name if customer else "Unknown"
                    cancelled_details.append(f"{customer_name} ({order.quantity} units)")
                    cancelled_units += order.quantity
                summary += "\n" + self._t('orders_cancelled',
                    cancelled_orders=len(cancelled_orders),
                    cancelled_units=cancelled_units,
                    details=', '.join(cancelled_details)
                )
            
            summary += "\n\n" + self._t('total_allocated',
                allocated=units_allocated,
                available=units_available
            )
            summary += f"\n📊 {offer_status_msg}"
            
            if deleted_boxes > 0:
                summary += "\n" + self._t('cleaned_empty_boxes', count=deleted_boxes)
            
            self._send_message(chat_id, summary)
            return {'status': 'success'}
    
    def handle_cancel_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /cancel_offer command"""
        if not args:
            self._send_message(chat_id, self._t('usage_cancel_offer'))
            return {'status': 'invalid_args'}

        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error
        
        if offer.status != OfferStatus.ACTIVE.value:
            self._send_message(chat_id, self._t('offer_not_active'))
            return {'status': 'offer_not_active'}
        
        # Get all orders for this offer
        all_orders = self.db.get_orders_by_offer(offer.offer_id)
        active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
        
        if not active_orders:
            # No active orders, just cancel the offer
            self.db.update_offer(offer.offer_id, {'status': OfferStatus.INACTIVE.value})
            self._delete_offer_boxes(offer.offer_id)
            self._send_message(chat_id, self._t('offer_cancelled_no_orders', offer_id=offer.offer_id))
            return {'status': 'success'}
        
        # Show confirmation with order details
        message = self._t('cancel_offer_warning',
            offer_id=offer.offer_id,
            name=offer.name,
            order_count=len(active_orders)
        )
        
        # Add inline keyboard for confirmation
        keyboard = {
            "inline_keyboard": [[
                {"text": self._t('confirm_cancel'), "callback_data": f"confirm_cancel_offer_{offer.offer_id}"},
                {"text": self._t('keep_offer'), "callback_data": "cancel_action"}
            ]]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'confirmation_required'}
    
    def handle_confirm_cancel_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_cancel_offer command"""
        if not args:
            self._send_message(chat_id, self._t('usage_confirm_cancel_offer'))
            return {'status': 'invalid_args'}
        
        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error
            
        # Get all pending orders
        all_orders = self.db.get_orders_by_offer(offer.offer_id)
        active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
        
        # Cancel all active orders and notify customers
        cancelled_count = 0
        for order in active_orders:
            if self.db.update_order(order.order_id, {'status': OrderStatus.CANCELLED.value}):
                cancelled_count += 1
                self._notify_customer_cancellation(order, offer)
        
        # Delete all boxes
        deleted_boxes = self._delete_offer_boxes(offer.offer_id)
        
        # Delete notification messages for cancelled offer
        self._cleanup_offer_notifications(offer.offer_id)
        
        # Cancel the offer
        self.db.update_offer(offer.offer_id, {'status': OfferStatus.INACTIVE.value})
        
        # Send summary
        summary = self._t('offer_cancelled_summary',
            offer_id=offer.offer_id,
            cancelled_count=cancelled_count,
            deleted_boxes=deleted_boxes,
            notified_count=cancelled_count
        )
        
        self._send_message(chat_id, summary)
        return {'status': 'success'}
    
    def _delete_offer_boxes(self, offer_id: int) -> int:
        """Delete all boxes for an offer and return count"""
        boxes = self.db.get_boxes_by_offer(offer_id)
        deleted_count = 0
        for box in boxes:
            if self.db.delete_box(box.box_id):
                deleted_count += 1
        return deleted_count
    
    def _notify_customer_cancellation(self, order, offer):
        """Notify customer about order cancellation"""
        customer = self.db.get_customer(order.customer_id)
        if customer:
            message = self._t('order_cancelled_offer_cancelled',
                name=offer.name,
                quantity=order.quantity
            )
            self._send_message(customer.telegram_user_id, message)

    def _cleanup_offer_notifications(self, offer_id: int):
        """Clean up notification messages for cancelled offer"""
        try:
            offer = self.db.get_offer(offer_id)
            if not offer:
                return
            
            notifications = self.db.get_notification_messages_by_offer(offer_id)
            
            # Check if offer is within 48 hours (172800 seconds)
            from datetime import datetime, UTC, timedelta
            now = datetime.now(UTC)
            offer_age = now - offer.created_at
            within_48_hours = offer_age < timedelta(hours=48)
            
            for notification in notifications:
                try:
                    if within_48_hours:
                        # Delete message from Telegram
                        self._delete_message(notification.chat_id, notification.message_id)
                    
                    # Always remove from database
                    self.db.delete_notification_message(notification.notification_id)
                except Exception as e:
                    import logging
                    logging.error(f"Failed to cleanup notification {notification.notification_id}: {e}")
        except Exception as e:
            import logging
            logging.error(f"Error cleaning up offer notifications: {e}")
