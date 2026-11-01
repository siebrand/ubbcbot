#!/usr/bin/env python3
"""
Phase 0: Callback Router Tests
Tests for the CallbackRouter infrastructure before any migration.
Following TDD: Write tests first, then implement router.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from unittest.mock import Mock

import pytest


class TestCallbackRouter:
    """Test CallbackRouter infrastructure"""

    @pytest.fixture
    def router(self):
        """Create CallbackRouter instance"""
        from services.routing.callback_router import CallbackRouter

        return CallbackRouter()

    # Test 1: Basic Registration
    def test_register_handler(self, router):
        """Test that handlers can be registered with patterns"""
        handler = Mock()
        router.register(r"^test_(\d+)$", handler)
        assert len(router.routes) == 1

    # Test 2: Basic Matching
    def test_dispatch_matches_pattern(self, router):
        """Test that callback data matches registered pattern"""
        handler = Mock()
        router.register(r"^test_(\d+)$", handler)

        context = {"chat_id": 123}
        result = router.dispatch("test_456", context)

        assert result is True
        handler.assert_called_once()
        # Verify match object was passed
        call_args = handler.call_args[0]
        match = call_args[0]
        assert match.groups() == ("456",)

    # Test 3: No Match Returns False
    def test_dispatch_no_match_returns_false(self, router):
        """Test that unmatched callback returns False"""
        handler = Mock()
        router.register(r"^test_(\d+)$", handler)

        context = {"chat_id": 123}
        result = router.dispatch("other_456", context)

        assert result is False
        handler.assert_not_called()

    # Test 4: Multiple Pattern Groups
    def test_dispatch_extracts_multiple_groups(self, router):
        """Test that multiple capture groups are extracted correctly"""
        handler = Mock()
        router.register(r"^order_(\d+)_(\d+)_(\d+)$", handler)

        context = {"chat_id": 123}
        router.dispatch("order_111_222_333", context)

        call_args = handler.call_args[0]
        match = call_args[0]
        assert match.groups() == ("111", "222", "333")

    # Test 5: First Match Wins
    def test_dispatch_first_match_wins(self, router):
        """Test that first matching route is taken"""
        handler1 = Mock()
        handler2 = Mock()

        router.register(r"^test_\d+$", handler1)
        router.register(r"^test_\d+$", handler2)

        context = {"chat_id": 123}
        router.dispatch("test_123", context)

        handler1.assert_called_once()
        handler2.assert_not_called()

    # Test 6: Context Passed to Handler
    def test_dispatch_passes_context(self, router):
        """Test that context is passed to handler"""
        handler = Mock()
        router.register(r"^test_(\d+)$", handler)

        context = {"chat_id": 123, "user_id": 456}
        router.dispatch("test_789", context)

        call_args = handler.call_args[0]
        assert call_args[1] == context

    # Test 7: Alias Registration
    def test_register_with_aliases(self, router):
        """Test that aliases are registered correctly"""
        handler = Mock()
        router.register(r"^approve_user_(\d+)$", handler, aliases=[r"^appr_(\d+)$", r"^a_(\d+)$"])

        # Should have 3 routes: main + 2 aliases
        assert len(router.routes) == 3

    # Test 8: Alias Matching
    def test_dispatch_matches_alias(self, router):
        """Test that aliases route to same handler"""
        handler = Mock()
        router.register(r"^approve_user_(\d+)$", handler, aliases=[r"^appr_(\d+)$"])

        context = {"chat_id": 123}

        # Test main pattern
        router.dispatch("approve_user_456", context)
        assert handler.call_count == 1

        # Test alias
        router.dispatch("appr_456", context)
        assert handler.call_count == 2

    # Test 9: Multiple Aliases Extract Groups
    def test_aliases_extract_groups_correctly(self, router):
        """Test that aliases extract capture groups correctly"""
        handler = Mock()
        router.register(r"^order_for_quantity_(\d+)_(\d+)_(\d+)$", handler, aliases=[r"^ofq_(\d+)_(\d+)_(\d+)$"])

        context = {"chat_id": 123}
        router.dispatch("ofq_111_222_333", context)

        call_args = handler.call_args[0]
        match = call_args[0]
        assert match.groups() == ("111", "222", "333")

    # Test 10: Empty Aliases List
    def test_register_with_empty_aliases(self, router):
        """Test that empty aliases list doesn't break registration"""
        handler = Mock()
        router.register(r"^test_(\d+)$", handler, aliases=[])

        assert len(router.routes) == 1

        context = {"chat_id": 123}
        result = router.dispatch("test_456", context)
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
