"""/edit_order unit price, against the (mocked) database (audit 6, B2).

Decision: an order gets a new price as long as no payment is recorded for it. Before the delivery overview no money
is involved; an order awaiting payment gets the new price on condition that its credit is as it was read, with the
credit kept within the new total (what is left over goes back to the customer's balance in the same write) and the
admin told what the customer was asked for and what is due now. A completed order keeps its price (its payment event
holds the amount), and so does a cancelled one.
"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.order.order_editing import OrderEditing
from models.entities import AuthorizationStatus, Customer, CustomerCredit, Order
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = OrderEditing(db, ADMIN_ID, "prod", "token")
    handler.sent = []
    handler._send_message = Mock(side_effect=lambda chat, text, **kw: handler.sent.append((chat, text)) or {})
    return handler


@pytest.fixture
def jan(db):
    return db.create_customer(
        Customer(telegram_user_id=42, first_name="Jan", authorization_status=AuthorizationStatus.APPROVED.value)
    )


def place(db, who, status, credit="0", quantity=2, price="5.00"):
    order = Order(
        order_id="order-0001-aaaa",
        customer_id=who.customer_id,
        box_id="box-1",
        offer_id=7,
        quantity=quantity,
        unit_price=Decimal(price),
        total_price=Decimal(price) * quantity,
        credit_applied=Decimal(credit),
        status=status,
    )
    assert db.order_repo.create_order(order)
    return db.get_order(order.order_id)


def balance(db, who) -> Decimal:
    credit = db.get_customer_credit(who.customer_id)
    return credit.current_balance if credit else Decimal("0")


@pytest.mark.parametrize("status", ["pending", "ordered", "ready_for_labeling", "labeling_completed"])
def test_an_order_before_payment_gets_the_new_price(db, handler, jan, status):
    order = place(db, jan, status)

    ok, key, _ = handler._apply_unit_price_change(order, "3.50")

    assert (ok, key) == (True, "edit_order_price_success")
    stored = db.get_order(order.order_id)
    assert (stored.unit_price, stored.total_price) == (Decimal("3.50"), Decimal("7.00"))


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_a_paid_or_cancelled_order_keeps_its_price(db, handler, jan, status):
    order = place(db, jan, status)

    ok, key, _ = handler._apply_unit_price_change(order, "3.50")

    assert (ok, key) == (False, "edit_order_price_not_allowed")
    assert db.get_order(order.order_id).total_price == Decimal("10.00")


def test_awaiting_payment_with_credit_within_the_new_total(db, handler, jan):
    order = place(db, jan, "awaiting_payment", credit="4.00")

    ok, key, params = handler._apply_unit_price_change(order, "4.00")

    assert (ok, key) == (True, "edit_order_price_success_awaiting_payment")
    stored = db.get_order(order.order_id)
    assert (stored.total_price, stored.credit_applied, stored.amount_due) == (
        Decimal("8.00"),
        Decimal("4.00"),
        Decimal("4.00"),
    )
    assert params == {"old_due": 6.0, "new_due": 4.0, "returned": 0.0}


def test_awaiting_payment_credit_above_the_new_total_goes_back_to_the_balance(db, handler, jan):
    db.create_customer_credit(CustomerCredit(customer_id=jan.customer_id, current_balance=Decimal("1.00")))
    order = place(db, jan, "awaiting_payment", credit="8.00")

    ok, key, params = handler._apply_unit_price_change(order, "2.50")

    assert (ok, key) == (True, "edit_order_price_success_awaiting_payment")
    stored = db.get_order(order.order_id)
    assert (stored.total_price, stored.credit_applied, stored.amount_due) == (
        Decimal("5.00"),
        Decimal("5.00"),
        Decimal("0.00"),
    )
    assert balance(db, jan) == Decimal("4.00")
    assert params == {"old_due": 2.0, "new_due": 0.0, "returned": 3.0}


def test_a_debt_charged_with_the_order_stays_with_it(db, handler, jan):
    order = place(db, jan, "awaiting_payment", credit="-2.00")

    ok, _, params = handler._apply_unit_price_change(order, "4.00")

    assert ok
    stored = db.get_order(order.order_id)
    assert (stored.credit_applied, stored.amount_due) == (Decimal("-2.00"), Decimal("10.00"))
    assert params["returned"] == 0.0


def test_the_price_is_not_set_when_the_credit_changed_after_the_read(db, handler, jan):
    order = place(db, jan, "awaiting_payment", credit="0")
    db.order_repo.update_order(order.order_id, {"credit_applied": Decimal("10.00")})  # the overview, in between

    ok, key, _ = handler._apply_unit_price_change(order, "1.00")

    assert (ok, key) == (False, "edit_order_update_failed")
    assert db.get_order(order.order_id).total_price == Decimal("10.00")


def test_the_price_is_not_set_when_the_order_was_paid_after_the_read(db, handler, jan):
    order = place(db, jan, "awaiting_payment", credit="8.00")
    db.order_repo.update_order(order.order_id, {"status": "completed"})

    ok, key, _ = handler._apply_unit_price_change(order, "1.00")

    assert (ok, key) == (False, "edit_order_update_failed")
    assert balance(db, jan) == Decimal("0")
    assert db.get_order(order.order_id).credit_applied == Decimal("8.00")


def test_the_admin_is_told_what_the_customer_was_asked_and_what_is_due(db, handler, jan):
    db.create_customer_credit(CustomerCredit(customer_id=jan.customer_id, current_balance=Decimal("0")))
    order = place(db, jan, "awaiting_payment", credit="8.00")

    handler.apply_price_input(ADMIN_ID, order.order_id, "2.50")

    text = handler.sent[0][1]
    assert "2.00" in text and "0.00" in text and "3.00" in text
