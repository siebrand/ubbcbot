import logging

from models.entities import OrderHistory, OrderStatus

logger = logging.getLogger()


class PurchaseEvents:
    """Records purchase analytics events (order placed / payment received).

    Only two event types are written, both carrying a euro ``amount``:
      - ORDER_CREATED    — when an order is placed (timing of demand)
      - PAYMENT_RECEIVED — when an order is paid (realized spend)

    No personal data is stored; the customer is referenced only by the
    pseudonymous ``customer_id`` (names are resolved from the customers table
    at report time). Cancellations, price changes and other status transitions
    are intentionally NOT recorded here — this is an analytics event store, not
    an audit trail.

    Built on the repositories, not on the database facade, so the facade can own it without a circular dependency.
    """

    def __init__(self, order_history_repo, offer_repo):
        self.order_history_repo = order_history_repo
        self.offer_repo = offer_repo

    @staticmethod
    def is_payment(old_status: str, new_status: str) -> bool:
        """An order is paid when it goes from awaiting_payment to completed; no other change is an event"""
        return old_status == OrderStatus.AWAITING_PAYMENT.value and new_status == OrderStatus.COMPLETED.value

    def order_created(self, order) -> None:
        """Record that an order was placed. Amount is the ordered value."""
        self.order_history_repo.create_order_history(self._event(order, "ORDER_CREATED"))
        logger.info(f"Analytics: order created {order.order_id}")

    def payment_received(self, order) -> None:
        """Record that an order was paid. Amount is the paid value."""
        self.order_history_repo.create_order_history(self._event(order, "PAYMENT_RECEIVED"))
        logger.info(f"Analytics: payment received {order.order_id} - amount {order.total_price}")

    def payments_received(self, orders: list) -> None:
        """Record that these orders were paid, in one batch write"""
        if not orders:
            return
        created_count = self.order_history_repo.batch_create_order_history(
            [self._event(order, "PAYMENT_RECEIVED") for order in orders]
        )
        logger.info(f"Analytics: batch payment received - {created_count} orders")

    def _event(self, order, event_type: str) -> OrderHistory:
        return OrderHistory(
            customer_id=order.customer_id,
            offer_name=self._offer_name(order.offer_id),
            event_type=event_type,
            amount=order.total_price,
        )

    def _offer_name(self, offer_id: int) -> str:
        """The offer name is denormalized into the event (a product is not personal data)"""
        offer = self.offer_repo.get_offer(offer_id)
        return offer.name if offer else "Unknown"
