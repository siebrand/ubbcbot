#!/usr/bin/env python3

import time
from decimal import Decimal
from unittest.mock import Mock

import pytest

from models.entities import Offer
from services.offer_cache import OfferCache


class TestOfferCache:
    """Test OfferCache service"""

    def setup_method(self):
        """Set up test fixtures"""
        # Clear cache before each test
        OfferCache.invalidate_cache()

        # Create mock database
        self.mock_db = Mock()

        # Create test offers
        self.test_offers = [
            Offer(
                offer_id=1,
                supplier_name="Test Supplier",
                name="Test Beer 1",
                price_per_unit=Decimal("5.00"),
                wholesale_box_size=12,
                status="active",
            ),
            Offer(
                offer_id=2,
                supplier_name="Test Supplier",
                name="Test Beer 2",
                price_per_unit=Decimal("6.00"),
                wholesale_box_size=24,
                status="active",
            ),
        ]

        # Return a new list copy each time to allow identity checks in tests
        self.mock_db._list_offers_uncached.side_effect = lambda: list(self.test_offers)

    def test_cache_miss_calls_database(self):
        """Test cache miss fetches from database"""
        offers = OfferCache.get_offers(self.mock_db)

        assert offers == self.test_offers
        self.mock_db._list_offers_uncached.assert_called_once()

    def test_cache_hit_does_not_call_database(self):
        """Test cache hit returns cached data without database call"""
        # First call - cache miss
        offers1 = OfferCache.get_offers(self.mock_db)

        # Second call - cache hit
        offers2 = OfferCache.get_offers(self.mock_db)

        # Should be same object from cache
        assert offers1 is offers2
        # Database should only be called once
        self.mock_db._list_offers_uncached.assert_called_once()

    def test_cache_invalidation_clears_cache(self):
        """Test cache invalidation forces new database call"""
        # First call - cache miss
        offers1 = OfferCache.get_offers(self.mock_db)

        # Invalidate cache
        OfferCache.invalidate_cache()

        # Second call - cache miss again
        offers2 = OfferCache.get_offers(self.mock_db)

        # Should be different objects
        assert offers1 is not offers2
        # Database should be called twice
        assert self.mock_db._list_offers_uncached.call_count == 2

    def test_cache_ttl_expiration(self):
        """Test cache expires after TTL"""
        # Temporarily reduce TTL for testing
        original_ttl = OfferCache._ttl
        OfferCache._ttl = 1  # 1 second

        try:
            # First call - cache miss
            offers1 = OfferCache.get_offers(self.mock_db)

            # Wait for TTL to expire
            time.sleep(1.1)

            # Second call - cache expired, should fetch again
            offers2 = OfferCache.get_offers(self.mock_db)

            # Should be different objects
            assert offers1 is not offers2
            # Database should be called twice
            assert self.mock_db._list_offers_uncached.call_count == 2
        finally:
            # Restore original TTL
            OfferCache._ttl = original_ttl

    def test_cache_returns_empty_list_on_error(self):
        """Test cache handles database errors gracefully"""
        self.mock_db._list_offers_uncached.side_effect = lambda: []

        offers = OfferCache.get_offers(self.mock_db)

        assert offers == []

    def test_multiple_cache_invalidations(self):
        """Test multiple invalidations work correctly"""
        # First call
        OfferCache.get_offers(self.mock_db)

        # Multiple invalidations
        OfferCache.invalidate_cache()
        OfferCache.invalidate_cache()
        OfferCache.invalidate_cache()

        # Should still work
        offers = OfferCache.get_offers(self.mock_db)
        assert offers == self.test_offers
        assert self.mock_db._list_offers_uncached.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
