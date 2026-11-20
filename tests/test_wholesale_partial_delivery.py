"""A wholesale delivery with fewer units than ordered, from the delivery to the payment message.

Against the (mocked) database: what the delivery service writes is what the delivery overview reads.
"""

import json
from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler
from models.entities import AuthorizationStatus, Box, Customer, Offer, OfferStatus, Order, OrderStatus
from services.box_status_manager import BoxStatusManager
from services.database import DynamoDBService
from services.user_cache import UserCache
from services.wholesaler_delivery import WholesalerDeliveryService

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
            wholesale_box_size=6,
            status=OfferStatus.SOLD_OUT.value,
        )
    )
    assert service.create_box(Box(box_id=BOX_ID, offer_id=7, max_capacity=6, current_quantity=6, status="ordered"))
    yield service
    UserCache.invalidate_cache()


def customer(db, telegram_user_id: int, name: str) -> Customer:
    return db.create_customer(
        Customer(
            telegram_user_id=telegram_user_id,
            first_name=name,
            location="Utrecht",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


def order(db, customer: Customer, quantity: int) -> Order:
    created = db.order_repo.create_order(
        Order(
            customer_id=customer.customer_id,
            box_id=BOX_ID,
            offer_id=7,
            quantity=quantity,
            unit_price=Decimal("2.50"),
            total_price=Decimal("2.50") * quantity,
            status=OrderStatus.ORDERED.value,
        )
    )
    assert created
    return created


def deliver(db, units: int, is_delayed: bool) -> None:
    service = WholesalerDeliveryService(db, BoxStatusManager(db), ADMIN_ID)
    assert service.process_wholesaler_delivery(BOX_ID, units, is_delayed)


def label(db) -> None:
    """What labeling does: every order that is ready for labeling is labeled"""
    for o in db.get_orders_by_box(BOX_ID):
        if o.status == OrderStatus.READY_FOR_LABELING.value:
            assert db.update_order(o.order_id, {"status": OrderStatus.LABELING_COMPLETED.value})


def overview(db) -> tuple[DeliveryOverviewHandler, list[dict]]:
    handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"status": "sent"})
    handler.start_send_overviews(ADMIN_ID)
    context = db.get_edit_context_by_chat_id(ADMIN_ID)
    return handler, json.loads(context.entity_id)["customers_data"]


class TestTheCustomersAreTold:
    """A customer whose units come later, or not at all, hears it when the delivery is processed (audit 4, B2)"""

    @staticmethod
    def process(db, units: int, is_delayed: bool) -> list[tuple[int, str]]:
        handler = WholesaleDeliveryHandler(db, ADMIN_ID, "prod", "token")
        handler._send_message = Mock(return_value={"success": True})
        handler._check_offer_status_after_change = Mock()
        assert handler._process_box_delivery(BOX_ID, units, is_delayed)
        return [(c.args[0], c.args[1]) for c in handler._send_message.call_args_list]

    @staticmethod
    def two_customers(db) -> tuple[Order, Order]:
        jan, piet = customer(db, 101, "Jan"), customer(db, 102, "Piet")
        return order(db, jan, 3), order(db, piet, 3)

    @pytest.mark.parametrize(
        ("is_delayed", "key"), [(True, "wholesale_units_delayed"), (False, "wholesale_units_cancelled")]
    )
    def test_each_customer_short_of_units_gets_one_message_with_their_missing_units(self, db, is_delayed, key):
        first, second = self.two_customers(db)

        messages = self.process(db, 4, is_delayed)

        # Who is filled first is the order of the orders read: one customer misses 2 units, the other 3 or none
        missing = {
            o.customer_id: o.quantity - (db.get_order(o.order_id).received_quantity or 0) for o in (first, second)
        }
        if not is_delayed:
            missing = {o.customer_id: 0 for o in (first, second)}
            for o in db.get_orders_by_box(BOX_ID):
                if o.status == OrderStatus.CANCELLED.value:
                    missing[o.customer_id] += o.quantity
        telegram_ids = {first.customer_id: 101, second.customer_id: 102}
        expected = sorted(
            (telegram_ids[cid], TelegramText.of(db, key, telegram_ids[cid], units=units))
            for cid, units in missing.items()
            if units
        )
        assert sorted(messages) == expected
        assert sum(missing.values()) == 2

    def test_a_full_delivery_tells_nobody(self, db):
        self.two_customers(db)

        assert self.process(db, 6, is_delayed=False) == []

    def test_a_guest_is_not_messaged(self, db):
        guest = db.create_customer(
            Customer(telegram_user_id=-2, first_name="Gast", is_guest=True, authorization_status="approved")
        )
        order(db, guest, 6)

        assert self.process(db, 4, is_delayed=False) == []


class TelegramText:
    @staticmethod
    def of(db, key: str, telegram_id: int, units: int) -> str:
        handler = WholesaleDeliveryHandler(db, ADMIN_ID, "prod", "token")
        return handler._t(key, telegram_id, units=units, product="[7] Pils")


