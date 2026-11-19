"""/credit <username> <amount> [reason], against the (mocked) database"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.credit_commands import CreditCommands
from models.entities import AuthorizationStatus, Customer
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    service = DynamoDBService()
    service.create_customer(
        Customer(
            telegram_user_id=101,
            username="jan",
            first_name="Jan",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = CreditCommands(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"status": "sent"})
    return handler


def balance(db) -> Decimal:
    (jan,) = db.get_all_customers()
    credit = db.get_customer_credit(jan.customer_id)
    return credit.current_balance if credit else Decimal("0")


def answer(handler) -> str:
    return handler._send_message.call_args_list[-1].args[1]


class TestReason:
    def test_a_positive_amount_needs_no_reason(self, handler, db):
        handler.handle_credit(ADMIN_ID, ["jan", "5"])

        assert balance(db) == Decimal("5")
        assert answer(handler) == handler._t(
            "credit_issued_success", ADMIN_ID, amount=Decimal("5"), customer_name="Jan"
        )

    def test_a_negative_amount_needs_a_reason(self, handler, db):
        handler.handle_credit(ADMIN_ID, ["jan", "-5"])

        assert balance(db) == Decimal("0")
        assert answer(handler) == handler._t("reason_required_negative", ADMIN_ID)

    def test_a_negative_amount_with_a_reason_is_a_debt(self, handler, db):
        handler.handle_credit(ADMIN_ID, ["jan", "-5", "broken", "bottle"])

        assert balance(db) == Decimal("-5")
        (transaction,) = db.get_credit_transactions_by_customer(db.get_all_customers()[0].customer_id)
        assert transaction.reason == "broken bottle"


class TestAmount:
    @pytest.mark.parametrize("text", ["abc", "NaN", "sNaN", "Infinity", "-Infinity", "1e9", "10000", "0", "1.005", ""])
    def test_an_amount_that_is_not_a_sane_amount_of_euros_is_refused(self, handler, db, text):
        result = handler.handle_credit(ADMIN_ID, ["jan", text, "reason"])

        assert result["status"] == "invalid_format"
        assert answer(handler) == handler._t("invalid_amount", ADMIN_ID)
        assert balance(db) == Decimal("0")

    @pytest.mark.parametrize(
        ("text", "expected"), [("2.50", "2.50"), ("2,50", "2.50"), ("-0.01", "-0.01"), ("1000", "1000")]
    )
    def test_amounts_in_euros_and_cents_are_accepted(self, handler, db, text, expected):
        handler.handle_credit(ADMIN_ID, ["jan", text, "reason"])

        assert balance(db) == Decimal(expected)
