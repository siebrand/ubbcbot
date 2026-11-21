"""An admin who reads English gets English on the payment and import screens (audit 5, B4) and the order screens
(audit 6, B4), against the mocked database. Every Dutch text is marked, so a text that bypasses the admin's
language shows."""

import json
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.import_handler import ImportHandler
from handlers.admin.labeling_commands import LabelingCommands
from handlers.admin.order.order_cancellation import OrderCancellation
from handlers.admin.order.order_editing import OrderEditing
from handlers.admin.order.order_placement import OrderPlacement
from handlers.admin.order.order_status import OrderStatusManagement
from handlers.admin.order.order_viewing import OrderViewing
from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler
from handlers.base_handler import BaseHandler
from models.entities import AuthorizationStatus, Box, Customer, Offer, Order, OrderStatus
from services import translator
from services.database import DynamoDBService
from services.user_cache import UserCache

ADMIN_ID = 15005473
BOX_ID = "abcdef12-0000-4000-8000-000000000000"
DUTCH = "🇳🇱"


@pytest.fixture
def db(dynamodb, monkeypatch):
    UserCache.invalidate_cache()
    monkeypatch.setitem(translator._loaded, "en", translator.load_translations("en"))
    monkeypatch.setitem(translator._loaded, "nl", {k: DUTCH + v for k, v in translator.load_translations("nl").items()})
    service = DynamoDBService()
    service.create_offer(
        Offer(offer_id=7, name="Pils", price_per_unit=Decimal("1.00"), wholesale_box_size=24, status="sold_out")
    )
    assert service.create_box(Box(box_id=BOX_ID, offer_id=7, max_capacity=24, current_quantity=24, status="delivered"))
    # The admin's own record says English; it is not a customer that orders
    service.create_customer(Customer(telegram_user_id=ADMIN_ID, first_name="Admin", language="en"))
    yield service
    UserCache.invalidate_cache()


@pytest.fixture
def jan(db) -> Customer:
    """A Dutch customer with a labeled order and one awaiting payment"""
    jan = db.create_customer(
        Customer(telegram_user_id=101, first_name="Jan", authorization_status=AuthorizationStatus.APPROVED.value)
    )
    for status in (OrderStatus.LABELING_COMPLETED, OrderStatus.AWAITING_PAYMENT):
        assert db.order_repo.create_order(
            Order(
                customer_id=jan.customer_id,
                box_id=BOX_ID,
                offer_id=7,
                quantity=2,
                received_quantity=2,
                unit_price=Decimal("1.00"),
                total_price=Decimal("2"),
                status=status.value,
                payment_link="https://pay.example/jan" if status == OrderStatus.AWAITING_PAYMENT else None,
            )
        )
    return jan


@pytest.fixture(autouse=True)
def sent():
    """Every message any handler sends, also the ones a screen builds on its way back to a list"""
    with patch.object(BaseHandler, "_send_message", Mock(return_value={"success": True})) as sent:
        yield sent


def screen(cls, db):
    handler = cls(db, ADMIN_ID, "prod", "token")
    handler.lambda_client = Mock()
    handler._send_user_message = Mock(return_value={"success": True})
    return handler


def admin_texts(handler) -> list[str]:
    """Every text the admin got: the messages and their buttons"""
    texts = []
    for c in BaseHandler._send_message.call_args_list:
        if c.args[0] != ADMIN_ID:
            continue
        texts.append(c.args[1])
        markup = c.kwargs.get("reply_markup") or {}
        texts += [b["text"] for row in markup.get("inline_keyboard", []) for b in row]
        if "input_field_placeholder" in markup:
            texts.append(markup["input_field_placeholder"])
    return texts


def assert_english(handler) -> None:
    texts = admin_texts(handler)
    assert texts
    dutch = [t for t in texts if DUTCH in t]
    assert dutch == []


