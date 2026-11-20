import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from handlers.admin.order.order_editing import OrderEditing
from models.entities import Order


class TestOrderEditingPriceStatus(unittest.TestCase):
    def setUp(self):
        self.mock_db = Mock()
        self.handler = OrderEditing(self.mock_db, 15005473, "test", "token")

    def _order(self, **kw):
        defaults = {
            "order_id": "abc12345-1111",
            "customer_id": "c1",
            "offer_id": 724,
            "box_id": "box-old",
            "quantity": 3,
        }
        defaults.update(kw)
        return Order(**defaults)

    # --- unit price ---
    def test_unit_price_recomputes_total(self):
        order = self._order(quantity=3)
        self.mock_db.update_order.return_value = True
        ok, key = self.handler._apply_unit_price_change(order, "2.50")
        self.assertTrue(ok)
        self.assertEqual(key, "edit_order_price_success")
        updates = self.mock_db.update_order.call_args[0][1]
        self.assertEqual(updates["unit_price"], Decimal("2.50"))
        self.assertEqual(updates["total_price"], Decimal("7.50"))  # 2.50 * 3

    def test_unit_price_rejects_invalid(self):
        order = self._order()
        ok, key = self.handler._apply_unit_price_change(order, "not-a-number")
        self.assertFalse(ok)
        self.assertEqual(key, "edit_order_bad_price")
        self.mock_db.update_order.assert_not_called()

    def test_unit_price_rejects_negative(self):
        order = self._order()
        ok, key = self.handler._apply_unit_price_change(order, "-1")
        self.assertFalse(ok)
        self.assertEqual(key, "edit_order_bad_price")

    def test_unit_price_allows_zero_free_item(self):
        order = self._order(quantity=4)
        self.mock_db.update_order.return_value = True
        ok, key = self.handler._apply_unit_price_change(order, "0")
        self.assertTrue(ok)
        self.assertEqual(key, "edit_order_price_success")
        updates = self.mock_db.update_order.call_args[0][1]
        self.assertEqual(updates["unit_price"], Decimal("0"))
        self.assertEqual(updates["total_price"], Decimal("0"))

    # --- status ---
    def test_status_options_in_workflow_order(self):
        self.assertEqual(
            self.handler._status_options(self._order(status="ordered")),
            ["pending", "received_partial_delayed", "ready_for_labeling", "labeling_completed", "cancelled"],
        )

    def test_a_delivered_order_is_not_offered_cancelled(self):
        options = self.handler._status_options(self._order(status="ready_for_labeling"))
        self.assertNotIn("cancelled", options)
        self.assertNotIn("awaiting_payment", options)

    def test_apply_status_change_valid(self):
        order = self._order(status="ordered")
        self.mock_db.batch_update_order_status.return_value = [order.order_id]
        ok, key = self.handler._apply_status_change(order, "ready_for_labeling")
        self.assertTrue(ok)
        self.assertEqual(key, "edit_order_status_success")
        # only while the order still has the status it was read with
        self.mock_db.batch_update_order_status.assert_called_once_with(
            [order.order_id], "ready_for_labeling", 15005473, "ordered"
        )

    def test_apply_status_change_rejects_a_status_not_offered(self):
        order = self._order(status="pending")
        ok, key = self.handler._apply_status_change(order, "completed")
        self.assertFalse(ok)
        self.assertEqual(key, "edit_order_status_not_allowed")
        self.mock_db.batch_update_order_status.assert_not_called()

    def test_apply_status_change_rejects_unknown(self):
        order = self._order()
        ok, key = self.handler._apply_status_change(order, "bogus")
        self.assertFalse(ok)
        self.assertEqual(key, "edit_order_bad_status")
        self.mock_db.batch_update_order_status.assert_not_called()


if __name__ == "__main__":
    unittest.main()
