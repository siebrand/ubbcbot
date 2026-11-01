#!/usr/bin/env python3
"""
Phase 1: Approve User Callback Migration Tests
Integration tests for migrating approve_user_ callbacks to router
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from unittest.mock import Mock

import pytest

from services.routing.callback_router import CallbackRouter


class TestApproveUserCallbackMigration:
    """Test approve_user callback routing integration"""

    @pytest.fixture
    def router(self):
        """Create CallbackRouter instance"""
        return CallbackRouter()

    @pytest.fixture
    def mock_user_handler(self):
        """Mock user handler"""
        handler = Mock()
        handler.handle_approve_user_by_id = Mock(return_value={"status": "success"})
        handler.handle_approve_user_select = Mock(return_value={"status": "success"})
        return handler

    # Test 1: approve_user_ pattern registration
    def test_approve_user_pattern_registered(self, router, mock_user_handler):
        """Test that approve_user_ pattern can be registered"""

        def handler_wrapper(match, context):
            customer_id = match.group(1)
            return mock_user_handler.handle_approve_user_by_id(context["chat_id"], customer_id)

        router.register(r"^approve_user_(\d+)$", handler_wrapper)
        assert len(router.routes) == 1

    # Test 2: approve_user_ callback dispatches correctly
    def test_approve_user_callback_dispatches(self, router, mock_user_handler):
        """Test that approve_user_123 routes to handler with correct ID"""

        def handler_wrapper(match, context):
            customer_id = match.group(1)
            return mock_user_handler.handle_approve_user_by_id(context["chat_id"], customer_id)

        router.register(r"^approve_user_(\d+)$", handler_wrapper)

        context = {"chat_id": 12345}
        result = router.dispatch("approve_user_789", context)

        assert result is True
        mock_user_handler.handle_approve_user_by_id.assert_called_once_with(12345, "789")

    # Test 3: approve_user_select_ pattern registration
    def test_approve_user_select_pattern_registered(self, router, mock_user_handler):
        """Test that approve_user_select_ pattern can be registered"""

        def handler_wrapper(match, context):
            customer_id = match.group(1)
            return mock_user_handler.handle_approve_user_select(context["chat_id"], customer_id)

        router.register(r"^approve_user_select_(.+)$", handler_wrapper)
        assert len(router.routes) == 1

    # Test 4: approve_user_select_ callback dispatches correctly
    def test_approve_user_select_callback_dispatches(self, router, mock_user_handler):
        """Test that approve_user_select_123 routes correctly"""

        def handler_wrapper(match, context):
            customer_id = match.group(1)
            return mock_user_handler.handle_approve_user_select(context["chat_id"], customer_id)

        router.register(r"^approve_user_select_(.+)$", handler_wrapper)

        context = {"chat_id": 12345}
        result = router.dispatch("approve_user_select_abc123", context)

        assert result is True
        mock_user_handler.handle_approve_user_select.assert_called_once_with(12345, "abc123")

    # Test 5: Both patterns coexist without conflict
    def test_both_approve_patterns_coexist(self, router, mock_user_handler):
        """Test that both approve patterns can be registered and work independently"""

        def handler_wrapper_1(match, context):
            customer_id = match.group(1)
            return mock_user_handler.handle_approve_user_by_id(context["chat_id"], customer_id)

        def handler_wrapper_2(match, context):
            customer_id = match.group(1)
            return mock_user_handler.handle_approve_user_select(context["chat_id"], customer_id)

        router.register(r"^approve_user_(\d+)$", handler_wrapper_1)
        router.register(r"^approve_user_select_(.+)$", handler_wrapper_2)

        context = {"chat_id": 12345}

        # Test first pattern
        router.dispatch("approve_user_789", context)
        mock_user_handler.handle_approve_user_by_id.assert_called_once_with(12345, "789")

        # Test second pattern
        router.dispatch("approve_user_select_abc", context)
        mock_user_handler.handle_approve_user_select.assert_called_once_with(12345, "abc")

    # Test 6: Non-matching callback returns False
    def test_non_approve_callback_not_matched(self, router, mock_user_handler):
        """Test that non-approve callbacks don't match"""

        def handler_wrapper(match, context):
            customer_id = match.group(1)
            return mock_user_handler.handle_approve_user_by_id(context["chat_id"], customer_id)

        router.register(r"^approve_user_(\d+)$", handler_wrapper)

        context = {"chat_id": 12345}
        result = router.dispatch("reject_user_789", context)

        assert result is False
        mock_user_handler.handle_approve_user_by_id.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
