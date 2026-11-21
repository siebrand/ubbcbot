"""/list_open_payments: the customers with unpaid orders, oldest first (partial-payments-design.md, PP-5)"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.order.order_status import OrderStatusManagement
from models.entities import AuthorizationStatus, Customer, Order
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
NOW = datetime.now(UTC)


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = OrderStatusManagement(db, ADMIN_ID, "prod", "token")
    handler.sent = []

    def send(chat, text, reply_markup=None, **_):
        buttons = [b["callback_data"] for row in (reply_markup or {}).get("inline_keyboard", []) for b in row]
        handler.sent.append((text, buttons))
        return {"success": True}

    handler._send_message = Mock(side_effect=send)
    return handler


def customer(db, telegram_id, first, status=AuthorizationStatus.APPROVED.value):
    return db.create_customer(Customer(telegram_user_id=telegram_id, first_name=first, authorization_status=status))


def order(db, who, total, days_open, status="awaiting_payment", credit="0"):
    assert db.order_repo.create_order(
        Order(
            customer_id=who.customer_id,
            box_id="b1",
            offer_id=7,
            total_price=Decimal(total),
            credit_applied=Decimal(credit),
            status=status,
            created_at=NOW - timedelta(days=days_open + 10),
            update_date=NOW - timedelta(days=days_open, hours=1),
        )
    )


def test_customers_are_listed_oldest_first_with_their_totals_counts_and_ages(db, handler):
    jan, piet = customer(db, 101, "Jan"), customer(db, 102, "Piet")
    order(db, jan, "10.00", days_open=2)
    order(db, jan, "5.00", days_open=1, credit="2.00")
    order(db, piet, "7.50", days_open=9)
    order(db, piet, "99.00", days_open=30, status="completed")  # paid: not open

    assert handler.handle_list_open_payments(ADMIN_ID, []) == {"status": "open_payments_shown"}

    text, buttons = handler.sent[-1]
    lines = [line for line in text.splitlines() if line.startswith("•")]
    assert lines == [
        handler._t("list_open_payments_line", ADMIN_ID, name="Piet", amount=Decimal("7.50"), count=1, days=9),
        handler._t("list_open_payments_line", ADMIN_ID, name="Jan", amount=Decimal("13.00"), count=2, days=2),
    ]
    assert "cmd:process_payment" in buttons and "admin:main" in buttons


def test_customers_without_open_orders_are_not_listed(db, handler):
    jan = customer(db, 101, "Jan")
    customer(db, 102, "Piet")
    order(db, jan, "10.00", days_open=2)

    handler.handle_list_open_payments(ADMIN_ID, [])

    assert "Piet" not in handler.sent[-1][0]


def test_no_open_payments(db, handler):
    assert handler.handle_list_open_payments(ADMIN_ID, []) == {"status": "no_open_payments"}
    assert handler.sent[-1][0] == handler._t("no_open_payments", ADMIN_ID)


def test_ten_per_page(db, handler):
    for n in range(12):
        order(db, customer(db, 200 + n, f"Klant{n:02d}"), "1.00", days_open=n)

    handler.handle_list_open_payments(ADMIN_ID, [], page=2)

    text, buttons = handler.sent[-1]
    assert [line for line in text.splitlines() if line.startswith("•")][0].startswith("• Klant01")  # 2nd youngest
    assert "page_list_open_payments_1" in buttons
