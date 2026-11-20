import logging
from collections import defaultdict
from collections.abc import Callable

from config import ADMIN_USER_ID
from models.entities import Order, OrderStatus
from services.box_status_manager import BoxStatusManager
from services.database import DynamoDBService

logger = logging.getLogger(__name__)

# Told to a customer whose units come later ("delayed") or not at all ("cancelled"):
# (customer_id, offer_id, kind, units)
ShortageNotifier = Callable[[str, int, str, int], None]


class WholesalerDeliveryService:
    def __init__(
        self,
        db_service: DynamoDBService,
        box_status_manager: BoxStatusManager,
        admin_user_id: int = ADMIN_USER_ID,
        notify_shortage: ShortageNotifier | None = None,
    ):
        self.db = db_service
        self.box_status_manager = box_status_manager
        self.admin_user_id = admin_user_id
        self.notify_shortage = notify_shortage

    def process_wholesaler_delivery(self, box_id: str, units_received: int, is_delayed: bool) -> bool:
        """
        Process wholesaler delivery and handle discrepancies

        Args:
            box_id: ID of the box being delivered
            units_received: Number of units actually received
            is_delayed: True if missing units will arrive later, False if cancelled

        Returns:
            bool: True if processing successful
        """
        try:
            # Get box and validate
            box = self.db.get_box(box_id)
            if not box:
                return False

            # Get all orders for this box
            orders = [o for o in self._get_orders_by_box(box_id) if o.status == OrderStatus.ORDERED.value]
            if not orders:
                return False

            # Calculate expected vs received
            total_expected = sum(order.quantity for order in orders)

            if units_received == total_expected:
                # Full match - all units received
                self._process_full_delivery(orders, box_id)
            elif units_received < total_expected:
                # Partial delivery
                missing_units = total_expected - units_received
                shortages: dict[tuple[str, int], int] = defaultdict(int)
                if is_delayed:
                    self._process_partial_delayed(orders, units_received, missing_units, box_id, shortages)
                else:
                    self._process_partial_cancelled(orders, units_received, missing_units, box_id, shortages)
                self._tell_customers(shortages, "delayed" if is_delayed else "cancelled")

            return True

        except Exception as e:
            logger.error(f"Error processing wholesaler delivery: {e}")
            return False

    def _get_orders_by_box(self, box_id: str) -> list[Order]:
        """Get all orders for a specific box"""
        return self.db.get_orders_by_box(box_id)

    def _process_full_delivery(self, orders: list[Order], box_id: str):
        """Process full delivery - all units received"""
        for order in orders:
            self.db.update_order(
                order.order_id,
                {"received_quantity": order.quantity, "status": OrderStatus.READY_FOR_LABELING.value},
                admin_id=self.admin_user_id,
                reason="Full wholesale delivery received",
            )

        # Update box status to DELIVERED via service
        self.box_status_manager.mark_box_as_delivered(box_id)

    def _process_partial_delayed(
        self, orders: list[Order], units_received: int, missing_units: int, box_id: str, shortages: dict
    ):
        """Process partial delivery where missing units are delayed.

        The received units go to labeling (and are charged); the delayed ones stay ``ordered``, and so does the box,
        so the next /process_delivery finds them when they arrive.
        """
        remaining_to_allocate = units_received

        for order in orders:
            if remaining_to_allocate <= 0:
                # No more units to allocate: the whole order is delayed and stays ordered
                shortages[(order.customer_id, order.offer_id)] += order.quantity
            elif remaining_to_allocate >= order.quantity:
                # Full order can be fulfilled
                self.db.update_order(
                    order.order_id,
                    {"received_quantity": order.quantity, "status": OrderStatus.READY_FOR_LABELING.value},
                    admin_id=self.admin_user_id,
                    reason="Full delivery received",
                )
                remaining_to_allocate -= order.quantity
            else:
                # Partial fulfillment: the received units go to labeling, the rest is an ordered order of its own
                if self._split(order, remaining_to_allocate, OrderStatus.ORDERED.value):
                    shortages[(order.customer_id, order.offer_id)] += order.quantity - remaining_to_allocate
                remaining_to_allocate = 0

        # The box is delivered once nothing in it is still on its way
        if not any(o.status == OrderStatus.ORDERED.value for o in self._get_orders_by_box(box_id)):
            self.box_status_manager.mark_box_as_delivered(box_id)

    def _split(self, order: Order, received: int, rest_status: str) -> bool:
        """The order keeps its ``received`` units, ready for labeling; the other units become an order of their own
        with ``rest_status``. One transaction, so units are neither lost nor counted twice."""
        rest = Order(
            customer_id=order.customer_id,
            box_id=order.box_id,
            offer_id=order.offer_id,
            quantity=order.quantity - received,
            received_quantity=0,
            unit_price=order.unit_price,
            total_price=order.unit_price * (order.quantity - received),
            status=rest_status,
            placed_by_admin=order.placed_by_admin,
            created_at=order.created_at,
        )
        if self.db.split_order(order, received, OrderStatus.READY_FOR_LABELING.value, rest):
            return True
        logger.error(f"Order {order.order_id} could not be split after a partial delivery")
        return False

    def _process_partial_cancelled(
        self, orders: list[Order], units_received: int, missing_units: int, box_id: str, shortages: dict
    ):
        """Process partial delivery where missing units are cancelled"""
        remaining_to_allocate = units_received

        for order in orders:
            if remaining_to_allocate <= 0:
                # No more units to allocate - cancel entire order
                self.db.cancel_order(order.order_id, self.admin_user_id, "Wholesale delivery - units unavailable")
                shortages[(order.customer_id, order.offer_id)] += order.quantity
            elif remaining_to_allocate >= order.quantity:
                # Full order can be fulfilled
                self.db.update_order(
                    order.order_id,
                    {"received_quantity": order.quantity, "status": OrderStatus.READY_FOR_LABELING.value},
                    admin_id=self.admin_user_id,
                    reason="Full delivery received",
                )
                remaining_to_allocate -= order.quantity
            else:
                # Partial fulfillment - the order shrinks to the received units (so they are delivered and charged),
                # and the rest becomes a cancelled order of its own
                if self._split(order, remaining_to_allocate, OrderStatus.CANCELLED.value):
                    shortages[(order.customer_id, order.offer_id)] += order.quantity - remaining_to_allocate
                remaining_to_allocate = 0

        # Update box status to DELIVERED via service
        self.box_status_manager.mark_box_as_delivered(box_id)

    def _tell_customers(self, shortages: dict[tuple[str, int], int], kind: str) -> None:
        """One message per customer and offer, with all their units that come later or not at all"""
        if not self.notify_shortage:
            return
        for (customer_id, offer_id), units in shortages.items():
            try:
                self.notify_shortage(customer_id, offer_id, kind, units)
            except Exception as e:
                # The delivery is processed: a message that fails must not undo or stop it
                logger.error(f"Telling customer {customer_id} about {kind} units failed: {type(e).__name__}")
