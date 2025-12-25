import os
from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Offer, Box, Order, BoxStatus, OfferStatus, OrderStatus

class OfferCommands(BaseHandler):
    def handle_create_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /create_offer command - creates draft offer"""
        if len(args) < 4:
            self._send_message(chat_id, "Usage: /create_offer [supplier_name] [name] [price] [box_size]")
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

            # Check supplier exists and is active
            supplier = self.db.get_supplier_by_name(supplier_name)
            if not supplier:
                self._send_message(chat_id, "❌ Supplier not found")
                return {'status': 'supplier_not_found'}
            
            if supplier.status != "active":
                self._send_message(chat_id, f"❌ Supplier '{supplier_name}' is retired and cannot be used for new offers")
                return {'status': 'supplier_retired'}

            # Create draft offer
            offer = Offer(
                supplier_name=supplier_name,
                name=name,
                price_per_unit=Decimal(str(price)),
                wholesale_box_size=box_size,
                min_quantity_breakeven=max(1, int(box_size * 0.8)),
                status=OfferStatus.DRAFT.value
            )

            if self.db.create_offer(offer):
                message = f"✅ Draft offer created!\n\n"
                message += f"Offer ID: {offer.offer_id}\n"
                message += f"Name: {offer.name}\n"
                message += f"Price: €{offer.price_per_unit:.2f}\n"
                message += f"Box size: {offer.wholesale_box_size}\n"
                message += f"Status: {offer.status}\n\n"
                message += f"Choose next step:"
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "📝 Edit Details", "callback_data": f"edit_offer_details_{offer.offer_id}"}],
                        [{"text": "👁️ Preview Offer", "callback_data": f"preview_offer_{offer.offer_id}"}],
                        [{"text": "🚀 Publish Offer", "callback_data": f"publish_offer_{offer.offer_id}"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
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
            self._send_message(chat_id, "Usage: /fulfill_offer [offer_id]")
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
            message += f"📋 Pending Orders ({len(pending_orders)} orders):\n"
            
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
                    {"text": f"✅ Fulfill with {boxes_needed} boxes", "callback_data": f"confirm_fulfill_{offer_id}_{boxes_needed}"},
                    {"text": "❌ Cancel", "callback_data": "cancel_action"}
                ]]
            }
            
            self._send_message(chat_id, message, reply_markup=keyboard)
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
                    msg = f"❌ Your order has been cancelled due to insufficient availability:\n\n"
                    msg += f"🍺 {offer.name}\n"
                    msg += f"Quantity: {order.quantity} units\n"
                    msg += f"Amount: €{order.total_price:.2f}\n\n"
                    msg += f"We apologize for the inconvenience."
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
            summary = f"✅ Offer {offer_id} fulfilled with {boxes_ordered} boxes:\n\n"
            summary += f"✅ Fulfilled: {len(fulfilled_orders)} orders ({fulfilled_units} units)\n"
            if updated_orders:
                order, old_qty, new_qty = updated_orders[0]
                customer = self.db.get_customer(order.customer_id)
                customer_name = customer.first_name if customer else "Unknown"
                summary += f"⚠️ Reduced: {customer_name}'s order from {old_qty} to {new_qty} units\n"
            if cancelled_orders:
                cancelled_details = []
                cancelled_units = 0
                for order in cancelled_orders:
                    customer = self.db.get_customer(order.customer_id)
                    customer_name = customer.first_name if customer else "Unknown"
                    cancelled_details.append(f"{customer_name} ({order.quantity} units)")
                    cancelled_units += order.quantity
                summary += f"❌ Cancelled: {len(cancelled_orders)} orders ({cancelled_units} units) - {', '.join(cancelled_details)}\n"
            summary += f"\n📦 Total units allocated: {units_allocated}/{units_available}\n"
            summary += f"📊 {offer_status_msg}"
            if deleted_boxes > 0:
                summary += f"\n🗑️ Cleaned up {deleted_boxes} empty boxes"
            
            self._send_message(chat_id, summary)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid format")
            return {'status': 'invalid_format'}
    
    def handle_cancel_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /cancel_offer command"""
        if not args:
            self._send_message(chat_id, "Usage: /cancel_offer [offer_id]")
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
            
            # Get all orders for this offer
            all_orders = self.db.get_orders_by_offer(offer_id)
            active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
            
            if not active_orders:
                # No active orders, just cancel the offer
                self.db.update_offer(offer_id, {'status': OfferStatus.INACTIVE.value})
                self._delete_offer_boxes(offer_id)
                self._send_message(chat_id, f"✅ Offer {offer_id} cancelled (no active orders)")
                return {'status': 'success'}
            
            # Show confirmation with order details
            message = f"⚠️ WARNING: Cancelling offer {offer_id} will:\n\n"
            message += f"🍺 Cancel offer: {offer.name}\n"
            message += f"📦 Delete all boxes\n"
            message += f"❌ Cancel {len(active_orders)} active orders\n"
            message += f"📧 Notify all affected customers\n\n"
            
            # Add inline keyboard for confirmation
            keyboard = {
                "inline_keyboard": [[
                    {"text": "✅ Confirm Cancel", "callback_data": f"confirm_cancel_offer_{offer_id}"},
                    {"text": "❌ Keep Offer", "callback_data": "cancel_action"}
                ]]
            }
            
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'confirmation_required'}
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}
    
    def handle_confirm_cancel_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_cancel_offer command"""
        if not args:
            self._send_message(chat_id, "Usage: /confirm_cancel_offer <offer_id>")
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            # Get all pending orders
            all_orders = self.db.get_orders_by_offer(offer_id)
            active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
            
            # Cancel all active orders and notify customers
            cancelled_count = 0
            for order in active_orders:
                if self.db.update_order(order.order_id, {'status': OrderStatus.CANCELLED.value}):
                    cancelled_count += 1
                    self._notify_customer_cancellation(order, offer)
            
            # Delete all boxes
            deleted_boxes = self._delete_offer_boxes(offer_id)
            
            # Delete notification messages for cancelled offer
            self._cleanup_offer_notifications(offer_id)
            
            # Cancel the offer
            self.db.update_offer(offer_id, {'status': OfferStatus.INACTIVE.value})
            
            # Send summary
            summary = f"✅ Offer {offer_id} cancelled:\n\n"
            summary += f"❌ Cancelled {cancelled_count} orders\n"
            summary += f"🗑️ Deleted {deleted_boxes} boxes\n"
            summary += f"📧 Notified {cancelled_count} customers"
            
            self._send_message(chat_id, summary)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}
    
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
            message = f"❌ Your order has been cancelled due to offer cancellation:\n\n"
            message += f"🍺 {offer.name}\n"
            message += f"Quantity: {order.quantity} units\n\n"
            message += f"We apologize for the inconvenience."
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

    def handle_add_box(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_box command"""
        if not args:
            self._send_message(chat_id, "Usage: /add_box [offer_id]")
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            # Create new box
            box = Box(
                offer_id=offer_id,
                max_capacity=offer.wholesale_box_size,
                min_breakeven=offer.min_quantity_breakeven
            )
            
            if self.db.create_box(box):
                # Update offer status from sold_out to active if needed
                if offer.status == OfferStatus.SOLD_OUT.value:
                    self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value})
                    status_msg = " (offer status updated to active)"
                else:
                    status_msg = ""
                
                self._send_message(chat_id, f"✅ Added new box for offer {offer_id}{status_msg}")
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to create box")
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}

    def handle_box_status(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Handle /box_status command with pagination"""
        offers = self.db.list_offers()
        active_offers = [offer for offer in offers if offer.status == OfferStatus.ACTIVE.value]
        
        if not active_offers:
            self._send_message(chat_id, "🍺 No active offers available")
            return {'status': 'no_offers'}
        
        # Build list of offer-box combinations for pagination
        offer_boxes = []
        for offer in active_offers:
            boxes = self.db.get_boxes_by_offer(offer.offer_id)
            boxes.sort(key=lambda x: x.box_id)
            for box in boxes:
                offer_boxes.append((offer, box))
        
        # Paginate results
        page_items, total_pages = self._paginate_list(offer_boxes, page, 10)
        
        message = f"📦 Box Status (Page {page}/{total_pages}):\n\n"
        for offer, box in page_items:
            status_emoji = {
                BoxStatus.OPEN.value: "🟢",
                BoxStatus.MINIMUM_REACHED.value: "🟡",
                BoxStatus.FULL.value: "🔴",
                BoxStatus.ORDERED.value: "📦",
                BoxStatus.DELIVERED.value: "✅"
            }.get(box.status, "❓")
            
            message += f"🍺 {offer.name} €{offer.price_per_unit:.2f}\n   {status_emoji} Box {box.box_id[:8]}: {box.current_quantity}/{box.max_capacity} ({box.status})\n\n"
        
        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_pagination_keyboard(page, total_pages, "boxes")
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_edit_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /edit_offer command"""
        if not args:
            self._send_message(chat_id, "Usage: /edit_offer [offer_id]")
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            # Show current offer details with edit options
            message = f"📝 Edit Offer {offer_id}:\n\n"
            message += f"Name: {offer.name}\n"
            message += f"Price: €{offer.price_per_unit:.2f}\n"
            message += f"Box Size: {offer.wholesale_box_size}\n"
            message += f"Status: {offer.status}\n"
            message += f"Supplier: {offer.supplier_name}\n\n"
            message += "Select what to edit:"
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📝 Edit Name", "callback_data": f"edit_offer_name_{offer_id}"}],
                    [{"text": "💰 Edit Price", "callback_data": f"edit_offer_price_{offer_id}"}],
                    [{"text": "📦 Edit Description", "callback_data": f"edit_offer_description_{offer_id}"}],
                    [{"text": "❌ Cancel", "callback_data": "cancel_action"}]
                ]
            }
            
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}

    def _announce_offer(self, offer):
        """Announce new offer to default group and subscribers using rich format"""
        default_group_id = os.environ.get('DEFAULT_GROUP_ID')
        
        # Send rich offer message to default group
        if default_group_id:
            self._send_rich_offer_message(int(default_group_id), offer, force_group=True)
        
        # Send to subscribers in batches
        self._notify_subscribers_rich(offer)
    
    def _send_rich_offer_message(self, chat_id: int, offer, preview: bool = False, force_group: bool = False):
        """Send rich offer message with description and images"""
        # Build message text
        if preview:
            message = f"👁️ PREVIEW - How offer will look:\n\n"
        else:
            message = f"🍺 New offer available!\n\n"
        
        message += f"[{offer.offer_id}] {offer.name}\n"
        message += f"Price: €{offer.price_per_unit:.2f} per unit\n"
        message += f"Box size: {offer.wholesale_box_size} units\n"
        message += f"Supplier: {offer.supplier_name}\n"
        
        if offer.description:
            message += f"\n{offer.description}\n"
        
        if not preview:
            message += f"\nOrder with: /order {offer.offer_id} [quantity]"
        
        # Create inline keyboard with order buttons (only for non-preview)
        reply_markup = None
        if not preview:
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🍺 Order 1", "callback_data": f"order_{offer.offer_id}_1"},
                        {"text": "🍺🍺 Order 2", "callback_data": f"order_{offer.offer_id}_2"}
                    ]
                ]
            }
        
        # Send images first if available
        if offer.images:
            for image_url in offer.images:
                try:
                    self._send_photo(chat_id, image_url, force_group=force_group)
                except Exception as e:
                    print(f"Failed to send image {image_url}: {e}")
        
        # Send text message
        result = self._send_message(chat_id, message, reply_markup=reply_markup, force_group=force_group)
        return result
    
    def _notify_subscribers_rich(self, offer):
        """Send rich offer notification to all subscribers in batches and store message IDs"""
        import time
        from models.entities import AuthorizationStatus, NotificationMessage
        
        # Get all approved customers
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        subscribers = [c for c in customers if getattr(c, 'subscribed_to_offers', False)]
        
        # Send in batches to avoid rate limits (30 messages per second max)
        batch_size = 25
        for i in range(0, len(subscribers), batch_size):
            batch = subscribers[i:i + batch_size]
            
            for customer in batch:
                try:
                    # Send images first
                    if offer.images:
                        for image_url in offer.images:
                            try:
                                self._send_photo(customer.telegram_user_id, image_url)
                            except Exception as e:
                                print(f"Failed to send image to subscriber {customer.customer_id}: {e}")
                    
                    # Send text message with order buttons
                    message = f"🍺 New offer available!\n\n"
                    message += f"[{offer.offer_id}] {offer.name}\n"
                    message += f"Price: €{offer.price_per_unit:.2f} per unit\n"
                    message += f"Box size: {offer.wholesale_box_size} units\n"
                    message += f"Supplier: {offer.supplier_name}\n"
                    
                    if offer.description:
                        message += f"\n{offer.description}\n"
                    
                    message += f"\nOrder with: /order {offer.offer_id} [quantity]"
                    
                    reply_markup = {
                        "inline_keyboard": [
                            [
                                {"text": "🍺 Order 1", "callback_data": f"order_{offer.offer_id}_1"},
                                {"text": "🍺🍺 Order 2", "callback_data": f"order_{offer.offer_id}_2"}
                            ]
                        ]
                    }
                    
                    result = self._send_message(customer.telegram_user_id, message, reply_markup=reply_markup)
                    if result.get('success') and result.get('message_id'):
                        # Store notification message for later deletion
                        notification = NotificationMessage(
                            offer_id=offer.offer_id,
                            chat_id=customer.telegram_user_id,
                            message_id=result['message_id']
                        )
                        self.db.create_notification_message(notification)
                except Exception as e:
                    # Log error but continue with other subscribers
                    import logging
                    logging.error(f"Failed to notify subscriber {customer.customer_id}: {e}")
            
            # Rate limiting: wait 1 second between batches
            if i + batch_size < len(subscribers):
                time.sleep(1)
    
    def handle_update_offer_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_offer_name command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /update_offer_name [offer_id] [new_name]")
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            new_name = ' '.join(args[1:]).strip()
            
            if len(new_name) > 100:
                self._send_message(chat_id, "❌ Product name too long (max 100 characters)")
                return {'status': 'invalid_name'}
            
            if '<' in new_name or '>' in new_name:
                self._send_message(chat_id, "❌ Product name cannot contain < or > characters")
                return {'status': 'invalid_name'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            if self.db.update_offer(offer_id, {'name': new_name}):
                self._send_message(chat_id, f"✅ Offer name updated: '{offer.name}' → '{new_name}'")
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to update offer name")
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}
    
    def handle_update_offer_price(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_offer_price command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /update_offer_price [offer_id] [new_price]")
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            new_price = float(args[1])
            
            if new_price <= 0:
                self._send_message(chat_id, "❌ Price must be positive")
                return {'status': 'invalid_price'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            from decimal import Decimal
            if self.db.update_offer(offer_id, {'price_per_unit': Decimal(str(new_price))}):
                self._send_message(chat_id, f"✅ Offer price updated: €{offer.price_per_unit:.2f} → €{new_price:.2f}")
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to update offer price")
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID or price format")
            return {'status': 'invalid_format'}
    
    def handle_update_offer_description(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_offer_description command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /update_offer_description [offer_id] [new_description]")
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            new_description = ' '.join(args[1:]).strip()
            
            if len(new_description) > 500:
                self._send_message(chat_id, "❌ Description too long (max 500 characters)")
                return {'status': 'invalid_description'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            if self.db.update_offer(offer_id, {'description': new_description}):
                old_desc = offer.description or "Not set"
                
                # Send confirmation with button to continue editing
                message = f"✅ Offer description updated: '{old_desc}' → '{new_description}'\n\n"
                message += "Continue editing?"
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "📝 Continue Editing", "callback_data": f"edit_offer_details_{offer_id}"}],
                        [{"text": "👁️ Preview Offer", "callback_data": f"preview_offer_{offer_id}"}],
                        [{"text": "✅ Done", "callback_data": "cancel_action"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to update offer description")
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}
    
    def handle_edit_offer_details(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /edit_offer_details command"""
        if not args:
            self._send_message(chat_id, "Usage: /edit_offer_details [offer_id]")
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            # Show current offer details with edit options
            message = f"📝 Edit Offer Details {offer_id}:\n\n"
            message += f"Name: {offer.name}\n"
            message += f"Price: €{offer.price_per_unit:.2f}\n"
            message += f"Box Size: {offer.wholesale_box_size}\n"
            message += f"Status: {offer.status}\n"
            message += f"Supplier: {offer.supplier_name}\n"
            message += f"Description: {offer.description or 'Not set'}\n"
            message += f"Images: {len(offer.images)} uploaded\n\n"
            message += "Select what to edit:"
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📝 Edit Description", "callback_data": f"edit_offer_description_{offer_id}"}],
                    [{"text": "🖼️ Upload Image", "callback_data": f"upload_offer_image_{offer_id}"}],
                    [{"text": "🗑️ Clear Images", "callback_data": f"clear_offer_images_{offer_id}"}] if offer.images else [],
                    [{"text": "👁️ Preview Offer", "callback_data": f"preview_offer_{offer_id}"}],
                    [{"text": "❌ Cancel", "callback_data": "cancel_action"}]
                ]
            }
            
            # Remove empty rows
            keyboard["inline_keyboard"] = [row for row in keyboard["inline_keyboard"] if row]
            
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}
    
    def handle_publish_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /publish_offer command"""
        if not args:
            self._send_message(chat_id, "Usage: /publish_offer [offer_id]")
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            if offer.status != OfferStatus.DRAFT.value:
                self._send_message(chat_id, f"❌ Offer is not in draft status (current: {offer.status})")
                return {'status': 'offer_not_draft'}
            
            # Update offer status to active
            if self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value}):
                # Create initial box
                box = Box(
                    offer_id=offer_id,
                    max_capacity=offer.wholesale_box_size,
                    min_breakeven=offer.min_quantity_breakeven
                )
                self.db.create_box(box)

                # Auto-order 1 unit for admin
                admin_customer = self.db.get_customer_by_telegram_id(self.admin_user_id)
                if admin_customer:
                    admin_order = Order(
                        customer_id=admin_customer.customer_id,
                        box_id=box.box_id,
                        offer_id=offer_id,
                        quantity=1,
                        unit_price=offer.price_per_unit,
                        total_price=offer.price_per_unit
                    )
                    self.db.create_order(admin_order)
                    
                    # Update box quantity
                    updates = {'current_quantity': 1}
                    if 1 >= box.max_capacity:
                        updates['status'] = BoxStatus.FULL.value
                    elif 1 >= box.min_breakeven:
                        updates['status'] = BoxStatus.MINIMUM_REACHED.value
                    
                    self.db.update_box(box.box_id, updates)

                # Update offer object for announcement
                offer.status = OfferStatus.ACTIVE.value
                
                # Announce offer to default group and subscribers
                self._announce_offer(offer)
                
                self._send_message(chat_id, f"✅ Offer {offer_id} published and announced!")
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to publish offer")
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}
    
    def handle_preview_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /preview_offer command"""
        if not args:
            # Show list of draft offers as buttons
            offers = self.db.list_offers()
            draft_offers = [o for o in offers if o.status == OfferStatus.DRAFT.value]
            
            if not draft_offers:
                self._send_message(chat_id, "❌ No draft offers available to preview")
                return {'status': 'no_draft_offers'}
            
            message = "📝 Select draft offer to preview:\n\n"
            keyboard = {"inline_keyboard": []}
            
            for offer in draft_offers:
                button_text = f"[{offer.offer_id}] {offer.name} - €{offer.price_per_unit:.2f}"
                keyboard["inline_keyboard"].append([{
                    "text": button_text,
                    "callback_data": f"preview_offer_{offer.offer_id}"
                }])
            
            keyboard["inline_keyboard"].append([{"text": "❌ Cancel", "callback_data": "cancel_action"}])
            
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'success'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            # Show rich offer preview
            self._send_rich_offer_message(chat_id, offer, preview=True)
            
            # Add action buttons after preview
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📝 Edit Details", "callback_data": f"edit_offer_details_{offer_id}"}],
                    [{"text": "🚀 Publish Offer", "callback_data": f"publish_offer_{offer_id}"}] if offer.status == OfferStatus.DRAFT.value else [],
                    [{"text": "❌ Cancel", "callback_data": "cancel_action"}]
                ]
            }
            
            # Remove empty rows
            keyboard["inline_keyboard"] = [row for row in keyboard["inline_keyboard"] if row]
            
            self._send_message(chat_id, "Choose an action:", reply_markup=keyboard)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}