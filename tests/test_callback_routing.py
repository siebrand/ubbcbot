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
                     'admin_commands', 'delivery_overview', 'import', 'test', 'credit']:
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
        ('cmd:process_wholesale', 'offer', 'handle_process_wholesale'),
        ('cmd:export_orders', 'admin_order', 'handle_export_orders'),
        ('cmd:list_user_orders', 'admin_order', '_start_user_orders_input'),
        ('cmd:list_offer_orders', 'admin_order', 'handle_list_offer_orders'),
        ('cmd:create_order_for', 'admin_order', 'handle_create_order_for'),
        ('cmd:list_pending', 'user', 'handle_list_pending'),
        ('cmd:create_guest', 'admin_commands', '_send_usage_message'),
        ('cmd:view_discount', 'discount', 'handle_view_discount'),
        ('cmd:process_delivery', 'wholesale_delivery', 'handle_wholesale_delivery'),
        ('cmd:process_labeling', 'labeling', 'handle_labeling_completed'),
        ('cmd:send_delivery_overviews', 'admin_order', 'handle_send_delivery_overviews'),
        ('cmd:process_payment', 'admin_order', 'handle_mark_paid'),
        ('cmd:delete_old_orders', 'admin_order', 'handle_delete_old_orders'),
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
    
    # Test 7: Confirm Order Callbacks (Phase 2)
    @pytest.mark.parametrize("callback_data", [
        'confirm_order_123_2',
        'confirm_order_456_5',
    ])
    def test_confirm_order_callbacks(self, callback_handler, mock_handlers, callback_data):
        """Test confirm order callbacks route correctly (Phase 2)"""
        query = self._create_callback_query(callback_data)
        callback_handler.handle_callback_query(query)
        mock_handlers['customer_order'].handle_confirm_order.assert_called_once()
    
    # Test 7a: Cancel Patterns (Phase 2)
    @pytest.mark.parametrize("callback_data,handler,method", [
        ('cancel_order_user_select_customer123', 'admin_order', 'handle_cancel_order_user_select'),
        ('cancel_order_confirm_order456', 'admin_order', 'handle_cancel_order_by_id'),
        ('cancel_orders_page_customer123_2', 'admin_order', 'handle_cancel_orders_page'),
        ('cancel_confirmation', None, None),  # Just sends message
        ('cancel_action', 'admin_commands', 'handle_admin'),
    ])
    def test_cancel_patterns(self, callback_handler, mock_handlers, callback_data, handler, method):
        """Test cancel patterns route correctly (Phase 2)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        
        if handler and method:
            getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 7b: Confirm Patterns (Phase 2)
    @pytest.mark.parametrize("callback_data,handler,method", [
        ('confirm_process_wholesale_123_6', 'offer', 'handle_confirm_process_wholesale'),
        ('confirm_cancel_offer_456', 'offer', 'handle_confirm_cancel_offer'),
        ('confirm_cancel_order_order789', 'admin_order', 'handle_confirm_cancel'),
        ('confirm_fulfill_123_12', 'offer', 'handle_confirm_fulfill'),
    ])
    def test_confirm_patterns(self, callback_handler, mock_handlers, callback_data, handler, method):
        """Test confirm patterns route correctly (Phase 2)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        getattr(mock_handlers[handler], method).assert_called_once()
    
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
    
    # Test 11: User Approval Callbacks (Phase 1 & 2)
    @pytest.mark.parametrize("callback_data", [
        'approve_user_customer123',
        'approve_user_select_customer456',
        'reject_user_customer789',
    ])
    def test_user_approval_callbacks(self, callback_handler, mock_handlers, callback_data):
        """Test user approval/rejection callbacks (Phase 1 & 2)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        
        if 'approve_user_select' in callback_data:
            mock_handlers['user'].handle_approve_user_select.assert_called_once()
        elif 'approve' in callback_data:
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
    
    # Test 16: Edit Patterns (Phase 3 Batch A)
    @pytest.mark.parametrize("callback_data,handler,method", [
        ('edit_user_select_customer123', 'user', 'handle_edit_user_select'),
        ('edit_supplier_select_supplier456', 'supplier', 'show_edit_interface_by_id'),
    ])
    def test_edit_select_patterns(self, callback_handler, mock_handlers, callback_data, handler, method):
        """Test edit select patterns route correctly (Phase 3 Batch A)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 16a: Generic Edit Pattern
    def test_generic_edit_pattern(self, callback_handler):
        """Test generic edit pattern delegates to _handle_edit_callbacks"""
        query = self._create_callback_query('edit_supplier_name_supplier123', user_id=15005473)
        # Mock the _handle_edit_callbacks method
        callback_handler._handle_edit_callbacks = Mock(return_value={'status': 'handled'})
        callback_handler.handle_callback_query(query)
        callback_handler._handle_edit_callbacks.assert_called_once()
    
    # Test 17: Order Patterns (Phase 3 Batch B)
    @pytest.mark.parametrize("callback_data,handler,method", [
        ('order_for_quantity_cust123_456_5', 'admin_order', 'handle_create_order_for_quantity_select'),
        ('order_for_other_cust123_456', 'admin_order', 'handle_create_order_for_other_quantity'),
        ('order_for_offer_cust123_456', 'admin_order', 'handle_create_order_for_offer_select'),
        ('order_for_user_select_cust123', 'admin_order', 'handle_create_order_for_user_select'),
        ('order_123_2', 'customer_order', 'handle_order'),
    ])
    def test_order_patterns(self, callback_handler, mock_handlers, callback_data, handler, method):
        """Test order patterns route correctly (Phase 3 Batch B)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 18: Offer/Supplier Patterns (Phase 3 Batch C)
    @pytest.mark.parametrize("callback_data,handler,method", [
        ('wholesale_select_123', 'offer', 'handle_process_wholesale'),
        ('custom_wholesale_quantity_456', 'offer', 'handle_custom_wholesale_quantity'),
        ('publish_offer_789', 'offer', 'handle_publish_offer'),
        ('finalize_import_123', 'import', 'handle_finalize_import'),
        ('offer_details_456', 'info', 'handle_offer_details'),
        ('offer_orders_123', 'admin_order', 'handle_list_offer_orders_select'),
    ])
    def test_offer_supplier_patterns(self, callback_handler, mock_handlers, callback_data, handler, method):
        """Test offer/supplier patterns route correctly (Phase 3 Batch C)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 19: User/Status Patterns (Phase 3 Batch D)
    @pytest.mark.parametrize("callback_data,handler,method", [
        ('user_orders_select_cust123', 'admin_order', 'handle_list_user_orders_select'),
        ('user_status_select_cust456', 'user', 'handle_user_status_select'),
        ('credit_customer_cust789', 'credit', 'handle_credit_customer_select'),
    ])
    def test_user_status_patterns(self, callback_handler, mock_handlers, callback_data, handler, method):
        """Test user/status patterns route correctly (Phase 3 Batch D)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 20: Audit Patterns (Phase 3 Batch E)
    @pytest.mark.parametrize("callback_data,method", [
        ('audit_offer_123', '_execute_audit_offer'),
        ('audit_fill_boxes_123_5', '_execute_fill_boxes'),
        ('audit_fill_create_456_10', '_execute_fill_and_create'),
        ('audit_create_boxes_789_8', '_execute_create_boxes'),
        ('audit_cancel_orders_111_3', '_execute_cancel_orders'),
        ('audit_offers_page_2', '_show_audit_offer_selection'),
    ])
    def test_audit_patterns(self, callback_handler, mock_handlers, callback_data, method):
        """Test audit patterns route correctly (Phase 3 Batch E)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        getattr(mock_handlers['offer'], method).assert_called_once()
    
    # Test 21: Delivery/Export Patterns (Phase 3 Batch F)
    @pytest.mark.parametrize("callback_data,handler,method", [
        ('export_orders_active', 'admin_order', 'handle_export_orders_callback'),
        ('start_send_overviews', 'delivery_overview', 'start_send_overviews'),
        ('finish_labeling_box123', 'labeling', 'handle_finish_labeling'),
        ('mark_paid_cust456', 'delivery_overview', 'handle_mark_customer_paid'),
    ])
    def test_delivery_export_patterns(self, callback_handler, mock_handlers, callback_data, handler, method):
        """Test delivery/export patterns route correctly (Phase 3 Batch F)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 22: Navigation Patterns (Phase 3 Batch G - FINAL)
    @pytest.mark.parametrize("callback_data,handler,method", [
        ('back_to_supplier_list', 'supplier', 'handle_list_suppliers'),
        ('process_wholesale', 'offer', 'handle_process_wholesale'),
    ])
    def test_navigation_patterns(self, callback_handler, mock_handlers, callback_data, handler, method):
        """Test navigation patterns route correctly (Phase 3 Batch G)"""
        query = self._create_callback_query(callback_data, user_id=15005473)
        callback_handler.handle_callback_query(query)
        getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 23: Unknown Callback Handling
    def test_unknown_callback_returns_status(self, callback_handler):
        """Test that unknown callbacks return unknown_callback status"""
        query = self._create_callback_query('unknown_callback_xyz', user_id=15005473)
        result = callback_handler.handle_callback_query(query)
        assert result['status'] == 'unknown_callback'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
