"""Processing a wholesale delivery box by box, against the (mocked) database.

The delivery itself (WholesalerDeliveryService) has its own tests; here it is a stub. What is tested is the workflow
around it: finding the box from the short id in a button, the prompt for an incomplete delivery, the answer to it, and
where the admin is taken next.
"""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler
from models.entities import AuthorizationStatus, Box, Customer, DeliveryAction, Offer, OfferStatus, Order, Supplier
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
BOX_ID = "abcdef12-0000-4000-8000-000000000000"
OTHER_BOX_ID = "12345678-0000-4000-8000-000000000000"


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
            supplier_name="Brouwerij",
            status=OfferStatus.SOLD_OUT.value,
        )
    )
    service.create_offer(Offer(offer_id=8, name="Stout", price_per_unit=Decimal("3"), wholesale_box_size=6))
    jan = service.create_customer(
        Customer(telegram_user_id=101, first_name="Jan", authorization_status=AuthorizationStatus.APPROVED.value)
    )
    for box_id, offer_id in ((BOX_ID, 7), (OTHER_BOX_ID, 8)):
        assert service.create_box(
            Box(box_id=box_id, offer_id=offer_id, max_capacity=6, current_quantity=6, status="ordered")
        )
        assert service.order_repo.create_order(
            Order(
                customer_id=jan.customer_id,
                box_id=box_id,
                offer_id=offer_id,
                quantity=6,
                unit_price=Decimal("2.50"),
                total_price=Decimal("15"),
                status="ordered",
            )
        )
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def supplier(db):
    assert db.create_supplier(Supplier(name="Brouwerij"))
    return db.get_supplier_by_name("Brouwerij")


@pytest.fixture
def handler(db):
    handler = WholesaleDeliveryHandler(db, ADMIN_ID, "prod", "token")
    handler.sent = []

    def send(chat, text, **kwargs):
        handler.sent.append((chat, text, kwargs))
        return {"status": "sent"}

    handler._send_message = Mock(side_effect=send)
    handler.delivery_service.process_wholesaler_delivery = Mock(return_value=True)
    handler._check_offer_status_after_change = Mock()
    handler.handle_offer_selection = Mock(return_value={"status": "boxes_shown"})
    handler.handle_supplier_selection = Mock(return_value={"status": "offers_shown"})
    handler.handle_process_delivery = Mock(return_value={"status": "suppliers_shown"})
    return handler


def texts(handler) -> list[str]:
    return [text for _, text, _ in handler.sent]


def buttons(handler) -> list[tuple[str, str]]:
    markup = handler.sent[-1][2].get("reply_markup") or {}
    return [(b["text"], b["callback_data"]) for row in markup.get("inline_keyboard", []) for b in row]


def deliver(db):
    """What the delivery service does to the box status"""

    def process(box_id, _units, _is_delayed):
        db.update_box(box_id, {"status": "delivered"})
        return True

    return process


class TestRemainingUnits:
    """After an incomplete delivery: the rest comes later, or not at all"""

    @pytest.mark.parametrize(
        "action, is_delayed, word", [("delayed", True, "vertraagd"), ("cancel", False, "geannuleerd")]
    )
    def test_the_box_is_found_from_its_short_id(self, db, handler, supplier, action, is_delayed, word):
        result = handler.handle_partial_action(ADMIN_ID, action, BOX_ID[:8], 4)

        handler.delivery_service.process_wholesaler_delivery.assert_called_once_with(BOX_ID, 4, is_delayed)
        assert texts(handler) == [
            handler._t("partial_delivery_processed", ADMIN_ID, box_id=BOX_ID[:8], received_units=4, action=word)
        ]
        assert result == {"status": "boxes_shown"}
        handler.handle_offer_selection.assert_called_once_with(ADMIN_ID, 7, supplier.supplier_id[:8])

    def test_an_unknown_box(self, handler):
        handler.handle_partial_action(ADMIN_ID, "delayed", "ffffffff", 4)

        assert texts(handler) == [handler._t("box_not_found", ADMIN_ID)]
        handler.delivery_service.process_wholesaler_delivery.assert_not_called()

    def test_a_failed_delivery(self, handler):
        handler.delivery_service.process_wholesaler_delivery.return_value = False

        handler.handle_partial_action(ADMIN_ID, "delayed", BOX_ID[:8], 4)

        assert texts(handler) == [handler._t("delivery_processing_failed", ADMIN_ID)]


