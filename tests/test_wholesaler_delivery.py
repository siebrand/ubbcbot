import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from models.entities import Box, BoxStatus, Order, OrderStatus
from services.box_status_manager import BoxStatusManager
from services.database import DynamoDBService
from services.wholesaler_delivery import WholesalerDeliveryService


class TestWholesalerDelivery(unittest.TestCase):
    def setUp(self):
        self.mock_db = Mock(spec=DynamoDBService)
        self.mock_box_status_manager = Mock(spec=BoxStatusManager)
        # Mock the orders_table attribute
        self.mock_db.orders_table = Mock()
        self.service = WholesalerDeliveryService(self.mock_db, self.mock_box_status_manager)

    def test_partial_cancelled_delivery(self):
        """Test partial delivery with cancelled units (20 expected, 15 received, isDelayed=False)"""

        # Setup test data
        box_id = "test-box-123"
        offer_id = 1
        units_received = 15
        is_delayed = False

        # Create test box
        test_box = Box(
            box_id=box_id, offer_id=offer_id, current_quantity=20, max_capacity=20, status=BoxStatus.ORDERED.value
        )

        # Create test orders (total 20 units)
        test_orders = [
            Order(
                order_id="order-1",
                customer_id="customer-1",
                box_id=box_id,
                offer_id=offer_id,
                quantity=8,
                received_quantity=0,
                unit_price=Decimal("5.00"),
                total_price=Decimal("40.00"),
                status=OrderStatus.ORDERED.value,
            ),
            Order(
                order_id="order-2",
                customer_id="customer-2",
                box_id=box_id,
                offer_id=offer_id,
                quantity=7,
                received_quantity=0,
                unit_price=Decimal("5.00"),
                total_price=Decimal("35.00"),
                status=OrderStatus.ORDERED.value,
            ),
            Order(
                order_id="order-3",
                customer_id="customer-3",
                box_id=box_id,
                offer_id=offer_id,
                quantity=5,
                received_quantity=0,
                unit_price=Decimal("5.00"),
                total_price=Decimal("25.00"),
                status=OrderStatus.ORDERED.value,
            ),
        ]

        # Mock database responses
        self.mock_db.get_box.return_value = test_box
        self.mock_db.get_orders_by_box.return_value = test_orders
        self.mock_db.update_order.return_value = True
        self.mock_db.create_order.return_value = True
        self.mock_db.cancel_order.return_value = True

        # Mock notification methods
        with patch.object(self.service, "notify_customer_of_cancellation") as mock_cancel_notify:
            # Execute the method
            result = self.service.process_wholesaler_delivery(box_id, units_received, is_delayed)

            # Assertions
            self.assertTrue(result)

            # Verify database calls
            self.mock_db.get_box.assert_called_once_with(box_id)
            self.mock_db.get_orders_by_box.assert_called_once_with(box_id)

            # Verify order updates
            update_calls = self.mock_db.update_order.call_args_list
            cancel_calls = self.mock_db.cancel_order.call_args_list

            # Should have 2 update calls (first two orders fully received)
            self.assertEqual(len(update_calls), 2)

            # Should have 1 cancel call (third order completely cancelled)
            self.assertEqual(len(cancel_calls), 1)

            # Verify first order (8 units) - fully received
            first_update = update_calls[0]
            self.assertEqual(first_update[0][0], "order-1")  # order_id
            self.assertEqual(first_update[0][1]["received_quantity"], 8)
            self.assertEqual(first_update[0][1]["status"], OrderStatus.READY_FOR_LABELING.value)

            # Verify second order (7 units) - fully received
            second_update = update_calls[1]
            self.assertEqual(second_update[0][0], "order-2")
            self.assertEqual(second_update[0][1]["received_quantity"], 7)
            self.assertEqual(second_update[0][1]["status"], OrderStatus.READY_FOR_LABELING.value)

            # Verify third order was cancelled
            cancel_call = cancel_calls[0]
            self.assertEqual(cancel_call[0][0], "order-3")
            self.assertEqual(cancel_call[0][1], self.service.admin_user_id)
            self.assertEqual(cancel_call[0][2], "Wholesale delivery - units unavailable")

            # Verify cancellation notification was called for the cancelled order
            mock_cancel_notify.assert_called_once_with("order-3")

    def test_complete_delivery_button_in_keyboard(self):
        """Test that complete delivery button is added to box keyboard"""
        from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler
        from models.entities import Box, Order

        # Mock handler setup
        mock_db = Mock()
        handler = WholesaleDeliveryHandler(mock_db, 15005473, "test", "test_token")
        handler._t = Mock(side_effect=lambda key, **kwargs: f"TRANSLATED_{key}")

        # Create test boxes
        boxes = [
            Box(box_id="box1", offer_id=1, status="ordered", current_quantity=10, max_capacity=12),
            Box(box_id="box2", offer_id=1, status="ordered", current_quantity=8, max_capacity=12),
        ]

        # Mock orders for boxes
        mock_db.get_orders_by_box.return_value = [
            Order(order_id="order1", customer_id="cust1", box_id="box1", offer_id=1, quantity=5),
            Order(order_id="order2", customer_id="cust2", box_id="box1", offer_id=1, quantity=5),
        ]

        # Build keyboard with complete button
        keyboard = handler._build_box_keyboard(boxes, 1, "sup123", "wd", add_complete_button=True)

        # Verify complete delivery button is first
        self.assertEqual(len(keyboard["inline_keyboard"]), 4)  # Complete button + 2 boxes + back button
        self.assertIn("complete", keyboard["inline_keyboard"][0][0]["callback_data"])

    def test_handle_complete_delivery_confirmation(self):
        """Test complete delivery shows confirmation dialog"""
        from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler
        from models.entities import Box

        # Mock handler setup
        mock_db = Mock()
        handler = WholesaleDeliveryHandler(mock_db, 15005473, "test", "test_token")
        handler._t = Mock(side_effect=lambda key, **kwargs: f"TRANSLATED_{key}_{kwargs}")
        handler._send_message = Mock(return_value={"status": "sent"})

        # Mock ordered boxes
        ordered_boxes = [
            Box(box_id="box1", offer_id=1, status="ordered"),
            Box(box_id="box2", offer_id=1, status="ordered"),
        ]

        mock_db.get_boxes_by_offer.return_value = ordered_boxes

        handler.handle_complete_delivery(123, 1, "sup123")

        # Verify confirmation message is sent
        handler._send_message.assert_called_once()
        call_args = handler._send_message.call_args
        self.assertIn("reply_markup", call_args[1])


if __name__ == "__main__":
    unittest.main()
