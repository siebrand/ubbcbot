"""Taking a customer's approval away: /reject_user and the button on the user edit screen, against the (moto)
database"""

from unittest.mock import Mock

import pytest

from handlers.admin.user_commands import UserCommands
from models.entities import AuthorizationStatus, Customer
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def users(db):
    handler = UserCommands(db, ADMIN_ID, "prod", "token")
    handler.sent = []

    def send(chat, text, reply_markup=None, **_):
        buttons = [b["callback_data"] for row in (reply_markup or {}).get("inline_keyboard", []) for b in row]
        handler.sent.append((chat, text, buttons))
        return {"success": True}

    handler._send_message = Mock(side_effect=send)
    handler._notify_customer = Mock(return_value={"success": True})
    return handler


def approved(db, telegram_id, name):
    return db.create_customer(
        Customer(telegram_user_id=telegram_id, first_name=name, authorization_status=AuthorizationStatus.APPROVED.value)
    )


def status_of(db, customer) -> str:
    UserCache.invalidate_cache()
    return db.get_customer(customer.customer_id).authorization_status


class TestRejectUser:
    def test_the_list_of_matches_rejects_the_customer_picked(self, db, users):
        approved(db, 101, "Jan")
        janneke = approved(db, 102, "Janneke")

        assert users.handle_reject_user(ADMIN_ID, ["Jan"])["status"] == "disambiguation_shown"

        buttons = users.sent[-1][2]
        assert f"reject_user_{janneke.customer_id}" in buttons  # not the edit screen
        users.handle_reject_user_by_id(ADMIN_ID, janneke.customer_id)
        assert status_of(db, janneke) == AuthorizationStatus.REJECTED.value