class TestThePaymentScreens:
    def test_send_delivery_overviews(self, db, jan):
        handler = screen(OrderStatusManagement, db)

        handler.handle_send_delivery_overviews(ADMIN_ID, [])

        assert_english(handler)
        assert "Customers to notify: 1" in admin_texts(handler)[0]

    def test_the_overviews_from_start_to_the_next_batch(self, db, jan):
        handler = screen(DeliveryOverviewHandler, db)
        handler.start_send_overviews(ADMIN_ID)
        handler.handle_payment_link_input(ADMIN_ID, "not a link", db.get_edit_context_by_chat_id(ADMIN_ID).entity_id)
        # A second batch waits: 50 more customers (gone since) after Jan
        context = json.loads(db.get_edit_context_by_chat_id(ADMIN_ID).entity_id)
        context["customers_data"] += [
            {"customer_id": f"gone-{n}", "delivered_order_ids": [], "delayed_order_ids": [], "is_guest": False}
            for n in range(50)
        ]

        handler.handle_payment_link_input(ADMIN_ID, "https://pay.example/a", json.dumps(context))

        assert_english(handler)
        assert any("Ready for the next batch" in t for t in admin_texts(handler))
        # The customer's own message stays in their language
        (message,) = json.loads(handler.lambda_client.invoke.call_args.kwargs["Payload"])["messages"]
        assert DUTCH in message["message"]

    def test_a_failing_link_reply(self, db, jan):
        handler = screen(DeliveryOverviewHandler, db)
        handler.start_send_overviews(ADMIN_ID)
        db.batch_update_order_status = Mock(side_effect=RuntimeError("boom"))

        handler.handle_payment_link_input(
            ADMIN_ID, "https://pay.example/a", db.get_edit_context_by_chat_id(ADMIN_ID).entity_id
        )

        assert_english(handler)

    def test_process_payment_and_marking_paid(self, db, jan):
        handler = screen(DeliveryOverviewHandler, db)

        handler.handle_process_customer_paid(ADMIN_ID, jan.customer_id)
        handler.handle_process_customer_paid(ADMIN_ID, jan.customer_id)  # nothing left
        handler.handle_process_customer_paid(ADMIN_ID, "gone")

        assert_english(handler)

    def test_the_lists(self, db, jan):
        handler = screen(OrderStatusManagement, db)

        handler.handle_process_payment(ADMIN_ID, [])
        handler.handle_send_payment_reminder(ADMIN_ID, [])
        handler.handle_failed_notifications(ADMIN_ID, [])

        assert_english(handler)

    def test_the_empty_lists(self, db):
        handler = screen(OrderStatusManagement, db)

        handler.handle_send_delivery_overviews(ADMIN_ID, [])
        handler.handle_process_payment(ADMIN_ID, [])
        handler.handle_send_payment_reminder(ADMIN_ID, [])
        handler.handle_failed_notifications(ADMIN_ID, [])

        assert_english(handler)

    def test_a_reminder(self, db, jan):
        handler = screen(OrderStatusManagement, db)

        handler.handle_send_payment_reminder_to_customer(ADMIN_ID, jan.customer_id)
        handler._send_user_message.return_value = {"success": False, "error": "RuntimeError"}
        handler.handle_send_payment_reminder_to_customer(ADMIN_ID, jan.customer_id)
        handler.handle_send_payment_reminder_to_customer(ADMIN_ID, "gone")

        assert_english(handler)
        # The reminder itself is in the customer's language
        assert DUTCH in handler._send_user_message.call_args.args[1]


def place(db, who, order_id, box_id=BOX_ID, status=OrderStatus.PENDING.value) -> Order:
    order = Order(
        order_id=order_id,
        customer_id=who.customer_id,
        box_id=box_id,
        offer_id=7,
        quantity=1,
        unit_price=Decimal("1.00"),
        total_price=Decimal("1.00"),
        status=status,
    )
    assert db.order_repo.create_order(order)
    return order


