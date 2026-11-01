#!/usr/bin/env python3
"""Simple verification script for OfferCache without pytest"""

import sys
import time
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from decimal import Decimal  # noqa: E402

from models.entities import Offer  # noqa: E402
from services.offer_cache import OfferCache  # noqa: E402


class MockDB:
    def __init__(self):
        self.call_count = 0
        self.test_offers = [
            Offer(
                offer_id=1,
                supplier_name="Test",
                name="Beer 1",
                price_per_unit=Decimal("5.00"),
                wholesale_box_size=12,
                status="active",
            )
        ]

    def _list_offers_uncached(self):
        self.call_count += 1
        # Return a new list each time to simulate database fetch
        return [
            Offer(
                offer_id=1,
                supplier_name="Test",
                name="Beer 1",
                price_per_unit=Decimal("5.00"),
                wholesale_box_size=12,
                status="active",
            )
        ]


def test_cache_hit():
    """Test cache returns same object on second call"""
    OfferCache.invalidate_cache()
    db = MockDB()

    offers1 = OfferCache.get_offers(db)
    offers2 = OfferCache.get_offers(db)

    assert offers1 is offers2, "Cache should return same object"
    assert db.call_count == 1, f"DB should be called once, was called {db.call_count} times"
    print("✅ test_cache_hit passed")


def test_cache_invalidation():
    """Test cache invalidates correctly"""
    OfferCache.invalidate_cache()
    db = MockDB()

    offers1 = OfferCache.get_offers(db)
    OfferCache.invalidate_cache()
    offers2 = OfferCache.get_offers(db)

    assert offers1 is not offers2, "Cache should return different object after invalidation"
    assert db.call_count == 2, f"DB should be called twice, was called {db.call_count} times"
    print("✅ test_cache_invalidation passed")


def test_cache_ttl():
    """Test cache expires after TTL"""
    OfferCache.invalidate_cache()
    original_ttl = OfferCache._ttl
    OfferCache._ttl = 1  # 1 second

    try:
        db = MockDB()
        offers1 = OfferCache.get_offers(db)
        time.sleep(1.1)
        offers2 = OfferCache.get_offers(db)

        assert offers1 is not offers2, "Cache should expire after TTL"
        assert db.call_count == 2, f"DB should be called twice after TTL, was called {db.call_count} times"
        print("✅ test_cache_ttl passed")
    finally:
        OfferCache._ttl = original_ttl


if __name__ == "__main__":
    print("Running OfferCache verification tests...\n")

    try:
        test_cache_hit()
        test_cache_invalidation()
        test_cache_ttl()

        print("\n✅ All tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
