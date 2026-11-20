"""The order lists speak the language of whoever reads them: the customer's /my_orders, and the admin's cancel list
and payment reminders. Page labels and status names used to be English, or Dutch for everyone."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from handlers.admin.order.base_order_handler import BaseOrderHandler
from handlers.admin.order.order_cancellation import OrderCancellation
from handlers.admin.order.order_status import OrderStatusManagement
from models.entities import Customer, Order, OrderStatus

ADMIN_ID = 1
CUSTOMER_TELEGRAM_ID = 42


def _orders(count, status=OrderStatus.PENDING.value):
    return [
        Order(
            order_id=f"order-{n:02d}",
            customer_id="cust-1",
            offer_id=n,
            quantity=1,
            unit_price=Decimal("3.50"),
            total_price=Decimal("3.50"),
            status=status,
            created_at=datetime(2026, 11, 1, 12, n, tzinfo=UTC),
        )
        for n in range(1, count + 1)
    ]


def _handler(cls, language):
    """A handler whose reader (the admin or the customer) chose ``language``"""
    db = Mock()
    db.get_customer_by_telegram_id.return_value = SimpleNamespace(language=language)
    db.get_offer.return_value = SimpleNamespace(name="Pils")
    handler = cls(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler._get_bot_username = Mock(return_value="ubbc_bot")
    return handler


def _sent(handler):
    call = handler._send_message.call_args
    buttons = [b["text"] for row in call.kwargs["reply_markup"]["inline_keyboard"] for b in row]
    return call.args[1], buttons


CUSTOMER = Customer(customer_id="cust-1", telegram_user_id=CUSTOMER_TELEGRAM_ID, first_name="Jan", last_name="J")


class TestMyOrders:
    @pytest.mark.parametrize("language,page,status", [("nl", "Pagina 1/2", "OPEN:"), ("en", "Page 1/2", "PENDING:")])
    def test_the_customer_reads_the_list_in_their_language(self, language, page, status):
        handler = _handler(BaseOrderHandler, language)
        handler.db.get_orders_by_customer.return_value = _orders(11)

        handler.show_customer_orders(CUSTOMER_TELEGRAM_ID, CUSTOMER, user_id=CUSTOMER_TELEGRAM_ID)

        message, _ = _sent(handler)
        assert page in message
        assert status in message
        handler.db.get_customer_by_telegram_id.assert_called_with(CUSTOMER_TELEGRAM_ID)


class TestCancelList:
    @pytest.mark.parametrize(
        "language,title,previous,next_",
        [
            ("nl", "Bestelling annuleren voor Jan J", "◀️ Vorige", "Volgende ▶️"),
            ("en", "Cancel Order for Jan J", "◀️ Previous", "Next ▶️"),
        ],
    )
    def test_the_admin_reads_the_list_in_their_language(self, language, title, previous, next_):
        handler = _handler(OrderCancellation, language)
        handler.db.get_orders_by_customer.return_value = _orders(25)

        handler._show_user_orders_for_cancel(ADMIN_ID, CUSTOMER, page=2)

        message, buttons = _sent(handler)
        assert title in message
        assert previous in buttons and next_ in buttons
        assert ("Pagina 2/3" if language == "nl" else "Page 2/3") in buttons


class TestPaymentReminders:
    @pytest.mark.parametrize(
        "language,title,count",
        [
            ("nl", "Betalingsherinneringen - Pagina 1/1", "(2 bestellingen)"),
            ("en", "Payment Reminders - Page 1/1", "(2 orders)"),
        ],
    )
    def test_the_admin_reads_the_list_in_their_language(self, language, title, count):
        handler = _handler(OrderStatusManagement, language)
        handler.db.get_approved_customers_with_orders.return_value = [
            (CUSTOMER, _orders(2, OrderStatus.AWAITING_PAYMENT.value))
        ]

        handler.handle_send_payment_reminder(ADMIN_ID, [])

        message, _ = _sent(handler)
        assert title in message
        assert count in message
