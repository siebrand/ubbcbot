"""The offer checklist of /process_delivery and /process_labeling: tick offers, complete them all with one confirmation.

The ticks live in the keyboard of the message (Telegram sends it with every tap), so each test passes the keyboard of
the last screen back in, as Telegram does. Against the (moto) database."""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.labeling_completion_handler import LabelingCompletionHandler
from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler
from models.entities import AuthorizationStatus, Box, Customer, Offer, Order, Supplier
from services.callback_handler import CallbackHandler
from services.database import DynamoDBService
from services.offer_cache import OfferCache
from services.user_cache import UserCache

ADMIN_ID = 15005473
SUP = "sup12345"
MESSAGE = 77


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    OfferCache.invalidate_cache()
    service = DynamoDBService()
    service.create_supplier(Supplier(supplier_id=f"{SUP}-0000", name="DeMolen"))
    yield service
    UserCache.invalidate_cache()
    OfferCache.invalidate_cache()


@pytest.fixture
def jan(db):
    return db.create_customer(
        Customer(telegram_user_id=101, first_name="Jan", authorization_status=AuthorizationStatus.APPROVED.value)
    )


def offer(db, customer, offer_id, name, box_status, order_status, quantities=(2, 4)):
    db.create_offer(
        Offer(offer_id=offer_id, supplier_name="DeMolen", name=name, price_per_unit=Decimal("3"), status="sold_out")
    )
    box = db.create_box(Box(offer_id=offer_id, max_capacity=6, current_quantity=sum(quantities), status=box_status))
    for quantity in quantities:
        assert db.order_repo.create_order(
            Order(
                customer_id=customer.customer_id,
                box_id=box.box_id,
                offer_id=offer_id,
                quantity=quantity,
                received_quantity=quantity if order_status == "ready_for_labeling" else 0,
                unit_price=Decimal("3"),
                total_price=Decimal("3") * quantity,
                status=order_status,
            )
        )
    return box


class Screen:
    """What the handler showed last: its text and keyboard, and whether it edited the message in place"""

    def __init__(self, handler):
        self.shown = []

        def edit(chat_id, message_id, text, parse_mode=None, reply_markup=None):
            self.shown.append(("edit", text, reply_markup))
            return {"success": True}

        def send(chat_id, text, reply_markup=None, **_):
            self.shown.append(("send", text, reply_markup))
            return {"success": True, "message_id": MESSAGE}

        handler._edit_message_text = edit
        handler._send_message = send
        handler._notify_customer = Mock(return_value={"success": True})
        handler.sync_offer_messages = Mock()

    @property
    def last(self):
        return self.shown[-1]

    @property
    def markup(self):
        return self.last[2]

    def buttons(self):
        return [(b["text"], b["callback_data"]) for row in self.markup["inline_keyboard"] for b in row]

    def data(self):
        return [data for _, data in self.buttons()]


@pytest.fixture
def delivery(db):
    handler = WholesaleDeliveryHandler(db, ADMIN_ID, "prod", "token")
    return handler, Screen(handler)


@pytest.fixture
def two_ordered(db, jan):
    return offer(db, jan, 7, "Tripel", "ordered", "ordered"), offer(db, jan, 8, "Bock", "ordered", "ordered", (6,))


class TestTheChecklist:
    def test_picking_the_supplier_shows_every_offer_unticked_with_a_detail_button(self, delivery, two_ordered):
        handler, screen = delivery

        handler.handle_supplier_selection(ADMIN_ID, SUP)

        rows = screen.buttons()
        assert ("⏹️ Bock (1)", f"wd_tg:8:{SUP}") in rows
        assert ("⏹️ Tripel (1)", f"wd_tg:7:{SUP}") in rows
        assert ("›", f"wd_off:7:{SUP}") in rows
        assert ("✅ Aangetikte afronden (0)", f"wd_bulk:{SUP}") in rows

    def test_ticking_an_offer_edits_the_message_in_place(self, delivery, two_ordered):
        handler, screen = delivery
        handler.handle_supplier_selection(ADMIN_ID, SUP)

        handler.handle_checklist_toggle(ADMIN_ID, MESSAGE, screen.markup, 7, SUP)

        assert screen.last[0] == "edit"
        assert handler._selected(screen.markup) == {7}
        assert ("✅ Aangetikte afronden (1)", f"wd_bulk:{SUP}") in screen.buttons()

        handler.handle_checklist_toggle(ADMIN_ID, MESSAGE, screen.markup, 7, SUP)  # and off again
        assert handler._selected(screen.markup) == set()

    def test_all_and_none(self, delivery, two_ordered):
        handler, screen = delivery

        handler.handle_checklist_select(ADMIN_ID, MESSAGE, SUP, True)
        assert handler._selected(screen.markup) == {7, 8}
        handler.handle_checklist_select(ADMIN_ID, MESSAGE, SUP, False)
        assert handler._selected(screen.markup) == set()

    def test_the_detail_screen_still_works(self, delivery, two_ordered):
        handler, screen = delivery

        handler.handle_offer_selection(ADMIN_ID, 7, SUP)

        assert any(data.startswith("wd_box:") for data in screen.data())


