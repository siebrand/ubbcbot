"""Customer display names in the admin order handlers.

Customers can have no first and/or last name (guests, Telegram users without a
last name). The handlers must fall back to "Unknown" for a nameless customer
and must never render a missing part as the text "None".
"""

import os
import sys
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from handlers.admin.order.base_order_handler import BaseOrderHandler
from handlers.admin.order.order_cancellation import OrderCancellation
from handlers.admin.order.order_placement import OrderPlacement
from models.entities import Customer, OfferStatus, Order

ADMIN_ID = 15005473

# (label, first_name, last_name)
MISSING_NAME_CASES = [
    ("no last name", "Alice", None),
    ("no first name", None, "Smith"),
    ("empty last name", "Alice", ""),
]


def _customer(first, last):
    return Customer(customer_id="cust-1", telegram_user_id=1, first_name=first, last_name=last)


def _offer():
    return SimpleNamespace(
        offer_id=7,
        name="Test IPA",
        price_per_unit=Decimal("3.50"),
        supplier_name="Brewery",
        status=OfferStatus.ACTIVE.value,
    )


def _order(status="pending"):
    return Order(
        order_id="order-1",
        customer_id="cust-1",
        offer_id=7,
        quantity=2,
        unit_price=Decimal("3.50"),
        total_price=Decimal("7.00"),
        status=status,
        created_at=datetime(2026, 1, 5, 12, 0, tzinfo=UTC),
    )


class CustomerDisplayNameTestBase(unittest.TestCase):
    handler_class = None

    def setUp(self):
        self.db = Mock()
        self.handler = self.handler_class(self.db, ADMIN_ID, "test", "test_token")
        self.unknown = self.handler._t("unknown", user_id=None)

    def _sent_text(self, send_mock):
        send_mock.assert_called_once()
        return send_mock.call_args[0][1]

    def assert_shows_full_name(self, show):
        text = show(_customer("Alice", "Smith"))
        self.assertIn("Alice Smith", text)

    def assert_handles_missing_parts(self, show):
        for label, first, last in MISSING_NAME_CASES:
            with self.subTest(label):
                text = show(_customer(first, last))
                self.assertNotIn("None", text)
                self.assertIn(first or last, text)

    def assert_falls_back_to_unknown(self, show):
        for label, first, last in [("both None", None, None), ("both empty", "", "")]:
            with self.subTest(label):
                text = show(_customer(first, last))
                self.assertIn(self.unknown, text)


class TestPlacementOffersDisplayName(CustomerDisplayNameTestBase):
    handler_class = OrderPlacement

    def setUp(self):
        super().setUp()
        self.db.list_offers.return_value = [_offer()]
        self.db.get_supplier_by_name.return_value = SimpleNamespace(name="Brewery")

    def show(self, customer):
        with patch.object(OrderPlacement, "_send_message") as send:
            self.handler._show_offers_for_order_for(1, customer)
        return self._sent_text(send)

    def test_full_name(self):
        self.assert_shows_full_name(self.show)

    def test_missing_name_parts(self):
        self.assert_handles_missing_parts(self.show)

    def test_nameless_customer_shows_unknown(self):
        self.assert_falls_back_to_unknown(self.show)


class TestPlacementQuantityDisplayName(CustomerDisplayNameTestBase):
    handler_class = OrderPlacement

    def show(self, customer):
        with patch.object(OrderPlacement, "_send_message") as send:
            self.handler._show_quantity_selection_for_order_for(1, customer, _offer())
        return self._sent_text(send)

    def test_full_name(self):
        self.assert_shows_full_name(self.show)

    def test_missing_name_parts(self):
        self.assert_handles_missing_parts(self.show)

    def test_nameless_customer_shows_unknown(self):
        self.assert_falls_back_to_unknown(self.show)


class TestCancellationNoOrdersDisplayName(CustomerDisplayNameTestBase):
    handler_class = OrderCancellation

    def show(self, customer):
        self.db.get_orders_by_customer.return_value = []
        with patch.object(OrderCancellation, "_send_message") as send:
            self.handler._show_user_orders_for_cancel(1, customer)
        return self._sent_text(send)

    def test_full_name(self):
        self.assert_shows_full_name(self.show)

    def test_missing_name_parts(self):
        self.assert_handles_missing_parts(self.show)

    def test_nameless_customer_shows_unknown(self):
        self.assert_falls_back_to_unknown(self.show)


class TestCancellationOrderListDisplayName(CustomerDisplayNameTestBase):
    handler_class = OrderCancellation

    def show(self, customer):
        self.db.get_orders_by_customer.return_value = [_order()]
        self.db.get_offer.return_value = _offer()
        with patch.object(OrderCancellation, "_send_message") as send:
            self.handler._show_user_orders_for_cancel(1, customer)
        return self._sent_text(send)

    def test_full_name(self):
        self.assert_shows_full_name(self.show)

    def test_missing_name_parts(self):
        self.assert_handles_missing_parts(self.show)

    def test_nameless_customer_shows_unknown(self):
        self.assert_falls_back_to_unknown(self.show)


class TestBaseNoOrdersDisplayName(CustomerDisplayNameTestBase):
    handler_class = BaseOrderHandler

    def show(self, customer):
        self.db.get_orders_by_customer.return_value = []
        with patch.object(BaseOrderHandler, "_send_message") as send:
            self.handler.show_customer_orders(1, customer, user_id=ADMIN_ID)
        return self._sent_text(send)

    def test_full_name(self):
        self.assert_shows_full_name(self.show)

    def test_missing_name_parts(self):
        self.assert_handles_missing_parts(self.show)

    def test_nameless_customer_shows_unknown(self):
        self.assert_falls_back_to_unknown(self.show)


class TestBaseOrderListDisplayName(CustomerDisplayNameTestBase):
    handler_class = BaseOrderHandler

    def show(self, customer):
        self.db.get_orders_by_customer.return_value = [_order()]
        self.db.get_offer.return_value = _offer()
        with (
            patch.object(BaseOrderHandler, "_send_message") as send,
            patch.object(BaseOrderHandler, "_get_bot_username", return_value="test_bot"),
        ):
            self.handler.show_customer_orders(1, customer, user_id=ADMIN_ID)
        return self._sent_text(send)

    def test_full_name(self):
        self.assert_shows_full_name(self.show)

    def test_missing_name_parts(self):
        self.assert_handles_missing_parts(self.show)

    def test_nameless_customer_shows_unknown(self):
        self.assert_falls_back_to_unknown(self.show)


if __name__ == "__main__":
    unittest.main()
