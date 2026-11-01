import os
import sys
import unittest
from unittest.mock import Mock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from handlers.admin.order.base_order_handler import BaseOrderHandler
from models.entities import OfferStatus


class TestBaseOrderHandler(unittest.TestCase):
    """Test the BaseOrderHandler shared utilities"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.admin_user_id = 15005473
        self.environment = "test"
        self.telegram_token = "test_token"

        self.handler = BaseOrderHandler(self.mock_db, self.admin_user_id, self.environment, self.telegram_token)

    def test_check_offer_status_after_change_sold_out(self):
        """Test offer status changes to SOLD_OUT when all boxes are full"""
        # Mock offer
        mock_offer = Mock()
        mock_offer.status = OfferStatus.ACTIVE.value
        self.mock_db.get_offer.return_value = mock_offer

        # Mock boxes - all full and at capacity
        mock_box1 = Mock()
        mock_box1.status = "full"
        mock_box1.current_quantity = 24
        mock_box1.max_capacity = 24

        mock_box2 = Mock()
        mock_box2.status = "ordered"
        mock_box2.current_quantity = 12
        mock_box2.max_capacity = 12

        self.mock_db.get_boxes_by_offer.return_value = [mock_box1, mock_box2]

        # Call method
        self.handler._check_offer_status_after_change(1)

        # Verify offer updated to SOLD_OUT
        self.mock_db.update_offer.assert_called_once_with(1, {"status": OfferStatus.SOLD_OUT.value})

    def test_check_offer_status_after_change_active(self):
        """Test offer status changes to ACTIVE when boxes have capacity"""
        # Mock offer
        mock_offer = Mock()
        mock_offer.status = OfferStatus.SOLD_OUT.value
        self.mock_db.get_offer.return_value = mock_offer

        # Mock boxes - not all full
        mock_box1 = Mock()
        mock_box1.status = "full"
        mock_box1.current_quantity = 20
        mock_box1.max_capacity = 24

        self.mock_db.get_boxes_by_offer.return_value = [mock_box1]

        # Call method
        self.handler._check_offer_status_after_change(1)

        # Verify offer updated to ACTIVE
        self.mock_db.update_offer.assert_called_once_with(1, {"status": OfferStatus.ACTIVE.value})

    def test_check_offer_status_no_change_for_inactive(self):
        """Test no status change for inactive offers"""
        # Mock inactive offer
        mock_offer = Mock()
        mock_offer.status = OfferStatus.INACTIVE.value
        self.mock_db.get_offer.return_value = mock_offer

        # Call method
        self.handler._check_offer_status_after_change(1)

        # Verify no update called
        self.mock_db.update_offer.assert_not_called()

    def test_check_offer_status_no_offer(self):
        """Test no action when offer doesn't exist"""
        self.mock_db.get_offer.return_value = None

        # Call method
        self.handler._check_offer_status_after_change(1)

        # Verify no update called
        self.mock_db.update_offer.assert_not_called()

    def test_check_offer_status_no_boxes(self):
        """Test no action when offer has no boxes"""
        # Mock offer
        mock_offer = Mock()
        mock_offer.status = OfferStatus.ACTIVE.value
        self.mock_db.get_offer.return_value = mock_offer
        self.mock_db.get_boxes_by_offer.return_value = []

        # Call method
        self.handler._check_offer_status_after_change(1)

        # Verify no update called
        self.mock_db.update_offer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
