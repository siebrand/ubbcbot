"""The admin places an order for a customer ("order for"), against the (mocked) database and a fake Telegram."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from handlers.admin.order.order_placement import OrderPlacement
from models.entities import AuthorizationStatus, Box, Customer, Offer, OfferStatus
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
GROUP_ID = -100777


class FakeTelegram:
    """Every handler talks to Telegram through TelegramClient: this one records what is sent"""

    sent: list = []

    def __init__(self, token):
        pass

    def call(self, method, data=None, get=False):
        if method == "sendMessage":
            FakeTelegram.sent.append((data["chat_id"], data["text"]))
        return SimpleNamespace(ok=True, message_id=1, result={"username": "ubbc_bot"}, status_code=200, body="")


@pytest.fixture
def telegram(monkeypatch):
    monkeypatch.setenv("DEFAULT_GROUP_ID", str(GROUP_ID))
    FakeTelegram.sent = []
    with patch("handlers.base_handler.TelegramClient", FakeTelegram):
        yield FakeTelegram


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
            status=OfferStatus.ACTIVE.value,
        )
    )
    yield service
    UserCache.invalidate_cache()


def add_customer(db, telegram_id, name, is_guest=False, status=AuthorizationStatus.APPROVED.value):
    return db.create_customer(
        Customer(
            telegram_user_id=telegram_id,
            first_name=name,
            is_guest=is_guest,
            authorization_status=status,
        )
    )


def sent_to(telegram, chat_id) -> list[str]:
    return [text for chat, text in telegram.sent if chat == chat_id]


@pytest.fixture
def placement(db, telegram):
    handler = OrderPlacement(db, ADMIN_ID, "prod", "token")
    handler.sync_offer_messages = lambda *a, **k: None
    return handler


class TestOnlyApprovedCustomersAreMatched:
    """/order_for finds approved customers (guests are approved) and nobody else"""

    @pytest.fixture
    def others(self, db):
        add_customer(db, 201, "Janneke", status=AuthorizationStatus.UNAUTHORIZED.value)
        add_customer(db, 202, "Jantje", status=AuthorizationStatus.REJECTED.value)

    def test_a_pending_or_rejected_customer_is_not_matched_or_listed(self, db, placement, telegram, others):
        jan = add_customer(db, 101, "Jan")

        result = placement.handle_create_order_for(ADMIN_ID, ADMIN_ID, ["Jan"])

        assert result == {"status": "success"}  # one match: the offers are shown for Jan
        assert jan.first_name in sent_to(telegram, ADMIN_ID)[-1]
        assert not any("Janneke" in text or "Jantje" in text for text in sent_to(telegram, ADMIN_ID))

    def test_only_a_pending_customer_is_no_match(self, db, placement, telegram, others):
        result = placement.handle_create_order_for(ADMIN_ID, ADMIN_ID, ["Janneke"])

        assert result["status"] == "user_not_found"

    def test_the_one_line_form_does_not_order_for_a_rejected_customer(self, db, placement, telegram, others):
        result = placement.handle_create_order_for(ADMIN_ID, ADMIN_ID, ["Jantje", "7", "1"])

        assert result["status"] == "user_not_found"
        assert db.get_orders_by_offer(7) == []

    def test_a_guest_is_matched(self, db, placement, telegram):
        guest = add_customer(db, -1, "Gast", is_guest=True)

        result = placement.handle_create_order_for(ADMIN_ID, ADMIN_ID, ["Gast", "7", "1"])

        assert result == {"status": "success"}
        assert [o.customer_id for o in db.get_orders_by_offer(7)] == [guest.customer_id]


class TestOrderFor:
    def test_the_order_is_placed_announced_and_confirmed(self, db, placement, telegram):
        jan = add_customer(db, 101, "Jan")

        result = placement.handle_create_order_for_quantity_select(ADMIN_ID, jan.customer_id, "7", "2")

        assert result == {"status": "success"}
        assert [o.quantity for o in db.get_orders_by_customer(jan.customer_id)] == [2]
        assert len(sent_to(telegram, 101)) == 1  # the customer is told
        assert len(sent_to(telegram, GROUP_ID)) == 1  # the group sees the order
        [confirmation] = sent_to(telegram, ADMIN_ID)  # one message for the admin, not two
        [order] = db.get_orders_by_customer(jan.customer_id)
        assert "Jan" in confirmation and order.order_id[:8] in confirmation and "Pils" in confirmation

    def test_a_guest_is_never_messaged_and_its_order_not_announced(self, db, placement, telegram):
        add_customer(db, -1, "Gast", is_guest=True)
        guest = add_customer(db, -1, "Kees", is_guest=True)  # the second guest gets -2

        result = placement.handle_create_order_for_quantity_select(ADMIN_ID, guest.customer_id, "7", "1")

        assert result == {"status": "success"}
        assert [chat for chat, _ in telegram.sent if chat != ADMIN_ID] == []
        [confirmation] = sent_to(telegram, ADMIN_ID)
        assert "Kees" in confirmation
        assert placement._t("pm_notification_failed", name="Kees") not in confirmation

    def test_a_failed_message_to_the_customer_is_in_the_same_admin_message(self, db, placement, telegram):
        jan = add_customer(db, 101, "Jan")

        with patch.object(OrderPlacement, "_notify_customer", return_value={"success": False}):
            placement.handle_create_order_for_quantity_select(ADMIN_ID, jan.customer_id, "7", "1")

        [confirmation] = sent_to(telegram, ADMIN_ID)
        assert placement._t("pm_notification_failed", name="Jan") in confirmation

    def test_what_could_not_be_ordered_is_in_the_confirmation(self, db, placement, telegram):
        """docs/order-over-boxes.md: a delivered box with 2 free units and no new box allowed, 4 asked for"""
        jan = add_customer(db, 101, "Jan")
        assert db.create_box(Box(box_id="dlvr", offer_id=7, max_capacity=6, current_quantity=4, status="delivered"))

        result = placement.handle_create_order_for_quantity_select(ADMIN_ID, jan.customer_id, "7", "4")

        assert result == {"status": "success"}
        [order] = db.get_orders_by_customer(jan.customer_id)
        assert (order.box_id, order.quantity, order.status) == ("dlvr", 2, "ready_for_labeling")
        [confirmation] = sent_to(telegram, ADMIN_ID)
        assert placement._t("order_for_shortfall", ADMIN_ID, requested=4, placed=2) in confirmation
        [to_group] = sent_to(telegram, GROUP_ID)
        assert "2x" in to_group

    def test_a_request_over_two_boxes_is_one_confirmation(self, db, placement, telegram):
        jan = add_customer(db, 101, "Jan")
        db.update_offer(7, {"wholesale_box_size": 2})

        placement.handle_create_order_for_quantity_select(ADMIN_ID, jan.customer_id, "7", "3")

        orders = db.get_orders_by_customer(jan.customer_id)
        assert sorted(o.quantity for o in orders) == [1, 2]
        [confirmation] = sent_to(telegram, ADMIN_ID)
        assert all(o.order_id[:8] in confirmation for o in orders)
        assert placement._t("order_for_shortfall", ADMIN_ID, requested=3, placed=3) not in confirmation
        assert len(sent_to(telegram, GROUP_ID)) == 1
        [to_customer] = sent_to(telegram, 101)
        short_ids = ", ".join(sorted(o.order_id[:8] for o in orders))
        assert to_customer.endswith(
            f"Er is een bestelling voor je geplaatst door de beheerder:\n\n3x [7] <b>Pils</b> €7.50 ({short_ids})"
        )

    def test_the_admin_gets_one_order_line_with_the_customer_name(self, db, placement, telegram):
        jan = db.create_customer(
            Customer(telegram_user_id=101, first_name="Jan", last_name="<Jansen>", authorization_status="approved")
        )

        placement.handle_create_order_for_quantity_select(ADMIN_ID, jan.customer_id, "7", "2")

        [order] = db.get_orders_by_customer(jan.customer_id)
        [confirmation] = sent_to(telegram, ADMIN_ID)
        assert confirmation == (
            f"✅ Bestelling geplaatst voor Jan &lt;Jansen&gt;:\n\n2x [7] <b>Pils</b> €5.00 ({order.order_id[:8]})"
        )

    def test_the_offer_name_is_bold_and_escaped_for_the_customer(self, db, placement, telegram):
        jan = add_customer(db, 101, "Jan")
        db.update_offer(7, {"name": "Pils & <Co>"})

        placement.handle_create_order_for_quantity_select(ADMIN_ID, jan.customer_id, "7", "1")

        [to_customer] = sent_to(telegram, 101)
        assert "1x [7] <b>Pils &amp; &lt;Co&gt;</b> €2.50" in to_customer

    def test_the_confirmation_is_in_the_admins_language(self, db, placement, telegram):
        jan = db.create_customer(
            Customer(telegram_user_id=101, first_name="Jan", language="en", authorization_status="approved")
        )

        placement.handle_create_order_for_quantity_select(ADMIN_ID, jan.customer_id, "7", "1")

        [confirmation] = sent_to(telegram, ADMIN_ID)
        assert "Bestelling" in confirmation  # the admin reads Dutch, whatever the customer's language
