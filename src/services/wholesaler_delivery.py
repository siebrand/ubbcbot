import logging

from models.entities import Order, OrderStatus
from services.box_status_manager import BoxStatusManager
from services.database import DynamoDBService

logger = logging.getLogger(__name__)


class WholesalerDeliveryService:
    def __init__(
        self, db_service: DynamoDBService, box_status_manager: BoxStatusManager, admin_user_id: int = 15005473
    ):
        self.db = db_service
        self.box_status_manager = box_status_manager
        self.admin_user_id = admin_user_id

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
                if is_delayed:
                    self._process_partial_delayed(orders, units_received, missing_units, box_id)
                else:
                    self._process_partial_cancelled(orders, units_received, missing_units, box_id)

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

    def _process_partial_delayed(self, orders: list[Order], units_received: int, missing_units: int, box_id: str):
        """Process partial delivery where missing units are delayed"""
        remaining_to_allocate = units_received

        for order in orders:
            if remaining_to_allocate <= 0:
                # No more units to allocate - mark as delayed
                self.db.update_order(
                    order.order_id,
                    {"received_quantity": 0, "status": OrderStatus.RECEIVED_PARTIAL_DELAYED.value},
                    admin_id=self.admin_user_id,
                    reason="Partial delivery - units delayed",
                )
                self.notify_customer_of_delay(order.order_id)
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
                # Partial fulfillment of this order
                self.db.update_order(
                    order.order_id,
                    {"received_quantity": remaining_to_allocate, "status": OrderStatus.RECEIVED_PARTIAL_DELAYED.value},
                    admin_id=self.admin_user_id,
                    reason="Partial delivery - remaining delayed",
                )
                self.notify_customer_of_delay(order.order_id)
                remaining_to_allocate = 0

        # Update box status to DELIVERED via service
        self.box_status_manager.mark_box_as_delivered(box_id)

    def _process_partial_cancelled(self, orders: list[Order], units_received: int, missing_units: int, box_id: str):
        """Process partial delivery where missing units are cancelled"""
        remaining_to_allocate = units_received

        for order in orders:
            if remaining_to_allocate <= 0:
                # No more units to allocate - cancel entire order
                self.db.cancel_order(order.order_id, self.admin_user_id, "Wholesale delivery - units unavailable")
                self.notify_customer_of_cancellation(order.order_id)
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
                # Partial fulfillment - received units go to labeling, rest cancelled
                self.db.update_order(
                    order.order_id,
                    {"received_quantity": remaining_to_allocate, "status": OrderStatus.READY_FOR_LABELING.value},
                    admin_id=self.admin_user_id,
                    reason="Partial delivery - remaining cancelled",
                )

                # Create new order record for cancelled portion
                cancelled_order = Order(
                    customer_id=order.customer_id,
                    box_id=order.box_id,
                    offer_id=order.offer_id,
                    quantity=order.quantity - remaining_to_allocate,
                    received_quantity=0,
                    unit_price=order.unit_price,
                    total_price=order.unit_price * (order.quantity - remaining_to_allocate),
                    status=OrderStatus.CANCELLED.value,
                    placed_by_admin=order.placed_by_admin,
                )
                self.db.create_order(cancelled_order, admin_id=self.admin_user_id)
                self.notify_customer_of_cancellation(cancelled_order.order_id)
                remaining_to_allocate = 0

        # Update box status to DELIVERED via service
        self.box_status_manager.mark_box_as_delivered(box_id)

    def notify_customer_of_delay(self, order_id: str):
        """Stub method for notifying customer of delay"""
        logger.info(f"STUB: Notifying customer of delay for order {order_id}")

    def notify_customer_of_cancellation(self, order_id: str):
        """Stub method for notifying customer of cancellation"""
        logger.info(f"STUB: Notifying customer of cancellation for order {order_id}")
