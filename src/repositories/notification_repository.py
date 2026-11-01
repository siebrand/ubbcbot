import logging

from boto3.dynamodb.conditions import Key

from models.entities import NotificationMessage
from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class NotificationRepository(BaseRepository):
    def __init__(self):
        super().__init__("notifications")

    def create_notification_message(self, notification: NotificationMessage) -> bool:
        try:
            item = self._prepare_item(notification.__dict__)
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"Error creating notification message: {e}")
            return False

    def get_notification_messages_by_offer(self, offer_id: int) -> list[NotificationMessage]:
        try:
            response = self.table.query(IndexName="offer-index", KeyConditionExpression=Key("offer_id").eq(offer_id))
            return [NotificationMessage(**item) for item in response.get("Items", [])]
        except Exception as e:
            logger.error(f"Error getting notification messages: {e}")
            return []

    def delete_notification_message(self, notification_id: str) -> bool:
        try:
            self.table.delete_item(Key={"notification_id": notification_id})
            return True
        except Exception as e:
            logger.error(f"Error deleting notification message: {e}")
            return False
