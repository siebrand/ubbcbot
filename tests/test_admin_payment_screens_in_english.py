"""An admin who reads English gets English on the payment and import screens (audit 5, B4), against the mocked
database. Every Dutch text is marked, so a text that bypasses the admin's language shows."""

import json
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.import_handler import ImportHandler
from handlers.admin.order.order_status import OrderStatusManagement
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
