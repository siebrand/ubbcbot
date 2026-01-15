#!/usr/bin/env python3
"""
Phase 0: Command Routing Tests
Tests the ACTUAL CommandRouter code - command parsing, authorization logic, and routing decisions.
This establishes baseline before any refactoring.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import Mock
from services.command_router import CommandRouter
from models.entities import AuthorizationStatus, Customer


class TestCommandRouting:
    """Test actual command routing logic"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database - returns approved customer by default"""
        db = Mock()
        customer = Customer(
            customer_id="1",
            telegram_user_id=12345,
            first_name="Test",
            authorization_status=AuthorizationStatus.APPROVED.value
        )
        db.get_customer_by_telegram_id.return_value = customer
        db.get_edit_context_by_chat_id.return_value = None
        return db
    
    @pytest.fixture
    def mock_handlers(self):
        """Mock handlers - track which handler methods are called"""
        handlers = {}
        for name in ['info', 'customer_order', 'auth', 'test', 'supplier', 'offer', 
                     'import', 'admin_order', 'user', 'discount', 'wholesale_delivery', 
                     'labeling', 'admin_commands', 'changelog', 'credit']:
            handlers[name] = Mock()
        return handlers
    
    @pytest.fixture
    def router(self, mock_db, mock_handlers):
        """Create actual CommandRouter instance"""
        return CommandRouter(
            db=mock_db,
            admin_user_id=15005473,
            environment='test',
            handlers=mock_handlers
        )
    
    # Test 1: Command Parsing - Bot Mention Removal
    def test_bot_mention_stripped(self, router, mock_handlers):
        """Test that @botname is stripped from commands"""
        router.route_command(12345, 12345, '/help@ubbc_bot')
        mock_handlers['info'].handle_help.assert_called_once()
    
    # Test 2: Command Parsing - Parameter Extraction
    def test_parameter_extraction(self, router, mock_handlers):
        """Test that parameters are correctly extracted and passed"""
        router.route_command(12345, 12345, '/help orders')
        call_args = mock_handlers['info'].handle_help.call_args[0]
        # Verify parameters list contains 'orders'
        assert 'orders' in call_args[2]
    
    # Test 3: Authorization - Unauthorized User Blocked
    def test_unauthorized_user_blocked(self, router, mock_db):
        """Test that unauthorized users cannot access commands"""
        unauth_customer = Customer(
            customer_id="2",
            telegram_user_id=99999,
            first_name="Unauthorized",
            authorization_status=AuthorizationStatus.UNAUTHORIZED.value
        )
        mock_db.get_customer_by_telegram_id.return_value = unauth_customer
        
        result = router.route_command(12345, 99999, '/list_offers')
        assert result['status'] == 'unauthorized'
    
    # Test 4: Authorization - Admin Access
    def test_admin_bypasses_authorization(self, router, mock_db, mock_handlers):
        """Test that admin can access commands without customer record"""
        mock_db.get_customer_by_telegram_id.return_value = None
        
        router.route_command(12345, 15005473, '/create_supplier Test')
        mock_handlers['supplier'].handle_create_supplier.assert_called_once()
    
    # Test 5: Authorization - Non-Admin Blocked from Admin Commands
    def test_non_admin_blocked_from_admin_commands(self, router):
        """Test that regular users cannot access admin commands"""
        result = router.route_command(12345, 12345, '/create_supplier Test')
        assert result['status'] == 'unknown_command'
    
    # Test 6: Unknown Command Handling
    def test_unknown_command_returns_status(self, router):
        """Test that unknown commands return unknown_command status"""
        result = router.route_command(12345, 12345, '/nonexistent_command')
        assert result['status'] == 'unknown_command'
    
    # Test 7: Deep Link - Order Deep Link
    def test_deep_link_order(self, router, mock_handlers):
        """Test /start with order deep link routes to order handler"""
        router.route_command(12345, 12345, '/start create_order_123_2')
        mock_handlers['customer_order'].handle_order.assert_called_once()
        call_args = mock_handlers['customer_order'].handle_order.call_args[0]
        assert '123' in call_args[2]
        assert '2' in call_args[2]
    
    # Test 8: Deep Link - Confirm Order Deep Link
    def test_deep_link_confirm_order(self, router, mock_handlers):
        """Test /start with confirm deep link routes to confirm handler"""
        router.route_command(12345, 12345, '/start confirm_123_2')
        mock_handlers['customer_order'].handle_confirm_order.assert_called_once()
    
    # Test 9: Deep Link - Help Section Deep Link
    def test_deep_link_help_section(self, router, mock_handlers):
        """Test /start with help deep link routes to help handler"""
        router.route_command(12345, 12345, '/start help_orders')
        call_args = mock_handlers['info'].handle_help.call_args[0]
        assert 'orders' in call_args[2]
    
    # Test 10: Deep Link - Offer Details Deep Link  
    def test_deep_link_offer_details(self, router, mock_handlers):
        """Test /start with view_offer deep link"""
        router.route_command(12345, 12345, '/start view_offer_123')
        call_args = mock_handlers['info'].handle_offer_details.call_args[0]
        assert '123' in call_args[2]
    
    # Test 11: Environment - Test Environment Group Handling
    def test_test_env_allows_group_commands(self, router, mock_handlers):
        """Test that test environment allows group commands"""
        group_chat_id = -100123456789
        router.route_command(group_chat_id, 12345, '/help')
        mock_handlers['info'].handle_help.assert_called_once()
    
    # Test 12: Admin Command - Supplier Filter Parameter
    def test_list_suppliers_filter_parsing(self, router, mock_handlers):
        """Test that list_suppliers correctly parses status filter"""
        router.route_command(12345, 15005473, '/list_suppliers retired')
        call_args = mock_handlers['supplier'].handle_list_suppliers.call_args[0]
        assert call_args[2] == 'retired'
    
    # Test 13: Admin Command - Default Filter
    def test_list_suppliers_default_filter(self, router, mock_handlers):
        """Test that list_suppliers defaults to 'active' filter"""
        router.route_command(12345, 15005473, '/list_suppliers')
        call_args = mock_handlers['supplier'].handle_list_suppliers.call_args[0]
        assert call_args[2] == 'active'
    
    # Test 14: Admin Command - User List with Status Filter
    def test_list_users_status_filter(self, router, mock_handlers):
        """Test that list_users correctly parses status filter"""
        router.route_command(12345, 15005473, '/list_users approved')
        call_args = mock_handlers['user'].handle_list_users.call_args[0]
        assert call_args[2] == 'approved'
    
    # Test 15: Admin Command - User List with Search String
    def test_list_users_search_string(self, router, mock_handlers):
        """Test that list_users correctly parses search string"""
        router.route_command(12345, 15005473, '/list_users John Doe')
        call_args = mock_handlers['user'].handle_list_users.call_args[0]
        assert call_args[3] == 'John Doe'
    
    # Test 16: Admin Command - User List with Status and Search
    def test_list_users_status_and_search(self, router, mock_handlers):
        """Test that list_users parses both status filter and search string"""
        router.route_command(12345, 15005473, '/list_users approved John Doe')
        call_args = mock_handlers['user'].handle_list_users.call_args[0]
        assert call_args[2] == 'approved'
        assert call_args[3] == 'John Doe'
    
    # Test 17: Cancel Command - No Edit Context
    def test_cancel_no_context(self, router, mock_handlers):
        """Test /cancel when no edit context exists"""
        mock_handlers['info']._send_success.return_value = {'status': 'nothing_to_cancel'}
        result = router.route_command(12345, 12345, '/cancel')
        assert result['status'] == 'nothing_to_cancel'
    
    # Test 18: All Customer Commands Route Correctly
    @pytest.mark.parametrize("command,handler,method", [
        ('/start', 'info', 'handle_start'),
        ('/help', 'info', 'handle_help'),
        ('/create_order 1 2', 'customer_order', 'handle_order'),
        ('/order 1 2', 'customer_order', 'handle_order'),  # Permanent alias
        ('/list_my_orders', 'info', 'handle_my_orders'),
        ('/my_orders', 'info', 'handle_my_orders'),  # Permanent alias
        ('/list_offers', 'info', 'handle_list_offers'),
        ('/subscribe', 'info', 'handle_subscribe'),
        ('/unsubscribe', 'info', 'handle_unsubscribe'),
        ('/view_offer 1', 'info', 'handle_offer_details'),
        ('/confirm_order 1 2', 'customer_order', 'handle_confirm_order'),
        ('/delete_cancelled_orders', 'customer_order', 'handle_delete_cancelled'),
        ('/delete_completed_orders', 'customer_order', 'handle_delete_completed'),
        ('/changelog', 'changelog', 'handle_changelog'),
    ])
    def test_customer_command_routing(self, router, mock_handlers, command, handler, method):
        """Test that customer commands route to correct handlers"""
        router.route_command(12345, 12345, command)
        getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 19: All Admin Commands Route Correctly
    @pytest.mark.parametrize("command,handler,method", [
        ('/create_supplier Test', 'supplier', 'handle_create_supplier'),
        ('/archive_supplier Test', 'supplier', 'handle_retire_supplier'),
        ('/list_suppliers', 'supplier', 'handle_list_suppliers'),
        ('/update_supplier Test', 'supplier', 'handle_update_supplier'),
        ('/create_offer S B 10 12', 'offer', 'handle_create_offer'),
        ('/publish_offer 1', 'offer', 'handle_publish_offer'),
        ('/cancel_offer 1', 'offer', 'handle_cancel_offer'),
        ('/delete_offer 1', 'offer', 'handle_delete_offer'),
        ('/create_box 1', 'offer', 'handle_add_box'),
        ('/list_boxes', 'offer', 'handle_list_boxes'),
        ('/audit_offer 1', 'offer', 'handle_audit_offer'),
        ('/process_wholesale 1', 'offer', 'handle_process_wholesale'),
        ('/create_order_for user 1 2', 'admin_order', 'handle_create_order_for'),
        ('/order_for user 1 2', 'admin_order', 'handle_create_order_for'),  # Permanent alias
        ('/cancel_order 1', 'admin_order', 'handle_cancel_order'),
        ('/list_user_orders user', 'admin_order', 'handle_list_user_orders'),
        ('/list_offer_orders 1', 'admin_order', 'handle_list_offer_orders'),
        ('/export_orders', 'admin_order', 'handle_export_orders'),
        ('/list_pending', 'user', 'handle_list_pending'),
        ('/list_users', 'user', 'handle_list_users'),
        ('/approve_user test', 'user', 'handle_approve_user'),
        ('/reject_user test', 'user', 'handle_reject_user'),
        ('/create_guest John', 'user', 'handle_create_guest'),
        ('/create_discount 10', 'discount', 'handle_create_discount'),
        ('/cancel_discount', 'discount', 'handle_cancel_discount'),
        ('/view_discount', 'discount', 'handle_view_discount'),
        ('/process_delivery', 'wholesale_delivery', 'handle_wholesale_delivery'),
        ('/process_labeling', 'labeling', 'handle_labeling_completed'),
        ('/send_delivery_overviews', 'admin_order', 'handle_send_overviews'),
        ('/process_payment', 'admin_order', 'handle_mark_paid'),
        ('/import_orders', 'import', 'handle_import_orders'),
        ('/finalize_import 1', 'import', 'handle_finalize_import'),
        ('/delete_old_orders', 'admin_order', 'handle_delete_old_orders'),
        ('/audit_orders', 'admin_order', 'handle_audit_orders'),
        ('/admin', 'admin_commands', 'handle_admin'),
        ('/credit user 10 reason', 'credit', 'handle_credit'),
    ])
    def test_admin_command_routing(self, router, mock_handlers, command, handler, method):
        """Test that admin commands route to correct handlers"""
        router.route_command(12345, 15005473, command)
        getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 20: Permanent Aliases Route Correctly
    @pytest.mark.parametrize("alias,canonical,handler,method,user_id", [
        ('/order 1 2', '/create_order', 'customer_order', 'handle_order', 12345),
        ('/my_orders', '/list_my_orders', 'info', 'handle_my_orders', 12345),
        ('/order_for user 1 2', '/create_order_for', 'admin_order', 'handle_create_order_for', 15005473),
    ])
    def test_permanent_aliases(self, router, mock_handlers, alias, canonical, handler, method, user_id):
        """Test that permanent aliases route to same handlers as canonical commands"""
        router.route_command(12345, user_id, alias)
        getattr(mock_handlers[handler], method).assert_called_once()
    
    # Test 21: Old Commands Return Unknown
    @pytest.mark.parametrize("old_command", [
        '/retire_supplier Test',
        '/offer_details 1',
        '/add_box 1',
        '/wholesale_delivery',
        '/labeling_completed',
        '/send_overviews',
        '/mark_paid',
        '/delete_cancelled',
        '/delete_completed',
    ])
    def test_old_commands_rejected(self, router, old_command):
        """Test that old command names are rejected and return unknown_command"""
        result = router.route_command(12345, 15005473, old_command)
        assert result['status'] == 'unknown_command'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])