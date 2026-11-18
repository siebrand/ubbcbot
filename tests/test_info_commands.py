"""What customers and the admin see for /list_offers, /view_offer, /start, /help and /fomo.

The database is a mock; the translations are the real ones (Dutch unless the customer chose English). These tests
pin down the current output, so the offer list can be restructured without changing what anyone sees.
"""

import re
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from handlers.customer.info_commands import InfoCommands
from models.entities import Box, Customer, Offer, Order

ADMIN_ID = 15005473
CUSTOMER_ID = 4242
CHAT = 99

OFFERS = [
    Offer(offer_id=1, name="Draft Dubbel", status="draft", price_per_unit=Decimal("2.5")),
    Offer(offer_id=2, name="Import IPA", status="import", price_per_unit=Decimal("3")),
    Offer(offer_id=3, name="Pils", status="active", price_per_unit=Decimal("1.75")),
    Offer(offer_id=4, name="Stout", status="active", price_per_unit=Decimal("4")),
    Offer(offer_id=5, name="Kriek", status="sold_out", price_per_unit=Decimal("5")),
    Offer(offer_id=6, name="Tripel", status="completed", price_per_unit=Decimal("6")),
    Offer(offer_id=7, name="Weizen", status="inactive", price_per_unit=Decimal("7")),
]
BOXES = [
    Box(offer_id=3, max_capacity=12, status="ordered"),
    Box(offer_id=4, max_capacity=24, status="open"),
    Box(offer_id=5, max_capacity=12, status="full"),
    Box(offer_id=2, max_capacity=6, status="open"),
]
ORDERS = [
    Order(offer_id=3, quantity=5, status="ordered"),
    Order(offer_id=4, quantity=2),
    Order(offer_id=5, quantity=12),
    Order(offer_id=2, quantity=1),
]


