"""The /instant_order handler against the (moto) database and a fake Telegram (instant-orders-design.md, IO-5, IO-6)"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from handlers.admin.offer import OfferCommands
from models.entities import AuthorizationStatus, Customer, Supplier
from services.database import DynamoDBService
from services.offer_cache import OfferCache
from services.user_cache import UserCache

ADMIN_ID = 15005473
GROUP_ID = -100777


class FakeTelegram:
    """Records every message sent: (chat id, text, buttons)"""

    sent: list = []

    def __init__(self, token):
        pass

    def call(self, method, data=None, get=False):
        if method == "sendMessage":
            markup = data.get("reply_markup") or {}
            if isinstance(markup, str):
                import json

                markup = json.loads(markup)
            buttons = [b.get("callback_data") or b.get("url") for row in markup.get("inline_keyboard", []) for b in row]
            FakeTelegram.sent.append((data["chat_id"], data["text"], buttons))
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
    OfferCache.invalidate_cache()
    service = DynamoDBService()
    service.create_supplier(Supplier(name="DeMolen"))
    service.create_supplier(Supplier(name="Oud", status="retired"))
    yield service
    UserCache.invalidate_cache()
    OfferCache.invalidate_cache()


@pytest.fixture
def handler(db, telegram):
    return OfferCommands(db, ADMIN_ID, "prod", "token")  # prod: messages without the "TEST - " prefix


def add_customer(db, telegram_id, name, status=AuthorizationStatus.APPROVED.value, language="nl", is_guest=False):
    return db.create_customer(
        Customer(
            telegram_user_id=telegram_id,
            first_name=name,
            username=name.lower(),
            language=language,
            is_guest=is_guest,
            authorization_status=status,
        )
    )


def sent_to(telegram, chat_id) -> list[str]:
    return [text for chat, text, _ in telegram.sent if chat == chat_id]


def instant(handler, line: str):
    return handler.handle_instant_order(ADMIN_ID, line.split())


class TestCreation:
    def test_box_size_1_sells_the_offer_out_at_once(self, db, handler, telegram):
        jan = add_customer(db, 101, "Jan")

        result = instant(handler, "DeMolen Tripel 3.50 Jan")

        assert result["status"] == "success"
        offer = db.get_offer(result["offer_id"])
        assert (offer.name, offer.supplier_name, offer.status, offer.wholesale_box_size) == (
            "Tripel",
            "DeMolen",
            "sold_out",
            1,
        )
        [box] = db.get_boxes_by_offer(offer.offer_id)
        assert (box.status, box.current_quantity, box.max_capacity) == ("delivered", 1, 1)
        [order] = db.get_orders_by_offer(offer.offer_id)  # no admin auto-order
        assert (order.customer_id, order.box_id, order.status, order.quantity, order.received_quantity) == (
            jan.customer_id,
            box.box_id,
            "ready_for_labeling",
            1,
            1,
        )
        assert order.placed_by_admin is True

    def test_box_size_4_leaves_the_offer_active(self, db, handler, telegram):
        add_customer(db, 101, "Jan")

        result = instant(handler, "DeMolen Tripel 3.50 Jan 4")

        offer = db.get_offer(result["offer_id"])
        assert (offer.status, offer.wholesale_box_size) == ("active", 4)
        [box] = db.get_boxes_by_offer(offer.offer_id)
        assert (box.max_capacity, box.current_quantity) == (4, 1)
        assert f"/order_for jan {offer.offer_id}" in sent_to(telegram, ADMIN_ID)[-1]

    def test_the_order_created_event_is_recorded(self, db, handler, telegram):
        jan = add_customer(db, 101, "Jan")

        instant(handler, "DeMolen Tripel 3.50 Jan")

        assert [e.customer_id for e in db.get_events_by_type("ORDER_CREATED")] == [jan.customer_id]

    def test_the_customer_is_told_in_their_language(self, db, handler, telegram):
        add_customer(db, 101, "Jan", language="en")

        instant(handler, "DeMolen Tripel 3.50 Jan")

        [message] = sent_to(telegram, 101)
        assert "An order has been placed for you" in message and "Tripel" in message

    def test_a_guest_is_matched_and_not_messaged(self, db, handler, telegram):
        guest = add_customer(db, -1, "Gast", is_guest=True)

        result = instant(handler, "DeMolen Tripel 3.50 Gast")

        assert result["status"] == "success"
        assert [o.customer_id for o in db.get_orders_by_offer(result["offer_id"])] == [guest.customer_id]
        assert [chat for chat, _, _ in telegram.sent] == [ADMIN_ID]


class TestTheCustomer:
    def test_no_match_creates_nothing(self, db, handler, telegram):
        result = instant(handler, "DeMolen Tripel 3.50 Niemand")

        assert result["status"] == "user_not_found"
        assert db.list_offers() == []

    @pytest.mark.parametrize("status", [AuthorizationStatus.UNAUTHORIZED.value, AuthorizationStatus.REJECTED.value])
    def test_a_customer_who_is_not_approved_is_not_matched(self, db, handler, telegram, status):
        add_customer(db, 101, "Jan", status=status)

        assert instant(handler, "DeMolen Tripel 3.50 Jan")["status"] == "user_not_found"
        assert db.list_offers() == []

    def test_two_matches_show_a_list_and_create_nothing_until_a_pick(self, db, handler, telegram):
        add_customer(db, 101, "Jan")
        janneke = add_customer(db, 102, "Janneke")

        result = instant(handler, "DeMolen Tripel 3.50 Jan 4")

        assert result["status"] == "disambiguation_shown"
        assert db.list_offers() == []
        assert f"instant_order_customer_{janneke.customer_id}" in telegram.sent[-1][2]

        picked = handler.handle_instant_order_customer_select(ADMIN_ID, janneke.customer_id)

        assert picked["status"] == "success"
        offer = db.get_offer(picked["offer_id"])
        assert (offer.name, offer.wholesale_box_size) == ("Tripel", 4)
        assert [o.customer_id for o in db.get_orders_by_offer(offer.offer_id)] == [janneke.customer_id]
        assert db.get_edit_context_by_chat_id(ADMIN_ID) is None

    def test_a_pick_without_the_kept_input_has_expired(self, db, handler, telegram):
        jan = add_customer(db, 101, "Jan")

        result = handler.handle_instant_order_customer_select(ADMIN_ID, jan.customer_id)

        assert result == {"status": "context_expired"}
        assert handler._t("instant_order_context_expired", ADMIN_ID) in sent_to(telegram, ADMIN_ID)
        assert db.list_offers() == []


class TestInvalidInput:
    @pytest.mark.parametrize(
        "line, key",
        [
            ("Onbekend Tripel 3.50 Jan", "supplier_not_found"),
            ("Oud Tripel 3.50 Jan", "supplier_retired_cannot_use"),
            ("DeMolen Tripel 0 Jan", "instant_order_price_invalid"),
            ("DeMolen Tripel 3.50 Jan 7", "instant_order_box_size_invalid"),
            ("DeMolen <ul>Tripel</ul> 3.50 Jan", "html_unsupported_tag"),
            ("DeMolen Tripel", "usage_instant_order"),
        ],
    )
    def test_nothing_is_created(self, db, handler, telegram, line, key):
        add_customer(db, 101, "Jan")

        result = instant(handler, line)

        assert result["status"] != "success"
        assert sent_to(telegram, ADMIN_ID)[-1].startswith(handler._t(key, ADMIN_ID, name="X")[:12])
        assert db.list_offers() == []
        assert sent_to(telegram, 101) == []

    def test_no_arguments_show_the_usage(self, db, handler, telegram):
        assert handler.handle_instant_order(ADMIN_ID, []) == {"status": "invalid_args"}
        assert sent_to(telegram, ADMIN_ID) == [handler._t("usage_instant_order", ADMIN_ID)]
