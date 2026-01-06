import os
import time
import logging
from models.entities import AuthorizationStatus, NotificationMessage
from .base import OfferBaseHandler

logger = logging.getLogger()

class NotificationHandler(OfferBaseHandler):
    """Handler for offer notifications and announcements"""
    
    def _send_rich_offer_message(self, chat_id: int, offer, preview: bool = False, force_group: bool = False, include_buttons: bool = True):
        """Send rich offer message using offer_details formatting with optimizations"""

        if not preview:
            self._send_message(chat_id, self._t('new_offer_available'), force_group=force_group)
        
        # Pre-generate presigned URLs to avoid repeated S3 calls
        presigned_images = []
        if offer.images:
            for image_url in offer.images[:10]:
                try:
                    if 's3.amazonaws.com' in image_url:
                        presigned_url = self.db.get_presigned_url(image_url)
                        presigned_images.append(presigned_url if presigned_url else image_url)
                    else:
                        presigned_images.append(image_url)
                except Exception as e:
                    logger.error(f"Failed to get presigned URL for {image_url}: {e}")
        
        # Send images using pre-generated URLs
        if presigned_images:
            if len(presigned_images) == 1:
                self._send_photo(chat_id, presigned_images[0], force_group=force_group)
            else:
                media_group = [{"type": "photo", "media": url} for url in presigned_images]
                self._send_media_group(chat_id, media_group, force_group=force_group)

        # Get bot username for linking
        bot_username = self._get_bot_username()
        
        # Send offer details message
        message = f"<b><a href='https://t.me/{bot_username}?start=offer_details_{offer.offer_id}'>{offer.offer_id}</a>. {offer.name} €{offer.price_per_unit:.2f}</b>\n\n"
        message += f"{offer.description}\n"
        
        # Add order buttons for non-preview announcements
        reply_markup = None
        if not preview and include_buttons:
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": self._t('order_1'), "callback_data": f"order_{offer.offer_id}_1"},
                        {"text": self._t('order_2'), "callback_data": f"order_{offer.offer_id}_2"}
                    ]
                ]
            }
        
        self._send_message(chat_id, message, parse_mode="HTML", reply_markup=reply_markup, force_group=force_group)


    def _get_offer_capacity_info(self, offer_id: int):
        """Get order and capacity information for an offer"""
        boxes = self.db.get_boxes_by_offer(offer_id)
        total_capacity = sum(box.max_capacity for box in boxes)
        all_orders = self.db.get_orders_by_offer(offer_id)
        active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
        total_ordered = sum(order.quantity for order in active_orders)
        return total_ordered, total_capacity

    def _notify_subscribers_rich(self, offer):
        """Send rich offer notification to all subscribers using async approach"""
        # Get all approved customers
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        subscribers = [c for c in customers if getattr(c, 'subscribed_to_offers', False)]
        
        if not subscribers:
            return
        
        # For small subscriber counts, send synchronously with optimizations
        if len(subscribers) <= 10:
            self._send_notifications_sync_optimized(subscribers, offer)
        else:
            # For larger counts, use async Lambda invocation
            self._send_notifications_async(subscribers, offer)
    
    def _send_notifications_sync_optimized(self, subscribers, offer):
        """Send notifications synchronously with optimizations for small groups"""
        # Pre-generate presigned URLs for images to avoid repeated S3 calls
        presigned_images = []
        if offer.images:
            for image_url in offer.images[:10]:
                try:
                    if 's3.amazonaws.com' in image_url:
                        presigned_url = self.db.get_presigned_url(image_url)
                        presigned_images.append(presigned_url if presigned_url else image_url)
                    else:
                        presigned_images.append(image_url)
                except Exception as e:
                    logger.error(f"Failed to get presigned URL for {image_url}: {e}")
        
        # Send notifications with minimal delay
        for customer in subscribers:
            try:
                self._send_optimized_rich_message(customer.telegram_user_id, offer, presigned_images)
            except Exception as e:
                logger.error(f"Failed to notify subscriber {customer.customer_id}: {e}")
    
    def _send_notifications_async(self, subscribers, offer):
        """Send notifications asynchronously using Lambda invocation"""
        import json
        import boto3
        from decimal import Decimal
        
        try:
            lambda_client = boto3.client('lambda')
            function_name = os.environ.get('NOTIFICATION_LAMBDA_NAME', f"ubbc-bot-{os.environ.get('ENVIRONMENT', 'test')}-notification-sender")
            
            # Prepare payload with Decimal conversion
            payload = {
                'offer_id': offer.offer_id,
                'subscriber_ids': [c.customer_id for c in subscribers],
                'environment': os.environ.get('ENVIRONMENT', 'test')
            }
            
            # Custom JSON encoder to handle Decimal
            class DecimalEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    return super().default(obj)
            
            # Invoke async Lambda
            lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='Event',  # Async invocation
                Payload=json.dumps(payload, cls=DecimalEncoder)
            )
            
            logger.info(f"Async notification Lambda invoked for {len(subscribers)} subscribers")
            
        except Exception as e:
            logger.error(f"Failed to invoke async notification Lambda: {e}")
            # Fallback to sync with reduced batch size
            self._send_notifications_sync_fallback(subscribers, offer)
    
    def _send_notifications_sync_fallback(self, subscribers, offer):
        """Fallback sync notification with aggressive batching"""
        # Send only to first 15 subscribers to avoid timeout
        limited_subscribers = subscribers[:15]
        
        for customer in limited_subscribers:
            try:
                # Send simplified notification without images to save time
                self._send_simple_offer_notification(customer.telegram_user_id, offer)
            except Exception as e:
                logger.error(f"Failed to notify subscriber {customer.customer_id}: {e}")
        
        # Log remaining subscribers for manual follow-up
        if len(subscribers) > 15:
            remaining_count = len(subscribers) - 15
            logger.warning(f"Notification timeout risk: {remaining_count} subscribers not notified for offer {offer.offer_id}")
    
    def _send_optimized_rich_message(self, chat_id: int, offer, presigned_images):
        """Send optimized rich offer message with pre-generated URLs"""
        # Send images using pre-generated URLs
        if presigned_images:
            if len(presigned_images) == 1:
                self._send_photo(chat_id, presigned_images[0])
            else:
                media_group = [{"type": "photo", "media": url} for url in presigned_images]
                self._send_media_group(chat_id, media_group)
        
        # Send offer details
        total_ordered, total_capacity = self._get_offer_capacity_info(offer.offer_id)
        available = total_capacity - total_ordered
        
        # Get bot username for linking
        bot_username = self._get_bot_username()
        
        # Combine header and offer details in single message
        message = self._t('new_offer_available') + "\n\n"
        message += f"<b><a href='https://t.me/{bot_username}?start=offer_details_{offer.offer_id}'>{offer.offer_id}</a>. {offer.name} €{offer.price_per_unit:.2f}  ({available}/{total_capacity})</b>\n\n"
        message += f"{offer.description}\n"
        
        # Add order buttons
        reply_markup = {
            "inline_keyboard": [[
                {"text": self._t('order_1'), "callback_data": f"order_{offer.offer_id}_1"},
                {"text": self._t('order_2'), "callback_data": f"order_{offer.offer_id}_2"}
            ]]
        }
        
        self._send_message(chat_id, message, parse_mode="HTML", reply_markup=reply_markup)
    
    def _send_simple_offer_notification(self, chat_id: int, offer):
        """Send simplified notification without images for speed"""
        # Get bot username for linking
        bot_username = self._get_bot_username()
        
        message = self._t('new_offer_available') + "\n\n"
        message += f"<b><a href='https://t.me/{bot_username}?start=offer_details_{offer.offer_id}'>{offer.offer_id}</a>. {offer.name} €{offer.price_per_unit:.2f} </b>\n\n"
        message += f"{offer.description}\n\n"
        message += self._t('order_with_command', offer_id=offer.offer_id)
        
        reply_markup = {
            "inline_keyboard": [[
                {"text": self._t('order_1'), "callback_data": f"order_{offer.offer_id}_1"},
                {"text": self._t('order_2'), "callback_data": f"order_{offer.offer_id}_2"}
            ]]
        }
        
        self._send_message(chat_id, message, parse_mode="HTML", reply_markup=reply_markup)