@pytest.fixture
def env():
    db = Mock()
    db.list_offers.side_effect = lambda: list(OFFERS)
    db.get_all_boxes.return_value = BOXES
    db.get_all_orders.return_value = ORDERS
    db.get_customer_by_telegram_id.return_value = None  # Dutch
    handler = InfoCommands(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler._send_photo = Mock(return_value={"success": True})
    handler._send_media_group = Mock(return_value={"success": True})
    handler._get_bot_username = Mock(return_value="ubbc_bot")
    return SimpleNamespace(handler=handler, db=db)


def sent(env) -> str:
    return "\n".join(c.args[1] for c in env.handler._send_message.call_args_list)


def last_call(env):
    return env.handler._send_message.call_args


def offer_ids(text: str) -> list[int]:
    """The offer ids in the order they are listed"""
    return [int(i) for i in re.findall(r"view_offer_(\d+)'", text)]


def english_customer(env):
    env.db.get_customer_by_telegram_id.return_value = Customer(telegram_user_id=CUSTOMER_ID, language="en")


class TestListOffersForTheAdmin:
    def test_by_default_drafts_imports_and_active_offers_with_section_headers(self, env):
        assert env.handler.handle_list_offers(CHAT, ADMIN_ID, None) == {"status": "success"}

        text = sent(env)
        assert text.startswith("📋 Huidige Aanbiedingen (Concept + Actief):")
        assert offer_ids(text) == [1, 2, 3, 4]
        assert text.index("📝 CONCEPTEN:") < text.index("📥 IMPORT:") < text.index("🍺 ACTIEF:")
        assert last_call(env).kwargs == {"parse_mode": "HTML", "reply_markup": None}

    @pytest.mark.parametrize("args", [[], ["bogus"]])
    def test_no_or_an_unknown_filter_is_the_default(self, env, args):
        env.handler.handle_list_offers(CHAT, ADMIN_ID, args)

        assert offer_ids(sent(env)) == [1, 2, 3, 4]

    def test_lines_show_link_price_and_how_much_is_ordered(self, env):
        env.handler.handle_list_offers(CHAT, ADMIN_ID, None)

        text = sent(env)
        link = "<a href='https://t.me/ubbc_bot?start=view_offer_{0}'><b>{0}</b></a>"
        assert f"📝 {link.format(1)} <b>Draft Dubbel</b> €2.50\n" in text
        assert f"📥 {link.format(2)} <b>Import IPA</b> €3.00 (1/6 besteld)" in text
        assert "<b>Stout</b> €4.00 (2/24 besteld)" in text

    def test_an_active_offer_with_an_ordered_box_gets_the_box_icon(self, env):
        env.handler.handle_list_offers(CHAT, ADMIN_ID, None)

        text = sent(env)
        assert "📦🍺 <a href='https://t.me/ubbc_bot?start=view_offer_3'>" in text
        assert "\n🍺 <a href='https://t.me/ubbc_bot?start=view_offer_4'>" in text

    def test_all_shows_every_status_in_order(self, env):
        env.handler.handle_list_offers(CHAT, ADMIN_ID, ["all"])

        text = sent(env)
        assert text.startswith("📋 Alle Aanbiedingen (adminweergave):")
        assert offer_ids(text) == [1, 2, 3, 4, 5, 6, 7]
        assert text.index("🍺 ACTIEF:") < text.index("🚫 UITVERKOCHT:") < text.index("✅ VOLTOOID:")
        assert text.index("✅ VOLTOOID:") < text.index("❌ INACTIEF:")
        assert "<b>Kriek</b> €5.00 (12/12 besteld)" in text  # sold out: with availability
        assert "<b>Tripel</b> €6.00\n" in text  # completed: without

    @pytest.mark.parametrize(
        ("word", "title", "ids"),
        [
            ("draft", "📝 CONCEPTEN:", [1]),
            ("active", "🍺 ACTIEF:", [3, 4]),
            ("import", "📥 IMPORT:", [2]),
            ("archived", "📦 Gearchiveerde Aanbiedingen (Uitverkocht + Voltooid + Inactief):", [5, 6, 7]),
        ],
    )
    def test_a_single_filter_has_one_title_and_no_section_headers(self, env, word, title, ids):
        env.handler.handle_list_offers(CHAT, ADMIN_ID, [word])

        text = sent(env)
        assert text.startswith(title + "\n\n")
        assert text.count(":\n") == 1
        assert offer_ids(text) == ids

    @pytest.mark.parametrize(("word", "ids"), [("completed", [6]), ("inactive", [7])])
    def test_completed_and_inactive_list_only_that_status(self, env, word, ids):
        env.handler.handle_list_offers(CHAT, ADMIN_ID, [word])

        assert offer_ids(sent(env)) == ids

    @pytest.mark.parametrize("word", ["soldout", "sold_out", "SOLD_OUT"])
    def test_sold_out_in_any_spelling(self, env, word):
        env.handler.handle_list_offers(CHAT, ADMIN_ID, [word])

        text = sent(env)
        assert text.startswith("🚫 UITVERKOCHT")
        assert offer_ids(text) == [5]
        assert "(12/12 besteld)" in text

    def test_user_shows_the_customer_view(self, env):
        env.handler.handle_list_offers(CHAT, ADMIN_ID, ["user"])

        text = sent(env)
        assert text.startswith("📋 Actieve Aanbiedingen:")
        assert offer_ids(text) == [4, 3]  # newest first, like customers see it

    def test_help_includes_the_admin_filters(self, env):
        env.handler.handle_list_offers(CHAT, ADMIN_ID, ["help"])

        text = sent(env)
        assert "/list_offers help" in text and "/list_offers archived" in text
        assert last_call(env).kwargs == {}

    def test_no_offers_at_all(self, env):
        env.db.list_offers.side_effect = lambda: []

        assert env.handler.handle_list_offers(CHAT, ADMIN_ID, None) == {"status": "no_offers"}

    @pytest.mark.parametrize("args", [None, ["all"], ["draft"], ["soldout"], ["archived"]])
    def test_names_are_escaped_in_every_view(self, env, args):
        env.db.list_offers.side_effect = lambda: [
            Offer(offer_id=status_id, name=f"Bier & Co <{status}>", status=status)
            for status_id, status in enumerate(["draft", "active", "sold_out", "completed"], start=1)
        ]

        env.handler.handle_list_offers(CHAT, ADMIN_ID, args)

        text = sent(env)
        assert "Bier &amp; Co &lt;" in text
        assert "Bier & Co" not in text


class TestListOffersForCustomers:
    def test_only_active_offers_newest_first(self, env):
        assert env.handler.handle_list_offers(CHAT, CUSTOMER_ID, None) == {"status": "success"}

        text = sent(env)
        assert text.startswith("📋 Actieve Aanbiedingen:")
        assert offer_ids(text) == [4, 3]
        assert "📦" not in text  # the box icon is for the admin

    @pytest.mark.parametrize("args", [["all"], ["draft"], ["archived"], ["user"]])
    def test_admin_filters_do_nothing_for_customers(self, env, args):
        env.handler.handle_list_offers(CHAT, CUSTOMER_ID, args)

        assert offer_ids(sent(env)) == [4, 3]

    def test_sold_out_is_available_to_customers(self, env):
        env.handler.handle_list_offers(CHAT, CUSTOMER_ID, ["soldout"])

        assert offer_ids(sent(env)) == [5]

    def test_help_without_the_admin_filters(self, env):
        env.handler.handle_list_offers(CHAT, CUSTOMER_ID, ["help"])

        text = sent(env)
        assert "/list_offers help" in text
        assert "archived" not in text

    def test_no_active_offers(self, env):
        env.db.list_offers.side_effect = lambda: [o for o in OFFERS if o.status != "active"]

        assert env.handler.handle_list_offers(CHAT, CUSTOMER_ID, None) == {"status": "no_offers"}

    def test_no_sold_out_offers(self, env):
        env.db.list_offers.side_effect = lambda: [o for o in OFFERS if o.status != "sold_out"]

        assert env.handler.handle_list_offers(CHAT, CUSTOMER_ID, ["soldout"]) == {"status": "no_offers"}


class TestListOffersPagination:
    @pytest.fixture
    def many(self, env):
        offers = [Offer(offer_id=i, name=f"Bier {i}", status="active") for i in range(1, 46)]
        env.db.list_offers.side_effect = lambda: list(offers)
        env.db.get_all_boxes.return_value = []
        env.db.get_all_orders.return_value = []
        return env

    def keyboard(self, env) -> list[str]:
        markup = last_call(env).kwargs["reply_markup"]
        return [button["callback_data"] for row in markup["inline_keyboard"] for button in row]

    def test_twenty_per_page_with_page_buttons(self, many):
        many.handler.handle_list_offers(CHAT, CUSTOMER_ID, None, page=2)

        text = sent(many)
        assert offer_ids(text) == list(range(25, 5, -1))
        assert "2/3" in text
        assert self.keyboard(many) == [
            "page_list_offers_1",
            "page_list_offers_1",
            "page_info",
            "page_list_offers_3",
            "page_list_offers_3",
        ]

    def test_the_admin_filter_is_kept_in_the_page_buttons(self, many):
        many.handler.handle_list_offers(CHAT, ADMIN_ID, ["active"], page=1)

        assert "page_list_offers_active_2" in self.keyboard(many)

    def test_the_customer_view_of_the_admin_is_kept_in_the_page_buttons(self, many):
        many.handler.handle_list_offers(CHAT, ADMIN_ID, ["user"], page=1)

        assert "page_list_offers_user_2" in self.keyboard(many)

    def test_one_page_has_no_buttons(self, env):
        env.handler.handle_list_offers(CHAT, CUSTOMER_ID, None)

        assert last_call(env).kwargs["reply_markup"] is None


class TestViewOffer:
    @pytest.fixture
    def offer(self, env):
        offer = Offer(
            offer_id=3,
            name="Pils",
            status="active",
            price_per_unit=Decimal("1.75"),
            description="Lekker fris",
            wholesale_box_size=24,
            supplier_name="Brouwerij",
        )
        env.db.get_offer.return_value = offer
        env.db.get_boxes_by_offer.return_value = [Box(offer_id=3, max_capacity=24)]
        env.db.get_orders_by_offer.return_value = [
            Order(offer_id=3, quantity=4),
            Order(offer_id=3, quantity=9, status="cancelled"),
        ]
        return offer

    def buttons(self, env) -> list[str]:
        markup = last_call(env).kwargs["reply_markup"]
        return [button["callback_data"] for row in markup["inline_keyboard"] for button in row] if markup else []

    def test_a_customer_sees_availability_and_order_buttons(self, env, offer):
        assert env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["3"]) == {"status": "success"}

        text = sent(env)
        assert "<b>3. Pils €1.75 (20/24 " in text  # cancelled orders do not count
        assert "Lekker fris" in text
        assert "Brouwerij" not in text  # supplier is admin-only
        assert self.buttons(env) == ["order_3_1", "order_3_2"]

    def test_the_admin_also_sees_box_size_supplier_and_an_edit_button(self, env, offer):
        env.handler.handle_view_offer(CHAT, ADMIN_ID, ["3"])

        text = sent(env)
        assert "Brouwerij" in text and "24" in text
        assert self.buttons(env) == ["order_3_1", "order_3_2", "view_offer_3_edit"]

    def test_the_admin_can_view_it_as_a_customer(self, env, offer):
        env.handler.handle_view_offer(CHAT, ADMIN_ID, ["3", "user"])

        assert "Brouwerij" not in sent(env)
        assert self.buttons(env) == ["order_3_1", "order_3_2"]

    def test_edit_mode_for_the_admin(self, env, offer):
        env.handler.handle_view_offer(CHAT, ADMIN_ID, ["3", "edit"])

        assert self.buttons(env) == [
            "edit_offer_name_3",
            "edit_offer_price_3",
            "edit_offer_description_3",
            "upload_offer_image_3",
            "view_offer_3",
        ]

    def test_edit_mode_offers_clearing_images_when_there_are_some(self, env, offer):
        offer.images = ["https://example.com/a.jpg"]

        env.handler.handle_view_offer(CHAT, ADMIN_ID, ["3", "edit"])

        assert "clear_offer_images_3" in self.buttons(env)

    def test_edit_mode_is_ignored_for_customers(self, env, offer):
        env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["3", "edit"])

        assert self.buttons(env) == ["order_3_1", "order_3_2"]

    def test_a_draft_is_hidden_from_customers(self, env, offer):
        offer.status = "draft"

        assert env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["3"]) == {"status": "offer_not_available"}

    def test_a_draft_preview_for_the_admin_has_edit_and_publish(self, env, offer):
        offer.status = "draft"

        env.handler.handle_view_offer(CHAT, ADMIN_ID, ["3"])

        assert self.buttons(env) == ["view_offer_3_edit", "publish_offer_3"]

    @pytest.mark.parametrize("status", ["import", "inactive"])
    def test_a_restricted_offer_is_visible_to_customers_who_ordered_it(self, env, offer, status):
        offer.status = status
        env.db.get_customer_by_telegram_id.return_value = Customer(customer_id="c1", telegram_user_id=CUSTOMER_ID)

        env.db.get_orders_by_customer_and_offer.return_value = []
        assert env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["3"]) == {"status": "offer_not_available"}

        env.db.get_orders_by_customer_and_offer.return_value = [Order(offer_id=3)]
        assert env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["3"]) == {"status": "success"}
        assert self.buttons(env) == []

    def test_a_sold_out_offer_cannot_be_ordered(self, env, offer):
        offer.status = "sold_out"

        env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["3"])

        assert self.buttons(env) == []
        assert "<b>3. Pils €1.75</b>" in sent(env)

    def test_one_image_is_sent_as_a_photo(self, env, offer):
        offer.images = ["https://example.com/a.jpg"]

        env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["3"])

        env.handler._send_photo.assert_called_once_with(CHAT, "https://example.com/a.jpg")

    def test_several_images_are_sent_as_an_album_of_at_most_ten(self, env, offer):
        offer.images = [f"https://example.com/{i}.jpg" for i in range(12)]

        env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["3"])

        media = env.handler._send_media_group.call_args.args[1]
        assert len(media) == 10 and media[0] == {"type": "photo", "media": "https://example.com/0.jpg"}

    def test_s3_images_are_sent_presigned(self, env, offer):
        s3_url = "https://ubbc-bot-test-images.s3.amazonaws.com/offers/3/a.jpg"
        offer.images = [s3_url]
        env.db.get_presigned_url.return_value = "https://signed.example/a.jpg"

        env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["3"])

        env.db.get_presigned_url.assert_called_once_with(s3_url)
        env.handler._send_photo.assert_called_once_with(CHAT, "https://signed.example/a.jpg")

    @pytest.mark.parametrize("user", [CUSTOMER_ID, ADMIN_ID])
    def test_the_name_and_supplier_are_escaped_and_the_description_is_html(self, env, offer, user):
        offer.name = "Bier & Co <3"
        offer.supplier_name = "Brouwerij <De Molen>"
        offer.description = "<b>Lekker</b> fris"

        env.handler.handle_view_offer(CHAT, user, ["3"])

        text = sent(env)
        assert "Bier &amp; Co &lt;3" in text and "Bier & Co" not in text
        assert "<De Molen>" not in text
        assert "<b>Lekker</b> fris" in text

    def test_an_unknown_offer(self, env):
        env.db.get_offer.return_value = None

        assert env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["8"]) == {"status": "offer_not_found"}

    def test_a_non_numeric_id(self, env):
        assert env.handler.handle_view_offer(CHAT, CUSTOMER_ID, ["acht"]) == {"status": "invalid_format"}

    def test_without_an_id_the_list_is_shown(self, env):
        env.handler.handle_view_offer(CHAT, CUSTOMER_ID, [])

        assert sent(env).startswith("📋 Actieve Aanbiedingen:")


