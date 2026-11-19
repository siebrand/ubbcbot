"""/list_boxes and /audit_offer against the (mocked) database.

The audit compares the units of the active orders of an offer with the units in its boxes. Too many ordered units are
put in boxes with room (unordered boxes first), in new boxes, or, when there is no room at all, the newest orders are
cancelled.
"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.offer.boxes import BoxManagementHandler
from models.entities import AuthorizationStatus, Box, Customer, Offer, OfferStatus, Order, Supplier
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
PRICE = Decimal("2.50")


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    service = DynamoDBService()
    service.create_offer(
        Offer(
            offer_id=7,
            name="Pils",
            price_per_unit=PRICE,
            wholesale_box_size=6,
            supplier_name="Brouwerij",
            status=OfferStatus.ACTIVE.value,
        )
    )
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def handler(db):
    handler = BoxManagementHandler(db, ADMIN_ID, "prod", "token")
    handler.sent = []

    def send(chat, text, **kwargs):
        handler.sent.append((chat, text, kwargs))
        return {"success": True}

    handler._send_message = Mock(side_effect=send)
    handler.sync_offer_messages = Mock()
    return handler


def customer(db, telegram_id, name, language="nl"):
    return db.create_customer(
        Customer(
            telegram_user_id=telegram_id,
            first_name=name,
            language=language,
            authorization_status=AuthorizationStatus.APPROVED.value,
        )
    )


def order(db, order_id, who, box_id, quantity, day, status="pending", offer_id=7):
    created = Order(
        order_id=order_id,
        customer_id=who.customer_id,
        box_id=box_id,
        offer_id=offer_id,
        quantity=quantity,
        unit_price=PRICE,
        total_price=PRICE * quantity,
        status=status,
        created_at=f"2026-11-0{day}T10:00:00+00:00",
    )
    assert db.order_repo.create_order(created)
    return created


def box(db, box_id, quantity, status="open", offer_id=7, day=1):
    assert db.create_box(
        Box(
            box_id=box_id,
            offer_id=offer_id,
            max_capacity=6,
            current_quantity=quantity,
            status=status,
            created_at=f"2026-11-0{day}T09:00:00+00:00",
        )
    )


def quantity(db, box_id):
    return db.get_box(box_id).current_quantity


def messages_to(handler, chat_id) -> list[str]:
    return [text for chat, text, _ in handler.sent if chat == chat_id]


def last_buttons(handler) -> list[str]:
    markup = handler.sent[-1][2].get("reply_markup") or {}
    return [b["callback_data"] for row in markup.get("inline_keyboard", []) for b in row]


class TestListBoxes:
    @pytest.fixture
    def boxes(self, db):
        db.create_offer(Offer(offer_id=8, name="Stout", price_per_unit=PRICE, wholesale_box_size=6))
        box(db, "open0001", 2, "open", day=2)
        box(db, "full0001", 6, "full", day=3)
        box(db, "ordr0001", 6, "ordered", day=4)
        box(db, "dlvr0001", 6, "delivered", day=5)
        box(db, "stout001", 1, "open", offer_id=8)

    def _rows(self, handler) -> list[str]:
        text = messages_to(handler, ADMIN_ID)[-1]
        return [line for line in text.splitlines() if "  7  " in line or "  8  " in line]

    def test_active_boxes_by_offer_then_ordered_full_open(self, handler, boxes):
        handler.handle_list_boxes(ADMIN_ID)

        rows = self._rows(handler)
        assert [row.split()[2] for row in rows] == ["ordr0001", "full0001", "open0001", "stout001"]

    @pytest.mark.parametrize(
        "status, expected",
        [("ordered", ["ordr0001"]), ("full", ["full0001"]), ("delivered", ["dlvr0001"])],
    )
    def test_a_status_filter(self, handler, boxes, status, expected):
        handler.handle_list_boxes(ADMIN_ID, [status])

        assert [row.split()[2] for row in self._rows(handler)] == expected

    def test_all_boxes(self, handler, boxes):
        handler.handle_list_boxes(ADMIN_ID, ["all"])

        assert len(self._rows(handler)) == 5

    def test_the_boxes_of_one_offer(self, handler, boxes):
        handler.handle_list_boxes(ADMIN_ID, ["8"])

        assert [row.split()[2] for row in self._rows(handler)] == ["stout001"]

    def test_an_unknown_offer(self, handler, boxes):
        assert handler.handle_list_boxes(ADMIN_ID, ["99"]) == {"status": "offer_not_found"}

    def test_no_boxes(self, handler):
        assert handler.handle_list_boxes(ADMIN_ID, ["delivered"]) == {"status": "no_boxes"}

    def test_boxes_ready_for_labeling_get_a_button(self, db, handler, boxes):
        jan = customer(db, 101, "Jan")
        order(db, "o1", jan, "ordr0001", 6, 1, status="ready_for_labeling")
        order(db, "o2", jan, "full0001", 6, 1, status="ordered")

        handler.handle_list_boxes(ADMIN_ID)

        buttons = last_buttons(handler)
        assert "finish_labeling_ordr0001" in buttons
        assert "finish_labeling_full0001" not in buttons
        assert buttons[-1] == "admin:main"

    def test_a_long_list_is_paged(self, db, handler):
        for number in range(12):
            box(db, f"box{number:05d}", 1)

        handler.handle_list_boxes(ADMIN_ID, ["active", "2"])

        assert len(self._rows(handler)) == 2
        assert "page_boxes_active_1" in last_buttons(handler)


class TestAudit:
    def test_matching_units(self, db, handler):
        jan = customer(db, 101, "Jan")
        box(db, "b1", 4)
        order(db, "o1", jan, "b1", 4, 1)

        assert handler.execute_audit_offer(ADMIN_ID, 7) == {"status": "match"}

    def test_more_room_in_boxes_than_ordered(self, db, handler):
        jan = customer(db, 101, "Jan")
        box(db, "b1", 5)
        order(db, "o1", jan, "b1", 4, 1)

        assert handler.execute_audit_offer(ADMIN_ID, 7) == {"status": "excess_capacity"}

    def test_excess_orders_go_in_a_box_with_room(self, db, handler):
        jan = customer(db, 101, "Jan")
        box(db, "b1", 2)
        order(db, "o1", jan, "b1", 4, 1)

        handler.execute_audit_offer(ADMIN_ID, 7)
        assert "audit_fill_boxes_7_2" in last_buttons(handler)

        assert handler.execute_fill_boxes(ADMIN_ID, 7, 2) == {"status": "boxes_filled", "filled": 2}
        assert quantity(db, "b1") == 4

    def test_unordered_boxes_are_filled_before_ordered_ones(self, db, handler):
        box(db, "ordered1", 4, "ordered")
        box(db, "open0001", 4, "open")

        handler.execute_fill_boxes(ADMIN_ID, 7, 3)

        assert quantity(db, "open0001") == 6
        assert quantity(db, "ordered1") == 5

    def test_excess_orders_without_any_box_get_new_boxes(self, db, handler):
        jan = customer(db, 101, "Jan")
        order(db, "o1", jan, "gone", 8, 1)

        handler.execute_audit_offer(ADMIN_ID, 7)
        assert "audit_create_boxes_7_8" in last_buttons(handler)

        assert handler.execute_create_boxes(ADMIN_ID, 7, 8) == {"status": "boxes_created", "boxes": 2}
        assert sorted(b.current_quantity for b in db.get_boxes_by_offer(7)) == [2, 6]

    def test_fill_and_create(self, db, handler):
        jan = customer(db, 101, "Jan")
        box(db, "b1", 4)
        order(db, "o1", jan, "b1", 12, 1)

        handler.execute_audit_offer(ADMIN_ID, 7)
        assert "audit_fill_create_7_8" in last_buttons(handler)

        result = handler.execute_fill_and_create(ADMIN_ID, 7, 8)
        assert result == {"status": "filled_and_created", "filled": 2, "remaining": 6}
        assert sorted(b.current_quantity for b in db.get_boxes_by_offer(7)) == [6, 6]

    def test_without_room_the_newest_orders_are_proposed_for_cancelling(self, db, handler):
        jan, piet, kees = customer(db, 101, "Jan"), customer(db, 102, "Piet"), customer(db, 103, "Kees")
        box(db, "b1", 6, "ordered")
        order(db, "o1", jan, "b1", 6, 1)
        order(db, "o2", piet, "b1", 2, 2)
        order(db, "o3", kees, "b1", 1, 3)

        handler.execute_audit_offer(ADMIN_ID, 7)

        proposal = messages_to(handler, ADMIN_ID)[-1]
        assert "Kees (1 " in proposal and "Piet (2 " in proposal and "Jan" not in proposal
        assert "units" not in proposal  # the admin's language is Dutch
        assert "audit_cancel_orders_7_3" in last_buttons(handler)

    def test_cancelling_the_newest_orders(self, db, handler):
        jan, piet, kees = customer(db, 101, "Jan"), customer(db, 102, "Piet", "en"), customer(db, 103, "Kees")
        box(db, "b1", 6, "ordered")
        order(db, "o1", jan, "b1", 4, 1)
        order(db, "o2", piet, "b1", 2, 2)
        order(db, "o3", kees, "b1", 1, 3)

        result = handler.execute_cancel_orders(ADMIN_ID, 7, 1)

        assert result == {"status": "orders_cancelled", "cancelled": 1}
        assert db.get_order("o3").status == "cancelled"
        assert db.get_order("o2").status == "pending"
        assert quantity(db, "b1") == 5
        assert len(messages_to(handler, 103)) == 1
        assert messages_to(handler, 102) == []

    def test_a_cancelled_customer_hears_it_in_their_own_language(self, db, handler):
        piet = customer(db, 102, "Piet", "en")
        box(db, "b1", 6, "ordered")
        order(db, "o2", piet, "b1", 2, 2)

        handler.execute_cancel_orders(ADMIN_ID, 7, 2)

        assert messages_to(handler, 102)[0].startswith("❌ Your order has been cancelled")


class TestAuditSelection:
    def test_open_offers_with_their_supplier(self, db, handler):
        db.create_supplier(Supplier(name="Brouwerij"))
        db.create_offer(Offer(offer_id=8, name="Oud", price_per_unit=PRICE, status=OfferStatus.INACTIVE.value))

        handler.show_audit_offer_selection(ADMIN_ID)

        markup = handler.sent[-1][2]["reply_markup"]["inline_keyboard"]
        texts = [b["text"] for row in markup for b in row]
        assert any("Pils" in text and "(Brouwerij)" in text for text in texts)
        assert not any("Oud" in text for text in texts)
