from typing import Dict, List, Optional
from models.entities import Customer, AuthorizationStatus
import logging

logger = logging.getLogger()

class UserCache:
    """Cache for user lists to reduce DynamoDB queries"""
    
    _customers_by_status: Dict[str, List[Customer]] = {}
    _subscribers: Optional[List[Customer]] = None
    _all_customers: Optional[List[Customer]] = None
    _customers_by_telegram_id: Dict[int, Customer] = {}
    
    @classmethod
    def get_customers_by_status(cls, status: str, db_service) -> List[Customer]:
        """Get customers by status with caching"""
        if status not in cls._customers_by_status:
            logger.info(f"Cache miss for customers with status: {status}")
            customers = db_service._get_customers_by_status_uncached(status)
            cls._customers_by_status[status] = customers
            # Also populate telegram_id cache
            for customer in customers:
                cls._customers_by_telegram_id[customer.telegram_user_id] = customer
        else:
            logger.info(f"Cache hit for customers with status: {status}")
        
        return cls._customers_by_status[status]
    
    @classmethod
    def get_subscribers(cls, db_service) -> List[Customer]:
        """Get subscribers with caching"""
        if cls._subscribers is None:
            logger.info("Cache miss for subscribers")
            cls._subscribers = db_service._get_subscribers_uncached()
            # Also populate telegram_id cache
            for customer in cls._subscribers:
                cls._customers_by_telegram_id[customer.telegram_user_id] = customer
        else:
            logger.info("Cache hit for subscribers")
        
        return cls._subscribers
    
    @classmethod
    def get_all_customers(cls, db_service) -> List[Customer]:
        """Get all customers with caching"""
        if cls._all_customers is None:
            logger.info("Cache miss for all customers")
            # Combine all status lists
            all_customers = []
            for status in [AuthorizationStatus.APPROVED.value, 
                          AuthorizationStatus.UNAUTHORIZED.value, 
                          AuthorizationStatus.REJECTED.value]:
                all_customers.extend(cls.get_customers_by_status(status, db_service))
            cls._all_customers = all_customers
        else:
            logger.info("Cache hit for all customers")
        
        return cls._all_customers
    
    @classmethod
    def get_customer_by_telegram_id(cls, telegram_user_id: int, db_service) -> Optional[Customer]:
        """Get customer by telegram ID with caching"""
        if telegram_user_id not in cls._customers_by_telegram_id:
            logger.info(f"Cache miss for telegram_user_id: {telegram_user_id}")
            customer = db_service._get_customer_by_telegram_id_uncached(telegram_user_id)
            if customer:
                cls._customers_by_telegram_id[telegram_user_id] = customer
            return customer
        else:
            logger.info(f"Cache hit for telegram_user_id: {telegram_user_id}")
            return cls._customers_by_telegram_id[telegram_user_id]
    
    @classmethod
    def invalidate_cache(cls):
        """Invalidate all user caches"""
        logger.info("Invalidating user cache")
        cls._customers_by_status.clear()
        cls._subscribers = None
        cls._all_customers = None
        cls._customers_by_telegram_id.clear()
    
    @classmethod
    def invalidate_status_cache(cls, status: str):
        """Invalidate cache for specific status"""
        logger.info(f"Invalidating cache for status: {status}")
        if status in cls._customers_by_status:
            del cls._customers_by_status[status]
        cls._all_customers = None  # Also invalidate all customers cache
    
    @classmethod
    def invalidate_subscriber_cache(cls):
        """Invalidate subscriber cache"""
        logger.info("Invalidating subscriber cache")
        cls._subscribers = None
    
    @classmethod
    def invalidate_customer_cache(cls, telegram_user_id: int):
        """Invalidate cache for specific customer"""
        logger.info(f"Invalidating cache for telegram_user_id: {telegram_user_id}")
        if telegram_user_id in cls._customers_by_telegram_id:
            del cls._customers_by_telegram_id[telegram_user_id]