import logging
from datetime import datetime

from models.entities import OrderHistory

logger = logging.getLogger()


class AuditService:
    """Records purchase analytics events (order placed / payment received).

    Only two event types are written, both carrying a euro ``amount``:
      - ORDER_CREATED    — when an order is placed (timing of demand)
      - PAYMENT_RECEIVED — when an order is paid (realized spend)

    No personal data is stored; the customer is referenced only by the
    pseudonymous ``customer_id`` (names are resolved from the customers table
    at report time). Cancellations, price changes and other status transitions
    are intentionally NOT recorded here — this is an analytics event store, not
    an audit trail.
    """

    def __init__(self, db):
        self.db = db

    def _get_offer_name(self, offer_id: int) -> str:
        """Get offer name for denormalization (product is not personal data)."""
        offer = self.db.get_offer(offer_id)
        return offer.name if offer else "Unknown"

    def log_order_created(self, order, admin_id: int = 0):
        """Record that an order was placed. Amount is the ordered value."""
        history = OrderHistory(
            customer_id=order.customer_id,
            offer_name=self._get_offer_name(order.offer_id),
            event_type="ORDER_CREATED",
            amount=order.total_price,
        )
        self.db.create_order_history(history)
        logger.info(f"Analytics: order created {order.order_id}")

    def log_payment_received(self, order, admin_id: int = 0):
        """Record that an order was paid. Amount is the paid value."""
        history = OrderHistory(
            customer_id=order.customer_id,
            offer_name=self._get_offer_name(order.offer_id),
            event_type="PAYMENT_RECEIVED",
            amount=order.total_price,
        )
        self.db.create_order_history(history)
        logger.info(f"Analytics: payment received {order.order_id} - amount {order.total_price}")

    def log_payment_if_completed(self, order, old_status: str, new_status: str, admin_id: int = 0):
        """Record a PAYMENT_RECEIVED event only for an awaiting_payment -> completed
        transition. Any other status change is a no-op (not an analytics event)."""
        if old_status == "awaiting_payment" and new_status == "completed":
            self.log_payment_received(order, admin_id)

    def log_batch_payment_if_completed(self, orders: list, old_status: str, new_status: str, admin_id: int = 0):
        """Batch variant of log_payment_if_completed for a group of orders."""
        if not (old_status == "awaiting_payment" and new_status == "completed"):
            return
        histories = [
            OrderHistory(
                customer_id=order.customer_id,
                offer_name=self._get_offer_name(order.offer_id),
                event_type="PAYMENT_RECEIVED",
                amount=order.total_price,
            )
            for order in orders
        ]
        created_count = self.db.order_history_repo.batch_create_order_history(histories)
        logger.info(f"Analytics: batch payment received - {created_count} orders")

    def get_events_by_type(
        self, event_type: str, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> list[OrderHistory]:
        """Get all events of a specific type in a date range (for reporting)."""
        return self.db.get_events_by_type(event_type, start_date, end_date)
