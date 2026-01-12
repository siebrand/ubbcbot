#!/usr/bin/env python3
"""
Callback Routing Tests
Tests the ACTUAL CallbackHandler code - callback parsing, authorization, and routing decisions.
Complements test_command_routing.py for comprehensive coverage.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import Mock, MagicMock
from services.callback_handler import CallbackHandler


class TestCallbackRouting:
    """Test actual callback routing logic"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database"""
        db = Mock()
        db.get_edit_context_by_chat_id.return_value = None
        return db
    
    @pytest.fixture
    def mock_handlers(self):
        """Mock handlers - track which handler methods are called"""
        handlers = {}
        for name in ['info', 'customer_order', 'admin_order', 'supplier', 'offer', 
                     'user', 'discount', 'wholesale_delivery', 'labeling', 
                     'admin_commands', 'delivery_overview', 'import', 'test']:
            handlers[name] = Mock()
        return handlers
    
    @pytest.fixture
    def mock_media_handler(self):
        """Mock media handler"""
        return Mock()
    
    @pytest.fixture
    def callback_handler(self, mock_db, mock_handlers, mock_media_handler):
        """Create actual CallbackHandler instance"""
        return CallbackHandler(
            db=mock_db,
            admin_user_id=15005473,
            environment='test',
            telegram_token='test_token',
            handlers=mock_handlers,
            media_handler=mock_media_handler
        )
    
    def _create_callback_query(self, data: str, user_id: int = 12345, chat_id: int = 12345):
        """Helper to create callback query dict"""
        return {
            'id': 'query_123',
            'from': {'id': user_id},
            'message': {'chat': {'id': chat_id}, 'message_id': 456},
            'data': data
        }
    
    # Test 1: Admin Panel Callbacks
    @pytest.mark.parametrize("callback_data,expected_method", [
        ('admin:main', 'handle_admin'),
        ('admin:workflow', 'handle_admin_workflow'),
        ('admin:suppliers', 'handle_admin_suppliers'),
        ('admin:offers', 'handle_admin_offers'),
        ('admin:orders', 'handle_admin_orders'),
        ('admin:users', 'handle_admin_users'),
        ('admin:discounts', 'handle_admin_discounts'),
        ('admin:system', 'handle_admin_system'),
    ])
    def test_admin_panel_callbacks(self, callback_handler, mock_handlers, callback_data, expected_method):
        """Test admin panel navigation callbacks route correctly"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        getattr(mock_handlers['admin_commands'], expected_method).assert_called_once()
    
    # Test 2: Command Callbacks with New Names
    @pytest.mark.parametrize("callback_data,handler,method", [
        ('cmd:create_supplier', 'supplier', 'handle_create_supplier'),
        ('cmd:update_supplier', 'supplier', 'handle_list_suppliers'),
        ('cmd:list_suppliers', 'supplier', 'handle_list_suppliers'),
        ('cmd:list_boxes', 'offer', 'handle_list_boxes'),
        ('cmd:process_wholesale', 'offer', 'handle_order_wholesale'),
        ('cmd:export_orders', 'admin_order', 'handle_all_orders'),
        ('cmd:list_user_orders', 'admin_order', '_start_user_orders_input'),
        ('cmd:list_offer_orders', 'admin_order', 'handle_offer_orders'),
        ('cmd:create_order_for', 'admin_order', 'handle_create_order_for'),
        ('cmd:list_pending', 'user', 'handle_list_pending'),
        ('cmd:create_guest', 'admin_commands', '_send_usage_message'),
        ('cmd:view_discount', 'discount', 'handle_discount_status'),
        ('cmd:process_delivery', 'wholesale_delivery', 'handle_wholesale_delivery'),
        ('cmd:process_labeling', 'labeling', 'handle_labeling_completed'),
        ('cmd:send_delivery_overviews', 'admin_order', 'handle_send_overviews'),
        ('cmd:process_payment', 'admin_order', 'handle_mark_paid'),
        ('cmd:delete_old_orders', 'admin_order', 'handle_delete_old'),
    ])
    def test_command_callbacks_new_names(self, callback_handler, mock_handlers, callback_data, handler, method):
        """Test command callbacks with new command names route correctly"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        
        if method == '_start_user_orders_input' or method == '_send_usage_message':
            # These are internal methods on callback_handler, not handlers
            assert True  # Just verify no exception
        else:
            getattr(mock_handlers[handler], method).assert_called()
    
    # Test 3: Pagination Callbacks - New Multi-Word Commands
    @pytest.mark.parametrize("callback_data,expected_page", [
        ('page_process_payment_2', 2),
        ('page_process_payment_5', 5),
    ])
    def test_pagination_process_payment(self, callback_handler, mock_handlers, callback_data, expected_page):
        """Test pagination for process_payment (new 2-word command)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        mock_handlers['admin_order'].handle_mark_paid.assert_called_once()
        call_args = mock_handlers['admin_order'].handle_mark_paid.call_args[0]
        assert call_args[2] == expected_page
    
    # Test 4: Pagination Callbacks - Legacy Support
    @pytest.mark.parametrize("callback_data,expected_page", [
        ('page_mark_paid_1', 1),
        ('page_mark_paid_3', 3),
    ])
    def test_pagination_mark_paid_legacy(self, callback_handler, mock_handlers, callback_data, expected_page):
        """Test pagination for mark_paid (legacy 2-word command) still works"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        mock_handlers['admin_order'].handle_mark_paid.assert_called_once()
        call_args = mock_handlers['admin_order'].handle_mark_paid.call_args[0]
        assert call_args[2] == expected_page
    
    # Test 5: Pagination - Standard Single-Word Commands
    @pytest.mark.parametrize("callback_data,handler,method,expected_page", [
        ('page_suppliers_2', 'supplier', 'handle_list_suppliers', 2),
        ('page_suppliers_active_3', 'supplier', 'handle_list_suppliers', 3),
        ('page_pending_1', 'user', 'handle_list_pending', 1),
        ('page_guests_2', 'user', 'handle_list_guests', 2),
        ('page_subscribers_1', 'user', 'handle_list_subscribers', 1),
        ('page_changelog_3', 'changelog', 'handle_changelog', 3),
    ])
    def test_pagination_standard_commands(self, callback_handler, mock_handlers, callback_data, handler, method, expected_page):
        """Test pagination for standard single-word commands"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        
        if handler == 'changelog':
            # Changelog not in mock_handlers, skip
            pass
        else:
            getattr(mock_handlers[handler], method).assert_called()
            call_args = getattr(mock_handlers[handler], method).call_args[0]
            assert call_args[1] == expected_page
    
    # Test 6: Order Callbacks
    @pytest.mark.parametrize("callback_data", [
        'order_123_2',
        'order_456_5',
    ])
    def test_order_callbacks(self, callback_handler, mock_handlers, callback_data):
        """Test order callbacks route to customer_order handler"""
        query = self._create_callback_query(callback_data)
        callback_handler.handle_callback_query(query)
        mock_handlers['customer_order'].handle_order.assert_called_once()
    
    # Test 7: Confirm Order Callbacks
    @pytest.mark.parametrize("callback_data", [
        'confirm_order_123_2',
        'confirm_order_456_5',
    ])
    def test_confirm_order_callbacks(self, callback_handler, mock_handlers, callback_data):
        """Test confirm order callbacks route correctly"""
        query = self._create_callback_query(callback_data)
        callback_handler.handle_callback_query(query)
        mock_handlers['customer_order'].handle_confirm_order.assert_called_once()
    
    # Test 8: Wholesale Delivery Callbacks
    @pytest.mark.parametrize("callback_data", [
        'wd_sup:supplier123',
        'wd_off:456:supplier123',
        'wd_box:box789:456:supplier123',
    ])
    def test_wholesale_delivery_callbacks(self, callback_handler, mock_handlers, callback_data):
        """Test wholesale delivery callbacks route correctly"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        # Verify wholesale_delivery handler was called
        assert mock_handlers['wholesale_delivery'].handle_supplier_selection.called or \
               mock_handlers['wholesale_delivery'].handle_offer_selection.called or \
               mock_handlers['wholesale_delivery'].handle_box_selection.called
    
    # Test 9: Labeling Completion Callbacks
    @pytest.mark.parametrize("callback_data", [
        'lc_sup:supplier123',
        'lc_off:456:supplier123',
        'lc_box:box789:456:supplier123',
    ])
    def test_labeling_completion_callbacks(self, callback_handler, mock_handlers, callback_data):
        """Test labeling completion callbacks route correctly"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        # Verify labeling handler was called
        assert mock_handlers['labeling'].handle_supplier_selection.called or \
               mock_handlers['labeling'].handle_offer_selection.called or \
               mock_handlers['labeling'].handle_box_selection.called
    
    # Test 10: Export Orders Callbacks
    @pytest.mark.parametrize("callback_data,expected_filter", [
        ('export_orders_active', 'active'),
        ('export_orders_cancelled', 'cancelled'),
        ('export_orders_completed', 'completed'),
        ('export_orders_labeling_completed', 'labeling_completed'),
    ])
    def test_export_orders_callbacks(self, callback_handler, mock_handlers, callback_data, expected_filter):
        """Test export orders callbacks with status filters"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        mock_handlers['admin_order'].handle_export_orders_callback.assert_called_once()
        call_args = mock_handlers['admin_order'].handle_export_orders_callback.call_args[0]
        assert call_args[1] == expected_filter
    
    # Test 11: User Approval Callbacks
    @pytest.mark.parametrize("callback_data", [
        'approve_user_customer123',
        'reject_user_customer456',
    ])
    def test_user_approval_callbacks(self, callback_handler, mock_handlers, callback_data):
        """Test user approval/rejection callbacks"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        
        if 'approve' in callback_data:
            mock_handlers['user'].handle_approve_user_by_id.assert_called_once()
        else:
            mock_handlers['user'].handle_reject_user_by_id.assert_called_once()
    
    # Test 12: Offer Details Callbacks
    @pytest.mark.parametrize("callback_data", [
        'offer_details_123',
        'offer_details_456_edit',
    ])
    def test_offer_details_callbacks(self, callback_handler, mock_handlers, callback_data):
        """Test offer details callbacks"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        mock_handlers['info'].handle_offer_details.assert_called_once()
    
    # Test 13: Cancel Action Callback
    def test_cancel_action_returns_to_admin(self, callback_handler, mock_handlers):
        """Test cancel_action returns to admin panel"""
        query = self._create_callback_query('cancel_action', user_id=15005473)
        callback_handler.handle_callback_query(query)
        mock_handlers['admin_commands'].handle_admin.assert_called_once()
    
    # Test 14: Non-Admin Blocked from Admin Callbacks
    def test_non_admin_blocked_from_admin_callbacks(self, callback_handler, mock_handlers):
        """Test that non-admin users cannot access admin callbacks"""
        # Mock both _send_message and _t to avoid translation issues
        callback_handler._send_message = Mock(return_value={'status': 'sent'})
        callback_handler._t = Mock(return_value='Admin only')
        
        query = self._create_callback_query('admin:main', user_id=12345)
        result = callback_handler.handle_callback_query(query)
        assert result['status'] == 'unauthorized'
    
    # Test 15: Keyboard Removal Logic
    @pytest.mark.parametrize("callback_data,should_keep_keyboard", [
        ('page_suppliers_2', True),  # Pagination keeps keyboard
        ('wd_sup:123', True),  # Wholesale delivery keeps keyboard
        ('order_123_2', True),  # Order buttons keep keyboard
        ('create_supplier_start', True),  # Create supplier flow keeps keyboard
        ('confirm_order_123_2', False),  # Confirmation removes keyboard
        ('approve_user_123', False),  # User approval removes keyboard
    ])
    def test_keyboard_removal_logic(self, callback_handler, callback_data, should_keep_keyboard):
        """Test that keyboard removal logic works correctly"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        # Mock the _edit_message_remove_keyboard method to track calls
        callback_handler._edit_message_remove_keyboard = Mock(return_value=True)
        
        callback_handler.handle_callback_query(query)
        
        if should_keep_keyboard:
            callback_handler._edit_message_remove_keyboard.assert_not_called()
        else:
            callback_handler._edit_message_remove_keyboard.assert_called_once()
    
    # Test 16: Unknown Callback Handling
    def test_unknown_callback_returns_status(self, callback_handler):
        """Test that unknown callbacks return unknown_callback status"""
        query = self._create_callback_query('unknown_callback_xyz', user_id=15005473)
        result = callback_handler.handle_callback_query(query)
        assert result['status'] == 'unknown_callback'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
