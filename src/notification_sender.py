import json
import os
import logging
from typing import Dict, Any
from services.database import DynamoDBService
from handlers.base_handler import BaseHandler
from models.entities import AuthorizationStatus

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Async Lambda function to send offer notifications to subscribers"""
    try:
        # Get Telegram token
        import boto3
        ssm = boto3.client('ssm')
        environment = event.get('environment', 'test')
        token_param = f"/ubbc-bot/{environment}/telegram-bot-token"
        telegram_token = ssm.get_parameter(Name=token_param, WithDecryption=True)['Parameter']['Value']
        
        # Initialize database service
        db = DynamoDBService()
        
        # Create notification handler
        handler = NotificationSender(db, 15005473, environment, telegram_token)
        
        # Extract payload
        offer_id = event['offer_id']
        
        logger.info(f"Processing notifications for offer {offer_id}")
        
        # Get offer details
        offer = db.get_offer(offer_id)
        if not offer:
            logger.error(f"Offer {offer_id} not found")
            return {'statusCode': 404, 'body': 'Offer not found'}
        
        # Get all subscribers directly from database
        subscribers = db.get_subscribers()
        
        logger.info(f"Found {len(subscribers)} subscribers")
        
        # Send notifications
        success_count, error_count = handler.send_bulk_notifications(subscribers, offer)
        
        logger.info(f"Notification complete: {success_count} success, {error_count} errors")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success_count': success_count,
                'error_count': error_count,
                'total_subscribers': len(subscribers)
            })
        }
        
    except Exception as e:
        logger.error(f"Error in notification sender: {e}")
        return {'statusCode': 500, 'body': f'Error: {str(e)}'}

class NotificationSender(BaseHandler):
    """Notification sender using BaseHandler methods"""
    
    def send_bulk_notifications(self, subscribers, offer):
        """Send notifications to all subscribers"""
        import random
        random.shuffle(subscribers)
        # Pre-generate presigned URLs for images
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
        
        success_count = 0
        error_count = 0
        
        # Process in batches
        batch_size = 20
        for i in range(0, len(subscribers), batch_size):
            batch = subscribers[i:i + batch_size]
            
            for customer in batch:
                try:
                    self._send_notification_to_customer(customer, offer, presigned_images)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to notify subscriber {customer.customer_id}: {e}")
                    error_count += 1
            
            # Small delay between batches
            if i + batch_size < len(subscribers):
                import time
                time.sleep(0.5)
        
        return success_count, error_count
    
    def _send_notification_to_customer(self, customer, offer, presigned_images):
        """Send notification to a single customer using BaseHandler methods"""
        chat_id = customer.telegram_user_id
        
        # Send images using pre-generated URLs
        if presigned_images:
            if len(presigned_images) == 1:
                self._send_photo(chat_id, presigned_images[0])
            else:
                media_group = [{"type": "photo", "media": url} for url in presigned_images]
                self._send_media_group(chat_id, media_group)

        # Get bot username for linking
        bot_username = self._get_bot_username()
        
        # Combine header and offer details in single message
        message = f"<b><a href='https://t.me/{bot_username}?start=view_offer_{offer.offer_id}'>{offer.offer_id}</a>. {offer.name} €{offer.price_per_unit:.2f}</b>\n\n"
        message += f"{offer.description}\n"
        
        # Add order buttons
        reply_markup = {
            "inline_keyboard": [[
                {"text": self._t('order_1', customer.telegram_user_id), "callback_data": f"order_{offer.offer_id}_1"},
                {"text": self._t('order_2', customer.telegram_user_id), "callback_data": f"order_{offer.offer_id}_2"}
            ]]
        }
        
        self._send_message(chat_id, message, parse_mode="HTML", reply_markup=reply_markup)
