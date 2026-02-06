import logging
from typing import Dict, Any
from models.entities import OfferStatus, OrderStatus, BoxStatus
from .base import OfferBaseHandler
from services.box_status_manager import BoxStatusManager
from services.box_deletion_service import BoxDeletionService
from utils.pagination import PaginationUtils

logger = logging.getLogger()

class OfferManagementHandler(OfferBaseHandler):
    """Handler for offer management operations"""
    
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)
        self.box_deletion_service = BoxDeletionService(db)
    
    def handle_process_wholesale(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /order_wholesale command"""
        if not args:
            # Show available offers with pending orders
            return self._show_wholesale_offers_selection(chat_id, page=1)

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
        box_size = offer.wholesale_box_size  # Convert Decimal to int
        boxes_needed = (total_units + box_size - 1) // box_size  # Ceiling division
        
        # Show order summary
        message = self._t('wholesale_order_summary',
            offer_id=offer.offer_id,
            name=offer.name,
            price=offer.price_per_unit,
            box_size=offer.wholesale_box_size,
            total_units=total_units,
            boxes_needed=boxes_needed,
            order_count=len(pending_orders)
        )
        
        # Pre-calculate translation messages for efficiency
        units_singular = self._t('unit', chat_id)
        units_plural = self._t('units', chat_id)
        
        for i, order in enumerate(pending_orders, 1):  # Show all orders
            customer = self.db.get_customer(order.customer_id)
            customer_name = customer.first_name if customer else self._t('unknown', user_id=None)
            from utils.timezone import to_cet_string
            order_date = to_cet_string(order.created_at, '%m-%d %H:%M')
            units_text = units_singular if order.quantity == 1 else units_plural
            message += f"{i}. {customer_name}: {order.quantity} {units_text} [{order_date}]\n"
        
        # Add inline keyboard for confirmation
        keyboard = {
            "inline_keyboard": [[
                {"text": self._t('order_wholesale_boxes', boxes=boxes_needed), "callback_data": f"confirm_process_wholesale_{offer.offer_id}_{boxes_needed}"},
                {"text": self._t('custom_quantity'), "callback_data": f"custom_wholesale_quantity_{offer.offer_id}"},
                {"text": self._t('cancel'), "callback_data": "cancel_action"}
            ]]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_custom_wholesale_quantity(self, chat_id: int, offer_id: str) -> Dict[str, Any]:
        """Handle custom wholesale quantity input"""
        try:
            offer_id_int = int(offer_id)
            offer = self.db.get_offer(offer_id_int)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            # Store context for text input processing
            from utils.edit_context import EditContextManager
            edit_context_manager = EditContextManager(self.db, self._t, self._send_message)
            edit_context_manager.store_edit_context(chat_id, 'custom_wholesale_quantity', offer_id)
            
            # Prompt for custom quantity
            message = self._t('enter_custom_wholesale_quantity', offer_id=offer_id)
            self._send_message(chat_id, message)
            return {'status': 'awaiting_input'}
            
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
    
    def handle_confirm_process_wholesale(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_process_wholesale command"""
        logger.info(f"Starting handle_confirm_process_wholesale with args: {args}")
        
        if len(args) < 2:
            logger.error(f"Invalid args length: {len(args)}")
            self._send_message(chat_id, self._t('usage_confirm_process_wholesale'))
            return {'status': 'invalid_args'}
        
        logger.info(f"Validating offer with args[0]: {args[0]}")
        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            logger.error(f"Offer validation failed: {error}")
            return error
            
        logger.info(f"Parsing boxes arg: {args[1]}")
        try:
            boxes_ordered = int(args[1])
            logger.info(f"Successfully parsed boxes_ordered: {boxes_ordered}")
        except ValueError:
            logger.error(f"Failed to parse boxes arg as integer: {args[1]}")
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'invalid_format'}
            
        if boxes_ordered <= 0:
            self._send_message(chat_id, self._t('boxes_must_positive'))
            return {'status': 'invalid_quantity'}
        
        # Get box size from offer
        box_size = offer.wholesale_box_size
        
        # Get pending orders sorted by date ascending (oldest first)
        all_orders = self.db.get_orders_by_offer(offer.offer_id)
        pending_orders = [o for o in all_orders if o.status == 'pending']
        pending_orders.sort(key=lambda x: x.created_at)
        
        units_available = boxes_ordered * box_size
        units_allocated = 0
        fulfilled_orders = []
        cancelled_orders = []
        updated_orders = []
        
        # Process orders from oldest to newest (FIFO - first in, first out)
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
        # Update fulfilled orders to 'ordered' and track which boxes need ORDERED status
        boxes_with_fulfilled_orders = set()
        for order in fulfilled_orders:
            self.db.update_order(order.order_id, {'status': 'ordered'}, admin_id=self.admin_user_id, reason="Wholesale order processed")
            boxes_with_fulfilled_orders.add(order.box_id)
        
        # Update partially fulfilled orders and track boxes
        for order, old_qty, new_qty in updated_orders:
            new_total_price = new_qty * order.unit_price
            self.db.update_order(order.order_id, {
                'quantity': new_qty,
                'total_price': new_total_price,
                'status': 'ordered'
            }, admin_id=self.admin_user_id, reason="Partial fulfillment - wholesale order")
            boxes_with_fulfilled_orders.add(order.box_id)
            
            # Notify customer of quantity reduction
            customer = self.db.get_customer(order.customer_id)
            if customer:
                msg = self._t('order_updated_limited',
                    name=offer.name,
                    old_qty=old_qty,
                    new_qty=new_qty,
                    total=float(new_total_price)
                )
                self._send_message(customer.telegram_user_id, msg)
        
        # Get current boxes and update state for boxes with fulfilled orders as ORDERED
        boxes = self.db.get_boxes_by_offer(offer.offer_id)
        boxes_to_mark_ordered = [b.box_id for b in boxes if b.box_id in boxes_with_fulfilled_orders and b.status != BoxStatus.ORDERED.value]
        
        if boxes_to_mark_ordered:
            self.box_status_manager.mark_boxes_as_ordered(boxes_to_mark_ordered)
        
        # Delete only empty non-ordered boxes
        for box in boxes:
            if box.current_quantity == 0 and box.status != BoxStatus.ORDERED.value and box.box_id not in boxes_with_fulfilled_orders:
                logger.info(f"Deleting empty box {box.box_id}")
                self.db.delete_box(box.box_id)
        
        # Cancel remaining orders
        for order in cancelled_orders:
            self.db.cancel_order_with_audit(order.order_id, self.admin_user_id, "Insufficient wholesale capacity")
            
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
        updated_orders_list = self.db.get_orders_by_offer(offer.offer_id)
        remaining_pending = [o for o in updated_orders_list if o.status == 'pending']
        
        # Check if there's remaining capacity
        remaining_capacity = units_available - units_allocated
        
        # Pre-calculate unit translations for status messages
        units_text = self._t('unit', chat_id) if remaining_capacity == 1 else self._t('units', chat_id)
        
        if not remaining_pending and remaining_capacity == 0:
            self.db.update_offer(offer.offer_id, {'status': 'sold_out'})
            offer_status_msg = self._t('offer_is_sold_out', chat_id)
        elif not remaining_pending:
            offer_status_msg = self._t('offer_remains_active_capacity', chat_id, capacity=remaining_capacity, units=units_text)
        else:
            offer_status_msg = self._t('offer_remains_active_pending', chat_id, pending_count=len(remaining_pending))
        
        # Create additional boxes if needed to match exact boxes ordered
        current_boxes = self.db.get_boxes_by_offer(offer.offer_id)
        ordered_boxes_count = len([b for b in current_boxes if b.status == BoxStatus.ORDERED.value or b.box_id in boxes_with_fulfilled_orders])
        
        if boxes_ordered > ordered_boxes_count:
            boxes_to_create = boxes_ordered - ordered_boxes_count
            for _ in range(boxes_to_create):
                from models.entities import Box
                new_box = Box(
                    offer_id=offer.offer_id,
                    max_capacity=box_size,
                    status=BoxStatus.ORDERED.value
                )
                self.db.create_box(new_box)
        
        # Clean up empty boxes (delete boxes with 0 orders and not ORDERED status)
        deleted_boxes = self.box_deletion_service.delete_empty_boxes(offer.offer_id)
        
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
            customer_name = customer.first_name if customer else self._t('unknown', user_id=None)
            summary += "\n" + self._t('order_reduced',
                customer=customer_name,
                old_qty=old_qty,
                new_qty=new_qty
            )
        
        if cancelled_orders:
            # Pre-calculate translation messages for efficiency
            units_singular = self._t('unit', chat_id)
            units_plural = self._t('units', chat_id)
            
            cancelled_details = []
            cancelled_units = 0
            for order in cancelled_orders:
                customer = self.db.get_customer(order.customer_id)
                customer_name = customer.first_name if customer else self._t('unknown', user_id=None)
                units_text = units_singular if order.quantity == 1 else units_plural
                cancelled_details.append(f"{customer_name} ({order.quantity} {units_text})")
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
        
        # Check if there are more offers to process
        all_offers = self.db.list_offers()
        active_offers = [o for o in all_offers if o.status in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value]]
        has_more_pending = False
        for offer in active_offers:
            orders = self.db.get_orders_by_offer(offer.offer_id)
            if any(o.status == 'pending' for o in orders):
                has_more_pending = True
                break
        
        if has_more_pending:
            # Add button to continue with next offer
            keyboard = {
                "inline_keyboard": [
                    [{"text": self._t('process_next_offer'), "callback_data": "process_wholesale"}],
                    [{"text": self._t('back_to_admin'), "callback_data": "admin:main"}]
                ]
            }
        else:
            # No more offers, just show back button
            keyboard = {
                "inline_keyboard": [[
                    {"text": self._t('back_to_admin'), "callback_data": "admin:main"}
                ]]
            }
        
        self._send_message(chat_id, summary, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_process_wholesale_page(self, chat_id: int, page: int) -> Dict[str, Any]:
        """Handle pagination for process_wholesale offer selection"""
        return self._show_wholesale_offers_selection(chat_id, page=page)
    
    def _show_wholesale_offers_selection(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Show offers with pending orders for wholesale ordering"""
        # Get all active and sold out offers
        all_offers = self.db.list_offers()
        active_offers = [o for o in all_offers if o.status in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value]]
        
        # Filter offers that have pending orders
        offers_with_orders = []
        for offer in active_offers:
            orders = self.db.get_orders_by_offer(offer.offer_id)
            pending_orders = [o for o in orders if o.status == 'pending']
            if pending_orders:
                total_units = sum(order.quantity for order in pending_orders)
                offers_with_orders.append((offer, len(pending_orders), total_units))
        
        if not offers_with_orders:
            self._send_message(chat_id, self._t('no_pending_orders'))
            return {'status': 'no_offers'}
        
        # Sort alphabetically by offer name
        offers_with_orders.sort(key=lambda x: x[0].name.lower())
        
        # Paginate
        page_offers, total_pages = PaginationUtils.paginate_list(offers_with_orders, page, page_size=10)
        
        # Create message with offer selection
        message = self._t('select_offer_wholesale')
        if total_pages > 1:
            message += f" (Page {page}/{total_pages})"
        message += "\n\n"
        keyboard_buttons = []
        
        for offer, order_count, total_units in page_offers:
            supplier = self.db.get_supplier_by_name(offer.supplier_name)
            supplier_name = supplier.name if supplier else self._t('unknown', user_id=None)
            
            box_size = offer.wholesale_box_size
            boxes_needed = (total_units + box_size - 1) // box_size
            boxes_text = self._t('box', chat_id) if boxes_needed == 1 else self._t('boxes', chat_id)
            orders_text = self._t('orders_abbrev', chat_id)
            units_text = self._t('units', chat_id)
            
            message += f"🍺 {offer.name} ({offer.offer_id}) • {order_count} {orders_text} • {total_units} {units_text} • {boxes_needed} {boxes_text} • {supplier_name}\n"
            
            keyboard_buttons.append([{
                "text": self._t('select_wholesale_offer', name=offer.name, boxes=boxes_needed),
                "callback_data": f"wholesale_select_{offer.offer_id}"
            }])
        
        # Add pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": "◀️ Prev", "callback_data": f"page_process_wholesale_{page-1}"})
            if page < total_pages:
                nav_buttons.append({"text": "Next ▶️", "callback_data": f"page_process_wholesale_{page+1}"})
            if nav_buttons:
                keyboard_buttons.append(nav_buttons)
        
        keyboard_buttons.append([{"text": self._t('cancel'), "callback_data": "cancel_action"}])
        keyboard = {"inline_keyboard": keyboard_buttons}
        
        self._send_message(chat_id, message, reply_markup=keyboard)
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
        notified_customers = []
        for order in active_orders:
            if self.db.cancel_order_with_audit(order.order_id, self.admin_user_id, "Offer cancelled by admin"):
                cancelled_count += 1
                customer = self.db.get_customer(order.customer_id)
                if customer:
                    notified_customers.append(customer.first_name)
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
        
        if notified_customers:
            summary += "\n" + self._t('notified_customers', customers=", ".join(notified_customers))
        
        self._send_message(chat_id, summary)
        return {'status': 'success'}
    
    def _delete_offer_boxes(self, offer_id: int) -> int:
        """Delete all boxes for an offer and return count"""
        return self.box_deletion_service.delete_offer_boxes(offer_id)
    
    def _notify_customer_cancellation(self, order, offer):
        """Notify customer about order cancellation"""
        customer = self.db.get_customer(order.customer_id)
        if customer:
            message = self._t('order_cancelled_offer_cancelled',
                name=offer.name,
                quantity=order.quantity,
                total=float(order.total_price)
            )
            self._send_message(customer.telegram_user_id, message)

    def handle_delete_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /delete_offer command"""
        if not args:
            self._send_message(chat_id, self._t('usage_delete_offer'))
            return {'status': 'invalid_args'}

        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error
        
        if offer.status not in [OfferStatus.COMPLETED.value, OfferStatus.INACTIVE.value]:
            self._send_message(chat_id, self._t('offer_cannot_delete', status=self._t(f'status_{offer.status}')))
            return {'status': 'invalid_status'}
        
        # Delete all boxes first
        self._delete_offer_boxes(offer.offer_id)
        
        # Delete the offer
        if self.db.delete_offer(offer.offer_id):
            self._send_message(chat_id, self._t('offer_deleted', offer_id=offer.offer_id, name=offer.name))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_delete_offer'))
            return {'status': 'failed'}

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
