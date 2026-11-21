"""A partial payment: the admin enters the amount received, the bot proposes the oldest open orders that add up to it,
and the confirmation pays those (partial-payments-design.md, PP-2, PP-3). Against the (moto) database."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from handlers.admin.order.order_status import OrderStatusManagement
from models.entities import AuthorizationStatus, Customer, Offer, Order
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
START = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    service = DynamoDBService()
    service.create_offer(Offer(offer_id=7, name="Pils", price_per_unit=Decimal("2.50"), status="completed"))
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def jan(db):
    return db.create_customer(
        Customer(
            telegram_user_id=101,
            first_name="Jan",
            last_name="Jansen",
            language="en",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


def open_order(db, customer, n: int, total: str, credit: str = "0", status="awaiting_payment") -> Order:
    """The n-th oldest open order"""
    order = Order(
        order_id=f"order-{n:03d}",
        customer_id=customer.customer_id,
        box_id="b1",
        offer_id=7,
        quantity=1,
        unit_price=Decimal(total),
        total_price=Decimal(total),
        credit_applied=Decimal(credit),
        status=status,
        created_at=START,
        update_date=START + timedelta(hours=n),
    )
    assert db.order_repo.create_order(order)
    return order


@pytest.fixture
def three(db, jan):
    """12.00, 8.50 and 20.00, oldest first"""
    return [open_order(db, jan, 1, "12.00"), open_order(db, jan, 2, "8.50"), open_order(db, jan, 3, "20.00")]


@pytest.fixture
def handler(db):
    handler = OrderStatusManagement(db, ADMIN_ID, "prod", "token")
    handler.sent = []

    def send(chat, text, reply_markup=None, **_):
        buttons = [b["callback_data"] for row in (reply_markup or {}).get("inline_keyboard", []) for b in row]
        handler.sent.append((chat, text, buttons))
        return {"success": True}

    handler._send_message = Mock(side_effect=send)
    handler._send_user_message = Mock(return_value={"success": True})
    return handler


def statuses(db, orders) -> list[str]:
    return [db.get_order(o.order_id).status for o in orders]


def propose(handler, jan, amount: str, page: int = 1):
    return handler.handle_payment_amount_answer(ADMIN_ID, f"{jan.customer_id}_{page}", amount)


def confirm_button(handler) -> str:
    [button] = [b for _, _, buttons in handler.sent for b in buttons if b.startswith("payok_")]
    return button


def confirm(handler, button: str):
    _, rest = button.split("_", 1)
    customer_id, amount_cents, token, page = rest.rsplit("_", 3)
    return handler.handle_payment_confirm(ADMIN_ID, customer_id, int(amount_cents), token, int(page))


class TestTheProposal:
    def test_a_match_shows_the_orders_and_a_confirm_button(self, db, handler, jan, three):
        result = propose(handler, jan, "20,50")

        assert result == {"status": "proposal_shown"}
        _, text, _ = handler.sent[-1]
        assert "20.50" in text and "12.00" in text and "8.50" in text
        assert "€20.00 (1 bestellingen)" in text  # what stays open (the admin reads Dutch)
        assert len(confirm_button(handler).encode()) <= 64

    def test_the_worst_case_button_fits_in_64_bytes(self, db, handler, jan):
        open_order(db, jan, 1, "10000.00")

        propose(handler, jan, "10000", page=99)

        assert len(confirm_button(handler).encode()) <= 64

    def test_no_match_reports_the_closest_total_and_changes_nothing(self, db, handler, jan, three):
        result = propose(handler, jan, "5")

        assert result == {"status": "no_match"}
        assert "8.50" in handler.sent[0][1]
        assert statuses(db, three) == ["awaiting_payment"] * 3
        assert any(b.startswith("process_payment_") for b in handler.sent[-1][2])  # the list again

    def test_an_invalid_amount_is_asked_again(self, db, handler, jan, three):
        assert propose(handler, jan, "veel") == {"status": "invalid_amount"}

        context = db.get_edit_context_by_chat_id(ADMIN_ID)
        assert (context.edit_type, context.entity_id) == ("payment_amount_input", f"{jan.customer_id}_1")

    def test_too_many_orders(self, db, handler, jan):
        for n in range(61):
            open_order(db, jan, n, "1.00")

        assert propose(handler, jan, "1")["status"] == "too_many"

    def test_an_unknown_customer(self, db, handler):
        assert handler.handle_payment_amount_answer(ADMIN_ID, "nobody_1", "5")["status"] == "customer_not_found"

    def test_a_customer_without_open_orders(self, db, handler, jan):
        open_order(db, jan, 1, "5.00", status="completed")

        assert propose(handler, jan, "5")["status"] == "no_orders"


class TestTheConfirmation:
    def test_it_pays_exactly_the_selected_and_the_zero_due_orders(self, db, handler, jan, three):
        free = open_order(db, jan, 4, "3.00", credit="3.00")
        propose(handler, jan, "20.50")

        result = confirm(handler, confirm_button(handler))

        assert result == {"status": "paid", "paid": 3}
        assert statuses(db, three) == ["completed", "completed", "awaiting_payment"]
        assert db.get_order(free.order_id).status == "completed"
        events = db.get_events_by_type("PAYMENT_RECEIVED")
        assert sorted(e.amount for e in events) == [Decimal("3.00"), Decimal("8.50"), Decimal("12.00")]

    def test_orders_that_changed_after_the_proposal_change_nothing(self, db, handler, jan, three):
        propose(handler, jan, "20.50")
        db.update_order(three[1].order_id, {"status": "cancelled"})  # cancelled in between
        db.update_order(three[0].order_id, {"status": "completed"})  # paid by hand

        result = confirm(handler, confirm_button(handler))

        assert result == {"status": "match_changed"}
        assert db.get_order(three[2].order_id).status == "awaiting_payment"
        assert [e.amount for e in db.get_events_by_type("PAYMENT_RECEIVED")] == [Decimal("12.00")]  # by hand only

    def test_a_second_confirm_changes_nothing(self, db, handler, jan, three):
        propose(handler, jan, "20.50")
        button = confirm_button(handler)
        confirm(handler, button)

        assert confirm(handler, button) == {"status": "match_changed"}
        assert len(db.get_events_by_type("PAYMENT_RECEIVED")) == 2
        assert db.get_order(three[2].order_id).status == "awaiting_payment"

    def test_an_order_that_fails_the_conditional_update_is_reported(self, db, handler, jan, three):
        propose(handler, jan, "20.50")
        real = db.order_repo.batch_update_order_status

        def one_fails(order_ids, *args, **kwargs):
            return real(order_ids[1:], *args, **kwargs)

        with patch.object(db.order_repo, "batch_update_order_status", side_effect=one_fails):
            result = confirm(handler, confirm_button(handler))

        assert result == {"status": "paid", "paid": 1}
        texts = [t for _, t, _ in handler.sent]
        assert any("1 van de 2 bestellingen" in t for t in texts)
        assert statuses(db, three) == ["awaiting_payment", "completed", "awaiting_payment"]

    def test_an_unknown_customer(self, db, handler):
        assert handler.handle_payment_confirm(ADMIN_ID, "nobody", 100, "abcdef", 1)["status"] == "customer_not_found"


class TestTheCustomerIsTold:
    """PP-3: from the admin account, in the customer's language; guests get nothing"""

    def test_a_partial_payment_tells_what_was_paid_and_what_is_still_open(self, db, handler, jan, three):
        propose(handler, jan, "20.50")
        confirm(handler, confirm_button(handler))

        [(user_id, message)] = [c.args[:2] for c in handler._send_user_message.call_args_list]
        assert user_id == 101
        assert message == handler._t(
            "payment_partial_received_notification",
            101,
            amount=Decimal("20.50"),
            count=2,
            open_total=Decimal("20.00"),
            open_count=1,
        )
        assert "20.50" in message and "20.00" in message  # English: the customer's language

    def test_the_last_payment_sends_the_existing_message(self, db, handler, jan, three):
        propose(handler, jan, "40.50")
        confirm(handler, confirm_button(handler))

        [message] = [c.args[1] for c in handler._send_user_message.call_args_list]
        assert message == handler._t(
            "payment_received_notification", 101, total_amount=Decimal("40.50"), location=jan.location
        )

    def test_a_guest_gets_nothing(self, db, handler):
        guest = db.create_customer(
            Customer(telegram_user_id=-1, first_name="Gast", is_guest=True, authorization_status="approved")
        )
        open_order(db, guest, 1, "5.00")
        open_order(db, guest, 2, "6.00")
        propose(handler, guest, "5")
        confirm(handler, confirm_button(handler))

        handler._send_user_message.assert_not_called()

    def test_a_failed_send_is_reported_and_the_orders_stay_paid(self, db, handler, jan, three):
        handler._send_user_message.return_value = {"success": False, "error": "PeerIdInvalid"}
        propose(handler, jan, "8.50")

        result = confirm(handler, confirm_button(handler))

        assert result["status"] == "paid"
        assert db.get_order(three[1].order_id).status == "completed"
        expected = handler._t("payment_customer_not_reached", ADMIN_ID, customer_name="Jan Jansen")
        assert any(expected in t for _, t, _ in handler.sent)
