"""The orders of one request, its new boxes and the increments of the existing boxes in one transaction
(DynamoDBService.create_orders_in_boxes): all or nothing, and an existing box is only added to while it has room."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from models.entities import Box, Order
from services.database import DynamoDBService


@pytest.fixture
def db(dynamodb):
    return DynamoDBService()


def order(box_id, quantity, order_id):
    return Order(
        order_id=order_id,
        customer_id="c1",
        box_id=box_id,
        offer_id=7,
        quantity=quantity,
        unit_price=Decimal("2"),
        total_price=Decimal("2") * quantity,
    )


def test_new_boxes_orders_and_increments_are_written_together(db):
    assert db.create_box(Box(box_id="old", offer_id=7, max_capacity=6, current_quantity=3))
    new = Box(box_id="new", offer_id=7, max_capacity=6, current_quantity=2)

    with patch.object(db.purchase_events, "order_created") as created:
        assert db.create_orders_in_boxes([order("old", 3, "o1"), order("new", 2, "o2")], [new], [("old", 3, 6)])

    assert db.get_box("old").current_quantity == 6
    assert db.get_box("new").current_quantity == 2
    assert {db.get_order("o1").box_id, db.get_order("o2").box_id} == {"old", "new"}
    assert created.call_count == 2  # one ORDER_CREATED event per order


def test_a_box_without_the_room_any_more_rejects_the_whole_request(db):
    assert db.create_box(Box(box_id="old", offer_id=7, max_capacity=6, current_quantity=5))  # taken in between
    new = Box(box_id="new", offer_id=7, max_capacity=6, current_quantity=2)

    assert not db.create_orders_in_boxes([order("old", 3, "o1"), order("new", 2, "o2")], [new], [("old", 3, 6)])

    assert db.get_box("old").current_quantity == 5
    assert db.get_box("new") is None  # no empty new box left behind
    assert db.get_order("o1") is None and db.get_order("o2") is None
