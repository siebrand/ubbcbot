import logging
import os
from datetime import datetime
from typing import Any

import boto3

from models.entities import Box, Customer, Offer, Order, Supplier
from repositories.box_repository import BoxRepository
from repositories.credit_repository import CreditRepository
from repositories.customer_repository import CustomerRepository
from repositories.edit_context_repository import EditContextRepository
from repositories.notification_repository import NotificationRepository
from repositories.offer_repository import OfferRepository
from repositories.order_history_repository import OrderHistoryRepository
from repositories.order_repository import OrderRepository
from repositories.processed_update_repository import ProcessedUpdateRepository
from repositories.supplier_repository import SupplierRepository
from repositories.system_repository import SystemRepository
from services.offer_cache import OfferCache
from utils.s3_url import extract_s3_key

logger = logging.getLogger(__name__)


class DynamoDBService:
    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb")
        self.s3 = boto3.client("s3")
        self.table_prefix = os.environ.get("DYNAMODB_TABLE_PREFIX", "ubbc-bot-test")
        self.s3_bucket = os.environ.get("S3_BUCKET_NAME", f"{self.table_prefix}-images")

        # Initialize repositories
        self.system_repo = SystemRepository()
        self.supplier_repo = SupplierRepository()
        self.offer_repo = OfferRepository(self.system_repo)
        self.customer_repo = CustomerRepository(self.system_repo)
        self.box_repo = BoxRepository()
        self.order_repo = OrderRepository()
        self.order_history_repo = OrderHistoryRepository()
        self.credit_repo = CreditRepository()
        self.notification_repo = NotificationRepository()
        self.edit_context_repo = EditContextRepository()
        self.processed_update_repo = ProcessedUpdateRepository()

        # Initialize tables (Legacy - to be removed)
        self.suppliers_table = self.dynamodb.Table(f"{self.table_prefix}-suppliers")
        self.offers_table = self.dynamodb.Table(f"{self.table_prefix}-offers")
        self.customers_table = self.dynamodb.Table(f"{self.table_prefix}-customers")
        self.boxes_table = self.dynamodb.Table(f"{self.table_prefix}-boxes")
        self.orders_table = self.dynamodb.Table(f"{self.table_prefix}-orders")
        self.counters_table = self.dynamodb.Table(f"{self.table_prefix}-counters")
        self.notifications_table = self.dynamodb.Table(f"{self.table_prefix}-notifications")
        self.edit_contexts_table = self.dynamodb.Table(f"{self.table_prefix}-edit-contexts")
        self.order_history_table = self.dynamodb.Table(f"{self.table_prefix}-order-history")
        self.customer_credits_table = self.dynamodb.Table(f"{self.table_prefix}-customer-credits")
        self.credit_transactions_table = self.dynamodb.Table(f"{self.table_prefix}-credit-transactions")

    def _serialize_datetime(self, obj):
        """Convert datetime objects to ISO strings"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    def _prepare_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Prepare item for DynamoDB storage"""
        prepared = {}
        for key, value in item.items():
            if isinstance(value, datetime):
                prepared[key] = value.isoformat()
            elif value is not None:
                prepared[key] = value
        return prepared

    def _get_next_offer_id(self) -> int:
        """Get next auto-incrementing offer ID"""
        return self.system_repo.get_next_id("offer_id")

    def get_next_guest_id(self) -> int:
        """Get next auto-incrementing guest ID"""
        return self.system_repo.get_next_id("guest_id")

    # Supplier operations
    def create_supplier(self, supplier: Supplier) -> bool:
        return self.supplier_repo.create_supplier(supplier)

    def get_supplier(self, supplier_id: str) -> Supplier | None:
        return self.supplier_repo.get_supplier(supplier_id)

    def get_supplier_by_name(self, name: str) -> Supplier | None:
        return self.supplier_repo.get_supplier_by_name(name)

    def update_supplier(self, supplier_id: str, updates: dict[str, Any]) -> bool:
        return self.supplier_repo.update_supplier(supplier_id, updates)

    def list_suppliers(self) -> list[Supplier]:
        return self.supplier_repo.list_suppliers()

    # Offer operations
    def create_offer(self, offer: Offer) -> bool:
        return self.offer_repo.create_offer(offer)

    def get_offer(self, offer_id: int) -> Offer | None:
        return self.offer_repo.get_offer(offer_id)

    def list_offers(self) -> list[Offer]:
        """Get all offers with caching"""
        return self.offer_repo.list_offers()

    def _list_offers_uncached(self) -> list[Offer]:
        """Internal method to get offers without caching"""
        return self.offer_repo._list_offers_uncached()

    def list_sold_out_offers_recent(self, days: int = 7) -> list[Offer]:
        """Get sold out offers from last N days"""
        return self.offer_repo.list_sold_out_offers_recent(days)

    def update_offer(self, offer_id: int, updates: dict[str, Any]) -> bool:
        return self.offer_repo.update_offer(offer_id, updates)

    def append_offer_image(self, offer_id: int, image_url: str) -> bool:
        """Atomically append an image to offer's images list"""
        return self.offer_repo.append_offer_image(offer_id, image_url)

    def delete_box(self, box_id: str) -> bool:
        return self.box_repo.delete_box(box_id)

    # Customer operations
    def create_customer(self, customer: Customer) -> Customer | None:
        """Create customer and invalidate cache"""
        return self.customer_repo.create_customer(customer)

    def get_customer_by_telegram_id(self, telegram_user_id: int) -> Customer | None:
        """Get customer by telegram ID with caching"""
        return self.customer_repo.get_customer_by_telegram_id(telegram_user_id)

    def _get_customer_by_telegram_id_uncached(self, telegram_user_id: int) -> Customer | None:
        """Internal method to get customer by telegram ID without caching"""
        return self.customer_repo._get_customer_by_telegram_id_uncached(telegram_user_id)

    # Box operations
    def create_box(self, box: Box) -> Box | None:
        return self.box_repo.create_box(box)

    def get_boxes_by_offer(self, offer_id: int) -> list[Box]:
        return self.box_repo.get_boxes_by_offer(offer_id)

    def update_box(self, box_id: str, updates: dict[str, Any]) -> bool:
        return self.box_repo.update_box(box_id, updates)

    def increment_box_quantity(self, box_id: str, delta: int, max_capacity: int) -> bool:
        return self.box_repo.increment_box_quantity(box_id, delta, max_capacity)

    # Order operations
    def create_order(self, order: Order, admin_id: int = 0) -> Order | None:
        """Create order with automatic audit logging"""
        try:
            from services.audit_service import AuditService

            result = self.order_repo.create_order(order)
            if result:
                audit = AuditService(self)
                audit.log_order_created(order, admin_id)
            return result
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return None

    def create_order_with_box_increment(
        self, order: Order, box_id: str, quantity: int, max_capacity: int, admin_id: int = 0
    ) -> Order | None:
        """Create an order and increment its box in a single DynamoDB transaction.

        Previously the order Put and the box quantity Update were two separate writes;
        if the second failed, an order could exist without its box being updated (or
        vice versa). TransactWriteItems makes both all-or-nothing, and the box Update
        keeps the capacity guard so a transaction that would overfill is rejected
        atomically. Audit logging runs only after the transaction commits.

        Returns the created Order on success, or None if the transaction failed
        (including the capacity guard rejecting it).
        """
        from boto3.dynamodb.types import TypeSerializer
        from botocore.exceptions import ClientError

        serializer = TypeSerializer()
        order_item = {k: serializer.serialize(v) for k, v in self.order_repo._prepare_item(order.__dict__).items()}
        threshold = max_capacity - quantity

        # Use a plain low-level client: the resource's client applies its own
        # (de)serialization, which would double-wrap our already-serialized items.
        client = boto3.client("dynamodb")

        try:
            client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": f"{self.table_prefix}-orders",
                            "Item": order_item,
                            "ConditionExpression": "attribute_not_exists(order_id)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": f"{self.table_prefix}-boxes",
                            "Key": {"box_id": {"S": box_id}},
                            "UpdateExpression": "ADD current_quantity :delta",
                            "ConditionExpression": "attribute_exists(box_id) AND current_quantity <= :threshold",
                            "ExpressionAttributeValues": {
                                ":delta": {"N": str(quantity)},
                                ":threshold": {"N": str(threshold)},
                            },
                        }
                    },
                ]
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("TransactionCanceledException", "ConditionalCheckFailedException"):
                logger.warning(f"Order+box transaction rejected for box {box_id}: {e}")
            else:
                logger.error(f"Order+box transaction failed for box {box_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Order+box transaction failed for box {box_id}: {e}")
            return None

        # Audit only after the atomic write has committed.
        try:
            from services.audit_service import AuditService

            AuditService(self).log_order_created(order, admin_id)
        except Exception as e:
            logger.error(f"Order created but audit logging failed for {order.order_id}: {e}")

        return order

    def get_orders_by_customer(self, customer_id: str) -> list[Order]:
        return self.order_repo.get_orders_by_customer(customer_id)

    def get_orders_by_offer(self, offer_id: int) -> list[Order]:
        return self.order_repo.get_orders_by_offer(offer_id)

    def get_all_boxes(self) -> list[Box]:
        """Scan all boxes from DynamoDB with minimal fields for list_offers"""
        return self.box_repo.get_all_boxes()

    def get_all_orders(self, statuses: list[str] = None) -> list[Order]:
        """Scan all orders with minimal fields for list_offers"""
        return self.order_repo.get_all_orders(statuses)

    def get_orders_by_customer_and_offer(self, customer_id: str, offer_id: int) -> list[Order]:
        """Get orders for a specific customer and offer combination"""
        try:
            orders = self.get_orders_by_offer(offer_id)
            return [order for order in orders if order.customer_id == customer_id]
        except Exception as e:
            logger.error(f"Error getting orders by customer and offer: {e}")
            return []

    def get_orders_by_customer_and_status(self, customer_id: str, status: str) -> list[Order]:
        """Get orders for a specific customer with specific status"""
        try:
            orders = self.get_orders_by_customer(customer_id)
            return [order for order in orders if order.status == status]
        except Exception as e:
            logger.error(f"Error getting orders by customer and status: {e}")
            return []

    def get_orders_by_box(self, box_id: str) -> list[Order]:
        """Get all orders for a specific box"""
        return self.order_repo.get_orders_by_box(box_id)

    def get_order(self, order_id: str) -> Order | None:
        return self.order_repo.get_order(order_id)

    def get_customer(self, customer_id: str) -> Customer | None:
        return self.customer_repo.get_customer(customer_id)

    def get_box(self, box_id: str) -> Box | None:
        return self.box_repo.get_box(box_id)

    def delete_order(self, order_id: str) -> bool:
        return self.order_repo.delete_order(order_id)

    def update_order(self, order_id: str, updates: dict[str, Any], admin_id: int = 0, reason: str = "") -> bool:
        """Update order with automatic audit logging"""
        try:
            from services.audit_service import AuditService

            old_order = self.get_order(order_id)
            if not old_order:
                return False

            if not self.order_repo.update_order(order_id, updates):
                return False

            # Auto-log significant changes
            audit = AuditService(self)
            new_order = self.get_order(order_id)

            if "total_price" in updates and old_order.total_price != new_order.total_price:
                audit.log_price_change(new_order, old_order.total_price, new_order.total_price, admin_id, reason)
            elif "status" in updates and old_order.status != new_order.status:
                audit.log_status_change(new_order, old_order.status, new_order.status, admin_id, reason)

            return True
        except Exception as e:
            logger.error(f"Error updating order: {e}")
            return False

    def batch_update_order_status(self, order_ids: list[str], status: str, admin_id: int = 0) -> int:
        """Batch update order status with audit logging. Returns count of successful updates."""
        from services.audit_service import AuditService

        # Batch fetch orders before update for audit trail
        orders = self.order_repo.batch_get_orders(order_ids)

        updated_count = self.order_repo.batch_update_order_status(order_ids, status)

        if updated_count > 0 and orders:
            audit = AuditService(self)
            # Batch audit logging instead of looping
            audit.log_batch_status_change(
                orders[:updated_count], orders[0].status, status, admin_id, "Delivery overview queued"
            )

        return updated_count

    def get_customers_by_status(self, status: str) -> list[Customer]:
        """Get customers by status with caching"""
        return self.customer_repo.get_customers_by_status(status)

    def _get_customers_by_status_uncached(self, status: str) -> list[Customer]:
        """Internal method to get customers by status without caching"""
        return self.customer_repo._get_customers_by_status_uncached(status)

    def get_customer_by_username(self, username: str) -> Customer | None:
        return self.customer_repo.get_customer_by_username(username)

    def get_customer_by_name(self, name: str) -> Customer | None:
        """Search customer by name (first + last)"""
        return self.customer_repo.get_customer_by_name(name)

    def update_customer(self, customer_id: str, updates: dict[str, Any]) -> bool:
        return self.customer_repo.update_customer(customer_id, updates)

    def get_subscribers(self) -> list[Customer]:
        """Get subscribers with caching"""
        return self.customer_repo.get_subscribers()

    # Notification message operations
    def create_notification_message(self, notification) -> bool:
        return self.notification_repo.create_notification_message(notification)

    def get_notification_messages_by_offer(self, offer_id: int):
        return self.notification_repo.get_notification_messages_by_offer(offer_id)

    def delete_notification_message(self, notification_id: str) -> bool:
        return self.notification_repo.delete_notification_message(notification_id)

    def create_edit_context(self, context) -> bool:
        return self.edit_context_repo.create_edit_context(context)

    def mark_update_processed(self, update_id: int) -> bool:
        """Return True if this update_id is seen for the first time (see repository)."""
        return self.processed_update_repo.mark_processed(update_id)

    def get_edit_context_by_chat_id(self, chat_id: int):
        return self.edit_context_repo.get_edit_context_by_chat_id(chat_id)

    def delete_edit_context(self, context_id: str) -> bool:
        return self.edit_context_repo.delete_edit_context(context_id)

    def cleanup_old_edit_contexts(self) -> int:
        return self.edit_context_repo.cleanup_old_edit_contexts()

    def upload_image_to_s3(self, file_content: bytes, file_name: str, offer_id: int) -> str | None:
        """Upload image to S3 and return URL"""
        try:
            key = f"offers/{offer_id}/{file_name}"
            self.s3.put_object(Bucket=self.s3_bucket, Key=key, Body=file_content, ContentType="image/jpeg")
            return f"https://{self.s3_bucket}.s3.amazonaws.com/{key}"
        except Exception as e:
            logger.error(f"Error uploading image to S3: {e}")
            return None

    def get_presigned_url(self, s3_url: str, expiration: int = 3600) -> str | None:
        """Generate presigned URL for S3 object"""
        try:
            # Extract key from S3 URL (host-validated, not a substring match)
            key = extract_s3_key(s3_url)
            if key is None:
                return None

            presigned_url = self.s3.generate_presigned_url(
                "get_object", Params={"Bucket": self.s3_bucket, "Key": key}, ExpiresIn=expiration
            )
            return presigned_url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None

    def get_suppliers_with_boxes_by_status(self, box_status: str) -> list[Supplier]:
        """Get suppliers that have boxes with specified status"""
        try:
            # Get all boxes with specified status
            response = self.boxes_table.scan(
                FilterExpression="#status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": box_status},
            )

            # Get unique offer IDs from boxes
            offer_ids = set()
            for item in response.get("Items", []):
                offer_ids.add(item["offer_id"])

            # Get supplier names from offers
            supplier_names = set()
            for offer_id in offer_ids:
                offer = self.get_offer(offer_id)
                if offer:
                    supplier_names.add(offer.supplier_name)

            # Get supplier objects
            suppliers = []
            for name in supplier_names:
                supplier = self.get_supplier_by_name(name)
                if supplier:
                    suppliers.append(supplier)

            return suppliers
        except Exception as e:
            logger.error(f"Error getting suppliers with {box_status} boxes: {e}")
            return []

    def get_offers_by_supplier_and_box_status(self, supplier_name: str, box_status: str) -> list[Offer]:
        """Get offers for a supplier that have boxes with specified status"""
        try:
            # Get all boxes with specified status
            response = self.boxes_table.scan(
                FilterExpression="#status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": box_status},
            )

            # Get offer IDs from boxes
            offer_ids = set()
            for item in response.get("Items", []):
                offer_ids.add(item["offer_id"])

            # Get offers for this supplier that have boxes with specified status
            offers = []
            for offer_id in offer_ids:
                offer = self.get_offer(offer_id)
                if offer and offer.supplier_name == supplier_name:
                    offers.append(offer)

            return offers
        except Exception as e:
            logger.error(f"Error getting {box_status} offers by supplier: {e}")
            return []

    def get_suppliers_with_ordered_offers(self) -> list[Supplier]:
        """Get suppliers that have boxes with ORDERED status"""
        return self.get_suppliers_with_boxes_by_status("ordered")

    def get_ordered_offers_by_supplier(self, supplier_name: str) -> list[Offer]:
        """Get offers for a supplier that have boxes with ORDERED status"""
        return self.get_offers_by_supplier_and_box_status(supplier_name, "ordered")

    def get_boxes_by_offer_with_orders(self, offer_id: int) -> list[Box]:
        """Get boxes for an offer that have orders"""
        try:
            boxes = self.get_boxes_by_offer(offer_id)
            boxes_with_orders = []

            for box in boxes:
                orders = self.get_orders_by_box(box.box_id)
                if orders:  # Only include boxes that have orders
                    boxes_with_orders.append(box)

            return boxes_with_orders
        except Exception as e:
            logger.error(f"Error getting boxes with orders: {e}")
            return []

    def get_suppliers_with_ready_for_labeling_offers(self) -> list[Supplier]:
        """Get suppliers that have orders with READY_FOR_LABELING status"""
        return self.get_suppliers_with_orders_by_status("ready_for_labeling")

    def get_ready_for_labeling_offers_by_supplier(self, supplier_name: str) -> list[Offer]:
        """Get offers for a supplier that have orders with READY_FOR_LABELING status"""
        return self.get_offers_by_supplier_and_order_status(supplier_name, "ready_for_labeling")

    def get_boxes_by_offer_with_ready_orders(self, offer_id: int) -> list[Box]:
        """Get boxes for an offer that have orders with READY_FOR_LABELING status"""
        return self.get_boxes_by_offer_with_order_status(offer_id, "ready_for_labeling")

    def get_suppliers_with_orders_by_status(self, order_status: str) -> list[Supplier]:
        """Get suppliers that have orders with specified status"""
        try:
            # Get all orders with specified status
            response = self.orders_table.scan(
                FilterExpression="#status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": order_status},
            )

            # Get unique offer IDs from orders
            offer_ids = set()
            for item in response.get("Items", []):
                offer_ids.add(item["offer_id"])

            # Get supplier names from offers
            supplier_names = set()
            for offer_id in offer_ids:
                offer = self.get_offer(offer_id)
                if offer:
                    supplier_names.add(offer.supplier_name)

            # Get supplier objects
            suppliers = []
            for name in supplier_names:
                supplier = self.get_supplier_by_name(name)
                if supplier:
                    suppliers.append(supplier)

            return suppliers
        except Exception as e:
            logger.error(f"Error getting suppliers with {order_status} orders: {e}")
            return []

    def get_offers_by_supplier_and_order_status(self, supplier_name: str, order_status: str) -> list[Offer]:
        """Get offers for a supplier that have orders with specified status"""
        try:
            # Get all orders with specified status
            response = self.orders_table.scan(
                FilterExpression="#status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": order_status},
            )

            # Get offer IDs from orders
            offer_ids = set()
            for item in response.get("Items", []):
                offer_ids.add(item["offer_id"])

            # Get offers for this supplier that have orders with specified status
            offers = []
            for offer_id in offer_ids:
                offer = self.get_offer(offer_id)
                if offer and offer.supplier_name == supplier_name:
                    offers.append(offer)

            return offers
        except Exception as e:
            logger.error(f"Error getting {order_status} offers by supplier: {e}")
            return []

    def get_boxes_by_offer_with_order_status(self, offer_id: int, order_status: str) -> list[Box]:
        """Get boxes for an offer that have orders with specified status"""
        try:
            boxes = self.get_boxes_by_offer(offer_id)
            boxes_with_status_orders = []

            for box in boxes:
                orders = self.get_orders_by_box(box.box_id)
                status_orders = [o for o in orders if o.status == order_status]
                if status_orders:  # Only include boxes that have orders with specified status
                    boxes_with_status_orders.append(box)

            return boxes_with_status_orders
        except Exception as e:
            logger.error(f"Error getting boxes with {order_status} orders: {e}")
            return []

    def delete_offer(self, offer_id: int) -> bool:
        try:
            self.offers_table.delete_item(Key={"offer_id": offer_id})

            # Invalidate cache
            OfferCache.invalidate_cache()

            return True
        except Exception as e:
            logger.error(f"Error deleting offer: {e}")
            return False

    def delete_offer_images(self, offer_id: int) -> bool:
        """Delete all images for an offer from S3"""
        try:
            prefix = f"offers/{offer_id}/"
            response = self.s3.list_objects_v2(Bucket=self.s3_bucket, Prefix=prefix)

            if "Contents" in response:
                objects = [{"Key": obj["Key"]} for obj in response["Contents"]]
                self.s3.delete_objects(Bucket=self.s3_bucket, Delete={"Objects": objects})
            return True
        except Exception as e:
            logger.error(f"Error deleting offer images: {e}")
            return False

    # Order History operations
    def create_order_history(self, history) -> bool:
        return self.order_history_repo.create_order_history(history)

    def get_order_history(self, order_id: str, limit: int = 50) -> list:
        return self.order_history_repo.get_order_history(order_id, limit)

    def get_customer_events(self, customer_id: str, event_type: str | None = None, days: int = 30) -> list:
        return self.order_history_repo.get_customer_events(customer_id, event_type, days)

    def get_events_by_type(
        self, event_type: str, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> list:
        return self.order_history_repo.get_events_by_type(event_type, start_date, end_date)

    def get_history_by_customer_name(self, customer_name: str, event_type: str | None = None, limit: int = 50) -> list:
        return self.order_history_repo.get_history_by_customer_name(customer_name, event_type, limit)

    # Transaction methods for sensitive operations (audit enforced)
    def cancel_order_with_audit(self, order_id: str, admin_id: int, reason: str) -> bool:
        """Cancel order with mandatory audit logging"""
        try:
            from services.audit_service import AuditService

            order = self.get_order(order_id)
            if not order:
                return False

            # Log cancellation first
            audit = AuditService(self)
            audit.log_order_cancelled(order, admin_id, reason)

            # Then update order (will also log status change via update_order)
            return self.update_order(order_id, {"status": "cancelled"}, admin_id, reason)
        except Exception as e:
            logger.error(f"Error cancelling order with audit: {e}")
            return False

    def adjust_order_price_with_audit(self, order_id: str, new_price, admin_id: int, reason: str) -> bool:
        """Adjust order price with mandatory audit logging and optional refund linkage"""
        try:
            from decimal import Decimal

            from services.audit_service import AuditService

            order = self.get_order(order_id)
            if not order:
                return False

            old_price = order.total_price
            new_price = Decimal(str(new_price))

            # Log price change with refund linkage
            audit = AuditService(self)
            audit.log_price_change(order, old_price, new_price, admin_id, reason)

            # Update order (will also log via update_order, but price change already logged above)
            return self.update_order(order_id, {"total_price": new_price}, admin_id, reason)
        except Exception as e:
            logger.error(f"Error adjusting order price with audit: {e}")
            return False

    def mark_order_paid_with_audit(self, order_id: str, admin_id: int) -> bool:
        """Mark order as paid with mandatory audit logging"""
        try:
            order = self.get_order(order_id)
            if not order:
                return False

            # Update order status (audit logging handled by update_order)
            return self.update_order(order_id, {"status": "completed"}, admin_id, "Payment received")
        except Exception as e:
            logger.error(f"Error marking order paid with audit: {e}")
            return False

    # Credit system operations
    def create_customer_credit(self, credit) -> bool:
        return self.credit_repo.create_customer_credit(credit)

    def get_customer_credit(self, customer_id: str):
        return self.credit_repo.get_customer_credit(customer_id)

    def update_customer_credit(self, customer_id: str, updates: dict[str, Any]) -> bool:
        return self.credit_repo.update_customer_credit(customer_id, updates)

    def increment_customer_credit(
        self, customer_id: str, balance_delta, issued_delta, used_delta, last_updated: str, created_at: str
    ) -> bool:
        return self.credit_repo.increment_balance(
            customer_id, balance_delta, issued_delta, used_delta, last_updated, created_at
        )

    def create_credit_transaction(self, transaction) -> bool:
        return self.credit_repo.create_credit_transaction(transaction)

    def get_credit_transactions_by_customer(self, customer_id: str, limit: int = 50) -> list:
        return self.credit_repo.get_credit_transactions_by_customer(customer_id, limit)

    def get_customers_with_credit_balance(self, min_amount=None) -> list:
        return self.credit_repo.get_customers_with_credit_balance(min_amount)

    # Payment link operations
    def store_payment_link(self, payment_url: str) -> bool:
        """Store payment link in counters table"""
        return self.system_repo.store_payment_link(payment_url)

    def get_payment_link(self) -> str | None:
        """Get stored payment link from counters table"""
        return self.system_repo.get_payment_link()
