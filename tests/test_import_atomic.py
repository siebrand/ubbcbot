"""An imported order and the unit it takes in its box are one write (against the mocked database)"""

from decimal import Decimal

import pytest

from handlers.admin.import_handler import ImportHandler
from models.entities import AuthorizationStatus, Box, BoxStatus, Customer, Offer, OfferStatus
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
BOX_ID = "abcdef12-0000-4000-8000-000000000000"


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    service = DynamoDBService()
    service.create_offer(
        Offer(
            offer_id=7,
            name="Pils",
            price_per_unit=Decimal("2.50"),
            wholesale_box_size=2,
            status=OfferStatus.IMPORT.value,
        )
    )
    assert service.create_box(Box(box_id=BOX_ID, offer_id=7, max_capacity=2, current_quantity=1))
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def jan(db) -> Customer:
    return db.create_customer(
        Customer(telegram_user_id=101, first_name="Jan", authorization_status=AuthorizationStatus.APPROVED.value)
    )


def box_filled_after_the_next_read(db) -> None:
    """A customer takes the last unit of the box right after the import reads the boxes"""
    read = db.get_boxes_by_offer

    def read_then_fill(offer_id):
        db.get_boxes_by_offer = read
        boxes = read(offer_id)
        assert db.increment_box_quantity(BOX_ID, 1, 2)
        return boxes

    db.get_boxes_by_offer = read_then_fill


def test_an_import_order_does_not_overfill_a_box_that_was_filled_meanwhile(db, jan):
    handler = ImportHandler(db, ADMIN_ID, "prod", "token")
    box_filled_after_the_next_read(db)

    assert handler._create_import_order(db.get_offer(7), jan)["success"]

    boxes = {box.box_id: box for box in db.get_boxes_by_offer(7)}
    assert boxes[BOX_ID].current_quantity == 2
    assert db.get_orders_by_box(BOX_ID) == []
    (new_box,) = [b for b in boxes.values() if b.box_id != BOX_ID]
    (order,) = db.get_orders_by_box(new_box.box_id)
    assert (order.customer_id, new_box.current_quantity) == (jan.customer_id, 1)


def test_the_order_and_its_unit_are_written_together(db, jan):
    handler = ImportHandler(db, ADMIN_ID, "prod", "token")

    assert handler._create_import_order(db.get_offer(7), jan)["success"]

    (order,) = db.get_orders_by_box(BOX_ID)
    assert order.quantity == 1
    box = db.get_box(BOX_ID)
    assert (box.current_quantity, box.status) == (2, BoxStatus.FULL.value)
