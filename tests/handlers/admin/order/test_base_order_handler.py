import os
import sys
import unittest
from unittest.mock import Mock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from handlers.admin.order.base_order_handler import BaseOrderHandler


class TestBaseOrderHandler(unittest.TestCase):
    """Test the BaseOrderHandler shared utilities"""

    def setUp(self):
        self.mock_db = Mock()
        self.handler = BaseOrderHandler(self.mock_db, 15005473, "test", "test_token")
        self.handler.box_status_manager = Mock()

    def test_check_offer_status_delegates_to_box_status_manager(self):
        """_check_offer_status_after_change recomputes status via the box status
        manager. (The old sold-out notification-delete behaviour has been removed;
        status messages are now edited by the offer status/content sync, not
        deleted here.)"""
        self.handler._check_offer_status_after_change(1)
        self.handler.box_status_manager.update_offer_status_after_change.assert_called_once_with(1)

    def test_check_offer_status_does_not_delete_notifications(self):
        """The handler must no longer touch notification messages."""
        self.handler._check_offer_status_after_change(1)
        self.mock_db.get_notification_messages_by_offer.assert_not_called()
        self.mock_db.delete_notification_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
