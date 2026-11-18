"""Prompts that ask the admin to type an answer: the context is stored and the hint in the input field is translated."""

from unittest.mock import Mock, patch

import pytest

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.order.order_placement import OrderPlacement
from handlers.base_handler import BaseHandler
from models.entities import Customer
from services.callback_handler import CallbackHandler

ADMIN_ID = 15005473


@pytest.fixture
def db():
    db = Mock()
    db.get_customer_by_telegram_id.return_value = None  # the admin has no customer record: Dutch
    db.get_edit_context_by_chat_id.return_value = None
    db.cleanup_old_edit_contexts.return_value = 0
    return db


def english(db):
    db.get_customer_by_telegram_id.return_value = Customer(telegram_user_id=ADMIN_ID, language="en")


def reply_markup(send: Mock) -> dict:
    return send.call_args.kwargs["reply_markup"]


def placeholder(send: Mock) -> str:
    return reply_markup(send)["input_field_placeholder"]


class TestCancellationReason:
    @pytest.fixture
    def callback(self, db):
        handler = CallbackHandler(db, ADMIN_ID, "prod", "token", handlers={}, media_handler=Mock())
        handler._base_handler = BaseHandler(db, ADMIN_ID, "prod", "token")
        handler._base_handler._send_message = Mock(return_value={"success": True})
        return handler

    def test_the_reason_is_asked_and_the_order_remembered(self, callback, db):
        assert callback._request_cancellation_reason(ADMIN_ID, "order-1") == {"status": "awaiting_reason_input"}

        context = db.create_edit_context.call_args.args[0]
        assert (context.chat_id, context.edit_type, context.entity_id) == (ADMIN_ID, "cancel_order_reason", "order-1")
        send = callback._base_handler._send_message
        assert send.call_args.args[1] == callback._t("enter_cancellation_reason")
        assert reply_markup(send)["force_reply"] is True
        assert placeholder(send) == "Voer reden in"

    def test_the_hint_follows_the_admins_language(self, callback, db):
        english(db)

        callback._request_cancellation_reason(ADMIN_ID, "order-1")

        assert placeholder(callback._base_handler._send_message) == "Enter reason"


class TestPaymentLink:
    @pytest.fixture
    def handler(self, db):
        with patch("handlers.admin.delivery_overview_handler.boto3"):
            handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
        handler._send_message = Mock(return_value={"success": True})
        handler._store_context = Mock()
        return handler

    @pytest.mark.parametrize(("language", "hint"), [(None, "Voer betaallink in"), ("en", "Enter payment link")])
    def test_the_hint_is_translated(self, handler, db, language, hint):
        if language:
            english(db)

        assert handler._request_payment_link(ADMIN_ID, [{"customer_id": "c1"}], 0) == {
            "status": "awaiting_payment_link"
        }
        assert placeholder(handler._send_message) == hint


class TestOtherQuantity:
    @pytest.mark.parametrize(("language", "hint"), [(None, "Voer aantal in"), ("en", "Enter quantity")])
    def test_the_hint_is_translated(self, db, language, hint):
        if language:
            english(db)
        handler = OrderPlacement(db, ADMIN_ID, "prod", "token")
        handler._send_message = Mock(return_value={"success": True})

        assert handler.handle_create_order_for_other_quantity(ADMIN_ID, "c1", "7") == {
            "status": "awaiting_quantity_input"
        }
        assert db.create_edit_context.call_args.args[0].entity_id == "c1_7"
        assert placeholder(handler._send_message) == hint
