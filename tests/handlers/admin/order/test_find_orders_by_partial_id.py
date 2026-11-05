import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from handlers.admin.order.base_order_handler import BaseOrderHandler
from models.entities import AuthorizationStatus


class _Order:
    def __init__(self, order_id, customer_id, status="ordered"):
        self.order_id = order_id
        self.customer_id = customer_id
        self.status = status


class _Customer:
    def __init__(self, customer_id):
        self.customer_id = customer_id


class TestFindOrdersByPartialId(unittest.TestCase):
    def setUp(self):
        self.mock_db = Mock()
        self.handler = BaseOrderHandler(self.mock_db, 15005473, "test", "token")

        self.cust_a = _Customer("cust-a")
        self.cust_b = _Customer("cust-b")
        self.mock_db.get_customers_by_status.return_value = [self.cust_a, self.cust_b]

        self.orders = {
            "cust-a": [
                _Order("abc12345-1111", "cust-a", status="ordered"),
                _Order("zzz99999-0000", "cust-a", status="cancelled"),
            ],
            "cust-b": [
                _Order("abc12345-2222", "cust-b", status="awaiting_payment"),
                _Order("abc99999-3333", "cust-b", status="ordered"),
            ],
        }
        self.mock_db.get_orders_by_customer.side_effect = lambda cid: self.orders[cid]

    def test_returns_matches_with_customer(self):
        results = self.handler.find_orders_by_partial_id("abc12345")
        ids = sorted(o.order_id for o, _ in results)
        self.assertEqual(ids, ["abc12345-1111", "abc12345-2222"])
        # each result pairs the order with its owning customer
        for order, customer in results:
            self.assertEqual(order.customer_id, customer.customer_id)

    def test_excludes_cancelled_by_default(self):
        # "zzz99999" only exists as a cancelled order -> excluded by default
        self.assertEqual(self.handler.find_orders_by_partial_id("zzz99999"), [])

    def test_include_cancelled_when_requested(self):
        results = self.handler.find_orders_by_partial_id("zzz99999", include_cancelled=True)
        self.assertEqual([o.order_id for o, _ in results], ["zzz99999-0000"])

    def test_no_match_returns_empty(self):
        self.assertEqual(self.handler.find_orders_by_partial_id("ffffffff"), [])

    def test_scans_only_approved_customers(self):
        self.handler.find_orders_by_partial_id("abc12345")
        self.mock_db.get_customers_by_status.assert_called_once_with(AuthorizationStatus.APPROVED.value)


if __name__ == "__main__":
    unittest.main()
