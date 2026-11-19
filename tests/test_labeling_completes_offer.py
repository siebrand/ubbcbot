"""The last box labeled completes a sold-out offer, and its announcements lose their order buttons"""

from unittest.mock import Mock

import pytest

from handlers.admin.labeling_completion_handler import LabelingCompletionHandler
from models.entities import Box, BoxStatus, Offer, OfferStatus, Order, OrderStatus

ADMIN_ID = 15005473
BOX_ID = "abcdef12-0000-4000-8000-000000000000"


@pytest.fixture
def db():
    db = Mock()
    db.get_offer.return_value = Offer(offer_id=7, name="Pils", status=OfferStatus.SOLD_OUT.value)
    db.get_boxes_by_offer_with_ready_orders.side_effect = [[Box(box_id=BOX_ID, offer_id=7)], []]
    db.get_orders_by_box.return_value = [Order(box_id=BOX_ID, status=OrderStatus.READY_FOR_LABELING.value)]
    db.update_order.return_value = True
    db.update_offer.return_value = True
    return db


@pytest.fixture
def handler(db):
    handler = LabelingCompletionHandler(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"status": "sent"})
    handler.sync_offer_messages = Mock()
    return handler


def test_the_completed_offer_is_synced_once(handler, db):
    db.get_boxes_by_offer.return_value = [Box(box_id=BOX_ID, offer_id=7, status=BoxStatus.DELIVERED.value)]

    handler.handle_labeling_action(ADMIN_ID, "complete", BOX_ID[:8], 7, "sup12345")

    db.update_offer.assert_called_once_with(7, {"status": OfferStatus.COMPLETED.value})
    handler.sync_offer_messages.assert_called_once_with(7)


def test_an_offer_that_is_not_completed_is_not_synced(handler, db):
    db.get_boxes_by_offer.return_value = [
        Box(box_id=BOX_ID, offer_id=7, status=BoxStatus.DELIVERED.value),
        Box(offer_id=7, status=BoxStatus.ORDERED.value),
    ]

    handler.handle_labeling_action(ADMIN_ID, "complete", BOX_ID[:8], 7, "sup12345")

    db.update_offer.assert_not_called()
    handler.sync_offer_messages.assert_not_called()
