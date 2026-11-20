import logging
import os
from datetime import datetime
from typing import Any

from models.entities import AuthorizationStatus, Box, BoxStatus, Customer, Offer, Order, OrderStatus, Supplier
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
from services.box_refill import REFILLABLE_BOX_STATUSES
from services.image_store import ImageStore
from services.purchase_events import PurchaseEvents

logger = logging.getLogger(__name__)


class DynamoDBService:
    def __init__(self):
        self.table_prefix = os.environ.get("DYNAMODB_TABLE_PREFIX", "ubbc-bot-test")
        self.images = ImageStore()

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
        self.purchase_events = PurchaseEvents(self.order_history_repo, self.offer_repo)

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

    def update_offer(self, offer_id: int, updates: dict[str, Any]) -> bool:
        return self.offer_repo.update_offer(offer_id, updates)

    def append_offer_image(self, offer_id: int, image_url: str) -> bool:
        """Atomically append an image to offer's images list"""
        return self.offer_repo.append_offer_image(offer_id, image_url)

    def delete_box(self, box_id: str) -> bool:
        return self.box_repo.delete_box(box_id)

    def delete_box_if_empty(self, box_id: str) -> bool:
        """Delete a box that is not yet ordered, only while it holds nothing"""
        return self.box_repo.delete_box_if_empty(box_id, REFILLABLE_BOX_STATUSES)

    # Customer operations
    def create_customer(self, customer: Customer) -> Customer | None:
        """Create customer and invalidate cache"""
        return self.customer_repo.create_customer(customer)

    def get_customer_by_telegram_id(self, telegram_user_id: int) -> Customer | None:
        """Get customer by telegram ID with caching"""
        return self.customer_repo.get_customer_by_telegram_id(telegram_user_id)

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
        """Create order (records an ORDER_CREATED analytics event)"""
        try:
            result = self.order_repo.create_order(order)
            if result:
                self.purchase_events.order_created(order)
            return result
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return None

    def split_order(self, order: Order, kept_quantity: int, kept_status: str, rest: Order) -> bool:
        """Split an order in two in one transaction (see OrderRepository.split). No purchase event: the units were
        counted when the order was placed, and they stay ordered."""
        return self.order_repo.split(order, kept_quantity, kept_status, rest)

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
        if not self.order_repo.create_with_box_increment(order, box_id, quantity, max_capacity):
            return None

        # The analytics event only after the atomic write has committed.
        try:
            self.purchase_events.order_created(order)
        except Exception as e:
            logger.error(f"Order created but the analytics event failed for {order.order_id}: {e}")

        return order

    def move_order_to_box(
        self, order_id: str, quantity: int, from_box_id: str, to_box_id: str, to_max_capacity: int
    ) -> bool:
        """Move a pending order between two boxes that are not yet ordered, in one transaction (see box_refill)"""
        return self.order_repo.move_to_box(
            order_id, quantity, from_box_id, to_box_id, to_max_capacity, REFILLABLE_BOX_STATUSES
        )

    def get_orders_by_customer(self, customer_id: str, strict: bool = False) -> list[Order]:
        return self.order_repo.get_orders_by_customer(customer_id, strict=strict)

    def get_orders_by_offer(self, offer_id: int) -> list[Order]:
        return self.order_repo.get_orders_by_offer(offer_id)

    def get_all_boxes(self) -> list[Box]:
        """Scan all boxes from DynamoDB with minimal fields for list_offers"""
        return self.box_repo.get_all_boxes()

    def get_all_orders(self, statuses: list[str] | None = None) -> list[Order]:
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
        """Update an order; a payment (awaiting_payment -> completed) records a PAYMENT_RECEIVED analytics event"""
        try:
            old_order = self.get_order(order_id)
            if not old_order:
                return False

            if not self.order_repo.update_order(order_id, updates):
                return False

            # Read the order back only for a payment: the event holds the amount as stored
            if self.purchase_events.is_payment(old_order.status, updates.get("status", old_order.status)):
                paid_order = self.get_order(order_id)
                if paid_order:
                    self.purchase_events.payment_received(paid_order)

            return True
        except Exception as e:
            logger.error(f"Error updating order: {e}")
            return False

    def batch_update_order_status(
        self, order_ids: list[str], status: str, admin_id: int = 0, from_status: str | None = None
    ) -> list[str]:
        """Set the status of many orders; with ``from_status`` only of those that still have it. Returns the ids
        of the orders that were updated."""
        # Read before the update: the old status of each order decides whether it is a payment
        orders = self.order_repo.batch_get_orders(order_ids)
        updated = set(self.order_repo.batch_update_order_status(order_ids, status, from_status))

        if updated:
            self.purchase_events.payments_received(
                [
                    order
                    for order in orders
                    if order.order_id in updated and self.purchase_events.is_payment(order.status, status)
                ]
            )
        return [order_id for order_id in order_ids if order_id in updated]

    def get_customers_by_status(self, status: str) -> list[Customer]:
        """Get customers by status with caching"""
        return self.customer_repo.get_customers_by_status(status)

    def get_approved_customers_with_orders(self, order_status: str) -> list[tuple[Customer, list[Order]]]:
        """The approved customers that have orders with this status, each with those orders, in the order of the
        approved customers. One query for the orders (status-index), not one per customer."""
        orders_by_customer: dict[str, list[Order]] = {}
        for order in self.order_repo.get_orders_by_status(order_status):
            orders_by_customer.setdefault(order.customer_id, []).append(order)
        return [
            (customer, orders_by_customer[customer.customer_id])
            for customer in self.get_customers_by_status(AuthorizationStatus.APPROVED.value)
            if customer.customer_id in orders_by_customer
        ]

    def get_all_customers(self) -> list[Customer]:
        """Every customer, whatever their approval status (cached)"""
        return self.customer_repo.get_all_customers()

    def get_customer_by_username(self, username: str) -> Customer | None:
        return self.customer_repo.get_customer_by_username(username)

    def get_customer_by_name(self, name: str) -> Customer | None:
        """Search customer by name (first + last)"""
        return self.customer_repo.get_customer_by_name(name)

    def update_customer(self, customer_id: str, updates: dict[str, Any]) -> bool:
        return self.customer_repo.update_customer(customer_id, updates)

    def delete_customer(self, customer_id: str) -> bool:
        return self.customer_repo.delete_customer(customer_id)

    def claim_data_export(self, customer_id: str, now: int, min_interval_seconds: int):
        return self.customer_repo.claim_data_export(customer_id, now, min_interval_seconds)

    def release_data_export_claim(self, customer_id: str, claimed_at: int, previous: int | None) -> bool:
        return self.customer_repo.release_data_export_claim(customer_id, claimed_at, previous)

    def clear_data_export(self, customer_id: str) -> bool:
        return self.customer_repo.clear_data_export(customer_id)

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

    # Offer images (S3): see services/image_store.py
    def upload_image_to_s3(self, file_content: bytes, file_name: str, offer_id: int) -> str | None:
        return self.images.upload(file_content, file_name, offer_id)

    def get_presigned_url(self, s3_url: str, expiration: int = 3600) -> str | None:
        return self.images.presigned_url(s3_url, expiration)

    # The delivery and labeling workflows: which suppliers and offers have boxes or orders in a status. The offers
    # are read once (the cached list) and the suppliers once, instead of one read per offer and per supplier name.
    def _offers_with_ids(self, offer_ids: set) -> list[Offer]:
        return [offer for offer in self.list_offers() if offer.offer_id in offer_ids]

    def _suppliers_of(self, offers: list[Offer]) -> list[Supplier]:
        names = {offer.supplier_name.strip() for offer in offers if offer.supplier_name}
        return [supplier for supplier in self.list_suppliers() if supplier.name in names]

    def _offer_ids_with_boxes_in(self, box_status: str) -> set:
        return {box.offer_id for box in self.box_repo.get_boxes_by_status(box_status)}

    def _offer_ids_with_orders_in(self, order_status: str) -> set:
        return {order.offer_id for order in self.order_repo.get_orders_by_status(order_status)}

    def get_suppliers_with_boxes_by_status(self, box_status: str) -> list[Supplier]:
        """Get suppliers that have boxes with specified status"""
        try:
            return self._suppliers_of(self._offers_with_ids(self._offer_ids_with_boxes_in(box_status)))
        except Exception as e:
            logger.error(f"Error getting suppliers with {box_status} boxes: {e}")
            return []

    def get_offers_by_supplier_and_box_status(self, supplier_name: str, box_status: str) -> list[Offer]:
        """Get offers for a supplier that have boxes with specified status"""
        try:
            offers = self._offers_with_ids(self._offer_ids_with_boxes_in(box_status))
            return [offer for offer in offers if offer.supplier_name == supplier_name]
        except Exception as e:
            logger.error(f"Error getting {box_status} offers by supplier: {e}")
            return []

    def get_suppliers_with_ordered_offers(self) -> list[Supplier]:
        """Get suppliers that have boxes with ORDERED status"""
        return self.get_suppliers_with_boxes_by_status(BoxStatus.ORDERED.value)

    def get_ordered_offers_by_supplier(self, supplier_name: str) -> list[Offer]:
        """Get offers for a supplier that have boxes with ORDERED status"""
        return self.get_offers_by_supplier_and_box_status(supplier_name, BoxStatus.ORDERED.value)

    def get_boxes_by_offer_with_orders(self, offer_id: int) -> list[Box]:
        """Get boxes for an offer that have orders"""
        return self.get_boxes_by_offer_with_order_status(offer_id, None)

    def get_suppliers_with_ready_for_labeling_offers(self) -> list[Supplier]:
        """Get suppliers that have orders with READY_FOR_LABELING status"""
        return self.get_suppliers_with_orders_by_status(OrderStatus.READY_FOR_LABELING.value)

    def get_ready_for_labeling_offers_by_supplier(self, supplier_name: str) -> list[Offer]:
        """Get offers for a supplier that have orders with READY_FOR_LABELING status"""
        return self.get_offers_by_supplier_and_order_status(supplier_name, OrderStatus.READY_FOR_LABELING.value)

    def get_boxes_by_offer_with_ready_orders(self, offer_id: int) -> list[Box]:
        """Get boxes for an offer that have orders with READY_FOR_LABELING status"""
        return self.get_boxes_by_offer_with_order_status(offer_id, OrderStatus.READY_FOR_LABELING.value)

    def get_suppliers_with_orders_by_status(self, order_status: str) -> list[Supplier]:
        """Get suppliers that have orders with specified status"""
        try:
            return self._suppliers_of(self._offers_with_ids(self._offer_ids_with_orders_in(order_status)))
        except Exception as e:
            logger.error(f"Error getting suppliers with {order_status} orders: {e}")
            return []

    def get_offers_by_supplier_and_order_status(self, supplier_name: str, order_status: str) -> list[Offer]:
        """Get offers for a supplier that have orders with specified status"""
        try:
            offers = self._offers_with_ids(self._offer_ids_with_orders_in(order_status))
            return [offer for offer in offers if offer.supplier_name == supplier_name]
        except Exception as e:
            logger.error(f"Error getting {order_status} offers by supplier: {e}")
            return []

    def get_boxes_by_offer_with_order_status(self, offer_id: int, order_status: str | None) -> list[Box]:
        """Get boxes for an offer that have orders with specified status (None: any order)

        The orders of the offer are read once (offer-index), not per box: an order is always in a box of its own offer.
        """
        try:
            box_ids = {
                o.box_id for o in self.get_orders_by_offer(offer_id) if order_status is None or o.status == order_status
            }
            return [box for box in self.get_boxes_by_offer(offer_id) if box.box_id in box_ids]
        except Exception as e:
            logger.error(f"Error getting boxes with {order_status} orders: {e}")
            return []

    def delete_offer(self, offer_id: int) -> bool:
        return self.offer_repo.delete_offer(offer_id)

    def delete_offer_images(self, offer_id: int) -> bool:
        return self.images.delete_offer_images(offer_id)

    # Order history (purchase analytics) operations
    def create_order_history(self, history) -> bool:
        return self.order_history_repo.create_order_history(history)

    def get_events_by_type(
        self,
        event_type: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        strict: bool = False,
    ) -> list:
        return self.order_history_repo.get_events_by_type(event_type, start_date, end_date, strict=strict)

    def get_order_history_by_customer(
        self, customer_id: str, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> list:
        return self.order_history_repo.get_events_by_customer(customer_id, start_date, end_date)

    # Transaction methods for sensitive order operations
    def cancel_order(self, order_id: str, admin_id: int, reason: str) -> bool:
        """Cancel an order (inventory correction handled by the status update). False when there is no such order."""
        return self.update_order(order_id, {"status": OrderStatus.CANCELLED.value}, admin_id, reason)

    def mark_order_paid(self, order_id: str, admin_id: int) -> bool:
        """Mark an order as paid (records a PAYMENT_RECEIVED analytics event)."""
        return self.update_order(order_id, {"status": OrderStatus.COMPLETED.value}, admin_id, "Payment received")

    # Credit system operations
    def create_customer_credit(self, credit) -> bool:
        return self.credit_repo.create_customer_credit(credit)

    def get_customer_credit(self, customer_id: str, strict: bool = False):
        return self.credit_repo.get_customer_credit(customer_id, strict=strict)

    def update_customer_credit(self, customer_id: str, updates: dict[str, Any]) -> bool:
        return self.credit_repo.update_customer_credit(customer_id, updates)

    def record_credit_change(self, transaction, issued_delta, used_delta, now: str, order_credits=None) -> bool:
        """The transaction, its balance change and the credit of the orders it is used for, in one write (see
        CreditRepository.record_change)"""
        return self.credit_repo.record_change(transaction, issued_delta, used_delta, now, order_credits)

    def create_credit_transaction(self, transaction) -> bool:
        return self.credit_repo.create_credit_transaction(transaction)

    def get_credit_transactions_by_customer(self, customer_id: str, limit: int = 50) -> list:
        return self.credit_repo.get_credit_transactions_by_customer(customer_id, limit)

    def get_all_credit_transactions_by_customer(self, customer_id: str) -> list:
        return self.credit_repo.get_all_credit_transactions_by_customer(customer_id)

    def get_customers_with_credit_balance(self, min_amount=None) -> list:
        return self.credit_repo.get_customers_with_credit_balance(min_amount)

    # Payment link operations
    def store_payment_link(self, payment_url: str) -> bool:
        """Store payment link in counters table"""
        return self.system_repo.store_payment_link(payment_url)

    def get_payment_link(self) -> str | None:
        """Get stored payment link from counters table"""
        return self.system_repo.get_payment_link()