class TestTheConfirmation:
    def test_nothing_ticked_says_so(self, delivery, two_ordered):
        handler, screen = delivery
        handler.handle_supplier_selection(ADMIN_ID, SUP)

        assert handler.handle_checklist_bulk(ADMIN_ID, MESSAGE, screen.markup, SUP) == {"status": "nothing_selected"}

    def test_it_totals_the_ticked_offers_and_carries_them(self, delivery, two_ordered):
        handler, screen = delivery
        handler.handle_checklist_select(ADMIN_ID, MESSAGE, SUP, True)

        handler.handle_checklist_bulk(ADMIN_ID, MESSAGE, screen.markup, SUP)

        text = screen.last[1]
        assert "Tripel" in text and "Bock" in text and "2 aanbieding(en), 2 doos/dozen, 12 stuks" in text
        assert handler._selected(screen.markup) == {7, 8}
        assert f"wd_bulkok:{SUP}" in screen.data()

    def test_back_keeps_the_ticks(self, delivery, two_ordered):
        handler, screen = delivery
        handler.handle_checklist_toggle(ADMIN_ID, MESSAGE, None, 8, SUP)
        handler.handle_checklist_bulk(ADMIN_ID, MESSAGE, screen.markup, SUP)

        handler.handle_checklist_back(ADMIN_ID, MESSAGE, screen.markup, SUP)

        assert handler._selected(screen.markup) == {8}
        assert f"wd_bulk:{SUP}" in screen.data()


