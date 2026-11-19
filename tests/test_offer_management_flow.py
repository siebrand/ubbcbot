"""Processing a wholesale order and cancelling an offer, against the (mocked) database.

Wholesale: the pending orders are taken oldest first until the ordered boxes are full; the order that only partly
fits is reduced, the rest is cancelled. Boxes with fulfilled orders become "ordered", empty boxes are removed.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from handlers.admin.offer.management import OfferManagementHandler
from models.entities import AuthorizationStatus, Box, Customer, Offer, OfferStatus, Order
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
PRICE = Decimal("2.50")


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    service = DynamoDBService()
    service.create_offer(
        Offer(offer_id=7, name="Pils", price_per_unit=PRICE, wholesale_box_size=6, status=OfferStatus.ACTIVE.value)
    )
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = OfferManagementHandler(db, ADMIN_ID, "prod", "token")
    handler.sent = []
    handler._send_message = Mock(side_effect=lambda chat, text, **kw: handler.sent.append((chat, text)) or {})
    handler.sync_offer_messages = Mock()
    return handler


def customer(db, telegram_id, name, language="nl", is_guest=False):
    return db.create_customer(
        Customer(
            telegram_user_id=telegram_id,
            first_name=name,
            language=language,
            is_guest=is_guest,
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


def order(db, order_id, who, box_id, quantity, minutes, status="pending"):
    created = Order(
        order_id=order_id,
        customer_id=who.customer_id,
        box_id=box_id,
        offer_id=7,
        quantity=quantity,
        unit_price=PRICE,
        total_price=PRICE * quantity,
        status=status,
        created_at=f"2026-11-0{minutes}T10:00:00+00:00",
    )
    assert db.order_repo.create_order(created)
    return created


def box(db, box_id, quantity, status="open"):
    assert db.create_box(Box(box_id=box_id, offer_id=7, max_capacity=6, current_quantity=quantity, status=status))


def messages_to(handler, chat_id) -> list[str]:
    return [text for chat, text in handler.sent if chat == chat_id]


@pytest.fixture
def three_orders(db):
    """b1 is full with Jan (4, oldest) and Piet (2); b2 holds Kees (3, newest)"""
    jan, piet, kees = customer(db, 101, "Jan"), customer(db, 102, "Piet", "en"), customer(db, 103, "Kees")
    box(db, "b1", 6, "full")
    box(db, "b2", 3)
    order(db, "o1", jan, "b1", 4, 1)
    order(db, "o2", piet, "b1", 2, 2)
    order(db, "o3", kees, "b2", 3, 3)
    return SimpleNamespace(jan=jan, piet=piet, kees=kees)


class TestOneBoxForThreeOrders:
    def test_the_oldest_orders_fill_the_box_and_the_rest_is_cancelled(self, db, handler, three_orders):
        assert handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "1"]) == {"status": "success"}

        assert {o: db.get_order(o).status for o in ("o1", "o2", "o3")} == {
            "o1": "ordered",
            "o2": "ordered",
            "o3": "cancelled",
        }
        assert db.get_box("b1").status == "ordered"

    def test_the_cancelled_customer_is_told(self, db, handler, three_orders):
        handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "1"])

        assert len(messages_to(handler, 103)) == 1
        assert messages_to(handler, 101) == messages_to(handler, 102) == []

    def test_the_admin_gets_a_summary(self, db, handler, three_orders):
        handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "1"])

        summary = messages_to(handler, ADMIN_ID)[-1]
        assert "Kees" in summary

    def test_a_full_offer_without_pending_orders_is_sold_out(self, db, handler, three_orders):
        handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "1"])

        assert db.get_offer(7).status == "sold_out"
        handler.sync_offer_messages.assert_called_once_with(7)


class TestAnOrderThatOnlyPartlyFits:
    @pytest.fixture
    def orders(self, db):
        jan, piet = customer(db, 101, "Jan"), customer(db, 102, "Piet", "en")
        box(db, "b1", 4)
        box(db, "b2", 4)
        order(db, "o1", jan, "b1", 4, 1)
        order(db, "o2", piet, "b2", 4, 2)
        return SimpleNamespace(jan=jan, piet=piet)

    def test_it_is_reduced_to_what_is_left(self, db, handler, orders):
        handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "1"])

        reduced = db.get_order("o2")
        assert (reduced.status, reduced.quantity, reduced.total_price) == ("ordered", 2, PRICE * 2)
        assert len(messages_to(handler, 102)) == 1  # Piet is told


class TestInput:
    def test_a_box_count_must_be_positive(self, db, handler):
        assert handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "0"]) == {"status": "invalid_quantity"}

    def test_the_box_count_must_be_a_number(self, db, handler):
        assert handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "veel"]) == {"status": "invalid_format"}

    def test_two_arguments_are_needed(self, db, handler):
        assert handler.handle_confirm_process_wholesale(ADMIN_ID, ["7"]) == {"status": "invalid_args"}


class TestWholesaleSelection:
    def test_offers_with_pending_orders_are_listed_by_name(self, db, handler, three_orders):
        db.create_offer(Offer(offer_id=8, name="Abdij", wholesale_box_size=6, status=OfferStatus.ACTIVE.value))
        db.create_offer(Offer(offer_id=9, name="Zonder", wholesale_box_size=6, status=OfferStatus.ACTIVE.value))
        order(db, "o9", three_orders.jan, "b9", 1, 4)
        db.order_repo.update_order("o9", {"offer_id": 8})

        assert handler.handle_process_wholesale(ADMIN_ID, []) == {"status": "success"}

        text = messages_to(handler, ADMIN_ID)[-1]
        assert text.index("Abdij") < text.index("Pils")
        assert "Zonder" not in text

    def test_no_pending_orders(self, db, handler):
        assert handler.handle_process_wholesale(ADMIN_ID, []) == {"status": "no_offers"}


class TestCancelOffer:
    def test_every_open_order_is_cancelled_its_customer_told_and_the_boxes_removed(self, db, handler, three_orders):
        assert handler.handle_confirm_cancel_offer(ADMIN_ID, ["7"]) == {"status": "success"}

        assert {db.get_order(o).status for o in ("o1", "o2", "o3")} == {"cancelled"}
        assert db.get_boxes_by_offer(7) == []
        assert db.get_offer(7).status == "inactive"
        assert all(len(messages_to(handler, telegram_id)) == 1 for telegram_id in (101, 102, 103))
        handler.sync_offer_messages.assert_called_once_with(7, cancelled=True)

    def test_an_offer_without_orders_is_cancelled_at_once(self, db, handler):
        assert handler.handle_cancel_offer(ADMIN_ID, ["7"]) == {"status": "success"}

        assert db.get_offer(7).status == "inactive"

    def test_an_offer_with_orders_asks_for_confirmation(self, db, handler, three_orders):
        assert handler.handle_cancel_offer(ADMIN_ID, ["7"]) == {"status": "confirmation_required"}

        assert db.get_offer(7).status == "active"
