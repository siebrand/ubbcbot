import unittest
import sys
import os
from unittest.mock import Mock, patch
from decimal import Decimal

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.entities import Order, Box, OrderStatus, BoxStatus
from services.wholesaler_delivery import WholesalerDeliveryService
from services.database import DynamoDBService

class TestWholesalerDelivery(unittest.TestCase):
    
    def setUp(self):
        self.mock_db = Mock(spec=DynamoDBService)
        # Mock the orders_table attribute
        self.mock_db.orders_table = Mock()
        self.service = WholesalerDeliveryService(self.mock_db)
    
    def test_partial_cancelled_delivery(self):
        """Test partial delivery with cancelled units (20 expected, 15 received, isDelayed=False)"""
        
        # Setup test data
        box_id = "test-box-123"
        offer_id = 1
        units_received = 15
        is_delayed = False
        
        # Create test box
        test_box = Box(
            box_id=box_id,
            offer_id=offer_id,
            current_quantity=20,
            max_capacity=20,
            status=BoxStatus.ORDERED.value
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
                unit_price=Decimal('5.00'),
                total_price=Decimal('40.00'),
                status=OrderStatus.CONFIRMED.value
            ),
            Order(
                order_id="order-2", 
                customer_id="customer-2",
                box_id=box_id,
                offer_id=offer_id,
                quantity=7,
                received_quantity=0,
                unit_price=Decimal('5.00'),
                total_price=Decimal('35.00'),
                status=OrderStatus.CONFIRMED.value
            ),
            Order(
                order_id="order-3",
                customer_id="customer-3", 
                box_id=box_id,
                offer_id=offer_id,
                quantity=5,
                received_quantity=0,
                unit_price=Decimal('5.00'),
                total_price=Decimal('25.00'),
                status=OrderStatus.CONFIRMED.value
            )
        ]
        
        # Mock database responses
        self.mock_db.get_box.return_value = test_box
        self.mock_db.get_orders_by_box.return_value = test_orders
        self.mock_db.update_order.return_value = True
        self.mock_db.create_order.return_value = True
        
        # Mock notification methods
        with patch.object(self.service, 'notify_customer_of_cancellation') as mock_cancel_notify:
            # Execute the method
            result = self.service.process_wholesaler_delivery(box_id, units_received, is_delayed)
            
            # Assertions
            self.assertTrue(result)
            
            # Verify database calls
            self.mock_db.get_box.assert_called_once_with(box_id)
            self.mock_db.get_orders_by_box.assert_called_once_with(box_id)
            
            # Verify order updates
            update_calls = self.mock_db.update_order.call_args_list
            create_calls = self.mock_db.create_order.call_args_list
            
            # Should have 3 update calls (one for each original order)
            self.assertEqual(len(update_calls), 3)
            
            # Verify first order (8 units) - fully received
            first_update = update_calls[0]
            self.assertEqual(first_update[0][0], "order-1")  # order_id
            self.assertEqual(first_update[0][1]['received_quantity'], 8)
            self.assertEqual(first_update[0][1]['status'], OrderStatus.READY_FOR_LABELING.value)
            
            # Verify second order (7 units) - fully received  
            second_update = update_calls[1]
            self.assertEqual(second_update[0][0], "order-2")
            self.assertEqual(second_update[0][1]['received_quantity'], 7)
            self.assertEqual(second_update[0][1]['status'], OrderStatus.READY_FOR_LABELING.value)
            
            # Verify third order (5 units) - no units received, cancelled
            third_update = update_calls[2]
            self.assertEqual(third_update[0][0], "order-3")
            self.assertEqual(third_update[0][1]['received_quantity'], 0)
            self.assertEqual(third_update[0][1]['status'], OrderStatus.CANCELLED_UNAVAILABLE.value)
            
            # Verify cancellation notification was called for the cancelled order
            mock_cancel_notify.assert_called_once_with("order-3")
            
            # Verify no new orders were created (since third order was completely cancelled)
            self.assertEqual(len(create_calls), 0)

if __name__ == '__main__':
    unittest.main()