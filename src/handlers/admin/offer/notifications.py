import time
import logging
from models.entities import AuthorizationStatus, NotificationMessage
from .base import OfferBaseHandler

logger = logging.getLogger()

class NotificationHandler(OfferBaseHandler):
    """Handler for offer notifications and announcements"""
    
    def _send_rich_offer_message(self, chat_id: int, offer, preview: bool = False, force_group: bool = False):
        """Send rich offer message using offer_details formatting"""
        box_size = offer.wholesale_box_size
        if box_size == 1:
            logger.info(f"DEBUG: Box size 1 - Sending rich offer message to chat {chat_id}, preview: {preview}, force_group: {force_group}")
        
        # Send announcement header for non-preview
        if not preview:
            header_message = self._t('new_offer_available')
            header_result = self._send_message(chat_id, header_message, force_group=force_group)
            if box_size == 1:
                logger.info(f"DEBUG: Box size 1 - Header message result: {header_result}")
        
        # Send the rich offer details directly with proper force_group handling
        details_result = self._send_rich_offer_details_with_group_support(chat_id, offer, force_group=force_group)
        if box_size == 1:
            logger.info(f"DEBUG: Box size 1 - Details message completed")
        
        # Add order buttons for non-preview announcements
        if not preview:
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": self._t('order_1'), "callback_data": f"order_{offer.offer_id}_1"},
                        {"text": self._t('order_2'), "callback_data": f"order_{offer.offer_id}_2"}
                    ]
                ]
            }
            
            # Send order buttons message
            button_message = self._t('order_with_command', offer_id=offer.offer_id)
            button_result = self._send_message(chat_id, button_message, reply_markup=reply_markup, force_group=force_group)
            if box_size == 1:
                logger.info(f"DEBUG: Box size 1 - Button message result: {button_result}")

    def _send_rich_offer_details_with_group_support(self, chat_id: int, offer, force_group: bool = False):
        """Send rich offer details with group support"""
        # Send images if available
        if offer.images:
            if len(offer.images) == 1:
                try:
                    image_url = offer.images[0]
                    if 's3.amazonaws.com' in image_url:
                        presigned_url = self.db.get_presigned_url(image_url)
                        if presigned_url:
                            image_url = presigned_url
                    self._send_photo(chat_id, image_url, force_group=force_group)
                except Exception as e:
                    print(f"Failed to send image {image_url}: {e}")
            else:
                media_group = []
                for image_url in offer.images[:10]:
                    try:
                        if 's3.amazonaws.com' in image_url:
                            presigned_url = self.db.get_presigned_url(image_url)
                            if presigned_url:
                                image_url = presigned_url
                        media_group.append({"type": "photo", "media": image_url})
                    except Exception as e:
                        print(f"Failed to prepare image {image_url}: {e}")
                
                if media_group:
                    self._send_media_group(chat_id, media_group, force_group=force_group)
        
        # Build message
        total_ordered, total_capacity = self._get_offer_capacity_info(offer.offer_id)
        available = total_capacity - total_ordered
        
        message = f"<b>{offer.offer_id}. {offer.name} €{offer.price_per_unit:.2f}  ({available}/{total_capacity})</b>\n\n"
        message += f"{offer.description}\n"
        
        self._send_message(chat_id, message, parse_mode="HTML", force_group=force_group)
    
    def _get_offer_capacity_info(self, offer_id: int):
        """Get order and capacity information for an offer"""
        boxes = self.db.get_boxes_by_offer(offer_id)
        total_capacity = sum(box.max_capacity for box in boxes)
        all_orders = self.db.get_orders_by_offer(offer_id)
        active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
        total_ordered = sum(order.quantity for order in active_orders)
        return total_ordered, total_capacity

    def _notify_subscribers_rich(self, offer):
        """Send rich offer notification to all subscribers in batches using offer_details formatting"""
        # Get all approved customers
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        subscribers = [c for c in customers if getattr(c, 'subscribed_to_offers', False)]
        
        box_size = offer.wholesale_box_size
        if box_size == 1:
            logger.info(f"DEBUG: Box size 1 - Notifying {len(subscribers)} subscribers for offer {offer.offer_id}")
        
        # Send in batches to avoid rate limits (30 messages per second max)
        batch_size = 25
        for i in range(0, len(subscribers), batch_size):
            batch = subscribers[i:i + batch_size]
            
            if box_size == 1:
                logger.info(f"DEBUG: Box size 1 - Processing batch {i//batch_size + 1}, {len(batch)} subscribers")
            
            for customer in batch:
                try:
                    # Use the same rich offer message method for consistency
                    self._send_rich_offer_message(customer.telegram_user_id, offer, preview=False, force_group=False)
                    if box_size == 1:
                        logger.info(f"DEBUG: Box size 1 - Notified subscriber {customer.customer_id}")
                except Exception as e:
                    # Log error but continue with other subscribers
                    import logging
                    logging.error(f"Failed to notify subscriber {customer.customer_id}: {e}")
                    if box_size == 1:
                        logger.error(f"DEBUG: Box size 1 - Failed to notify subscriber {customer.customer_id}: {e}")
            
            # Rate limiting: wait 1 second between batches
            if i + batch_size < len(subscribers):
                time.sleep(1)
