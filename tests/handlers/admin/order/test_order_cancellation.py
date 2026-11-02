import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from handlers.admin.order.order_cancellation import OrderCancellation
from models.entities import BoxStatus


class TestOrderCancellation(unittest.TestCase):
    """Test the OrderCancellation module"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.admin_user_id = 15005473
        self.environment = "test"
        self.telegram_token = "test_token"

        self.handler = OrderCancellation(self.mock_db, self.admin_user_id, self.environment, self.telegram_token)

    @patch.object(OrderCancellation, "_send_message")
    def test_handle_cancel_order_no_args(self, mock_send):
        """Test cancel order with no arguments shows input UI"""
        result = self.handler.handle_cancel_order(123, [])

        self.assertEqual(result["status"], "awaiting_input")
        mock_send.assert_called_once()

        # Check keyboard structure
        call_args = mock_send.call_args
        self.assertIn("reply_markup", call_args[1])
        keyboard = call_args[1]["reply_markup"]
        self.assertIn("inline_keyboard", keyboard)

    @patch.object(OrderCancellation, "_handle_cancel_order_by_partial_id")
    def test_handle_cancel_order_partial_id(self, mock_partial):
        """Test cancel order with 8-character partial ID"""
        mock_partial.return_value = {"status": "success"}

        result = self.handler.handle_cancel_order(123, ["abc12345"])

        mock_partial.assert_called_once_with(123, "abc12345")
        self.assertEqual(result["status"], "success")

    @patch.object(OrderCancellation, "handle_cancel_order_by_id")
    def test_handle_cancel_order_full_id(self, mock_full):
        """Test cancel order with full numeric ID"""
        mock_full.return_value = {"status": "success"}

        result = self.handler.handle_cancel_order(123, ["123456789012"])

        mock_full.assert_called_once_with(123, "123456789012")
        self.assertEqual(result["status"], "success")

    @patch.object(OrderCancellation, "_find_customer_with_disambiguation")
    @patch.object(OrderCancellation, "_show_user_orders_for_cancel")
    def test_handle_cancel_order_username(self, mock_show, mock_find):
        """Test cancel order with username"""
        mock_customer = Mock()
        mock_find.return_value = (mock_customer, None)
        mock_show.return_value = {"status": "success"}

        result = self.handler.handle_cancel_order(123, ["testuser123"])

        mock_find.assert_called_once_with("testuser123", 123, "cancel_order_user_select")
        mock_show.assert_called_once_with(123, mock_customer)
        self.assertEqual(result["status"], "success")

    @patch.object(OrderCancellation, "_send_message")
    def test_execute_cancel_success(self, mock_send):
        """Test successful order cancellation"""
        # Mock order
        mock_order = Mock()
        mock_order.order_id = "test123"
        mock_order.quantity = 2
        mock_order.offer_id = 1
        mock_order.customer_id = "cust123"
        mock_order.total_price = 20.0

        # Mock box with proper attributes
        mock_box = Mock()
        mock_box.box_id = "box123"
        mock_box.current_quantity = 10
        mock_box.max_capacity = 24
        mock_box.status = BoxStatus.FULL.value

        # Mock refreshed box for final message
        refreshed_box = Mock()
        refreshed_box.current_quantity = 8
        refreshed_box.max_capacity = 24

        # Mock database operations - now uses cancel_order
        self.mock_db.cancel_order.return_value = True
        self.mock_db.get_box.return_value = refreshed_box

        # Mock customer and offer
        mock_customer = Mock()
        mock_customer.telegram_user_id = 456
        mock_offer = Mock()
        mock_offer.name = "Test Beer"

        self.mock_db.get_customer.return_value = mock_customer
        self.mock_db.get_offer.return_value = mock_offer

        result = self.handler._execute_cancel(mock_order, mock_box, 123, "Test reason")

        # Verify success
        self.assertEqual(result["status"], "success")

        # Verify cancel_order was called
        self.mock_db.cancel_order.assert_called_once_with("test123", self.admin_user_id, "Test reason")

    @patch.object(OrderCancellation, "_send_message")
    def test_execute_cancel_database_error(self, mock_send):
        """Test order cancellation with database error"""
        mock_order = Mock()
        mock_order.order_id = "test123"
        mock_order.quantity = 2
        mock_box = Mock()
        mock_box.box_id = "box123"
        mock_box.current_quantity = 10
        mock_box.max_capacity = 24

        # Mock database failure
        self.mock_db.cancel_order.return_value = False

        result = self.handler._execute_cancel(mock_order, mock_box, 123)

        self.assertEqual(result["status"], "error")
        mock_send.assert_called()

    def test_box_status_recalculation(self):
        """Test box status recalculation logic in cancellation"""
        mock_order = Mock()
        mock_order.order_id = "test123"
        mock_order.quantity = 5
        mock_order.offer_id = 1
        mock_order.customer_id = "cust123"
        mock_order.total_price = 25.0

        # Test case: quantity becomes 0
        mock_box = Mock()
        mock_box.box_id = "box123"
        mock_box.current_quantity = 5
        mock_box.max_capacity = 24
        mock_box.status = BoxStatus.FULL.value

        # Mock refreshed box for final message
        refreshed_box = Mock()
        refreshed_box.current_quantity = 0
        refreshed_box.max_capacity = 24

        self.mock_db.cancel_order.return_value = True
        self.mock_db.get_box.return_value = refreshed_box
        self.mock_db.get_customer.return_value = Mock()
        self.mock_db.get_offer.return_value = Mock()

        with patch.object(self.handler, "_send_message"):
            self.handler._execute_cancel(mock_order, mock_box, 123)

        # Verify cancel_order was called
        self.mock_db.cancel_order.assert_called()


if __name__ == "__main__":
    unittest.main()
