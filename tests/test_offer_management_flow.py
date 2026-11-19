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

    def test_the_box_of_the_cancelled_order_is_emptied_and_removed(self, db, handler, three_orders):
        handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "1"])

        assert db.get_box("b2") is None
        assert db.get_box("b1").current_quantity == 6

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

    def test_the_customer_is_told_in_their_own_language(self, db, handler, orders):
        handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "1"])

        english = handler._load_translations("en")["order_updated_limited"]
        assert messages_to(handler, 102) == [english.format(name="Pils", old_qty=4, new_qty=2, total=5.0)]

    def test_its_box_keeps_only_the_reduced_quantity(self, db, handler, orders):
        handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "1"])

        assert db.get_box("b2").current_quantity == 2
        assert db.get_box("b2").status == "ordered"


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

    def test_each_customer_is_told_in_their_language_and_guests_not_at_all(self, db, handler, three_orders):
        guest = customer(db, -1, "Gast", is_guest=True)
        box(db, "b3", 1)
        order(db, "o4", guest, "b3", 1, 4)

        handler.handle_confirm_cancel_offer(ADMIN_ID, ["7"])

        nl, en = handler._load_translations("nl"), handler._load_translations("en")
        params = {"name": "Pils", "quantity": 2, "total": 5.0}
        assert messages_to(handler, 102) == [en["order_cancelled_offer_cancelled"].format(**params)]
        assert messages_to(handler, 101)[0].startswith(nl["order_cancelled_offer_cancelled"][:10])
        assert messages_to(handler, -1) == []

    def test_an_offer_without_orders_is_cancelled_at_once(self, db, handler):
        assert handler.handle_cancel_offer(ADMIN_ID, ["7"]) == {"status": "success"}

        assert db.get_offer(7).status == "inactive"

    def test_an_offer_with_orders_asks_for_confirmation(self, db, handler, three_orders):
        assert handler.handle_cancel_offer(ADMIN_ID, ["7"]) == {"status": "confirmation_required"}

        assert db.get_offer(7).status == "active"


class TestWholesaleSummary:
    def test_the_pending_orders_are_listed_oldest_first_with_the_boxes_needed(self, db, handler, three_orders):
        assert handler.handle_process_wholesale(ADMIN_ID, ["7"]) == {"status": "success"}

        text = messages_to(handler, ADMIN_ID)[-1]
        assert text.index("Jan") < text.index("Piet") < text.index("Kees")
        keyboard = handler._send_message.call_args.kwargs["reply_markup"]["inline_keyboard"][0]
        # 9 units in boxes of 6: two boxes
        assert keyboard[0]["callback_data"] == "confirm_process_wholesale_7_2"
        assert keyboard[1]["callback_data"] == "custom_wholesale_quantity_7"

    def test_ordered_orders_are_not_listed_again(self, db, handler, three_orders):
        db.order_repo.update_order("o1", {"status": "ordered"})

        handler.handle_process_wholesale(ADMIN_ID, ["7"])

        assert "Jan" not in messages_to(handler, ADMIN_ID)[-1]

    def test_an_offer_without_pending_orders(self, db, handler):
        assert handler.handle_process_wholesale(ADMIN_ID, ["7"]) == {"status": "no_pending_orders"}

    @pytest.mark.parametrize("status", ["draft", "inactive", "completed"])
    def test_only_active_and_sold_out_offers_are_ordered(self, db, handler, status):
        db.update_offer(7, {"status": status})

        assert handler.handle_process_wholesale(ADMIN_ID, ["7"]) == {"status": "offer_not_active"}


class TestCustomWholesaleQuantityPrompt:
    def test_the_admin_is_asked_for_the_number_of_boxes(self, db, handler):
        assert handler.handle_custom_wholesale_quantity(ADMIN_ID, "7") == {"status": "awaiting_input"}

        context = db.get_edit_context_by_chat_id(ADMIN_ID)
        assert (context.edit_type, context.entity_id) == ("custom_wholesale_quantity", "7")

    def test_an_unknown_offer(self, db, handler):
        assert handler.handle_custom_wholesale_quantity(ADMIN_ID, "99") == {"status": "offer_not_found"}
        assert db.get_edit_context_by_chat_id(ADMIN_ID) is None

    def test_the_typed_box_count_processes_the_order(self, db, handler, three_orders):
        assert handler.handle_custom_wholesale_quantity_answer(ADMIN_ID, "7", "2") == {"status": "success"}

        assert {db.get_order(o).status for o in ("o1", "o2", "o3")} == {"ordered"}


class TestNextOfferButton:
    def buttons(self, handler) -> list[str]:
        markup = handler._send_message.call_args.kwargs["reply_markup"]
        return [button["callback_data"] for row in markup["inline_keyboard"] for button in row]

    def test_offered_while_another_offer_has_pending_orders(self, db, handler, three_orders):
        db.create_offer(Offer(offer_id=8, name="Abdij", wholesale_box_size=6, status=OfferStatus.ACTIVE.value))
        order(db, "o9", three_orders.jan, "b9", 1, 4)
        db.order_repo.update_order("o9", {"offer_id": 8})

        handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "2"])

        assert self.buttons(handler) == ["process_wholesale", "admin:main"]

    def test_not_offered_when_nothing_is_left(self, db, handler, three_orders):
        handler.handle_confirm_process_wholesale(ADMIN_ID, ["7", "2"])

        assert self.buttons(handler) == ["admin:main"]


class TestDeleteOffer:
    @pytest.mark.parametrize("status", ["completed", "inactive"])
    def test_a_finished_offer_is_deleted_with_its_boxes(self, db, handler, status):
        db.update_offer(7, {"status": status})
        box(db, "b1", 0)

        handler.handle_delete_offer(ADMIN_ID, ["7"])

        assert db.get_offer(7) is None
        assert db.get_boxes_by_offer(7) == []

    @pytest.mark.parametrize("status", ["active", "sold_out", "draft"])
    def test_an_offer_that_is_not_finished_stays(self, db, handler, status):
        db.update_offer(7, {"status": status})

        handler.handle_delete_offer(ADMIN_ID, ["7"])

        assert db.get_offer(7) is not None

    def test_several_offers_at_once_and_unknown_ids_are_skipped(self, db, handler):
        db.update_offer(7, {"status": "completed"})
        db.create_offer(Offer(offer_id=8, name="Abdij", wholesale_box_size=6, status=OfferStatus.INACTIVE.value))

        assert handler.handle_delete_offer(ADMIN_ID, ["7", "99", "8"]) == {"status": "success"}

        assert db.get_offer(7) is None and db.get_offer(8) is None

    def test_without_ids(self, db, handler):
        assert handler.handle_delete_offer(ADMIN_ID, []) == {"status": "invalid_args"}