class TestStartAndHelp:
    def test_start_for_a_customer(self, env):
        env.handler.handle_start(CHAT, CUSTOMER_ID)

        text = sent(env)
        assert "UBBC" in text
        assert env.handler._t("admin_sections_available") not in text

    def test_start_for_the_admin_mentions_the_admin_sections(self, env):
        env.handler.handle_start(CHAT, ADMIN_ID)

        assert env.handler._t("admin_sections_available") in sent(env)

    def test_start_with_a_section_shows_that_section(self, env):
        env.handler.handle_start(CHAT, CUSTOMER_ID, ["orders"])

        assert sent(env) == env.handler._t("help_orders")

    def test_help_lists_the_sections_with_the_bot_name(self, env):
        env.handler.handle_help(CHAT, CUSTOMER_ID)

        assert "ubbc_bot" in sent(env)
        assert last_call(env).kwargs == {"parse_mode": "Markdown"}

    @pytest.mark.parametrize("section", ["general", "orders"])
    def test_customer_sections(self, env, section):
        env.handler.handle_help(CHAT, CUSTOMER_ID, [section.upper()])

        assert sent(env) == env.handler._t(f"help_{section}")

    @pytest.mark.parametrize("section", ["suppliers", "offers", "users", "delivery", "import", "system", "reports"])
    def test_admin_sections_are_admin_only(self, env, section):
        env.handler.handle_help(CHAT, CUSTOMER_ID, [section])
        assert sent(env) == env.handler._t("admin_only_section")

        env.handler._send_message.reset_mock()
        env.handler.handle_help(CHAT, ADMIN_ID, [section])
        assert sent(env) == env.handler._t(f"help_{section}")

    def test_all_sends_every_section_the_caller_may_see(self, env):
        env.handler.handle_help(CHAT, CUSTOMER_ID, ["all"])
        assert env.handler._send_message.call_count == 2

        env.handler._send_message.reset_mock()
        env.handler.handle_help(CHAT, ADMIN_ID, ["all"])
        assert env.handler._send_message.call_count == 9

    def test_an_unknown_section_lists_the_ones_there_are(self, env):
        env.handler.handle_help(CHAT, CUSTOMER_ID, ["bier"])

        text = sent(env)
        assert "bier" in text and "general, orders, all" in text
        assert "reports" not in text


