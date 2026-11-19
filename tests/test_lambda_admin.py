"""The admin is config.ADMIN_USER_ID everywhere (no hard-coded id), and the message Lambda gets the admin's language."""

from unittest.mock import Mock, patch

import notification_sender
from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler
from handlers.base_handler import BaseHandler

ADMIN_ID = 4242


def test_the_wholesale_delivery_records_the_handlers_admin():
    handler = WholesaleDeliveryHandler(Mock(), ADMIN_ID, "test", "token")

    assert handler.delivery_service.admin_user_id == ADMIN_ID


def test_the_notification_lambda_uses_the_configured_admin(monkeypatch):
    monkeypatch.setattr(notification_sender, "ADMIN_USER_ID", ADMIN_ID)
    ssm = Mock()
    ssm.get_parameter.return_value = {"Parameter": {"Value": "token"}}

    with (
        patch("boto3.client", return_value=ssm),
        patch("notification_sender.DynamoDBService"),
        patch("notification_sender.NotificationSender") as sender,
    ):
        notification_sender.lambda_handler({"offer_id": 12, "environment": "test"}, None)

    assert sender.call_args.args[1] == ADMIN_ID


def test_the_message_sender_event_carries_the_admins_language():
    db = Mock()
    db.get_customer_by_telegram_id.return_value = Mock(language="en")
    handler = BaseHandler(db, ADMIN_ID, "test", "token")
    messages = [{"user_id": 42, "message": "hoi", "from_admin": True}]

    event = handler._message_sender_event(messages)

    assert event == {"messages": messages, "environment": "test", "admin_language": "en"}
    db.get_customer_by_telegram_id.assert_called_with(ADMIN_ID)
