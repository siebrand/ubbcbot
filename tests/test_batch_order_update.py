"""Test batch order status updates for data integrity and performance"""

import unittest
from unittest.mock import MagicMock

from models.entities import OrderStatus
from repositories.order_repository import OrderRepository


class TestBatchOrderUpdate(unittest.TestCase):
    def setUp(self):
        self.repo = OrderRepository()
        self.repo.table = MagicMock()

    def test_batch_update_uses_update_expression(self):
        """Verify batch update uses UpdateExpression, not put_item"""
        order_ids = ["order1", "order2", "order3"]

        result = self.repo.batch_update_order_status(order_ids, OrderStatus.AWAITING_PAYMENT.value)

        # Should call update_item, not put_item
        self.assertEqual(self.repo.table.update_item.call_count, 3)
        self.assertEqual(result, 3)

        # Verify UpdateExpression used
        call_args = self.repo.table.update_item.call_args_list[0][1]
        self.assertIn("UpdateExpression", call_args)
        self.assertIn("SET #status = :status", call_args["UpdateExpression"])

    def test_batch_update_only_modifies_status_and_date(self):
        """Verify only status and update_date are modified"""
        order_ids = ["order1"]

        self.repo.batch_update_order_status(order_ids, OrderStatus.AWAITING_PAYMENT.value)

        call_args = self.repo.table.update_item.call_args[1]
        attr_names = call_args["ExpressionAttributeNames"]

        # Should only update these two fields
        self.assertEqual(set(attr_names.values()), {"status", "update_date"})

    def test_batch_update_handles_errors_gracefully(self):
        """Verify errors don't crash entire batch"""
        order_ids = ["order1", "order2", "order3"]
        self.repo.table.update_item.side_effect = [None, Exception("DB error"), None]

        self.repo.batch_update_order_status(order_ids, OrderStatus.AWAITING_PAYMENT.value)

        # Should continue despite error
        self.assertEqual(self.repo.table.update_item.call_count, 3)

    def test_batch_processes_in_chunks(self):
        """Verify large batches are chunked"""
        order_ids = [f"order{i}" for i in range(25)]

        self.repo.batch_update_order_status(order_ids, OrderStatus.AWAITING_PAYMENT.value)

        # Should process all orders
        self.assertEqual(self.repo.table.update_item.call_count, 25)


if __name__ == "__main__":
    unittest.main()