class TestFomoAndSubscriptions:
    def test_fomo_lists_active_offers_not_ordered_yet_by_name(self, env):
        customer = Customer(customer_id="c1", telegram_user_id=CUSTOMER_ID, first_name="Jan")
        env.db.get_customer_by_telegram_id.return_value = customer
        env.db.get_orders_by_customer.return_value = [
            Order(offer_id=4, status="pending"),
            Order(offer_id=3, status="cancelled"),
        ]

        env.handler.handle_fomo(CHAT, CUSTOMER_ID)

        assert offer_ids(sent(env)) == [3]  # Stout is ordered; the cancelled Pils order does not count

    def test_fomo_needs_a_registered_customer(self, env):
        assert env.handler.handle_fomo(CHAT, CUSTOMER_ID) == {"status": "not_registered"}

    @pytest.mark.parametrize(("method", "value"), [("handle_subscribe", True), ("handle_unsubscribe", False)])
    def test_subscribing(self, env, method, value):
        env.db.get_customer_by_telegram_id.return_value = Customer(customer_id="c1", telegram_user_id=CUSTOMER_ID)
        env.db.update_customer.return_value = True

        assert getattr(env.handler, method)(CHAT, CUSTOMER_ID) == {"status": "success"}
        env.db.update_customer.assert_called_once_with("c1", {"subscribed_to_offers": value})

    def test_a_failed_subscription_update(self, env):
        env.db.get_customer_by_telegram_id.return_value = Customer(customer_id="c1", telegram_user_id=CUSTOMER_ID)
        env.db.update_customer.return_value = False

        assert env.handler.handle_subscribe(CHAT, CUSTOMER_ID) == {"status": "error"}
