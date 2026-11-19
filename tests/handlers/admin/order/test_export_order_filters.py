"""Which orders each /export_orders filter selects."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.order.order_viewing import OrderViewing
from models.entities import Customer, Order, OrderStatus

ADMIN_ID = 1
ALL = {s.value for s in OrderStatus}


def _order(status: OrderStatus) -> Order:
    return Order(
        order_id=f"order-{status.value}",
        customer_id="cust-1",
        offer_id=7,
        quantity=1,
        unit_price=Decimal("2.00"),
        total_price=Decimal("2.00"),
        status=status.value,
        created_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
    )


def _exported(status_filter: str) -> set[str] | None:
    """The statuses of the exported orders, or None when nothing was exported"""
    db = Mock()
    db.get_customer_by_telegram_id.return_value = None
    db.get_customers_by_status.return_value = [Customer(customer_id="cust-1", telegram_user_id=42, first_name="Jan")]
    db.get_orders_by_customer.return_value = [_order(s) for s in OrderStatus]
    handler = OrderViewing(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler._send_document_message = Mock(return_value={"success": True, "message_id": 5})
    handler.expire_exports = Mock()
    handler.export_expiry = Mock()
    pick_list = Mock(return_value="csv")
    full = Mock(return_value="csv")
    handler._generate_pick_list_csv = pick_list
    handler._generate_full_export_csv = full

    result = handler._export_orders_by_status(ADMIN_ID, status_filter)

    if result["status"] == "no_orders":
        return None
    generator = full if status_filter == "full" else pick_list
    return {order.status for _customer, order in generator.call_args.args[0]}


@pytest.mark.parametrize(
    "status_filter,statuses",
    [
        ("active", {"pending", "ordered"}),
        ("ordered", {"ordered"}),
        ("cancelled", {"cancelled"}),
        ("ready_for_labeling", {"ready_for_labeling"}),
        ("labeling_completed", {"labeling_completed"}),
        ("awaiting_payment", {"awaiting_payment"}),
        ("completed", {"completed"}),
        ("all", ALL),
        ("full", ALL),
    ],
)
def test_a_filter_selects_its_orders(status_filter, statuses):
    assert _exported(status_filter) == statuses


@pytest.mark.parametrize("status_filter", ["pending", "bier"])
def test_an_unknown_filter_exports_nothing(status_filter):
    assert _exported(status_filter) is None
