import pytest
from repositories.notification_repository import NotificationRepository
from models.entities import NotificationMessage

@pytest.fixture
def notification_repo(dynamodb):
    return NotificationRepository()

class TestNotificationRepository:
    def test_create_notification_message(self, notification_repo):
        notification = NotificationMessage(
            notification_id="notif-1",
            offer_id=1,
            chat_id=12345,
            message_id=67890
        )
        assert notification_repo.create_notification_message(notification) is True

    def test_get_notification_messages_by_offer(self, notification_repo):
        notif1 = NotificationMessage(notification_id="notif-2", offer_id=2, chat_id=111, message_id=222)
        notif2 = NotificationMessage(notification_id="notif-3", offer_id=2, chat_id=333, message_id=444)
        
        notification_repo.create_notification_message(notif1)
        notification_repo.create_notification_message(notif2)
        
        notifications = notification_repo.get_notification_messages_by_offer(2)
        assert len(notifications) == 2

    def test_delete_notification_message(self, notification_repo):
        notification = NotificationMessage(notification_id="notif-4", offer_id=3, chat_id=555, message_id=666)
        notification_repo.create_notification_message(notification)
        
        assert notification_repo.delete_notification_message("notif-4") is True
