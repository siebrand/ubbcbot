"""/my_orders and /list_user_orders show an order in every status, each under its own heading."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from handlers.admin.order.base_order_handler import BaseOrderHandler
from models.entities import Customer, Order, OrderStatus

ADMIN_ID = 1
CUSTOMER = Customer(customer_id="cust-1", telegram_user_id=42, first_name="Jan", last_name="J")


@pytest.mark.parametrize("status", list(OrderStatus))
def test_an_order_in_any_status_is_listed(status):
    db = Mock()
    db.get_customer_by_telegram_id.return_value = None
    db.get_offer.return_value = SimpleNamespace(name="Pils")
    db.get_orders_by_customer.return_value = [
        Order(
            order_id="order-1",
            customer_id="cust-1",
            offer_id=7,
            quantity=3,
            unit_price=Decimal("2.00"),
            total_price=Decimal("6.00"),
            status=status.value,
            created_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
        )
    ]
    handler = BaseOrderHandler(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler._get_bot_username = Mock(return_value="ubbc_bot")

    handler.show_customer_orders(42, CUSTOMER, user_id=42)

    message = handler._send_message.call_args.args[1]
    assert "Pils €2.00 3x €6.00" in message
    assert "❓" not in message  # every status has its own mark
