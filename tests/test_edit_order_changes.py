"""/edit_order against the real classes and a (moto) database: what a status, box or price edit does to the order,
its box and the money (audit 6, A3, A4, B2). Only what talks to Telegram is replaced."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from handlers.admin.order.order_editing import OrderEditing
from handlers.base_handler import BaseHandler
from models.entities import AuthorizationStatus, Box, BoxStatus, Customer, Offer, Order
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def sent():
    messages: list[tuple[str, list[str]]] = []

    def record(self, chat_id, text, reply_markup=None, **_):
        buttons = [b["callback_data"] for row in (reply_markup or {}).get("inline_keyboard", []) for b in row]
        messages.append((text, buttons))
        return {"success": True, "message_id": 1}

    with patch.object(BaseHandler, "_send_message", record):
        yield messages


@pytest.fixture
def editing(db, sent):
    return OrderEditing(db, ADMIN_ID, "test", "token")


@pytest.fixture
def customer(db):
    assert db.create_offer(
        Offer(offer_id=7, name="Pils", price_per_unit=Decimal("2.50"), wholesale_box_size=6, status="active")
    )
    return db.create_customer(
        Customer(
            telegram_user_id=4242,
            username="siebrand",
            first_name="Siebrand",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


def make_box(db, quantity, status=BoxStatus.OPEN.value, capacity=6):
    return db.create_box(Box(offer_id=7, max_capacity=capacity, current_quantity=quantity, status=status))


def make_order(db, customer, box, quantity=2, status="pending", **kw):
    order = Order(
        customer_id=customer.customer_id,
        box_id=box.box_id,
        offer_id=7,
        quantity=quantity,
        unit_price=Decimal("2.50"),
        total_price=Decimal("2.50") * quantity,
        status=status,
        **kw,
    )
    assert db.order_repo.create_order(order)
    return order


def status_buttons(sent):
    """The statuses offered: edit_order_setstatus_<short order id>_<status>"""
    return [b.split("_", 4)[4] for b in sent[-1][1] if b.startswith("edit_order_setstatus_")]


def box_buttons(sent):
    """The boxes offered: edit_order_setbox_<short order id>_<short box id>"""
    return [b.rsplit("_", 1)[1] for b in sent[-1][1] if b.startswith("edit_order_setbox_")]


class TestMovingAnOrderToAnotherBox:
    """Audit 6, A4: the order and both boxes in one write, only where the move makes sense"""

    def test_a_pending_order_moves_with_its_units(self, db, editing, customer):
        old = make_box(db, 6, status=BoxStatus.FULL.value)
        new = make_box(db, 4)
        order = make_order(db, customer, old)

        result = editing.apply_box(ADMIN_ID, order.order_id, new.box_id[:8])

        assert result == {"status": "edit_order_box_success"}
        assert db.get_order(order.order_id).box_id == new.box_id
        assert (db.get_box(old.box_id).current_quantity, db.get_box(old.box_id).status) == (4, "open")
        assert (db.get_box(new.box_id).current_quantity, db.get_box(new.box_id).status) == (6, "full")

    def test_an_order_that_changed_since_it_was_read_leaves_both_boxes_as_they_were(self, db, editing, customer):
        old = make_box(db, 2)
        new = make_box(db, 0)
        order = make_order(db, customer, old)
        stale = db.get_order(order.order_id)
        db.update_order(order.order_id, {"status": "cancelled"})  # cancelled in between

        ok, _key = editing._apply_box_change(stale, new.box_id)

        assert not ok
        assert db.get_box(old.box_id).current_quantity == 2
        assert db.get_box(new.box_id).current_quantity == 0
        assert db.get_order(order.order_id).box_id == old.box_id

    def test_a_pending_order_is_not_moved_into_a_box_ordered_at_the_wholesaler(self, db, editing, customer, sent):
        old = make_box(db, 2)
        ordered = make_box(db, 0, status=BoxStatus.ORDERED.value)
        order = make_order(db, customer, old)

        editing.show_box_options(ADMIN_ID, order.order_id)
        offered = box_buttons(sent)
        result = editing.apply_box(ADMIN_ID, order.order_id, ordered.box_id[:8])

        assert ordered.box_id[:8] not in offered
        assert result == {"status": "edit_failed"}
        assert db.get_box(ordered.box_id).current_quantity == 0
        assert db.get_order(order.order_id).box_id == old.box_id

    def test_an_ordered_order_moves_between_ordered_boxes_only(self, db, editing, customer, sent):
        old = make_box(db, 2, status=BoxStatus.ORDERED.value)
        other_ordered = make_box(db, 0, status=BoxStatus.ORDERED.value)
        open_box = make_box(db, 0)
        order = make_order(db, customer, old, status="ordered")

        editing.show_box_options(ADMIN_ID, order.order_id)

        assert box_buttons(sent) == [other_ordered.box_id[:8]]
        assert editing.apply_box(ADMIN_ID, order.order_id, open_box.box_id[:8]) == {"status": "edit_failed"}
        assert editing.apply_box(ADMIN_ID, order.order_id, other_ordered.box_id[:8]) == {
            "status": "edit_order_box_success"
        }
        assert db.get_box(other_ordered.box_id).current_quantity == 2
        assert db.get_box(old.box_id).current_quantity == 0

    def test_a_delivered_order_is_not_moved(self, db, editing, customer, sent):
        old = make_box(db, 2, status=BoxStatus.DELIVERED.value)
        new = make_box(db, 0)
        order = make_order(db, customer, old, status="ready_for_labeling")

        result = editing.apply_box(ADMIN_ID, order.order_id, new.box_id[:8])

        assert result == {"status": "edit_failed"}
        assert db.get_box(new.box_id).current_quantity == 0
        assert db.get_box(old.box_id).current_quantity == 2


class TestTheStatusEditKeepsTheBoxRight:
    """Audit 6, A3: crossing `cancelled` is a cancel, the money statuses are left to the payment flow"""

    def test_editing_a_pending_order_to_cancelled_frees_its_box(self, db, editing, customer):
        box = make_box(db, 2)
        order = make_order(db, customer, box)

        result = editing.apply_status(ADMIN_ID, order.order_id, "cancelled")

        assert result == {"status": "edit_order_status_success"}
        assert db.get_order(order.order_id).status == "cancelled"
        assert db.get_box(box.box_id).current_quantity == 0

    def test_a_cancelled_order_is_not_brought_back(self, db, editing, customer):
        box = make_box(db, 6, status=BoxStatus.FULL.value)  # its room went to other orders
        order = make_order(db, customer, box, status="cancelled")

        result = editing.apply_status(ADMIN_ID, order.order_id, "pending")

        assert result == {"status": "edit_failed"}
        assert db.get_order(order.order_id).status == "cancelled"
        assert db.get_box(box.box_id).current_quantity == 6

    @pytest.mark.parametrize("status", ["pending", "ordered", "labeling_completed"])
    def test_awaiting_payment_is_not_set_by_hand(self, db, editing, customer, status):
        box = make_box(db, 2, status=BoxStatus.DELIVERED.value)
        order = make_order(db, customer, box, status=status)

        result = editing.apply_status(ADMIN_ID, order.order_id, "awaiting_payment")

        assert result == {"status": "edit_failed"}
        assert db.get_order(order.order_id).status == status

    def test_an_order_awaiting_payment_with_credit_does_not_go_back(self, db, editing, customer):
        box = make_box(db, 2, status=BoxStatus.DELIVERED.value)
        order = make_order(db, customer, box, status="awaiting_payment", credit_applied=Decimal("3.00"))

        result = editing.apply_status(ADMIN_ID, order.order_id, "labeling_completed")

        assert result == {"status": "edit_failed"}
        assert db.get_order(order.order_id).status == "awaiting_payment"

    def test_an_order_awaiting_payment_can_be_marked_paid(self, db, editing, customer):
        box = make_box(db, 2, status=BoxStatus.DELIVERED.value)
        order = make_order(db, customer, box, status="awaiting_payment", credit_applied=Decimal("3.00"))

        result = editing.apply_status(ADMIN_ID, order.order_id, "completed")

        assert result == {"status": "edit_order_status_success"}
        paid = db.get_order(order.order_id)
        assert (paid.status, paid.credit_applied) == ("completed", Decimal("3.00"))

    def test_a_completed_order_keeps_its_status(self, db, editing, customer):
        box = make_box(db, 2, status=BoxStatus.DELIVERED.value)
        order = make_order(db, customer, box, status="completed")

        result = editing.apply_status(ADMIN_ID, order.order_id, "ready_for_labeling")

        assert result == {"status": "edit_failed"}
        assert db.get_order(order.order_id).status == "completed"

    def test_a_status_that_changed_since_it_was_read_is_not_overwritten(self, db, editing, customer):
        box = make_box(db, 2, status=BoxStatus.ORDERED.value)
        order = make_order(db, customer, box, status="ordered")
        stale = db.get_order(order.order_id)
        db.update_order(order.order_id, {"status": "awaiting_payment"})  # the delivery overview, in between

        ok, _key = editing._apply_status_change(stale, "ready_for_labeling")

        assert not ok
        assert db.get_order(order.order_id).status == "awaiting_payment"

    def test_only_the_statuses_that_may_be_set_are_offered(self, db, editing, customer, sent):
        box = make_box(db, 2)
        order = make_order(db, customer, box)

        editing.show_status_options(ADMIN_ID, order.order_id)

        assert status_buttons(sent) == [
            "ordered",
            "received_partial_delayed",
            "ready_for_labeling",
            "labeling_completed",
            "cancelled",
        ]

    def test_an_order_awaiting_payment_is_only_offered_paid(self, db, editing, customer, sent):
        box = make_box(db, 2, status=BoxStatus.DELIVERED.value)
        order = make_order(db, customer, box, status="awaiting_payment")

        editing.show_status_options(ADMIN_ID, order.order_id)

        assert status_buttons(sent) == ["completed"]
