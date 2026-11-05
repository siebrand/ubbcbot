import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from models.entities import Offer, Order
from services.database import DynamoDBService


class TestDeliveryOverviewAggregation(unittest.TestCase):
    def setUp(self):
        self.mock_db = Mock(spec=DynamoDBService)
        self.handler = DeliveryOverviewHandler(self.mock_db, admin_user_id=1, environment="test", telegram_token="t")

    def _offer(self, offer_id, name):
        return Offer(offer_id=offer_id, name=name)

    def test_aggregates_same_offer_and_sums(self):
        # Two orders of the same offer (724) should collapse into one line.
        self.mock_db.get_offer.return_value = self._offer(724, "Fermentaria Local Reserva Local (WILD) 75cl")
        orders = [
            Order(offer_id=724, quantity=1, total_price=Decimal("11.50")),
            Order(offer_id=724, quantity=1, total_price=Decimal("11.50")),
        ]
        rows = self.handler._aggregate_order_lines(orders)
        self.assertEqual(len(rows), 1)
        name, offer_id, quantity, total = rows[0]
        self.assertEqual(offer_id, 724)
        self.assertEqual(quantity, 2)
        self.assertEqual(total, Decimal("23.00"))
        self.assertEqual(name, "Fermentaria Local Reserva Local (WILD) 75cl")

    def test_sorts_alphabetically_by_name(self):
        offers = {
            1: self._offer(1, "Zeta Beer"),
            2: self._offer(2, "alpha ale"),  # lowercase -> must still sort first
            3: self._offer(3, "Mango Sour"),
        }
        self.mock_db.get_offer.side_effect = lambda oid: offers[oid]
        orders = [
            Order(offer_id=1, quantity=1, total_price=Decimal("5")),
            Order(offer_id=2, quantity=1, total_price=Decimal("5")),
            Order(offer_id=3, quantity=1, total_price=Decimal("5")),
        ]
        names = [r[0] for r in self.handler._aggregate_order_lines(orders)]
        self.assertEqual(names, ["alpha ale", "Mango Sour", "Zeta Beer"])

    def test_line_format_includes_offer_id(self):
        self.mock_db.get_offer.return_value = self._offer(724, "Fermentaria Local Reserva Local (WILD) 75cl")
        orders = [
            Order(offer_id=724, quantity=1, total_price=Decimal("11.50")),
            Order(offer_id=724, quantity=1, total_price=Decimal("11.50")),
        ]
        name, offer_id, quantity, total = self.handler._aggregate_order_lines(orders)[0]
        line = f"- {quantity}x [{offer_id}] {name} — €{total:.2f}"
        self.assertEqual(line, "- 2x [724] Fermentaria Local Reserva Local (WILD) 75cl — €23.00")


if __name__ == "__main__":
    unittest.main()
