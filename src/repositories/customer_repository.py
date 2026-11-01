import logging
from typing import Any

from models.entities import Customer
from repositories.base_repository import BaseRepository
from repositories.system_repository import SystemRepository
from services.user_cache import UserCache

logger = logging.getLogger(__name__)


class CustomerRepository(BaseRepository):
    def __init__(self, system_repo: SystemRepository):
        super().__init__("customers")
        self.system_repo = system_repo

    def create_customer(self, customer: Customer) -> Customer | None:
        """Create customer and invalidate cache"""
        try:
            # Handle guest users
            if customer.is_guest and (customer.telegram_user_id == -1 or customer.telegram_user_id == 0):
                # Assign a unique negative ID for guests
                next_id = self.system_repo.get_next_id("guest_id")
                customer.telegram_user_id = -next_id

            # Check for existing customer by Telegram ID (if not guest or guest with fixed ID)
            existing = self.get_customer_by_telegram_id(customer.telegram_user_id)
            if existing:
                return existing

            item = self._prepare_item(customer.__dict__)
            self.table.put_item(Item=item)

            # Invalidate cache
            UserCache.invalidate_cache()

            return customer
        except Exception as e:
            logger.error(f"Error creating customer: {e}")
            return None

    def get_customer(self, customer_id: str) -> Customer | None:
        try:
            response = self.table.get_item(Key={"customer_id": customer_id})
            if "Item" in response:
                return Customer(**response["Item"])
            return None
        except Exception as e:
            logger.error(f"Error getting customer: {e}")
            return None

    def update_customer(self, customer_id: str, updates: dict[str, Any]) -> bool:
        try:
            # Get current customer to check if status changed
            current_customer = self.get_customer(customer_id)

            update_expression = "SET "
            expression_values = {}
            expression_names = {}

            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key

            update_expression = update_expression.rstrip(", ")

            self.table.update_item(
                Key={"customer_id": customer_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values,
            )

            # Invalidate relevant caches
            if current_customer:
                # Invalidate telegram_id cache
                UserCache.invalidate_customer_cache(current_customer.telegram_user_id)

                # If authorization status changed, invalidate both old and new status caches
                if "authorization_status" in updates:
                    UserCache.invalidate_status_cache(current_customer.authorization_status)
                    UserCache.invalidate_status_cache(updates["authorization_status"])
                else:
                    # Otherwise just invalidate current status cache
                    UserCache.invalidate_status_cache(current_customer.authorization_status)

                # If subscription status changed, invalidate subscriber cache
                if "subscribed_to_offers" in updates:
                    UserCache.invalidate_subscriber_cache()
            else:
                # If we can't determine current status, invalidate all caches
                UserCache.invalidate_cache()

            return True
        except Exception as e:
            logger.error(f"Error updating customer: {e}")
            return False

    def get_customer_by_telegram_id(self, telegram_user_id: int) -> Customer | None:
        """Get customer by telegram ID with caching"""
        return UserCache.get_customer_by_telegram_id(telegram_user_id, self)

    def _get_customer_by_telegram_id_uncached(self, telegram_user_id: int) -> Customer | None:
        """Internal method to get customer by telegram ID without caching"""
        try:
            response = self.table.scan(
                FilterExpression="telegram_user_id = :tid", ExpressionAttributeValues={":tid": telegram_user_id}
            )
            items = response.get("Items", [])
            if items:
                return Customer(**items[0])
            return None
        except Exception as e:
            logger.error(f"Error getting customer by telegram ID: {e}")
            return None

    def get_customers_by_status(self, status: str) -> list[Customer]:
        """Get customers by status with caching"""
        return UserCache.get_customers_by_status(status, self)

    def _get_customers_by_status_uncached(self, status: str) -> list[Customer]:
        """Internal method to get customers by status without caching"""
        try:
            response = self.table.scan(
                FilterExpression="authorization_status = :status", ExpressionAttributeValues={":status": status}
            )
            return [Customer(**item) for item in response.get("Items", [])]
        except Exception as e:
            logger.error(f"Error getting customers by status: {e}")
            return []

    def get_subscribers(self) -> list[Customer]:
        """Get subscribers with caching"""
        return UserCache.get_subscribers(self)

    def _get_subscribers_uncached(self) -> list[Customer]:
        """Internal method to get subscribers without caching"""
        try:
            response = self.table.scan(
                FilterExpression="subscribed_to_offers = :subscribed", ExpressionAttributeValues={":subscribed": True}
            )
            customers = []
            for item in response.get("Items", []):
                # Handle missing fields for backward compatibility
                if "is_guest" not in item:
                    item["is_guest"] = False
                if "contact_info" not in item:
                    item["contact_info"] = None
                customers.append(Customer(**item))
            return customers
        except Exception as e:
            logger.error(f"Error getting subscribers: {e}")
            return []

    def get_all_customers(self) -> list[Customer]:
        """Get all customers with caching"""
        return UserCache.get_all_customers(self)

    def get_customer_by_username(self, username: str) -> Customer | None:
        try:
            username = username.strip().lstrip("@")
            response = self.table.scan(
                FilterExpression="username = :username", ExpressionAttributeValues={":username": username}
            )
            items = response.get("Items", [])
            if items:
                return Customer(**items[0])
            return None
        except Exception as e:
            logger.error(f"Error getting customer by username: {e}")
            return None

    def get_customer_by_name(self, name: str) -> Customer | None:
        """Search customer by name (first + last)"""
        try:
            # This is a simple scan, might be slow with many users
            # Logic: check if name matches first_name, last_name, or "first last"
            name = name.lower().strip()
            all_customers = self.get_all_customers()

            for customer in all_customers:
                full_name = f"{customer.first_name or ''} {customer.last_name or ''}".lower().strip()
                if (
                    (customer.first_name and customer.first_name.lower() == name)
                    or (customer.last_name and customer.last_name.lower() == name)
                    or (full_name == name)
                ):
                    return customer
            return None
        except Exception as e:
            logger.error(f"Error getting customer by name: {e}")
            return None
