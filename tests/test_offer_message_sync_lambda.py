"""Handing the re-edit of many subscriber messages to the NotificationSender Lambda."""

import json
from decimal import Decimal
from unittest.mock import Mock, patch

from handlers.base_handler import BaseHandler
from models.entities import NotificationMessage, Offer
from services.offer_message_sync import notification_lambda_name, start_subscriber_sync


def invoked(lambda_client) -> dict:
    return lambda_client.invoke.call_args.kwargs


def test_the_sync_is_started_asynchronously_with_the_offer(monkeypatch):
    monkeypatch.delenv("NOTIFICATION_LAMBDA_NAME", raising=False)
    with patch("services.offer_message_sync.boto3") as boto3:
        assert start_subscriber_sync(7, True, "prod") is True

    call = invoked(boto3.client.return_value)
    assert call["FunctionName"] == "ubbc-bot-prod-notification-sender"
    assert call["InvocationType"] == "Event"
    assert json.loads(call["Payload"]) == {
        "action": "sync_offer_messages",
        "offer_id": 7,
        "cancelled": True,
        "environment": "prod",
    }


def test_an_offer_id_from_dynamodb_is_sent_as_a_number():
    with patch("services.offer_message_sync.boto3") as boto3:
        start_subscriber_sync(Decimal("7"), False, "test")

    assert json.loads(invoked(boto3.client.return_value)["Payload"])["offer_id"] == 7


def test_the_function_name_can_be_configured(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_LAMBDA_NAME", "custom")

    assert notification_lambda_name("prod") == "custom"


def test_a_failed_invoke_does_not_raise():
    with patch("services.offer_message_sync.boto3") as boto3:
        boto3.client.return_value.invoke.side_effect = RuntimeError("throttled")

        assert start_subscriber_sync(7, False, "test") is False


def test_the_handler_uses_its_own_environment(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("NOTIFICATION_LAMBDA_NAME", raising=False)
    db = Mock()
    db.get_notification_messages_by_offer.return_value = [
        NotificationMessage(notification_id=f"s{i}", offer_id=7, chat_id=i, message_id=i, kind="subscriber")
        for i in range(11)
    ]
    db.get_boxes_by_offer.return_value = []
    handler = BaseHandler(db, 1, "prod", "token")
    handler._get_bot_username = Mock(return_value="ubbc_bot")

    with patch("services.offer_message_sync.boto3") as boto3:
        handler.announcements.sync(Offer(offer_id=7, name="Pils"))

    call = invoked(boto3.client.return_value)
    assert call["FunctionName"] == "ubbc-bot-prod-notification-sender"
    assert json.loads(call["Payload"])["environment"] == "prod"
