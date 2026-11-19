"""Another warm container approves or rejects a user: this container sees it on the user's next update.

The cache in `UserCache` lives per Lambda container. A change made through another container does not invalidate it
here, so the test makes the change in the table directly, the way this container would see it.
"""

from itertools import count
from unittest.mock import patch

import pytest

from models.entities import AuthorizationStatus, Customer
from services import user_cache
from services.bot_service import BotService
from services.database import DynamoDBService
from services.telegram_client import TelegramClient, TelegramResponse
from services.user_cache import UserCache

UPDATE_IDS = count(1)


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def bot(db):
    with (
        patch.object(BotService, "_get_telegram_token", return_value="token"),
        patch.object(TelegramClient, "call", return_value=TelegramResponse(ok=True, result={"message_id": 1})),
    ):
        yield BotService()


def customer(db, status: AuthorizationStatus) -> Customer:
    return db.create_customer(
        Customer(telegram_user_id=101, username="jan", first_name="Jan", authorization_status=status.value)
    )


def set_status_elsewhere(dynamodb, customer: Customer, status: AuthorizationStatus) -> None:
    """What another container's /approve or /reject writes: the table changes, this container's cache does not"""
    dynamodb.Table("ubbc-bot-test-customers").update_item(
        Key={"customer_id": customer.customer_id},
        UpdateExpression="SET authorization_status = :s",
        ExpressionAttributeValues={":s": status.value},
    )


def command(bot, text: str) -> dict:
    return bot.process_update(
        {
            "update_id": next(UPDATE_IDS),
            "message": {
                "message_id": 1,
                "chat": {"id": 101, "type": "private"},
                "from": {"id": 101, "first_name": "Jan", "username": "jan"},
                "text": text,
            },
        }
    )


class TestTheSenderIsReadFresh:
    def test_a_user_rejected_in_another_container_is_refused(self, bot, db, dynamodb):
        jan = customer(db, AuthorizationStatus.APPROVED)
        assert command(bot, "/help")["status"] != "unauthorized"

        set_status_elsewhere(dynamodb, jan, AuthorizationStatus.REJECTED)

        assert command(bot, "/help") == {"status": "unauthorized"}

    def test_a_user_approved_in_another_container_is_let_in(self, bot, db, dynamodb):
        jan = customer(db, AuthorizationStatus.UNAUTHORIZED)
        assert command(bot, "/help") == {"status": "unauthorized"}

        set_status_elsewhere(dynamodb, jan, AuthorizationStatus.APPROVED)

        assert command(bot, "/help")["status"] != "unauthorized"


class TestTheListsExpire:
    def test_a_list_of_customers_is_read_again_after_a_minute(self, db, dynamodb, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(user_cache.time, "monotonic", lambda: now[0])
        jan = customer(db, AuthorizationStatus.APPROVED)
        assert [c.customer_id for c in db.get_customers_by_status("approved")] == [jan.customer_id]

        set_status_elsewhere(dynamodb, jan, AuthorizationStatus.REJECTED)
        now[0] += UserCache.TTL_SECONDS - 1
        assert [c.customer_id for c in db.get_customers_by_status("approved")] == [jan.customer_id]

        now[0] += 2
        assert db.get_customers_by_status("approved") == []
        assert db.get_customer_by_telegram_id(101).authorization_status == "rejected"
