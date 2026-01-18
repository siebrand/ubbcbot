import unittest
from unittest.mock import Mock, patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../src'))

from handlers.admin.order_commands import AdminOrderCommands

class TestAdminOrderCommands(unittest.TestCase):
    """Test the main AdminOrderCommands coordinator class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.admin_user_id = 15005473
        self.environment = "test"
        self.telegram_token = "test_token"
        
        self.order_commands = AdminOrderCommands(
            self.mock_db, 
            self.admin_user_id, 
            self.environment, 
            self.telegram_token
        )
    
    def test_initialization(self):
        """Test that all specialized handlers are properly initialized"""
        self.assertIsNotNone(self.order_commands.cancellation)
        self.assertIsNotNone(self.order_commands.placement)
        self.assertIsNotNone(self.order_commands.viewing)
        self.assertIsNotNone(self.order_commands.status_mgmt)
        self.assertIsNotNone(self.order_commands.maintenance)
    
    def test_cancellation_methods_exist(self):
        """Test that all cancellation methods are properly delegated"""
        methods = [
            'handle_cancel_order',
            'handle_confirm_cancel',
            'handle_confirm_cancel_with_reason',
            'handle_cancel_order_user_select',
            'handle_cancel_orders_page'
        ]
        
        for method in methods:
            self.assertTrue(hasattr(self.order_commands, method))
            self.assertTrue(callable(getattr(self.order_commands, method)))
    
    def test_placement_methods_exist(self):
        """Test that all placement methods are properly delegated"""
        methods = [
            'handle_create_order_for',
            'handle_create_order_for_user_select',
            'handle_create_order_for_offer_select',
            'handle_create_order_for_quantity_select',
            'handle_create_order_for_other_quantity'
        ]
        
        for method in methods:
            self.assertTrue(hasattr(self.order_commands, method))
            self.assertTrue(callable(getattr(self.order_commands, method)))
    
    def test_viewing_methods_exist(self):
        """Test that all viewing methods are properly delegated"""
        methods = [
            'handle_list_user_orders',
            'handle_export_orders',
            'handle_list_offer_orders',
            'handle_list_user_orders_select',
            'handle_list_offer_orders_page',
            'handle_list_offer_orders_detail_page',
            'handle_export_orders_callback'
        ]
        
        for method in methods:
            self.assertTrue(hasattr(self.order_commands, method))
            self.assertTrue(callable(getattr(self.order_commands, method)))
    
    def test_status_methods_exist(self):
        """Test that all status management methods are properly delegated"""
        methods = [
            'handle_send_delivery_overviews',
            'handle_mark_paid',
            'handle_failed_notifications'
        ]
        
        for method in methods:
            self.assertTrue(hasattr(self.order_commands, method))
            self.assertTrue(callable(getattr(self.order_commands, method)))
    
    def test_maintenance_methods_exist(self):
        """Test that all maintenance methods are properly delegated"""
        methods = [
            'handle_delete_old_orders',
            'handle_audit_orders'
        ]
        
        for method in methods:
            self.assertTrue(hasattr(self.order_commands, method))
            self.assertTrue(callable(getattr(self.order_commands, method)))
    
    @patch.object(AdminOrderCommands, '_send_message')
    def test_method_delegation(self, mock_send):
        """Test that methods properly delegate to specialized handlers"""
        # Test cancellation delegation
        with patch.object(self.order_commands.cancellation, 'handle_cancel_order') as mock_cancel:
            mock_cancel.return_value = {'status': 'success'}
            result = self.order_commands.handle_cancel_order(123, ['test'])
            mock_cancel.assert_called_once_with(123, ['test'])
            self.assertEqual(result['status'], 'success')
        
        # Test placement delegation
        with patch.object(self.order_commands.placement, 'handle_create_order_for') as mock_order:
            mock_order.return_value = {'status': 'success'}
            result = self.order_commands.handle_create_order_for(123, 456, ['test'])
            mock_order.assert_called_once_with(123, 456, ['test'])
            self.assertEqual(result['status'], 'success')
        
        # Test viewing delegation
        with patch.object(self.order_commands.viewing, 'handle_list_user_orders') as mock_view:
            mock_view.return_value = {'status': 'success'}
            result = self.order_commands.handle_list_user_orders(123, ['test'])
            mock_view.assert_called_once_with(123, ['test'])
            self.assertEqual(result['status'], 'success')

if __name__ == '__main__':
    unittest.main()