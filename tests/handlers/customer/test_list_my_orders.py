"""/list_my_orders is answered by InfoCommands itself, through the shared order list (no second handler)."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from handlers.customer.info_commands import InfoCommands
from models.entities import Customer, Order, OrderStatus

ADMIN_ID = 1
CUSTOMER = Customer(customer_id="cust-1", telegram_user_id=42, first_name="Jan", last_name="J", language="en")


def _handler():
    db = Mock()
    db.get_customer_by_telegram_id.return_value = CUSTOMER
    db.get_offer.return_value = SimpleNamespace(name="Pils")
    db.get_orders_by_customer.return_value = [
        Order(
            order_id="order-1234abcd",
            customer_id="cust-1",
            offer_id=7,
            quantity=2,
            unit_price=Decimal("2.00"),
            total_price=Decimal("4.00"),
            status=OrderStatus.PENDING.value,
            created_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
        )
    ]
    handler = InfoCommands(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler._get_bot_username = Mock(return_value="ubbc_bot")
    return handler


def test_the_customer_gets_their_orders():
    handler = _handler()

    assert handler.handle_list_my_orders(42, 42) == {"status": "success"}

    message = handler._send_message.call_args.args[1]
    assert message.startswith("📦 Your Orders:")
    assert "Pils €2.00 2x €4.00" in message
    assert "order-12" not in message


def test_with_id_the_order_ids_are_shown():
    handler = _handler()

    handler.handle_list_my_orders(42, 42, ["id"])

    assert "order-12" in handler._send_message.call_args.args[1]


def test_someone_without_a_customer_record_is_told():
    handler = _handler()
    handler.db.get_customer_by_telegram_id.return_value = None

    assert handler.handle_list_my_orders(42, 42) == {"status": "customer_not_found"}
