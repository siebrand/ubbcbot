"""DynamoDBService.update_order: audit logging after an order update.

The tests marked ``expectedFailure`` document behavior that is fixed in the
follow-up commit.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models.entities import Order
from services.database import DynamoDBService


class TestUpdateOrder(unittest.TestCase):
    def setUp(self):
        # Bypass __init__ (it creates AWS resources); only order_repo is used.
        self.db = DynamoDBService.__new__(DynamoDBService)
        self.db.order_repo = Mock()
        self.db.order_repo.update_order.return_value = True
        self.old_order = Order(order_id="o1", status="ordered")

    def _update(self, orders_returned, updates, admin_id=5):
        with (
            patch.object(DynamoDBService, "get_order", side_effect=orders_returned),
            patch("services.audit_service.AuditService") as audit_cls,
        ):
            result = self.db.update_order("o1", updates, admin_id=admin_id)
        return result, audit_cls.return_value

    def test_status_change_is_audited(self):
        new_order = Order(order_id="o1", status="completed")

        result, audit = self._update([self.old_order, new_order], {"status": "completed"})

        self.assertTrue(result)
        audit.log_payment_if_completed.assert_called_once_with(new_order, "ordered", "completed", 5)

    def test_non_status_update_is_not_audited(self):
        new_order = Order(order_id="o1", status="ordered")

        result, audit = self._update([self.old_order, new_order], {"quantity": 3})

        self.assertTrue(result)
        audit.log_payment_if_completed.assert_not_called()

    def test_unknown_order_fails_without_updating(self):
        result, _ = self._update([None], {"status": "completed"})

        self.assertFalse(result)
        self.db.order_repo.update_order.assert_not_called()

    def test_repository_failure_is_reported(self):
        self.db.order_repo.update_order.return_value = False

        result, _ = self._update([self.old_order], {"status": "completed"})

        self.assertFalse(result)

    @unittest.expectedFailure
    def test_order_missing_after_successful_update_still_succeeds(self):
        """The update already happened; failing to re-read the order for the audit
        must not turn it into a reported failure."""
        result, audit = self._update([self.old_order, None], {"status": "completed"})

        self.assertTrue(result)
        audit.log_payment_if_completed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