class TestRestDelayed:
    """The received units are labeled and charged; the late ones stay ordered until they arrive (audit 5, A1)"""

    def test_the_received_units_go_to_labeling_and_the_rest_stays_ordered(self, db):
        jan = customer(db, 101, "Jan")
        filled = order(db, jan, 6)

        deliver(db, 4, is_delayed=True)

        orders = {o.order_id: o for o in db.get_orders_by_box(BOX_ID)}
        kept = orders[filled.order_id]
        assert (kept.status, kept.quantity, kept.received_quantity, kept.total_price) == (
            OrderStatus.READY_FOR_LABELING.value,
            4,
            4,
            Decimal("10"),
        )
        (rest,) = [o for o in orders.values() if o.order_id != filled.order_id]
        assert (rest.status, rest.quantity, rest.received_quantity, rest.total_price) == (
            OrderStatus.ORDERED.value,
            2,
            0,
            Decimal("5"),
        )
        assert db.get_box(BOX_ID).status == "ordered"

    def test_the_received_units_are_charged_now_and_the_late_ones_when_they_come(self, db):
        jan = customer(db, 101, "Jan")
        order(db, jan, 6)

        deliver(db, 4, is_delayed=True)
        label(db)
        handler, customers_data = overview(db)
        first = handler._build_delivery_message_payload(customers_data[0], "https://pay.example")["message"]
        assert "4x [7] Pils — €10.00" in first

        handler.lambda_client = Mock()
        handler.handle_payment_link_input(
            ADMIN_ID, "https://pay.example", db.get_edit_context_by_chat_id(ADMIN_ID).entity_id
        )
        deliver(db, 2, is_delayed=False)
        label(db)
        handler, customers_data = overview(db)
        later = handler._build_delivery_message_payload(customers_data[0], "https://pay.example")["message"]

        assert "2x [7] Pils — €5.00" in later
        assert db.get_box(BOX_ID).status == "delivered"

    def test_an_order_that_changed_since_it_was_read_is_not_split(self, db):
        jan = customer(db, 101, "Jan")
        stale = order(db, jan, 6)
        assert db.update_order(stale.order_id, {"status": OrderStatus.CANCELLED.value})
        rest = Order(customer_id=jan.customer_id, box_id=BOX_ID, offer_id=7, quantity=2, status="ordered")

        assert not db.split_order(stale, 4, OrderStatus.READY_FOR_LABELING.value, rest)

        (only,) = db.get_orders_by_box(BOX_ID)
        assert (only.order_id, only.status, only.quantity) == (stale.order_id, OrderStatus.CANCELLED.value, 6)

    def test_a_split_that_is_refused_leaves_the_order_and_tells_nobody(self, db):
        jan = customer(db, 101, "Jan")
        order(db, jan, 6)
        db.split_order = Mock(return_value=False)

        messages = TestTheCustomersAreTold.process(db, 4, is_delayed=True)

        assert messages == []
        (only,) = db.get_orders_by_box(BOX_ID)
        assert (only.status, only.quantity) == (OrderStatus.ORDERED.value, 6)
        assert db.get_box(BOX_ID).status == "ordered"

    def test_orders_beyond_the_received_units_stay_ordered_whole(self, db):
        jan, piet = customer(db, 101, "Jan"), customer(db, 102, "Piet")
        order(db, jan, 3), order(db, piet, 3)

        deliver(db, 3, is_delayed=True)

        statuses = sorted(o.status for o in db.get_orders_by_box(BOX_ID))
        assert statuses == [OrderStatus.ORDERED.value, OrderStatus.READY_FOR_LABELING.value]
        assert len(db.get_orders_by_box(BOX_ID)) == 2


class TestRestCancelled:
    def test_the_received_units_are_charged_and_nothing_is_said_to_be_delayed(self, db):
        jan = customer(db, 101, "Jan")
        filled = order(db, jan, 6)

        deliver(db, 4, is_delayed=False)
        label(db)
        handler, customers_data = overview(db)

        assert customers_data[0]["delivered_order_ids"] == [filled.order_id]
        assert customers_data[0]["delayed_order_ids"] == []
        message = handler._build_delivery_message_payload(customers_data[0], "https://pay.example")["message"]
        assert "4x [7] Pils — €10.00" in message
        assert handler._t("will_arrive_later", 101) not in message

    def test_the_filled_order_holds_the_received_units_and_the_rest_is_a_cancelled_order(self, db):
        jan = customer(db, 101, "Jan")
        filled = order(db, jan, 6)

        deliver(db, 4, is_delayed=False)

        orders = {o.order_id: o for o in db.get_orders_by_box(BOX_ID)}
        assert (orders[filled.order_id].quantity, orders[filled.order_id].total_price) == (4, Decimal("10"))
        assert orders[filled.order_id].received_quantity == 4
        (rest,) = [o for o in orders.values() if o.order_id != filled.order_id]
        assert (rest.status, rest.quantity, rest.total_price) == (OrderStatus.CANCELLED.value, 2, Decimal("5"))

    def test_orders_beyond_the_received_units_are_cancelled_and_the_others_charged_in_full(self, db):
        jan, piet = customer(db, 101, "Jan"), customer(db, 102, "Piet")
        first, second = order(db, jan, 3), order(db, piet, 3)

        deliver(db, 3, is_delayed=False)

        statuses = {o.order_id: o.status for o in db.get_orders_by_box(BOX_ID)}
        filled, cancelled = (first, second) if statuses[first.order_id] != "cancelled" else (second, first)
        assert statuses[filled.order_id] == OrderStatus.READY_FOR_LABELING.value
        assert statuses[cancelled.order_id] == OrderStatus.CANCELLED.value
        assert db.get_order(filled.order_id).total_price == Decimal("7.5")