class TestTheOrderScreens:
    """Audit 6, B4: the order handlers translate for the admin"""

    @pytest.fixture
    def orders(self, db, jan):
        """Two orders whose ids start alike (a short id that matches both), one in an open box with room"""
        assert db.create_box(Box(box_id="open0000-box", offer_id=7, max_capacity=6, current_quantity=1, status="open"))
        assert db.create_box(Box(box_id="open1111-box", offer_id=7, max_capacity=6, current_quantity=0, status="open"))
        return place(db, jan, "dup00000-0001", "open0000-box"), place(db, jan, "dup00000-0002", "open0000-box")

    def test_edit_order(self, db, orders):
        order = orders[0]
        handler = screen(OrderEditing, db)

        handler.handle_edit_order(ADMIN_ID, ["dup0"])  # two orders match
        handler.handle_edit_order(ADMIN_ID, [order.order_id])
        handler.show_box_options(ADMIN_ID, order.order_id)
        handler.confirm_box(ADMIN_ID, order.order_id, "open1111")
        handler.show_status_options(ADMIN_ID, order.order_id)
        handler.confirm_status(ADMIN_ID, order.order_id, "ordered")
        handler.apply_price_input(ADMIN_ID, order.order_id, "2")

        assert_english(handler)

    def test_cancel_order(self, db, jan, orders):
        handler = screen(OrderCancellation, db)
        place(db, jan, "nobox000-0001", "gone-box")

        handler.handle_cancel_order(ADMIN_ID, [])
        handler.handle_cancel_order(ADMIN_ID, ["dup0"])
        handler.handle_cancel_order(ADMIN_ID, [orders[0].order_id])
        handler.handle_confirm_cancel_with_reason(ADMIN_ID, "gone", "reason")
        handler.handle_confirm_cancel_with_reason(ADMIN_ID, "nobox000-0001", "reason")

        assert_english(handler)

    def test_order_for(self, db, jan):
        handler = screen(OrderPlacement, db)
        db.create_offer(Offer(offer_id=8, name="Abdij", price_per_unit=Decimal("2.00"), wholesale_box_size=6))
        db.update_offer(8, {"status": "active"})

        handler.handle_create_order_for(ADMIN_ID, ADMIN_ID, [])
        handler.handle_create_order_for(ADMIN_ID, ADMIN_ID, ["Jan", "7", "0"])  # not positive
        handler.handle_create_order_for(ADMIN_ID, ADMIN_ID, ["Jan", "zeven"])
        handler.handle_create_order_for(ADMIN_ID, ADMIN_ID, ["Jan", "7"])  # sold out
        handler.handle_create_order_for(ADMIN_ID, ADMIN_ID, ["Jan", "99"])  # no such offer
        handler.handle_create_order_for_user_select(ADMIN_ID, jan.customer_id)  # the offers
        handler.handle_create_order_for_offer_select(ADMIN_ID, jan.customer_id, "8")  # the quantities
        handler.handle_create_order_for_offer_select(ADMIN_ID, jan.customer_id, "acht")
        handler.handle_create_order_for_offer_select(ADMIN_ID, "gone", "8")
        handler.handle_create_order_for_quantity_select(ADMIN_ID, jan.customer_id, "8", "11")  # over the limit

        assert_english(handler)

    def test_order_for_without_offers(self, db, jan):
        handler = screen(OrderPlacement, db)

        handler.handle_create_order_for_user_select(ADMIN_ID, jan.customer_id)

        assert_english(handler)

    def test_order_lists_and_exports(self, db, jan):
        handler = screen(OrderViewing, db)
        handler._send_document_message = Mock(return_value={"success": False})

        handler.handle_list_user_orders(ADMIN_ID, [])
        handler.handle_export_orders(ADMIN_ID, [])
        handler.handle_export_orders(ADMIN_ID, ["cancelled"])  # none
        handler.handle_export_orders(ADMIN_ID, ["all"])  # the document fails
        handler.handle_list_offer_orders(ADMIN_ID, [])
        handler.handle_list_offer_orders_select(ADMIN_ID, "7")

        assert_english(handler)

    def test_the_export_caption(self, db, jan):
        handler = screen(OrderViewing, db)
        handler._send_document_message = Mock(return_value={"success": True, "message_id": 5})

        handler.handle_export_orders(ADMIN_ID, ["all"])

        caption = handler._send_document_message.call_args.args[3]
        assert DUTCH not in caption

    def test_wholesale_delivery(self, db):
        assert db.create_box(
            Box(box_id="ordered0-box", offer_id=7, max_capacity=6, current_quantity=6, status="ordered")
        )
        handler = screen(WholesaleDeliveryHandler, db)

        handler.handle_complete_delivery(ADMIN_ID, 7, "")
        keyboard = handler._build_triage_keyboard("ordered0-box", 7, "")

        assert_english(handler)
        assert not [b["text"] for row in keyboard["inline_keyboard"] for b in row if DUTCH in b["text"]]

    def test_finish_labeling(self, db, jan):
        handler = screen(LabelingCommands, db)
        place(db, jan, "label000-0001", status=OrderStatus.READY_FOR_LABELING.value)

        handler.handle_finish_labeling(ADMIN_ID, "empty000-box")
        handler.handle_finish_labeling(ADMIN_ID, BOX_ID)

        assert_english(handler)


class TestTheImportScreens:
    def test_the_prompt_a_second_prompt_and_the_summary(self, db, jan):
        handler = screen(ImportHandler, db)
        handler.handle_import_orders(ADMIN_ID, ADMIN_ID)
        handler.handle_import_orders(ADMIN_ID, ADMIN_ID)  # already waiting for a file
        csv = "offer_id,username\nx,jan\n99,jan\n7,jan\n7,nobody\n"

        with patch.object(handler, "_download_file", return_value=csv.encode()):
            handler.handle_document_upload(ADMIN_ID, ADMIN_ID, "file", "orders.csv")

        assert_english(handler)

    def test_a_file_that_is_refused(self, db, jan):
        handler = screen(ImportHandler, db)
        handler.handle_import_orders(ADMIN_ID, ADMIN_ID)

        with patch.object(handler, "_download_file", return_value=b"wrong,headers\n1,2\n"):
            handler.handle_document_upload(ADMIN_ID, ADMIN_ID, "file", "orders.csv")

        assert_english(handler)

    def test_finalize_import(self, db):
        handler = screen(ImportHandler, db)

        handler.handle_finalize_import(ADMIN_ID, [])  # usage
        handler.handle_finalize_import(ADMIN_ID, ["7"])  # not an import offer

        assert_english(handler)
