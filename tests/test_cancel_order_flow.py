"""/cancel_order end to end, with the real handlers: list the orders, tap one, confirm, give a reason.

The buttons of this flow once did nothing: the route called AdminOrderCommands.handle_cancel_order_by_id, which did not
exist, and the error was only logged. The button tests use mocks, so this flow is also run against the real classes.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from handlers.admin.order_commands import AdminOrderCommands
from handlers.base_handler import BaseHandler
from models.entities import AuthorizationStatus, Box, BoxStatus, Customer, Offer, OfferStatus, Order
from services.callback_handler import CallbackHandler
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473


@dataclass
class SentMessage:
    chat_id: int
    text: str
    buttons: list[str] = field(default_factory=list)


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def order(db):
    assert db.create_offer(
        Offer(
            offer_id=7,
            name="Pils & Co",
            price_per_unit=Decimal("2.50"),
            wholesale_box_size=12,
            status=OfferStatus.ACTIVE.value,
        )
    )
    customer = db.create_customer(
        Customer(
            telegram_user_id=4242,
            username="siebrand",
            first_name="Siebrand",
            last_name="Mazeland",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )
    box = db.create_box(Box(offer_id=7, max_capacity=12, current_quantity=2, status=BoxStatus.OPEN.value))
    created = Order(
        customer_id=customer.customer_id,
        box_id=box.box_id,
        offer_id=7,
        quantity=2,
        unit_price=Decimal("2.50"),
        total_price=Decimal("5.00"),
        status="ordered",
    )
    assert db.order_repo.create_order(created)
    return created


@pytest.fixture
def flow(db):
    """The real admin order handler and callback handler. Only what talks to Telegram is replaced."""
    sent: list[SentMessage] = []

    def record(chat_id, text, reply_markup=None, **_):
        buttons = [b["callback_data"] for row in (reply_markup or {}).get("inline_keyboard", []) for b in row]
        sent.append(SentMessage(chat_id, text, buttons))
        return {"success": True, "message_id": 1}

    with patch.object(BaseHandler, "_send_message", lambda self, *args, **kwargs: record(*args, **kwargs)):
        admin_order = AdminOrderCommands(db, ADMIN_ID, "test", "token")
        callbacks = CallbackHandler(db, ADMIN_ID, "test", "token", {"admin_order": admin_order}, Mock())
        callbacks._send_message = record
        callbacks._answer_callback_query = Mock()
        callbacks._edit_message_remove_keyboard = Mock()
        callbacks._delete_message = Mock()
        yield SimpleNamespace(admin_order=admin_order, callbacks=callbacks, sent=sent)


def tap(flow, data):
    query = {"id": "q", "from": {"id": ADMIN_ID}, "message": {"chat": {"id": ADMIN_ID}, "message_id": 9}, "data": data}
    return flow.callbacks.handle_callback_query(query)


class TestCancelOrderFlow:
    def test_the_order_of_a_customer_is_listed_with_a_button(self, flow, order):
        flow.admin_order.handle_cancel_order(ADMIN_ID, ["siebran"])

        listing = flow.sent[-1]
        assert "Mazeland" in listing.text
        assert f"cancel_order_confirm_{order.order_id}" in listing.buttons

    def test_tapping_the_order_asks_for_confirmation(self, flow, order):
        result = tap(flow, f"cancel_order_confirm_{order.order_id}")

        assert result == {"status": "handled_by_router"}
        confirmation = flow.sent[-1]
        assert order.order_id in confirmation.text
        assert f"request_cancel_reason_{order.order_id}" in confirmation.buttons
        assert "cancel_action" in confirmation.buttons  # keep the order

    def test_confirming_asks_for_a_reason(self, flow, db, order):
        result = tap(flow, f"request_cancel_reason_{order.order_id}")

        assert result == {"status": "handled_by_router"}
        context = db.get_edit_context_by_chat_id(ADMIN_ID)
        assert (context.edit_type, context.entity_id) == ("cancel_order_reason", order.order_id)
        assert flow.sent  # the admin is asked for the reason

    def test_the_reason_cancels_the_order_and_frees_the_box(self, flow, db, order):
        flow.admin_order.handle_confirm_cancel_with_reason(ADMIN_ID, order.order_id, "Customer asked")

        assert db.get_order(order.order_id).status == "cancelled"
        assert db.get_box(order.box_id).current_quantity == 0

    def test_an_order_that_does_not_exist_is_reported_not_ignored(self, flow):
        result = tap(flow, "cancel_order_confirm_does-not-exist")

        assert result == {"status": "handled_by_router"}
        assert flow.sent, "the admin must get an answer"

    def test_next_page_of_a_long_list_works_with_a_real_customer_id(self, flow, db, order):
        """The page buttons carry the customer ID, a UUID with hyphens: the route must match it"""
        for _ in range(11):  # 12 orders, 10 per page
            assert db.order_repo.create_order(
                Order(
                    customer_id=order.customer_id,
                    box_id=order.box_id,
                    offer_id=7,
                    quantity=1,
                    unit_price=Decimal("2.50"),
                    total_price=Decimal("2.50"),
                    status="ordered",
                )
            )
        flow.admin_order.handle_cancel_order(ADMIN_ID, ["siebran"])
        first_page = flow.sent[-1]
        next_button = f"cancel_orders_page_{order.customer_id}_2"
        assert "Pagina 1/2" in first_page.text
        assert next_button in first_page.buttons

        result = tap(flow, next_button)

        assert result == {"status": "handled_by_router"}
        second_page = flow.sent[-1]
        assert "Pagina 2/2" in second_page.text
        assert sum(1 for button in second_page.buttons if button.startswith("cancel_order_confirm_")) == 2
        assert f"cancel_orders_page_{order.customer_id}_1" in second_page.buttons  # and back


def _order_placed_at(order, placed_at, quantity=1):
    return Order(
        customer_id=order.customer_id,
        box_id=order.box_id,
        offer_id=7,
        quantity=quantity,
        unit_price=Decimal("2.50"),
        total_price=Decimal("2.50") * quantity,
        status="ordered",
        created_at=placed_at,
    )


class TestTheOrderOfTheList:
    """The newest order is first: that is usually the one an admin wants to cancel"""

    def _listed_order_ids(self, flow, data=None):
        if data is None:
            flow.admin_order.handle_cancel_order(ADMIN_ID, ["siebran"])
        else:
            tap(flow, data)
        return [b.removeprefix("cancel_order_confirm_") for b in flow.sent[-1].buttons if "confirm_" in b]

    def test_orders_are_listed_newest_first_whatever_the_order_they_were_stored_in(self, flow, db, order):
        oldest = _order_placed_at(order, datetime(2026, 11, 1, 10, 0, tzinfo=UTC))
        newest = _order_placed_at(order, datetime(2026, 11, 15, 18, 30, tzinfo=UTC))
        middle = _order_placed_at(order, datetime(2026, 11, 8, 9, 15, tzinfo=UTC))
        order.created_at = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)  # the fixture order, between middle and newest
        assert db.order_repo.create_order(order)
        for created in (middle, newest, oldest):  # stored in a deliberately mixed order
            assert db.order_repo.create_order(created)

        listed = self._listed_order_ids(flow)

        assert listed == [newest.order_id, order.order_id, middle.order_id, oldest.order_id]

    def test_the_pages_follow_that_order(self, flow, db, order):
        order.created_at = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)  # the oldest of 12
        assert db.order_repo.create_order(order)
        newer = [_order_placed_at(order, datetime(2026, 11, 2 + day, 8, 0, tzinfo=UTC)) for day in range(11)]
        for created in reversed(newer):
            assert db.order_repo.create_order(created)

        first = self._listed_order_ids(flow)
        second = self._listed_order_ids(flow, f"cancel_orders_page_{order.customer_id}_2")

        assert first == [o.order_id for o in reversed(newer)][:10]  # the 10 newest
        assert second == [newer[0].order_id, order.order_id]  # then the next newest and the oldest

    def test_orders_placed_in_the_same_second_keep_a_stable_order(self, flow, db, order):
        same_moment = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
        twins = [_order_placed_at(order, same_moment, quantity=q) for q in (1, 2, 3)]
        order.created_at = datetime(2026, 11, 1, tzinfo=UTC)
        assert db.order_repo.create_order(order)
        for created in twins:
            assert db.order_repo.create_order(created)

        first_time = self._listed_order_ids(flow)
        second_time = self._listed_order_ids(flow)

        assert first_time == second_time
        assert first_time[-1] == order.order_id  # the older one is still last