class TestCompletingTheTickedOffers:
    def test_delivery_delivers_only_the_ticked_offers_in_full(self, db, delivery, two_ordered):
        handler, screen = delivery
        handler.handle_checklist_toggle(ADMIN_ID, MESSAGE, None, 7, SUP)
        handler.handle_checklist_bulk(ADMIN_ID, MESSAGE, screen.markup, SUP)

        result = handler.handle_checklist_confirm(ADMIN_ID, MESSAGE, screen.markup, SUP)

        assert result == {"status": "completed", "offers": 1, "skipped": 0, "failed": 0}
        assert db.get_box(two_ordered[0].box_id).status == "delivered"
        assert {o.status for o in db.get_orders_by_offer(7)} == {"ready_for_labeling"}
        assert db.get_box(two_ordered[1].box_id).status == "ordered"  # not ticked
        assert "1 aanbieding(en), 1 doos/dozen, 6 stuks" in screen.last[1]

    def test_a_second_confirmation_changes_nothing(self, db, delivery, two_ordered):
        handler, screen = delivery
        handler.handle_checklist_select(ADMIN_ID, MESSAGE, SUP, True)
        handler.handle_checklist_bulk(ADMIN_ID, MESSAGE, screen.markup, SUP)
        confirmation = screen.markup
        handler.handle_checklist_confirm(ADMIN_ID, MESSAGE, confirmation, SUP)

        again = handler.handle_checklist_confirm(ADMIN_ID, MESSAGE, confirmation, SUP)

        assert again["offers"] == 0 and again["skipped"] == 2
        assert "overgeslagen" in screen.last[1]

    def test_cancelled_and_delivered_orders_in_the_box_are_not_expected_from_the_wholesaler(self, db, jan, delivery):
        handler, screen = delivery
        box = offer(db, jan, 9, "Stout", "ordered", "ordered", (2, 3))
        for status, quantity in (("cancelled", 4), ("ready_for_labeling", 1)):
            assert db.order_repo.create_order(
                Order(
                    customer_id=jan.customer_id,
                    box_id=box.box_id,
                    offer_id=9,
                    quantity=quantity,
                    unit_price=Decimal("3"),
                    total_price=Decimal("3") * quantity,
                    status=status,
                )
            )

        assert handler._open_work(9) == (1, 5)
        assert handler._ordered_units(box.box_id) == 5

        handler.handle_checklist_toggle(ADMIN_ID, MESSAGE, None, 9, SUP)
        handler.handle_checklist_bulk(ADMIN_ID, MESSAGE, screen.markup, SUP)
        result = handler.handle_checklist_confirm(ADMIN_ID, MESSAGE, screen.markup, SUP)

        assert result["failed"] == 0
        assert db.get_box(box.box_id).status == "delivered"
        assert sorted((o.status, o.quantity) for o in db.get_orders_by_box(box.box_id)) == [
            ("cancelled", 4),
            ("ready_for_labeling", 1),
            ("ready_for_labeling", 2),
            ("ready_for_labeling", 3),
        ]
        assert "1 aanbieding(en), 1 doos/dozen, 5 stuks" in screen.last[1]

    def test_an_offer_handled_box_by_box_meanwhile_completes_only_what_is_left(self, db, jan, delivery):
        handler, screen = delivery
        first = offer(db, jan, 9, "Stout", "ordered", "ordered", (3,))
        second = offer(db, jan, 9, "Stout", "ordered", "ordered", (5,))
        handler.handle_checklist_toggle(ADMIN_ID, MESSAGE, None, 9, SUP)
        handler.handle_checklist_bulk(ADMIN_ID, MESSAGE, screen.markup, SUP)
        confirmation = screen.markup
        # Meanwhile the first box is handled through ›: incomplete, 1 of 3 units arrived, the rest is cancelled
        handler._process_box_delivery(first.box_id, 1, False)

        handler.handle_checklist_confirm(ADMIN_ID, MESSAGE, confirmation, SUP)

        assert db.get_box(second.box_id).status == "delivered"
        first_orders = db.get_orders_by_box(first.box_id)
        assert sorted((o.status, o.quantity) for o in first_orders) == [("cancelled", 2), ("ready_for_labeling", 1)]

    def test_labeling_labels_the_ticked_offers_and_completes_them(self, db, jan):
        offer(db, jan, 7, "Tripel", "delivered", "ready_for_labeling")
        offer(db, jan, 8, "Bock", "delivered", "ready_for_labeling", (6,))
        handler = LabelingCompletionHandler(db, ADMIN_ID, "prod", "token")
        screen = Screen(handler)
        handler.handle_checklist_select(ADMIN_ID, MESSAGE, SUP, True)
        handler.handle_checklist_bulk(ADMIN_ID, MESSAGE, screen.markup, SUP)

        handler.handle_checklist_confirm(ADMIN_ID, MESSAGE, screen.markup, SUP)

        assert {o.status for o in db.get_orders_by_offer(7) + db.get_orders_by_offer(8)} == {"labeling_completed"}
        assert {db.get_offer(7).status, db.get_offer(8).status} == {"completed"}


class TestTheButtonsKeepTheirMessage:
    """The checklist edits the tapped message: the router must not take its keyboard away (labeling's other
    buttons do lose it)"""

    @pytest.mark.parametrize("prefix, key", [("wd", "wholesale_delivery"), ("lc", "labeling")])
    @pytest.mark.parametrize("verb", ["tg:7:sup12345", "all:sup12345", "none:sup12345", "bulk:sup12345"])
    def test_tap(self, prefix, key, verb):
        workflow = Mock()
        callbacks = CallbackHandler(Mock(), ADMIN_ID, "test", "token", {key: workflow}, Mock())
        callbacks._answer_callback_query = Mock()
        callbacks._edit_message_remove_keyboard = Mock()
        markup = {"inline_keyboard": [[{"text": "☑ Tripel", "callback_data": f"{prefix}_tg:7:sup12345"}]]}
        message = {"chat": {"id": ADMIN_ID}, "message_id": MESSAGE, "reply_markup": markup}

        callbacks.handle_callback_query(
            {"id": "q", "from": {"id": ADMIN_ID}, "message": message, "data": f"{prefix}_{verb}"}
        )

        callbacks._edit_message_remove_keyboard.assert_not_called()
        assert workflow.method_calls  # the workflow got the tap
        if verb.startswith(("tg", "bulk")):
            assert markup in workflow.method_calls[0].args  # with the keyboard of the message
