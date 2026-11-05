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
        # Isolate the wrapper from the Telegram-touching message sync.
        self.handler.sync_offer_messages = Mock()

    def test_check_offer_status_delegates_to_box_status_manager(self):
        """_check_offer_status_after_change recomputes status via the box status
        manager."""
        self.handler.box_status_manager.update_offer_status_after_change.return_value = None
        self.handler._check_offer_status_after_change(1)
        self.handler.box_status_manager.update_offer_status_after_change.assert_called_once_with(1)

    def test_status_change_triggers_message_sync(self):
        """When the status actually changes, the channel/subscriber messages are
        re-synced (edited), not deleted."""
        self.handler.box_status_manager.update_offer_status_after_change.return_value = "sold_out"
        self.handler._check_offer_status_after_change(1)
        self.handler.sync_offer_messages.assert_called_once_with(1)

    def test_no_status_change_does_not_sync(self):
        """When the status is unchanged, no message edit is triggered."""
        self.handler.box_status_manager.update_offer_status_after_change.return_value = None
        self.handler._check_offer_status_after_change(1)
        self.handler.sync_offer_messages.assert_not_called()

    def test_check_offer_status_does_not_delete_notifications(self):
        """The handler must no longer delete notification messages."""
        self.handler.box_status_manager.update_offer_status_after_change.return_value = "active"
        self.handler._check_offer_status_after_change(1)
        self.mock_db.delete_notification_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
