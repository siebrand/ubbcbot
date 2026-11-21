"""/instant_order without arguments: supplier, name, price, customer and box size step by step, each answer kept in
the edit context (instant-orders-design.md, IO-8). The prompts go through the real BotService and CallbackHandler."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models.entities import AuthorizationStatus, Customer, Supplier
from services.bot_service import BotService
from services.offer_cache import OfferCache
from services.telegram_client import TelegramClient
from services.user_cache import UserCache

ADMIN_ID = 15005473
CUSTOMER_ID = 4242


class FakeTelegram:
    """Every Bot API call succeeds; the messages sent are recorded as (chat, text, buttons)"""

    sent: list = []

    @staticmethod
    def call(client, method, data=None, get=False):
        if method == "sendMessage":
            markup = data.get("reply_markup") or {}
            if isinstance(markup, str):
                markup = json.loads(markup)
            buttons = [b.get("callback_data") for row in markup.get("inline_keyboard", []) for b in row]
            FakeTelegram.sent.append((data["chat_id"], data["text"], buttons))
        return SimpleNamespace(ok=True, message_id=1, result={"username": "ubbc_bot"}, status_code=200, body="")


@pytest.fixture
def bot(dynamodb, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.delenv("DEFAULT_GROUP_ID", raising=False)
    UserCache.invalidate_cache()
    OfferCache.invalidate_cache()
    FakeTelegram.sent = []
    with (
        patch.object(BotService, "_get_telegram_token", return_value="token"),
        patch.object(TelegramClient, "call", FakeTelegram.call),
        patch("services.bot_service.ADMIN_USER_ID", ADMIN_ID),
    ):
        service = BotService()
        service.db.create_supplier(Supplier(name="DeMolen"))
        service.db.create_supplier(Supplier(name="Oud", status="retired"))
        yield service
    UserCache.invalidate_cache()
    OfferCache.invalidate_cache()


def text(bot, words: str, sender=ADMIN_ID):
    message = {"message_id": 1, "chat": {"id": sender, "type": "private"}, "from": {"id": sender}, "text": words}
    return bot.process_update({"update_id": abs(hash(words)) % 10**9, "message": message})


def tap(bot, data: str, sender=ADMIN_ID):
    query = {"id": "q", "from": {"id": sender}, "message": {"chat": {"id": sender}, "message_id": 9}, "data": data}
    return bot.process_update({"update_id": abs(hash(data + str(sender))) % 10**9, "callback_query": query})


def last(chat_id=ADMIN_ID):
    return [(t, b) for chat, t, b in FakeTelegram.sent if chat == chat_id][-1]


def add_customer(bot, telegram_id, name):
    return bot.db.create_customer(
        Customer(
            telegram_user_id=telegram_id,
            first_name=name,
            username=name.lower(),
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


def to_the_box_size(bot, customer="jan"):
    text(bot, "/instant_order")
    supplier_button = next(b for b in last()[1] if b.startswith("instant_order_supplier_"))
    tap(bot, supplier_button)
    text(bot, "Tripel 8")
    text(bot, "3,50")
    text(bot, customer)


class TestTheWholePath:
    def test_it_ends_with_the_same_entities_as_the_one_line_form(self, bot):
        jan = add_customer(bot, CUSTOMER_ID, "Jan")

        to_the_box_size(bot)
        assert [b for b in last()[1] if b.startswith("instant_order_box_")] == [
            f"instant_order_box_{n}" for n in range(1, 7)
        ]
        tap(bot, "instant_order_box_4")

        [offer] = bot.db.list_offers()
        assert (offer.supplier_name, offer.name, str(offer.price_per_unit), offer.wholesale_box_size, offer.status) == (
            "DeMolen",
            "Tripel 8",
            "3.50",
            4,
            "active",
        )
        [box] = bot.db.get_boxes_by_offer(offer.offer_id)
        assert (box.status, box.current_quantity) == ("delivered", 1)
        [order] = bot.db.get_orders_by_offer(offer.offer_id)
        assert (order.customer_id, order.status) == (jan.customer_id, "ready_for_labeling")
        assert bot.db.get_edit_context_by_chat_id(ADMIN_ID) is None

    def test_only_active_suppliers_are_offered(self, bot):
        text(bot, "/instant_order")

        supplier_buttons = [b for b in last()[1] if b.startswith("instant_order_supplier_")]
        assert len(supplier_buttons) == 1
        assert bot.db.get_supplier_by_name("DeMolen").supplier_id in supplier_buttons[0]

    def test_two_matching_customers_show_the_list_and_then_the_box_size(self, bot):
        add_customer(bot, CUSTOMER_ID, "Jan")
        janneke = add_customer(bot, 4343, "Janneke")

        to_the_box_size(bot, customer="Jan")
        assert f"instant_order_customer_{janneke.customer_id}" in last()[1]
        tap(bot, f"instant_order_customer_{janneke.customer_id}")
        tap(bot, "instant_order_box_1")

        [offer] = bot.db.list_offers()
        assert offer.status == "sold_out"
        assert [o.customer_id for o in bot.db.get_orders_by_offer(offer.offer_id)] == [janneke.customer_id]


class TestAnswersThatAreAskedAgain:
    def test_an_invalid_price_is_asked_again(self, bot):
        text(bot, "/instant_order")
        tap(bot, next(b for b in last()[1] if b.startswith("instant_order_supplier_")))
        text(bot, "Tripel")

        text(bot, "gratis")

        assert bot.db.get_edit_context_by_chat_id(ADMIN_ID).edit_type == "instant_order_price"
        assert bot.db.list_offers() == []

    def test_an_unknown_customer_is_asked_again(self, bot):
        to_the_box_size(bot, customer="Niemand")

        assert bot.db.get_edit_context_by_chat_id(ADMIN_ID).edit_type == "instant_order_customer"
        assert bot.db.list_offers() == []


class TestEndingTheFlow:
    def test_a_box_size_without_the_kept_input_has_expired(self, bot):
        tap(bot, "instant_order_box_3")

        assert last()[0].endswith(bot.handlers["offer"]._t("instant_order_context_expired", ADMIN_ID))
        assert bot.db.list_offers() == []

    def test_cancel_ends_the_flow(self, bot):
        add_customer(bot, CUSTOMER_ID, "Jan")
        text(bot, "/instant_order")
        tap(bot, next(b for b in last()[1] if b.startswith("instant_order_supplier_")))

        text(bot, "/cancel")

        assert bot.db.get_edit_context_by_chat_id(ADMIN_ID) is None

    def test_a_customer_tap_on_a_button_does_nothing(self, bot):
        add_customer(bot, CUSTOMER_ID, "Jan")
        to_the_box_size(bot)
        before = len(FakeTelegram.sent)

        tap(bot, "instant_order_box_2", sender=CUSTOMER_ID)
        tap(bot, f"instant_order_supplier_{bot.db.get_supplier_by_name('DeMolen').supplier_id}", sender=CUSTOMER_ID)

        assert bot.db.list_offers() == []
        assert bot.db.get_edit_context_by_chat_id(ADMIN_ID).edit_type == "instant_order_box_size_select"
        assert all(chat != ADMIN_ID for chat, _, _ in FakeTelegram.sent[before:])
