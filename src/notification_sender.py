import json
import logging

from config import ADMIN_USER_ID
from handlers.base_handler import BaseHandler
from services.database import DynamoDBService
from services.offer_message_builder import OfferMessageBuilder
from utils.log_redaction import configure_logging
from utils.s3_url import is_s3_url

logger = logging.getLogger()
configure_logging()


def lambda_handler(event, context):
    """Async Lambda function to send offer notifications to subscribers"""
    try:
        # Get Telegram token
        import boto3

        ssm = boto3.client("ssm")
        environment = event.get("environment", "test")
        token_param = f"/ubbc-bot/{environment}/telegram-bot-token"
        telegram_token = ssm.get_parameter(Name=token_param, WithDecryption=True)["Parameter"]["Value"]

        # Initialize database service
        db = DynamoDBService()

        # Create notification handler
        handler = NotificationSender(db, ADMIN_USER_ID, environment, telegram_token)

        # Extract payload
        offer_id = event["offer_id"]
        action = event.get("action", "send")

        # Edit-existing-messages mode: re-render the subscriber DMs for an offer
        # whose status/content changed (the group message is edited inline by the
        # webhook handler; this Lambda only handles large subscriber batches).
        if action == "sync_offer_messages":
            logger.info(f"Syncing subscriber messages for offer {offer_id}")
            offer = db.get_offer(offer_id)
            if not offer:
                logger.error(f"Offer {offer_id} not found")
                return {"statusCode": 404, "body": "Offer not found"}
            edited, failed = handler.sync_subscriber_messages(offer, cancelled=event.get("cancelled", False))
            logger.info(f"Subscriber message sync complete: {edited} edited, {failed} failed")
            return {
                "statusCode": 200,
                "body": json.dumps({"edited": edited, "failed": failed}),
            }

        logger.info(f"Processing notifications for offer {offer_id}")

        # Get offer details
        offer = db.get_offer(offer_id)
        if not offer:
            logger.error(f"Offer {offer_id} not found")
            return {"statusCode": 404, "body": "Offer not found"}

        # Get all subscribers directly from database
        subscribers = db.get_subscribers()

        logger.info(f"Found {len(subscribers)} subscribers")

        # Send notifications
        success_count, error_count = handler.send_bulk_notifications(subscribers, offer)

        logger.info(f"Notification complete: {success_count} success, {error_count} errors")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {"success_count": success_count, "error_count": error_count, "total_subscribers": len(subscribers)}
            ),
        }

    except Exception as e:
        logger.error(f"Error in notification sender: {e}")
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


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
                    if is_s3_url(image_url):
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
            batch = subscribers[i : i + batch_size]

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

    def sync_subscriber_messages(self, offer, cancelled: bool = False):
        """Edit the subscriber DM announcements for an offer. The group message is edited inline by the webhook
        handler. Returns (edited_count, failed_count)."""
        return self.announcements.sync_subscribers(offer, cancelled)

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

        # The same message as the group post and every later re-edit (the name escaped), buttons in the
        # subscriber's language. The re-edits (OfferAnnouncements) use the group language: a tracked message
        # row does not know its subscriber's language, and looking it up per row would cost a read each.
        builder = OfferMessageBuilder(self._get_bot_username(), lambda key: self._t(key, chat_id))
        message, reply_markup = builder.build(offer)

        result = self._send_message(chat_id, message, parse_mode="HTML", reply_markup=reply_markup)
        if result and result.get("success"):
            try:
                from models.entities import NotificationMessage

                self.db.create_notification_message(
                    NotificationMessage(
                        offer_id=offer.offer_id, chat_id=chat_id, message_id=result["message_id"], kind="subscriber"
                    )
                )
            except Exception as e:
                logger.error(f"Failed to track notification message for offer {offer.offer_id}: {e}")