class TestNextStep:
    def test_with_no_ordered_box_left_the_admin_goes_back_to_the_offers_of_the_supplier(self, db, handler, supplier):
        handler.delivery_service.process_wholesaler_delivery.side_effect = deliver(db)

        result = handler.handle_partial_action(ADMIN_ID, "cancel", BOX_ID[:8], 4)

        assert result == {"status": "offers_shown"}
        handler.handle_supplier_selection.assert_called_once_with(ADMIN_ID, supplier.supplier_id[:8])

    def test_without_a_known_supplier_the_admin_goes_back_to_the_start(self, db, handler):
        handler.delivery_service.process_wholesaler_delivery.side_effect = deliver(db)

        result = handler.handle_partial_action(ADMIN_ID, "cancel", BOX_ID[:8], 4)

        assert result == {"status": "suppliers_shown"}

    def test_a_full_delivery_also_moves_on(self, db, handler, supplier):
        result = handler.handle_delivery_action(ADMIN_ID, DeliveryAction.FULL.value, BOX_ID[:8], 7, "sup")

        handler.delivery_service.process_wholesaler_delivery.assert_called_once_with(BOX_ID, 6, False)
        assert result == {"status": "boxes_shown"}


class TestIncompleteDelivery:
    def test_the_admin_is_asked_how_many_units_came(self, db, handler):
        handler.handle_delivery_action(ADMIN_ID, DeliveryAction.INCOMPLETE.value, BOX_ID[:8], 7, "sup")

        context = db.get_edit_context_by_chat_id(ADMIN_ID)
        assert context.edit_type == "incomplete_delivery"
        assert context.entity_id == f"{BOX_ID}:6:7:sup"
        assert texts(handler) == [handler._t("enter_received_quantity", ADMIN_ID, total_units=6)]
        assert handler.sent[-1][2]["reply_markup"]["force_reply"] is True

    def test_all_units_is_a_full_delivery(self, handler, supplier):
        handler.handle_incomplete_delivery_reply(ADMIN_ID, "6", f"{BOX_ID}:6:7:sup")

        handler.delivery_service.process_wholesaler_delivery.assert_called_once_with(BOX_ID, 6, False)

    @pytest.mark.parametrize("received", ["0", "2"])
    def test_fewer_units_asks_what_happens_to_the_rest(self, handler, received):
        handler.handle_incomplete_delivery_reply(ADMIN_ID, received, f"{BOX_ID}:6:7:sup")

        assert buttons(handler) == [
            (handler._t("remaining_delayed_btn", ADMIN_ID), f"wd_partial:delayed:{BOX_ID[:8]}:{received}"),
            (handler._t("remaining_cancelled_btn", ADMIN_ID), f"wd_partial:cancel:{BOX_ID[:8]}:{received}"),
        ]
        handler.delivery_service.process_wholesaler_delivery.assert_not_called()

    @pytest.mark.parametrize("received, key", [("7", "invalid_quantity_range"), ("-1", "invalid_quantity_range")])
    def test_a_number_out_of_range(self, handler, received, key):
        handler.handle_incomplete_delivery_reply(ADMIN_ID, received, f"{BOX_ID}:6:7:sup")

        assert texts(handler) == [handler._t(key, ADMIN_ID, max_units=6)]

    def test_not_a_number(self, handler):
        handler.handle_incomplete_delivery_reply(ADMIN_ID, "veel", f"{BOX_ID}:6:7:sup")

        assert texts(handler) == [handler._t("invalid_number_format", ADMIN_ID)]


class TestTriage:
    def test_every_option_is_translated(self, handler):
        keyboard = handler._build_triage_keyboard(BOX_ID, 7, "sup")

        labels = [b["text"] for row in keyboard["inline_keyboard"] for b in row]
        assert handler._t("delayed_delivery_btn", None) in labels
        assert "⏳ Delayed" not in labels
