"""/refill_boxes against the (mocked) database: the proposal, the confirmation, and what the transactions guard."""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.offer.boxes import BoxManagementHandler
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
        Offer(offer_id=7, name="Pils & Co", price_per_unit=PRICE, wholesale_box_size=6, status=OfferStatus.ACTIVE.value)
    )
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = BoxManagementHandler(db, ADMIN_ID, "prod", "token")
    handler.sent = []

    def send(chat, text, **kwargs):
        handler.sent.append((chat, text, kwargs))
        return {"success": True}

    handler._send_message = Mock(side_effect=send)
    handler.sync_offer_messages = Mock()
    return handler


@pytest.fixture
def jan(db):
    return db.create_customer(
        Customer(
            telegram_user_id=42,
            first_name="Jan",
            last_name="Jansen",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


def box(db, box_id, quantity, day, status="open"):
    assert db.create_box(
        Box(
            box_id=box_id,
            offer_id=7,
            max_capacity=6,
            current_quantity=quantity,
            status=status,
            created_at=f"2026-11-0{day}T09:00:00+00:00",
        )
    )


def order(db, order_id, who, box_id, quantity, status="pending"):
    assert db.order_repo.create_order(
        Order(
            order_id=order_id,
            customer_id=who.customer_id,
            box_id=box_id,
            offer_id=7,
            quantity=quantity,
            unit_price=PRICE,
            total_price=PRICE * quantity,
            status=status,
        )
    )


@pytest.fixture
def gaps(db, jan):
    """Box A (first) lost two units to a cancellation; box B (later) holds one order of two"""
    box(db, "box-aaaa-1", 4, day=1)
    box(db, "box-bbbb-2", 2, day=2)
    order(db, "order-1", jan, "box-aaaa-1", 4)
    order(db, "order-2", jan, "box-aaaa-1", 2, status="cancelled")
    order(db, "order-3", jan, "box-bbbb-2", 2)


class TestProposal:
    def test_the_moves_are_shown_with_a_confirm_button(self, handler, gaps):
        assert handler.handle_refill_boxes(ADMIN_ID, ["7"]) == {"status": "confirmation_required", "moves": 1}

        _chat, text, kwargs = handler.sent[-1]
        assert "Pils &amp; Co" in text
        assert "2x Jan J: colli box-bbbb → colli box-aaaa" in text
        assert "Colli leeg: 1. Colli in gebruik: 2 → 1." in text
        assert kwargs["parse_mode"] == "HTML"
        buttons = [b["callback_data"] for row in kwargs["reply_markup"]["inline_keyboard"] for b in row]
        assert buttons == ["refill_boxes_confirm_7", "cancel_action"]

    def test_the_proposal_changes_nothing(self, handler, db, gaps):
        handler.handle_refill_boxes(ADMIN_ID, ["7"])

        assert db.get_order("order-3").box_id == "box-bbbb-2"
        assert db.get_box("box-bbbb-2").current_quantity == 2

    def test_nothing_to_move_is_said(self, handler, db, jan):
        box(db, "box-aaaa-1", 6, day=1, status="full")
        box(db, "box-bbbb-2", 2, day=2)

        assert handler.handle_refill_boxes(ADMIN_ID, ["7"]) == {"status": "nothing_to_move"}

    @pytest.mark.parametrize("status", [OfferStatus.COMPLETED.value, OfferStatus.INACTIVE.value])
    def test_a_completed_or_inactive_offer_is_left_alone(self, handler, db, gaps, status):
        db.update_offer(7, {"status": status})

        assert handler.handle_refill_boxes(ADMIN_ID, ["7"]) == {"status": "offer_closed"}
        assert handler.handle_confirm_refill_boxes(ADMIN_ID, 7) == {"status": "offer_closed"}
        assert db.get_order("order-3").box_id == "box-bbbb-2"

    @pytest.mark.parametrize("args,status", [([], "invalid_args"), (["zeven"], "invalid_format")])
    def test_without_an_offer_id_the_usage_is_shown(self, handler, args, status):
        assert handler.handle_refill_boxes(ADMIN_ID, args) == {"status": status}

    def test_an_unknown_offer_is_reported(self, handler):
        assert handler.handle_refill_boxes(ADMIN_ID, ["99"]) == {"status": "offer_not_found"}


class TestConfirmation:
    def test_the_order_moves_and_the_empty_box_is_removed(self, handler, db, gaps):
        result = handler.handle_confirm_refill_boxes(ADMIN_ID, 7)

        assert result == {"status": "refilled", "moved": 1, "planned": 1, "deleted": 1}
        assert db.get_order("order-3").box_id == "box-aaaa-1"
        first = db.get_box("box-aaaa-1")
        assert (first.current_quantity, first.status) == (6, "full")
        assert db.get_box("box-bbbb-2") is None
        handler.sync_offer_messages.assert_called_once_with(7)
        assert "1 bestellingen verplaatst, 1 lege colli verwijderd" in handler.sent[-1][1]

    def test_the_plan_is_made_again_at_the_confirmation(self, handler, db, gaps, jan):
        handler.handle_refill_boxes(ADMIN_ID, ["7"])
        # Meanwhile a new order takes the room in box A
        order(db, "order-4", jan, "box-aaaa-1", 2)
        assert db.increment_box_quantity("box-aaaa-1", 2, 6)

        assert handler.handle_confirm_refill_boxes(ADMIN_ID, 7) == {"status": "nothing_to_move"}
        assert db.get_order("order-3").box_id == "box-bbbb-2"


class TestTheMoveTransaction:
    def test_a_move_that_would_overfill_the_box_changes_nothing(self, db, gaps):
        assert not db.move_order_to_box("order-3", 2, "box-bbbb-2", "box-aaaa-1", to_max_capacity=5)

        assert db.get_order("order-3").box_id == "box-bbbb-2"
        assert db.get_box("box-aaaa-1").current_quantity == 4
        assert db.get_box("box-bbbb-2").current_quantity == 2

    def test_an_order_that_is_no_longer_pending_stays(self, db, gaps):
        db.update_order("order-3", {"status": "ordered"})

        assert not db.move_order_to_box("order-3", 2, "box-bbbb-2", "box-aaaa-1", to_max_capacity=6)
        assert db.get_box("box-aaaa-1").current_quantity == 4

    def test_a_box_ordered_at_the_wholesaler_meanwhile_is_not_touched(self, db, gaps):
        db.update_box("box-aaaa-1", {"status": "ordered"})

        assert not db.move_order_to_box("order-3", 2, "box-bbbb-2", "box-aaaa-1", to_max_capacity=6)
        assert db.get_order("order-3").box_id == "box-bbbb-2"

    def test_an_empty_box_that_got_an_order_meanwhile_is_kept(self, db, gaps):
        box(db, "box-cccc-3", 0, day=3)
        assert db.increment_box_quantity("box-cccc-3", 1, 6)

        assert not db.delete_box_if_empty("box-cccc-3")
        assert db.get_box("box-cccc-3") is not None
