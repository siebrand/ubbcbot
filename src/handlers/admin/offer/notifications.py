import time
from models.entities import AuthorizationStatus, NotificationMessage
from .base import OfferBaseHandler

class NotificationHandler(OfferBaseHandler):
    """Handler for offer notifications and announcements"""
    
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
