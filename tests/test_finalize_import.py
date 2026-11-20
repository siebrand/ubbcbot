"""/finalize_import (and /offer_status): the offer that is announced is active in the table too, a wrong status is
refused (against the mocked database)"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.import_handler import ImportHandler
from handlers.admin.offer.editing import OfferEditingHandler
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


def test_an_offer_that_is_not_being_imported_is_refused_with_its_status(handler, db):
    assert db.update_offer(7, {"status": OfferStatus.ACTIVE.value})

    assert handler.handle_finalize_import(ADMIN_ID, ["7"]) == {"status": "wrong_status"}

    assert OfferStatus.ACTIVE.value in handler._send_message.call_args.args[1]
    handler._announce_offer.assert_not_called()


def test_offer_status_with_an_unknown_status_names_it(db):
    """The same clash of a {status} in the text with the status of the answer (audit 5, B4)"""
    editing = OfferEditingHandler(db, ADMIN_ID, "prod", "token")
    editing._send_message = Mock(return_value={"status": "sent"})

    assert editing.handle_offer_status(ADMIN_ID, ["7", "bogus"]) == {"status": "invalid_status"}

    assert "bogus" in editing._send_message.call_args.args[1]
