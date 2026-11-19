from handlers.order_list import OrderListMixin
from models.entities import AuthorizationStatus, OrderStatus


class BaseOrderHandler(OrderListMixin):
    """Base class for order-related handlers with shared utilities"""

    def find_orders_by_partial_id(self, partial_id: str, include_cancelled: bool = False) -> list[tuple]:
        """Find orders whose order_id starts with the given short/partial id.

        Scans the orders of all approved customers and returns a list of
        (order, customer) tuples. Cancelled orders are excluded unless
        include_cancelled is True. Shared by /cancel_order and /edit_order so
        the short-id resolution and disambiguation live in one place.
        """
        matches = []
        for customer in self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value):
            for order in self.db.get_orders_by_customer(customer.customer_id):
                if not order.order_id.startswith(partial_id):
                    continue
                if not include_cancelled and order.status == OrderStatus.CANCELLED.value:
                    continue
                matches.append((order, customer))
        return matches
