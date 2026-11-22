"""/offer_overview: the list of offers that can be ordered, grouped by the style in their name, for the admin to pin
in the group (services/offer_overview.py and the handler, against the moto database)"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.offer import OfferCommands
from models.entities import Box, Customer, Offer, OfferStatus
from services import offer_overview
from services.database import DynamoDBService
from services.offer_cache import OfferCache
from services.user_cache import UserCache

ADMIN_ID = 15005473


class TestTheStyleInTheName:
    @pytest.mark.parametrize(
        "name, group",
        [
            ("Kaapse Jack (NEIPA) 2x33cl", "ipa"),
            ("Azvex Seagull Queen (TIPA) 44cl", "ipa"),
            ("Hot Cakes #13 / #14 (SMOOTHIE) 2x50cl", "smoothie_sour"),
            ("Azvex Strategic Reserve V (Coconut Maple) (IMPSTOUT) 44cl", "dark"),
            ("Métaphore Colosseum of Life (Blend No. 3) (WILD) 75cl", "wild"),
            ("Some Blend (sour/neipa)", "smoothie_sour"),  # the first style decides; not case-sensitive
            ("Kees Bubberman 2026 75cl", "other"),
            ("Cambier Double Citra / Nectaron ()NEDIPA) 2x44cl", "other"),
            ("Two Things (IPA/Lagerish)", "other"),  # every part must be a style
            ("Grand Tsaar ((BA)OATMEALSTOUT) 3x33cl", "dark"),  # (BA)X: barrel aged and plain X
            ("Kees Stout (BA)IMPSTOUT 3x33cl", "other"),  # outside parentheses it is no style
            ("Kees Fudge (BA / IMPSTOUT) 3x33cl", "dark"),  # BA alone is barrel aged, no style
            ("Arpus 9 Year Anniversary (PILS / IPA / DIPA) 3x44cl", "ipa"),
            ("To Øl Best Copenhagen Bitter (BITTER / LAGER) 4x44cl", "ipa"),
            ("Rulles Estivale (SAISON) 75cl", "wild"),
            ("Mogwaï All You Need Is Grapes (2026) (GRAPEALE) 44cl", "wild"),
            ("Sparkle Billie & Buddy (ULTRA / ULTRA TIPA) 2x44cl", "ipa"),
            ("Popihn Cidre Fermier (2025) (CIDER) 75cl", "other"),
            ("Set Braziliaanse (D)IPA's 4x44cl", "other"),
        ],
    )
    def test_the_group(self, name, group):
        assert offer_overview.style_group(name) == group


def offer(offer_id, name, price="11.00"):
    return Offer(offer_id=offer_id, name=name, price_per_unit=Decimal(price), status=OfferStatus.ACTIVE.value)


class TestGrouping:
    def test_groups_in_their_order_each_lowest_number_first_and_empty_ones_left_out(self):
        offers = [
            offer(931, "Kaapse Jack (NEIPA)"),
            offer(899, "Compelling & Rich (BABARLEYWINE)"),
            offer(952, "Seagull Queen (TIPA)"),
            offer(964, "Kees Bubberman 2026"),
        ]

        groups = offer_overview.grouped(offers)

        assert [(key, [o.offer_id for o in group]) for key, group in groups] == [
            ("ipa", [931, 952]),
            ("dark", [899]),
            ("other", [964]),
        ]


class TestHowManyCanStillBeOrdered:
    def test_delivered_stock(self):
        boxes = [Box(max_capacity=6, current_quantity=4, status="delivered")]

        assert offer_overview.can_still_be_ordered(boxes) == 2

    def test_an_open_box(self):
        boxes = [Box(max_capacity=12, current_quantity=9, status="open")]

        assert offer_overview.can_still_be_ordered(boxes) == 3

    def test_the_room_of_every_box(self):
        boxes = [
            Box(max_capacity=6, current_quantity=5, status="delivered"),
            Box(max_capacity=6, current_quantity=2, status="ordered"),
        ]

        assert offer_overview.can_still_be_ordered(boxes) == 5

    def test_no_boxes_yet_or_only_full_ones_is_no_number(self):
        """The next order opens a new box: there is no limit to show"""
        assert offer_overview.can_still_be_ordered([]) is None
        assert offer_overview.can_still_be_ordered([Box(max_capacity=6, current_quantity=6, status="full")]) is None


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    OfferCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()
    OfferCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = OfferCommands(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler._get_bot_username = Mock(return_value="ubbc_bot")
    return handler


def add(db, offer_id, name, price, status=OfferStatus.ACTIVE.value, box=None):
    db.create_offer(Offer(offer_id=offer_id, name=name, price_per_unit=Decimal(price), status=status))
    if box:
        assert db.create_box(Box(offer_id=offer_id, **box))


class TestTheCommand:
    def test_the_list_for_the_admin(self, db, handler):
        add(
            db,
            931,
            "Kaapse Jack (NEIPA) 2x33cl",
            "6.40",
            box={"max_capacity": 2, "current_quantity": 1, "status": "delivered"},
        )
        add(db, 953, "Azvex Lolling (CUSTARDALE) 44cl", "12.00", box={"max_capacity": 12, "current_quantity": 9})
        add(db, 965, "Folkingebrew Base & Blueprint (IPA) 4x44cl", "25.00")
        add(db, 970, "Sold Out (IPA)", "5.00", status=OfferStatus.SOLD_OUT.value)
        add(db, 971, "Draft (IPA)", "5.00", status=OfferStatus.DRAFT.value)

        assert handler.handle_offer_overview(ADMIN_ID) == {"status": "success"}

        [call] = handler._send_message.call_args_list
        chat, text = call.args
        assert chat == ADMIN_ID and call.kwargs["parse_mode"] == "HTML"
        link = "<a href='https://t.me/ubbc_bot?start=view_offer_{0}'><b>{0}</b></a>"
        assert text == (
            "<b>Op dit moment te bestellen bij UBBC:</b>\n\n"
            "<b>IPA EN ZO</b>\n\n"
            f"🍺 {link.format(931)} <b>Kaapse Jack (NEIPA) 2x33cl</b> €6.40 (1)\n"
            f"🍺 {link.format(965)} <b>Folkingebrew Base &amp; Blueprint (IPA) 4x44cl</b> €25.00\n\n"
            "<b>DONKER</b>\n\n"
            f"🍺 {link.format(953)} <b>Azvex Lolling (CUSTARDALE) 44cl</b> €12.00 (3)"
        )

    def test_dutch_whatever_the_admins_language(self, db, handler):
        db.create_customer(Customer(telegram_user_id=ADMIN_ID, first_name="Admin", language="en"))
        add(db, 931, "Kaapse Jack (NEIPA)", "6.40")

        handler.handle_offer_overview(ADMIN_ID)

        assert handler._send_message.call_args.args[1].startswith("<b>Op dit moment te bestellen bij UBBC:</b>")

    def test_nothing_to_order(self, db, handler):
        assert handler.handle_offer_overview(ADMIN_ID) == {"status": "no_offers"}
        assert handler._send_message.call_args.args[1] == handler._t("offer_overview_empty", ADMIN_ID)

    def test_a_long_list_is_split_between_lines(self, db, handler):
        for offer_id in range(100, 200):
            add(db, offer_id, f"A rather long beer name number {offer_id} with extras (IPA) 2x44cl", "12.50")

        handler.handle_offer_overview(ADMIN_ID)

        messages = [c.args[1] for c in handler._send_message.call_args_list]
        assert len(messages) > 1
        assert all(len(m) <= 4000 for m in messages)
        assert sum(m.count("🍺 ") for m in messages) == 100
