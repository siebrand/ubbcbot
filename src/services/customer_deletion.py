"""Customer deletion (right to be forgotten).

Deleting a customer removes the row from the customers table. Orders, credit
transactions and the pseudonymous order history stay: they reference only the
customer_id and are kept for the fiscal retention obligation.

A customer can only be deleted when nothing is outstanding: every order must be
completed (delivered and paid) or cancelled, and the credit balance must be zero.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from models.entities import Customer, Order, OrderStatus

# Orders in these statuses are settled. Everything else is not yet delivered and/or not yet paid.
SETTLED_ORDER_STATUSES = frozenset({OrderStatus.COMPLETED.value, OrderStatus.CANCELLED.value})


@dataclass
class DeletionBlockers:
    open_orders: list[Order] = field(default_factory=list)
    credit_balance: Decimal = Decimal("0.0")

    @property
    def blocked(self) -> bool:
        return bool(self.open_orders) or self.credit_balance != 0


class CustomerDeletionService:
    def __init__(self, db):
        self.db = db

    def get_blockers(self, customer: Customer) -> DeletionBlockers:
        """Return what prevents deleting this customer (empty blockers means deletion is allowed)"""
        orders = self.db.get_orders_by_customer(customer.customer_id)
        open_orders = [o for o in orders if o.status not in SETTLED_ORDER_STATUSES]

        credit = self.db.get_customer_credit(customer.customer_id)
        balance = Decimal(str(credit.current_balance)) if credit else Decimal("0.0")

        return DeletionBlockers(open_orders=open_orders, credit_balance=balance)

    def delete(self, customer: Customer) -> tuple[bool, DeletionBlockers]:
        """Delete the customer unless blocked. Returns (deleted, blockers)."""
        blockers = self.get_blockers(customer)
        if blockers.blocked:
            return False, blockers
        return self.db.delete_customer(customer.customer_id), blockers
