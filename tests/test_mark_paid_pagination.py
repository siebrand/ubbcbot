import pytest
from unittest.mock import Mock, MagicMock
from handlers.admin.order.order_status import OrderStatusManagement
from models.entities import Customer, Order, AuthorizationStatus, OrderStatus


class TestMarkPaidPagination:
    """Test pagination for /mark_paid command"""
    
    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.get_customers_by_status = Mock()
        db.get_orders_by_customer = Mock()
        return db
    
    @pytest.fixture
    def handler(self, mock_db):
        handler = OrderStatusManagement(
            db=mock_db,
            admin_user_id=15005473,
            environment='test',
            telegram_token='test_token'
        )
        handler._send_message = Mock()
        handler._t = Mock(side_effect=lambda key, **kwargs: key)
        return handler
    
    def test_mark_paid_no_customers(self, handler, mock_db):
        """Test mark_paid with no customers awaiting payment"""
        mock_db.get_customers_by_status.return_value = []
        
        result = handler.handle_mark_paid(123, [])
        
        assert result['status'] == 'no_customers'
        handler._send_message.assert_called_once()
    
    def test_mark_paid_single_page(self, handler, mock_db):
        """Test mark_paid with customers fitting in one page"""
        # Create 5 customers with awaiting payment orders
        customers = []
        for i in range(5):
            customer = Customer(
                customer_id=f'cust_{i}',
                telegram_user_id=1000 + i,
                first_name=f'First{i}',
                last_name=f'Last{i}',
                authorization_status=AuthorizationStatus.APPROVED.value
            )
            customers.append(customer)
        
        mock_db.get_customers_by_status.return_value = customers
        
        # Mock orders for each customer
        def get_orders(customer_id):
            return [Order(
                order_id=f'order_{customer_id}',
                customer_id=customer_id,
                offer_id='offer_1',
                quantity=2,
                total_price=20.0,
                status=OrderStatus.AWAITING_PAYMENT.value
            )]
        
        mock_db.get_orders_by_customer.side_effect = get_orders
        
        result = handler.handle_mark_paid(123, [], page=1)
        
        assert result['status'] == 'customers_shown'
        handler._send_message.assert_called_once()
        
        # Verify message contains all 5 customers
        call_args = handler._send_message.call_args
        message = call_args[0][1]
        reply_markup = call_args[1]['reply_markup']
        
        assert 'Page 1/1' in message
        for i in range(5):
            assert f'First{i}' in message
        
        # Verify button text format: ✓ Last, First €amount
        buttons = reply_markup['inline_keyboard']
        # 5 customer buttons + 1 Done button
        assert len(buttons) == 6
        for i in range(5):
            button_text = buttons[i][0]['text']
            assert button_text == f'✓ Last{i}, First{i} €20.00'
        # Verify Done button
        assert buttons[5][0]['callback_data'] == 'cancel_action'
    
    def test_mark_paid_multiple_pages(self, handler, mock_db):
        """Test mark_paid with customers requiring multiple pages"""
        # Create 25 customers (3 pages with 10 per page)
        # Use zero-padded numbers to ensure proper alphabetical sorting
        customers = []
        for i in range(25):
            customer = Customer(
                customer_id=f'cust_{i:02d}',
                telegram_user_id=1000 + i,
                first_name=f'First{i:02d}',
                last_name=f'Last{i:02d}',
                authorization_status=AuthorizationStatus.APPROVED.value
            )
            customers.append(customer)
        
        mock_db.get_customers_by_status.return_value = customers
        
        # Mock orders for each customer
        def get_orders(customer_id):
            return [Order(
                order_id=f'order_{customer_id}',
                customer_id=customer_id,
                offer_id='offer_1',
                quantity=2,
                total_price=20.0,
                status=OrderStatus.AWAITING_PAYMENT.value
            )]
        
        mock_db.get_orders_by_customer.side_effect = get_orders
        
        # Test page 1
        result = handler.handle_mark_paid(123, [], page=1)
        assert result['status'] == 'customers_shown'
        
        call_args = handler._send_message.call_args
        message = call_args[0][1]
        reply_markup = call_args[1]['reply_markup']
        
        assert 'Page 1/3' in message
        # Should show first 10 customers (00-09)
        for i in range(10):
            assert f'First{i:02d}' in message
        # Should not show customer 10+
        assert 'First10' not in message
        
        # Verify pagination keyboard exists
        assert 'inline_keyboard' in reply_markup
        # 10 customer buttons + pagination row + Done button
        assert len(reply_markup['inline_keyboard']) >= 11
    
    def test_mark_paid_page_2(self, handler, mock_db):
        """Test mark_paid showing page 2"""
        # Create 25 customers with zero-padded numbers
        customers = []
        for i in range(25):
            customer = Customer(
                customer_id=f'cust_{i:02d}',
                telegram_user_id=1000 + i,
                first_name=f'First{i:02d}',
                last_name=f'Last{i:02d}',
                authorization_status=AuthorizationStatus.APPROVED.value
            )
            customers.append(customer)
        
        mock_db.get_customers_by_status.return_value = customers
        
        def get_orders(customer_id):
            return [Order(
                order_id=f'order_{customer_id}',
                customer_id=customer_id,
                offer_id='offer_1',
                quantity=2,
                total_price=20.0,
                status=OrderStatus.AWAITING_PAYMENT.value
            )]
        
        mock_db.get_orders_by_customer.side_effect = get_orders
        
        # Test page 2
        result = handler.handle_mark_paid(123, [], page=2)
        
        call_args = handler._send_message.call_args
        message = call_args[0][1]
        
        assert 'Page 2/3' in message
        # Should show customers 10-19
        for i in range(10, 20):
            assert f'First{i:02d}' in message
        # Should not show customers 0-9 or 20+
        assert 'First09' not in message
        assert 'First20' not in message
    
    def test_mark_paid_with_multiple_orders(self, handler, mock_db):
        """Test mark_paid calculates total correctly for multiple orders"""
        customer = Customer(
            customer_id='cust_1',
            telegram_user_id=1001,
            first_name='John',
            last_name='Doe',
            authorization_status=AuthorizationStatus.APPROVED.value
        )
        
        mock_db.get_customers_by_status.return_value = [customer]
        
        # Multiple orders for same customer
        orders = [
            Order(
                order_id='order_1',
                customer_id='cust_1',
                offer_id='offer_1',
                quantity=2,
                total_price=20.0,
                status=OrderStatus.AWAITING_PAYMENT.value
            ),
            Order(
                order_id='order_2',
                customer_id='cust_1',
                offer_id='offer_2',
                quantity=3,
                total_price=30.0,
                status=OrderStatus.AWAITING_PAYMENT.value
            )
        ]
        
        mock_db.get_orders_by_customer.return_value = orders
        
        result = handler.handle_mark_paid(123, [], page=1)
        
        call_args = handler._send_message.call_args
        message = call_args[0][1]
        reply_markup = call_args[1]['reply_markup']
        
        # Should show total of both orders
        assert '€50.00' in message
        assert '(2 orders)' in message
        
        # Verify button text format
        button_text = reply_markup['inline_keyboard'][0][0]['text']
        assert button_text == '✓ Doe, John €50.00'
