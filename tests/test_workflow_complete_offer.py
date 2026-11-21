"""Completing a whole offer in /process_delivery and /process_labeling: everything in its open boxes moves on.

Pins the behaviour that the multi-offer checklist reuses, against the (moto) database."""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.labeling_completion_handler import LabelingCompletionHandler
from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler
from models.entities import AuthorizationStatus, Box, Customer, Offer, Order, Supplier
from services.database import DynamoDBService
from services.offer_cache import OfferCache
from services.user_cache import UserCache

ADMIN_ID = 15005473


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    OfferCache.invalidate_cache()
    service = DynamoDBService()
    service.create_supplier(Supplier(supplier_id="sup12345-0000", name="DeMolen"))
    yield service
    UserCache.invalidate_cache()
    OfferCache.invalidate_cache()


@pytest.fixture
def jan(db):
    return db.create_customer(
        Customer(telegram_user_id=101, first_name="Jan", authorization_status=AuthorizationStatus.APPROVED.value)
    )


def offer_with_boxes(db, customer, offer_id, box_status, order_status, boxes=2, per_box=(2, 4)):
    """An offer of DeMolen with ``boxes`` boxes, each with two orders of ``per_box`` units"""
    db.create_offer(
        Offer(
            offer_id=offer_id,
            supplier_name="DeMolen",
            name=f"Bier {offer_id}",
            price_per_unit=Decimal("3"),
            wholesale_box_size=6,
            status="sold_out",
        )
    )
    created = []
    for _ in range(boxes):
        box = db.create_box(Box(offer_id=offer_id, max_capacity=6, current_quantity=sum(per_box), status=box_status))
        for quantity in per_box:
            order = Order(
                customer_id=customer.customer_id,
                box_id=box.box_id,
                offer_id=offer_id,
                quantity=quantity,
                received_quantity=quantity if order_status == "ready_for_labeling" else 0,
                unit_price=Decimal("3"),
                total_price=Decimal("3") * quantity,
                status=order_status,
            )
            assert db.order_repo.create_order(order)
        created.append(box)
    return created


def quiet(handler):
    handler._send_message = Mock(return_value={"success": True, "message_id": 1})
    handler._notify_customer = Mock(return_value={"success": True})
    handler.sync_offer_messages = Mock()
    return handler


class TestCompleteDelivery:
    def test_every_ordered_box_is_delivered_in_full(self, db, jan):
        boxes = offer_with_boxes(db, jan, 7, "ordered", "ordered")
        handler = quiet(WholesaleDeliveryHandler(db, ADMIN_ID, "prod", "token"))

        handler.handle_confirm_complete_delivery(ADMIN_ID, 7, "sup12345")

        assert {db.get_box(b.box_id).status for b in boxes} == {"delivered"}
        orders = db.get_orders_by_offer(7)
        assert {(o.status, o.received_quantity == o.quantity) for o in orders} == {("ready_for_labeling", True)}

    def test_complete_offer_reports_the_boxes_and_units(self, db, jan):
        offer_with_boxes(db, jan, 7, "ordered", "ordered")
        handler = quiet(WholesaleDeliveryHandler(db, ADMIN_ID, "prod", "token"))

        result = handler.complete_offer(7)

        assert (result.boxes, result.units, result.failed_boxes) == (2, 12, 0)
        assert handler.complete_offer(7).boxes == 0  # nothing left to deliver


class TestCompleteLabeling:
    def test_complete_offer_reports_the_boxes_and_units(self, db, jan):
        offer_with_boxes(db, jan, 8, "delivered", "ready_for_labeling", boxes=1)
        handler = quiet(LabelingCompletionHandler(db, ADMIN_ID, "prod", "token"))

        result = handler.complete_offer(8)

        assert (result.boxes, result.units, result.failed_boxes) == (1, 6, 0)
        assert handler.complete_offer(8).units == 0  # nothing left to label

    def test_every_ready_order_is_labeled_and_a_sold_out_offer_completes(self, db, jan):
        offer_with_boxes(db, jan, 8, "delivered", "ready_for_labeling")
        handler = quiet(LabelingCompletionHandler(db, ADMIN_ID, "prod", "token"))

        handler.handle_confirm_complete_labeling(ADMIN_ID, 8, "sup12345")

        assert {o.status for o in db.get_orders_by_offer(8)} == {"labeling_completed"}
        assert db.get_offer(8).status == "completed"
