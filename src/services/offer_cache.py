import time
from typing import List

class OfferCache:
    """Runtime cache for offer operations"""
    
    _cache = {}
    _cache_timestamps = {}
    _ttl = 300  # 5 minutes
    
    @classmethod
    def _is_cache_valid(cls, cache_key: str) -> bool:
        """Check if cache entry is still valid"""
        if cache_key not in cls._cache:
            return False
        
        timestamp = cls._cache_timestamps.get(cache_key, 0)
        return (time.time() - timestamp) < cls._ttl
    
    @classmethod
    def get_offers(cls, db) -> List:
        """Get all offers with caching"""
        cache_key = "offers:all"
        
        if cls._is_cache_valid(cache_key):
            return cls._cache[cache_key]
        
        # Cache miss - fetch from database
        offers = db._list_offers_uncached()
        cls._cache[cache_key] = offers
        cls._cache_timestamps[cache_key] = time.time()
        
        return offers
    
    @classmethod
    def invalidate_cache(cls):
        """Invalidate all offer caches"""
        cls._cache.clear()
        cls._cache_timestamps.clear()
