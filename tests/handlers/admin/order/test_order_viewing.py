import unittest
from unittest.mock import Mock, patch
from decimal import Decimal
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../../src'))

from handlers.admin.order.order_viewing import OrderViewing
from models.entities import AuthorizationStatus, OrderStatus

class TestOrderViewing(unittest.TestCase):
    """Test the OrderViewing module"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.admin_user_id = 15005473
        self.environment = "test"
        self.telegram_token = "test_token"
        
        self.handler = OrderViewing(
            self.mock_db, 
            self.admin_user_id, 
            self.environment, 
            self.telegram_token
        )
    
    @patch.object(OrderViewing, '_send_message')
    def test_handle_list_user_orders_no_args(self, mock_send):
        """Test user orders with no arguments shows input UI"""
        result = self.handler.handle_list_user_orders(123, [])
        
        self.assertEqual(result['status'], 'awaiting_input')
        mock_send.assert_called_once()
        
        # Check keyboard structure
        call_args = mock_send.call_args
        self.assertIn('reply_markup', call_args[1])
    
    @patch.object(OrderViewing, '_send_message')
    def test_handle_export_orders_no_args(self, mock_send):
        """Test all orders with no arguments shows status selection"""
        result = self.handler.handle_export_orders(123, [])
        
        self.assertEqual(result['status'], 'selection_shown')
        mock_send.assert_called_once()
        
        # Check keyboard has status options
        call_args = mock_send.call_args
        keyboard = call_args[1]['reply_markup']
        self.assertIn('inline_keyboard', keyboard)
        self.assertTrue(len(keyboard['inline_keyboard']) > 0)
    
    def test_generate_pick_list_csv_format(self):
        """Test CSV generation format"""
        # Mock order data
        mock_customer = Mock()
        mock_customer.first_name = "John"
        mock_customer.last_name = "Doe"
        mock_customer.location = "Venster, Berlijnplein 520"
        
        mock_order = Mock()
        mock_order.offer_id = 1
        mock_order.quantity = 2
        mock_order.unit_price = Decimal('10.50')
        mock_order.total_price = Decimal('21.00')
        mock_order.status = 'pending'
        
        mock_offer = Mock()
        mock_offer.name = "Test Beer"
        self.mock_db.get_offer.return_value = mock_offer
        
        orders_data = [(mock_customer, mock_order)]
        
        csv_content = self.handler._generate_pick_list_csv(orders_data)
        
        # Check CSV structure
        lines = csv_content.strip().split('\n')
        self.assertEqual(len(lines), 3)  # Header + 2 data rows (quantity=2)
        
        # Check header
        header = lines[0]
        expected_headers = ['Naam', 'Product', 'Prijs', 'Locatie']
        self.assertEqual(header, ','.join(expected_headers))
        
        # Check data rows (should be 2 identical rows for quantity=2)
        for i in [1, 2]:
            data_row = lines[i]
            self.assertIn('"John Doe"', data_row)
            self.assertIn('"Test Beer"', data_row)
            self.assertIn('€10.50', data_row)
            self.assertIn('"Venst"', data_row)
    
    def test_generate_pick_list_csv_weer_prefix(self):
        """Test CSV generation with Weer location prefix"""
        # Mock customer with Weer location
        mock_customer = Mock()
        mock_customer.first_name = "Jane"
        mock_customer.last_name = "Smith"
        mock_customer.location = "Weerschijnvlinder 16"
        
        mock_order = Mock()
        mock_order.offer_id = 1
        mock_order.quantity = 1
        mock_order.unit_price = Decimal('12.00')
        mock_order.status = 'pending'
        
        mock_offer = Mock()
        mock_offer.name = "Test Beer"
        self.mock_db.get_offer.return_value = mock_offer
        
        orders_data = [(mock_customer, mock_order)]
        
        csv_content = self.handler._generate_pick_list_csv(orders_data)
        
        # Check that name is prefixed with "-"
        lines = csv_content.strip().split('\n')
        data_row = lines[1]
        self.assertIn('"-Jane Smith"', data_row)
        self.assertIn('"Weers"', data_row)
    
    @patch.object(OrderViewing, '_export_orders_by_status')
    def test_handle_export_orders_with_filter(self, mock_export):
        """Test all orders with status filter"""
        mock_export.return_value = {'status': 'success'}
        
        result = self.handler.handle_export_orders(123, ['active'])
        
        mock_export.assert_called_once_with(123, 'active')
        self.assertEqual(result['status'], 'success')
    
    @patch.object(OrderViewing, '_send_message')
    def test_export_orders_by_status_no_orders(self, mock_send):
        """Test export with no matching orders"""
        # Mock empty customer list
        self.mock_db.get_customers_by_status.return_value = []
        
        result = self.handler._export_orders_by_status(123, 'active')
        
        self.assertEqual(result['status'], 'no_orders')
        mock_send.assert_called_once()
    
    @patch.object(OrderViewing, '_send_document')
    @patch.object(OrderViewing, '_generate_pick_list_csv')
    def test_export_orders_by_status_success(self, mock_csv, mock_send_doc):
        """Test successful order export"""
        # Mock customer with orders
        mock_customer = Mock()
        mock_customer.first_name = "John"
        mock_customer.last_name = "Doe"
        
        mock_order = Mock()
        mock_order.status = 'pending'
        
        self.mock_db.get_customers_by_status.return_value = [mock_customer]
        self.mock_db.get_orders_by_customer.return_value = [mock_order]
        
        mock_csv.return_value = "csv_content"
        
        result = self.handler._export_orders_by_status(123, 'active')
        
        self.assertEqual(result['status'], 'success')
        mock_send_doc.assert_called_once()
        
        # Check CSV filename format
        call_args = mock_send_doc.call_args[0]
        filename = call_args[2]
        self.assertTrue(filename.startswith('orders_test_active_'))
        self.assertTrue(filename.endswith('.csv'))
    
    def test_status_filter_logic(self):
        """Test order status filtering logic"""
        # Mock orders with different statuses
        orders = [
            Mock(status='pending'),
            Mock(status='ordered'),
            Mock(status='cancelled'),
            Mock(status=OrderStatus.READY_FOR_LABELING.value),
            Mock(status=OrderStatus.COMPLETED.value)
        ]
        
        mock_customer = Mock()
        self.mock_db.get_customers_by_status.return_value = [mock_customer]
        self.mock_db.get_orders_by_customer.return_value = orders
        
        with patch.object(self.handler, '_generate_pick_list_csv') as mock_csv:
            with patch.object(self.handler, '_send_document'):
                mock_csv.return_value = "csv"
                
                # Test active filter
                self.handler._export_orders_by_status(123, 'active')
                call_args = mock_csv.call_args[0][0]
                active_orders = [order for _, order in call_args]
                self.assertEqual(len(active_orders), 2)  # pending + ordered
                
                # Test cancelled filter
                self.handler._export_orders_by_status(123, 'cancelled')
                call_args = mock_csv.call_args[0][0]
                cancelled_orders = [order for _, order in call_args]
                self.assertEqual(len(cancelled_orders), 1)  # cancelled only
    
    @patch.object(OrderViewing, '_send_message')
    def test_show_user_orders_aggregation(self, mock_send):
        """Test user orders aggregation logic"""
        # Mock customer
        mock_customer = Mock()
        mock_customer.first_name = "John"
        mock_customer.last_name = "Doe"
        
        # Mock orders for same offer but different dates
        from datetime import datetime, UTC
        mock_order1 = Mock()
        mock_order1.offer_id = 1
        mock_order1.unit_price = Decimal('10.00')
        mock_order1.status = 'pending'
        mock_order1.quantity = 2
        mock_order1.total_price = Decimal('20.00')
        mock_order1.order_id = 'order1'
        mock_order1.created_at = datetime.now(UTC)
        
        mock_order2 = Mock()
        mock_order2.offer_id = 1
        mock_order2.unit_price = Decimal('10.00')
        mock_order2.status = 'pending'
        mock_order2.quantity = 1
        mock_order2.total_price = Decimal('10.00')
        mock_order2.order_id = 'order2'
        mock_order2.created_at = datetime.now(UTC)
        
        self.mock_db.get_orders_by_customer.return_value = [mock_order1, mock_order2]
        
        # Mock offer
        mock_offer = Mock()
        mock_offer.name = "Test Beer"
        self.mock_db.get_offer.return_value = mock_offer
        
        with patch.object(self.handler, '_t') as mock_t:
            mock_t.return_value = "translated"
            with patch.object(self.handler, '_escape_html') as mock_escape:
                mock_escape.return_value = "John Doe"
                
                result = self.handler._show_user_orders(123, mock_customer)
        
        self.assertEqual(result['status'], 'success')
        mock_send.assert_called_once()
        
        # Verify message contains aggregated quantities (2 + 1 = 3)
        call_args = mock_send.call_args[0]
        message = call_args[1]
        self.assertIn('3x', message)  # Aggregated quantity
        self.assertIn('€30.00', message)  # Aggregated total

if __name__ == '__main__':
    unittest.main()