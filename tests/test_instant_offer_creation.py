"""An instant offer is created in one write: the offer, its delivered box and its first order (instant-orders-design.md,
IO-4)"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from models.entities import Box, BoxStatus, Offer, Order
from services.database import DynamoDBService
from services.offer_cache import OfferCache


@pytest.fixture
def db(dynamodb):
    OfferCache.invalidate_cache()
    yield DynamoDBService()
    OfferCache.invalidate_cache()


def entities():
    offer = Offer(supplier_name="De Molen", name="Tripel", price_per_unit=Decimal("3.00"), wholesale_box_size=4)
    box = Box(max_capacity=4, current_quantity=1, status=BoxStatus.DELIVERED.value)
    order = Order(
        customer_id="c1",
        quantity=1,
        received_quantity=1,
        unit_price=Decimal("3.00"),
        total_price=Decimal("3.00"),
        status="ready_for_labeling",
        placed_by_admin=True,
    )
    return offer, box, order


def test_all_three_exist_after_success(db):
    offer, box, order = entities()

    assert db.create_instant_offer(offer, box, order) is True

    assert db.get_offer(offer.offer_id).name == "Tripel"
    stored_box = db.get_box(box.box_id)
    assert (stored_box.offer_id, stored_box.current_quantity, stored_box.status) == (offer.offer_id, 1, "delivered")
    stored_order = db.get_order(order.order_id)
    assert (stored_order.box_id, stored_order.offer_id, stored_order.status) == (
        box.box_id,
        offer.offer_id,
        "ready_for_labeling",
    )


def test_the_new_offer_is_in_the_cached_list_at_once(db):
    db.list_offers()  # fill the cache
    offer, box, order = entities()

    db.create_instant_offer(offer, box, order)

    assert offer.offer_id in [o.offer_id for o in db.list_offers()]


def test_the_order_created_event_is_recorded(db):
    offer, box, order = entities()

    db.create_instant_offer(offer, box, order)

    [event] = db.get_events_by_type("ORDER_CREATED")
    assert (event.customer_id, event.amount) == ("c1", Decimal("3.00"))


def test_a_rejected_transaction_writes_nothing(db):
    offer, box, order = entities()
    assert db.order_repo.create_order(Order(order_id=order.order_id, customer_id="other"))  # the key exists already

    assert db.create_instant_offer(offer, box, order) is False

    assert db.get_offer(offer.offer_id) is None
    assert db.get_box(box.box_id) is None
    assert db.get_order(order.order_id).customer_id == "other"
    assert db.get_events_by_type("ORDER_CREATED") == []


def test_a_failed_write_writes_nothing(db):
    offer, box, order = entities()
    error = ClientError({"Error": {"Code": "InternalServerError", "Message": "boom"}}, "TransactWriteItems")

    with patch("botocore.client.BaseClient._make_api_call", side_effect=error):
        result = db.create_instant_offer(offer, box, order)

    assert result is False
    assert db.get_box(box.box_id) is None
    assert db.get_order(order.order_id) is None
