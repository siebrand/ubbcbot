"""The state an instant offer is in after it is created: an active offer whose only box is delivered and has free
units. The bot already handles this state (it also occurs after a partial wholesale delivery); these tests pin that
behavior, which instant orders rely on (instant-orders-design.md, IO-2)."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from handlers.admin.labeling_completion_handler import LabelingCompletionHandler
from handlers.admin.order.order_placement import OrderPlacement
from handlers.base_handler import BaseHandler
from handlers.customer.order_commands import CustomerOrderCommands
from models.entities import AuthorizationStatus, Box, BoxStatus, Customer, NotificationMessage, Offer, Order
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
GROUP_ID = -100777
PRICE = Decimal("3.00")


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


def add_customer(db, telegram_id, name):
    return db.create_customer(
        Customer(telegram_user_id=telegram_id, first_name=name, authorization_status=AuthorizationStatus.APPROVED.value)
    )


@pytest.fixture
def instant(db):
    """Offer 7 (box size 4) with a delivered box that holds one ready_for_labeling order, and a tracked group post"""
    offer = Offer(offer_id=7, name="Tripel", price_per_unit=PRICE, wholesale_box_size=4, status="active")
    assert db.create_offer(offer)
    box = db.create_box(Box(offer_id=7, max_capacity=4, current_quantity=1, status=BoxStatus.DELIVERED.value))
    first = add_customer(db, 101, "Jan")
    order = Order(
        customer_id=first.customer_id,
        box_id=box.box_id,
        offer_id=7,
        quantity=1,
        received_quantity=1,
        unit_price=PRICE,
        total_price=PRICE,
        status="ready_for_labeling",
        placed_by_admin=True,
    )
    assert db.order_repo.create_order(order)
    assert db.create_notification_message(NotificationMessage(offer_id=7, chat_id=GROUP_ID, message_id=55))
    return SimpleNamespace(box=box, order=order, piet=add_customer(db, 102, "Piet"))


@pytest.fixture
def edits():
    """The edits of tracked messages: (chat, message id, reply markup)"""
    calls: list = []

    def edit(self, chat_id, message_id, text, parse_mode=None, reply_markup=None):
        calls.append((chat_id, message_id, reply_markup))
        return {"success": True}

    with (
        patch.object(BaseHandler, "_edit_message_text", edit),
        patch.object(BaseHandler, "_send_message", return_value={"success": True, "message_id": 1}),
        patch.object(BaseHandler, "_get_bot_username", return_value="ubbc_bot"),
    ):
        yield calls


@pytest.fixture
def customer_orders(db, edits):
    return CustomerOrderCommands(db, ADMIN_ID, "test", "token")


def buttons(markup) -> list[str]:
    return [b.get("callback_data", b.get("url", "")) for row in (markup or {}).get("inline_keyboard", []) for b in row]


class TestOrdersOnADeliveredBoxWithFreeUnits:
    def test_a_customer_order_goes_into_the_delivered_box_ready_for_labeling(self, db, customer_orders, instant):
        result = customer_orders.handle_create_order(102, 102, ["7", "2"])

        assert result["status"] == "success"
        [order] = db.get_orders_by_customer(instant.piet.customer_id)
        assert (order.box_id, order.status, order.received_quantity) == (instant.box.box_id, "ready_for_labeling", 2)
        assert [b.box_id for b in db.get_boxes_by_offer(7)] == [instant.box.box_id]  # no box created
        assert db.get_box(instant.box.box_id).current_quantity == 3
        assert db.get_offer(7).status == "active"

    def test_the_order_that_fills_the_box_sells_the_offer_out_and_edits_the_group_post(
        self, db, customer_orders, instant, edits
    ):
        customer_orders.handle_create_order(102, 102, ["7", "3"])

        assert db.get_offer(7).status == "sold_out"
        [(chat, message_id, markup)] = [e for e in edits if e[0] == GROUP_ID]
        assert message_id == 55
        assert not any(b.startswith("order_") or "start=order" in b for b in buttons(markup))

    def test_the_admin_path_gives_the_same_result(self, db, instant, edits):
        placement = OrderPlacement(db, ADMIN_ID, "test", "token")

        result = placement.handle_create_order_for(ADMIN_ID, ADMIN_ID, ["Piet", "7", "3"])

        assert result == {"status": "success"}
        [order] = db.get_orders_by_customer(instant.piet.customer_id)
        assert (order.box_id, order.status, order.received_quantity) == (instant.box.box_id, "ready_for_labeling", 3)
        assert len(db.get_boxes_by_offer(7)) == 1
        assert db.get_offer(7).status == "sold_out"

    def test_a_customer_who_asks_for_more_than_the_free_units_gets_what_is_left(self, db, customer_orders, instant):
        """Planning item 5: the free units are ordered, the rest is the shortfall, and no box is added"""
        result = customer_orders.handle_create_order(102, 102, ["7", "4"])

        assert result == {"status": "success"}
        [order] = db.get_orders_by_customer(instant.piet.customer_id)
        assert (order.box_id, order.quantity, order.status) == (instant.box.box_id, 3, "ready_for_labeling")
        assert db.get_box(instant.box.box_id).current_quantity == 4
        assert len(db.get_boxes_by_offer(7)) == 1


class TestLabelingCompletesOnlyASoldOutOffer:
    @pytest.fixture
    def labeling(self, db, edits):
        handler = LabelingCompletionHandler(db, ADMIN_ID, "test", "token")
        handler.sync_offer_messages = Mock()
        return handler

    def test_an_active_offer_with_free_units_stays_active(self, db, instant, labeling):
        db.update_order(instant.order.order_id, {"status": "labeling_completed"})

        labeling._check_and_update_offer_status(7)

        assert db.get_offer(7).status == "active"

    def test_a_sold_out_offer_is_completed_once_everything_is_labeled(self, db, instant, labeling):
        db.update_offer(7, {"status": "sold_out"})
        db.update_order(instant.order.order_id, {"status": "labeling_completed"})

        labeling._check_and_update_offer_status(7)

        assert db.get_offer(7).status == "completed"
