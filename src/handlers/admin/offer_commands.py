import os
import logging
from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Offer, Box, Order, BoxStatus, OfferStatus, OrderStatus

logger = logging.getLogger()

class OfferCommands(BaseHandler):
    def handle_create_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /create_offer command - creates draft offer"""
        if len(args) < 4:
            self._send_message(chat_id, self._t('usage_create_offer'))
            return {'status': 'invalid_args'}

        try:
            supplier_name = args[0]
            price = float(args[-2])
            box_size = int(args[-1])
            
            # Validate and sanitize name
            name = ' '.join(args[1:-2]).strip()
            if len(name) > 100:
                self._send_message(chat_id, self._t('product_name_too_long'))
                return {'status': 'invalid_name'}
            
            if '<' in name or '>' in name:
                self._send_message(chat_id, self._t('product_name_invalid_chars'))
                return {'status': 'invalid_name'}

            # Validate box size
            valid_sizes = [1, 2, 6, 8, 10, 12, 15, 16, 18, 20, 24]
            if box_size not in valid_sizes:
                self._send_message(chat_id, self._t('invalid_box_size', sizes=valid_sizes))
                return {'status': 'invalid_box_size'}

            # Check supplier exists and is active
            supplier = self.db.get_supplier_by_name(supplier_name)
            if not supplier:
                self._send_message(chat_id, self._t('supplier_not_found'))
                return {'status': 'supplier_not_found'}
            
            if supplier.status != "active":
                self._send_message(chat_id, self._t('supplier_retired_cannot_use', name=supplier_name))
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
                message = self._t('draft_offer_created', 
                    offer_id=offer.offer_id,
                    name=offer.name,
                    price=offer.price_per_unit,
                    box_size=offer.wholesale_box_size,
                    status=offer.status
                )
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('edit_details'), "callback_data": f"offer_details_{offer.offer_id}_edit"}],
                        [{"text": self._t('view_details'), "callback_data": f"offer_details_{offer.offer_id}"}],
                        [{"text": self._t('publish_offer'), "callback_data": f"publish_offer_{offer.offer_id}"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_create_offer'))
                return {'status': 'error'}

        except (ValueError, IndexError) as e:
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'invalid_format'}

    def handle_fulfill_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /fulfill_offer command"""
        if not args:
            self._send_message(chat_id, self._t('usage_fulfill_offer'))
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, self._t('offer_not_active'))
                return {'status': 'offer_not_active'}
            
            # Get all pending orders for this offer, sorted by date ascending
            all_orders = self.db.get_orders_by_offer(offer_id)
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
                offer_id=offer_id,
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
                    {"text": self._t('fulfill_with_boxes', boxes=boxes_needed), "callback_data": f"confirm_fulfill_{offer_id}_{boxes_needed}"},
                    {"text": self._t('cancel'), "callback_data": "cancel_action"}
                ]]
            }
            
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
    
    def handle_confirm_fulfill(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_fulfill command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_confirm_fulfill'))
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            boxes_ordered = int(args[1])
            
            if boxes_ordered <= 0:
                self._send_message(chat_id, self._t('boxes_must_positive'))
                return {'status': 'invalid_quantity'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
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
                offer_id=offer_id,
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
            
        except ValueError:
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'invalid_format'}
    
    def handle_cancel_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /cancel_offer command"""
        if not args:
            self._send_message(chat_id, self._t('usage_cancel_offer'))
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, self._t('offer_not_active'))
                return {'status': 'offer_not_active'}
            
            # Get all orders for this offer
            all_orders = self.db.get_orders_by_offer(offer_id)
            active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
            
            if not active_orders:
                # No active orders, just cancel the offer
                self.db.update_offer(offer_id, {'status': OfferStatus.INACTIVE.value})
                self._delete_offer_boxes(offer_id)
                self._send_message(chat_id, self._t('offer_cancelled_no_orders', offer_id=offer_id))
                return {'status': 'success'}
            
            # Show confirmation with order details
            message = self._t('cancel_offer_warning',
                offer_id=offer_id,
                name=offer.name,
                order_count=len(active_orders)
            )
            
            # Add inline keyboard for confirmation
            keyboard = {
                "inline_keyboard": [[
                    {"text": self._t('confirm_cancel'), "callback_data": f"confirm_cancel_offer_{offer_id}"},
                    {"text": self._t('keep_offer'), "callback_data": "cancel_action"}
                ]]
            }
            
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'confirmation_required'}
            
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
    
    def handle_confirm_cancel_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_cancel_offer command"""
        if not args:
            self._send_message(chat_id, self._t('usage_confirm_cancel_offer'))
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
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
            summary = self._t('offer_cancelled_summary',
                offer_id=offer_id,
                cancelled_count=cancelled_count,
                deleted_boxes=deleted_boxes,
                notified_count=cancelled_count
            )
            
            self._send_message(chat_id, summary)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
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

    def handle_add_box(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_box command"""
        if not args:
            self._send_message(chat_id, self._t('usage_add_box'))
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
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
                    self._send_message(chat_id, self._t('box_added_offer_active', offer_id=offer_id))
                else:
                    self._send_message(chat_id, self._t('box_added', offer_id=offer_id))
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_create_box'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}

    def handle_box_status(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Handle /box_status command with pagination"""
        offers = self.db.list_offers()
        active_offers = [offer for offer in offers if offer.status == OfferStatus.ACTIVE.value]
        
        if not active_offers:
            self._send_message(chat_id, self._t('no_offers'))
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
        
        message = self._t('box_status_title', page=page, total_pages=total_pages)
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
            message = self._t('preview_how_offer_looks')
        else:
            message = self._t('new_offer_available',
                offer_id=offer.offer_id,
                name=offer.name,
                price=offer.price_per_unit,
                box_size=offer.wholesale_box_size,
                supplier_name=offer.supplier_name
            )
        
        if offer.description:
            message += f"\n{offer.description}\n"
        
        if not preview:
            message += "\n" + self._t('order_with_command', offer_id=offer.offer_id)
        
        # Create inline keyboard with order buttons (only for non-preview)
        reply_markup = None
        if not preview:
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": self._t('order_1'), "callback_data": f"order_{offer.offer_id}_1"},
                        {"text": self._t('order_2'), "callback_data": f"order_{offer.offer_id}_2"}
                    ]
                ]
            }
        
        # Send images first if available
        if offer.images:
            for image_url in offer.images:
                try:
                    # Generate presigned URL for S3 images
                    if 's3.amazonaws.com' in image_url:
                        presigned_url = self.db.get_presigned_url(image_url)
                        if presigned_url:
                            image_url = presigned_url
                    
                    self._send_photo(chat_id, image_url, force_group=force_group)
                except Exception as e:
                    print(f"Failed to send image {image_url}: {e}")
        
        # Send text message
        result = self._send_message(chat_id, message, reply_markup=reply_markup, force_group=force_group, parse_mode="HTML")
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
                    message = self._t('new_offer_available',
                        offer_id=offer.offer_id,
                        name=offer.name,
                        price=offer.price_per_unit,
                        box_size=offer.wholesale_box_size,
                        supplier_name=offer.supplier_name
                    )
                    
                    if offer.description:
                        message += f"\n{offer.description}\n"
                    
                    message += "\n" + self._t('order_with_command', offer_id=offer.offer_id)
                    
                    reply_markup = {
                        "inline_keyboard": [
                            [
                                {"text": self._t('order_1'), "callback_data": f"order_{offer.offer_id}_1"},
                                {"text": self._t('order_2'), "callback_data": f"order_{offer.offer_id}_2"}
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
            self._send_message(chat_id, self._t('usage_update_offer_name'))
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            new_name = ' '.join(args[1:]).strip()
            
            if len(new_name) > 100:
                self._send_message(chat_id, self._t('product_name_too_long'))
                return {'status': 'invalid_name'}
            
            if '<' in new_name or '>' in new_name:
                self._send_message(chat_id, self._t('product_name_invalid_chars'))
                return {'status': 'invalid_name'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if self.db.update_offer(offer_id, {'name': new_name}):
                # Send confirmation and return to edit menu
                message = self._t('offer_name_updated',
                    old_name=offer.name,
                    new_name=new_name
                )
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('continue_editing'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('view_details'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('done_editing'), "callback_data": "done_editing"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_update_offer_name'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
    
    def handle_update_offer_price(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_offer_price command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_update_offer_price'))
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            new_price = float(args[1])
            
            if new_price <= 0:
                self._send_message(chat_id, self._t('price_must_positive'))
                return {'status': 'invalid_price'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            from decimal import Decimal
            if self.db.update_offer(offer_id, {'price_per_unit': Decimal(str(new_price))}):
                # Send confirmation and return to edit menu
                message = self._t('offer_price_updated',
                    old_price=offer.price_per_unit,
                    new_price=new_price
                )
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('continue_editing'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('view_details'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('done_editing'), "callback_data": "done_editing"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_update_offer_price'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_price_format'))
            return {'status': 'invalid_format'}
    
    def handle_update_offer_description(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_offer_description command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_update_offer_description'))
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            new_description = ' '.join(args[1:]).strip()
            
            if len(new_description) > 500:
                self._send_message(chat_id, self._t('description_too_long'))
                return {'status': 'invalid_description'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if self.db.update_offer(offer_id, {'description': new_description}):
                logger.info(f"Stored description in DB: {new_description}")
                old_desc = offer.description or self._t('not_set')
                logger.info(f"Retrieved old description from DB: {old_desc}")
                
                # Send confirmation with button to continue editing
                message = self._t('offer_description_updated',
                    old_desc=old_desc,
                    new_desc=new_description
                )
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('continue_editing'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('view_details'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('done_editing'), "callback_data": "done_editing"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_update_offer_description'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
    

    def handle_publish_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /publish_offer command"""
        if not args:
            self._send_message(chat_id, self._t('usage_publish_offer'))
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if offer.status != OfferStatus.DRAFT.value:
                self._send_message(chat_id, self._t('offer_not_draft', status=offer.status))
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
                
                self._send_message(chat_id, self._t('offer_published_announced', offer_id=offer_id))
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_publish_offer'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
    
