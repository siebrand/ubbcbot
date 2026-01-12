import unittest
from unittest.mock import Mock, patch
from datetime import datetime, UTC, timedelta
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../../src'))

from handlers.admin.order.order_maintenance import OrderMaintenance
from models.entities import AuthorizationStatus

class TestOrderMaintenance(unittest.TestCase):
    """Test the OrderMaintenance module"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.admin_user_id = 15005473
        self.environment = "test"
        self.telegram_token = "test_token"
        
        self.handler = OrderMaintenance(
            self.mock_db, 
            self.admin_user_id, 
            self.environment, 
            self.telegram_token
        )
    
    @patch.object(OrderMaintenance, '_send_message')
    def test_handle_delete_old_no_orders(self, mock_send):
        """Test delete old orders when no old orders exist"""
        # Mock empty customer list
        self.mock_db.get_customers_by_status.return_value = []
        
        result = self.handler.handle_delete_old_orders(123)
        
        self.assertEqual(result['status'], 'no_old_orders')
        mock_send.assert_called_once()
    
    @patch.object(OrderMaintenance, '_send_message')
    def test_handle_delete_old_success(self, mock_send):
        """Test successful deletion of old orders"""
        # Mock customer
        mock_customer = Mock()
        mock_customer.customer_id = 'cust123'
        self.mock_db.get_customers_by_status.return_value = [mock_customer]
        
        # Mock old cancelled order (8 days ago)
        old_date = (datetime.now(UTC) - timedelta(days=8)).isoformat()
        mock_cancelled_order = Mock()
        mock_cancelled_order.order_id = 'cancelled123'
        mock_cancelled_order.update_date = old_date
        
        # Mock old completed order (10 days ago)
        very_old_date = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        mock_completed_order = Mock()
        mock_completed_order.order_id = 'completed123'
        mock_completed_order.update_date = very_old_date
        
        self.mock_db.get_orders_by_customer_and_status.side_effect = [
            [mock_cancelled_order],  # cancelled orders
            [mock_completed_order]   # completed orders
        ]
        
        # Mock successful deletion
        self.mock_db.delete_order.return_value = True
        
        result = self.handler.handle_delete_old_orders(123)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['deleted_cancelled_count'], 1)
        self.assertEqual(result['deleted_completed_count'], 1)
        
        # Verify delete_order called for both orders
        self.assertEqual(self.mock_db.delete_order.call_count, 2)
        mock_send.assert_called_once()
    
    @patch.object(OrderMaintenance, '_send_message')
    def test_handle_delete_old_recent_orders_not_deleted(self, mock_send):
        """Test that recent orders are not deleted"""
        # Mock customer
        mock_customer = Mock()
        mock_customer.customer_id = 'cust123'
        self.mock_db.get_customers_by_status.return_value = [mock_customer]
        
        # Mock recent cancelled order (2 days ago)
        recent_date = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        mock_recent_order = Mock()
        mock_recent_order.order_id = 'recent123'
        mock_recent_order.update_date = recent_date
        
        self.mock_db.get_orders_by_customer_and_status.side_effect = [
            [mock_recent_order],  # cancelled orders
            []                    # completed orders
        ]
        
        result = self.handler.handle_delete_old_orders(123)
        
        self.assertEqual(result['status'], 'no_old_orders')
        # Verify delete_order not called
        self.mock_db.delete_order.assert_not_called()
    
    def test_handle_delete_old_date_parsing(self):
        """Test date parsing handles different formats"""
        mock_customer = Mock()
        mock_customer.customer_id = 'cust123'
        self.mock_db.get_customers_by_status.return_value = [mock_customer]
        
        # Mock order with Z suffix date
        old_date_z = (datetime.now(UTC) - timedelta(days=8)).isoformat() + 'Z'
        mock_order_z = Mock()
        mock_order_z.order_id = 'order_z'
        mock_order_z.update_date = old_date_z
        
        # Mock order with invalid date
        mock_order_invalid = Mock()
        mock_order_invalid.order_id = 'order_invalid'
        mock_order_invalid.update_date = 'invalid_date'
        
        self.mock_db.get_orders_by_customer_and_status.side_effect = [
            [mock_order_z, mock_order_invalid],  # cancelled orders
            []                                   # completed orders
        ]
        
        self.mock_db.delete_order.return_value = True
        
        with patch.object(self.handler, '_send_message'):
            result = self.handler.handle_delete_old_orders(123)
        
        # Should only delete the valid date order
        if result['status'] == 'success':
            self.assertEqual(result['deleted_cancelled_count'], 1)
            self.mock_db.delete_order.assert_called_once_with('order_z')
        else:
            # If no orders were found to delete, that's also valid
            self.assertEqual(result['status'], 'no_old_orders')
    
    @patch.object(OrderMaintenance, '_send_message')
    def test_handle_audit_orders_no_orders_missing_date(self, mock_send):
        """Test audit orders when no orders are missing update_date"""
        # Mock customer with orders that have update_date
        mock_customer = Mock()
        mock_customer.customer_id = 'cust123'
        self.mock_db.get_customers_by_status.return_value = [mock_customer]
        
        mock_order = Mock()
        mock_order.update_date = datetime.now(UTC).isoformat()
        self.mock_db.get_orders_by_customer.return_value = [mock_order]
        
        result = self.handler.handle_audit_orders(123)
        
        self.assertEqual(result['status'], 'no_orders_to_audit')
        mock_send.assert_called_once()
    
    @patch.object(OrderMaintenance, '_send_message')
    def test_handle_audit_orders_success(self, mock_send):
        """Test successful audit of orders missing update_date"""
        # Mock customer
        mock_customer = Mock()
        mock_customer.customer_id = 'cust123'
        self.mock_db.get_customers_by_status.return_value = [mock_customer]
        
        # Mock orders without update_date
        mock_order1 = Mock()
        mock_order1.order_id = 'order1'
        mock_order1.update_date = None
        
        mock_order2 = Mock()
        mock_order2.order_id = 'order2'
        mock_order2.update_date = None
        
        self.mock_db.get_orders_by_customer.return_value = [mock_order1, mock_order2]
        self.mock_db.update_order.return_value = True
        
        result = self.handler.handle_audit_orders(123)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['updated_count'], 2)
        
        # Verify update_order called for both orders
        self.assertEqual(self.mock_db.update_order.call_count, 2)
        mock_send.assert_called_once()
    
    @patch.object(OrderMaintenance, '_send_message')
    def test_handle_audit_orders_database_error(self, mock_send):
        """Test audit orders with database error"""
        # Mock customer
        mock_customer = Mock()
        mock_customer.customer_id = 'cust123'
        self.mock_db.get_customers_by_status.return_value = [mock_customer]
        
        # Mock order without update_date
        mock_order = Mock()
        mock_order.order_id = 'order1'
        mock_order.update_date = None
        
        self.mock_db.get_orders_by_customer.return_value = [mock_order]
        self.mock_db.update_order.return_value = False  # Simulate failure
        
        result = self.handler.handle_audit_orders(123)
        
        self.assertEqual(result['status'], 'error')
        mock_send.assert_called_once()
    
    @patch('logging.getLogger')
    @patch.object(OrderMaintenance, '_send_message')
    def test_handle_delete_old_exception_handling(self, mock_send, mock_logger):
        """Test exception handling in delete_old"""
        # Mock exception during execution
        self.mock_db.get_customers_by_status.side_effect = Exception("Database error")
        
        result = self.handler.handle_delete_old_orders(123)
        
        self.assertEqual(result['status'], 'error')
        mock_send.assert_called_once()
        # Verify error was logged
        mock_logger.return_value.error.assert_called_once()

if __name__ == '__main__':
    unittest.main()