"""/finalize_import: the offer that is announced is active in the table too (against the mocked database)"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.import_handler import ImportHandler
from models.entities import Box, Offer, OfferStatus
from services.database import DynamoDBService

ADMIN_ID = 15005473


@pytest.fixture
def db(dynamodb):
    service = DynamoDBService()
    service.create_offer(
        Offer(offer_id=7, name="Pils", price_per_unit=Decimal("2.50"), wholesale_box_size=6, status="import")
    )
    return service


@pytest.fixture
def handler(db):
    handler = ImportHandler(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"status": "sent"})
    handler._announce_offer = Mock()
    return handler


def test_an_offer_without_imported_orders_is_announced_and_active(handler, db):
    handler.handle_finalize_import(ADMIN_ID, ["7"])

    handler._announce_offer.assert_called_once()
    assert db.get_offer(7).status == OfferStatus.ACTIVE.value


def test_an_offer_with_room_in_its_boxes_is_announced_and_active(handler, db):
    assert db.create_box(Box(offer_id=7, max_capacity=6, current_quantity=2))

    handler.handle_finalize_import(ADMIN_ID, ["7"])

    handler._announce_offer.assert_called_once()
    assert db.get_offer(7).status == OfferStatus.ACTIVE.value
