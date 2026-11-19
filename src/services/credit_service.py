"""
Credit Service - Core credit system business logic
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from models.entities import CreditTransaction
from repositories.credit_repository import CreditBalanceChanged

logger = logging.getLogger(__name__)


class CreditService:
    """Service for managing customer credits and transactions"""

    # How often a change is computed again when another write changed the balance in between
    MAX_ATTEMPTS = 3

    def __init__(self, db_service):
        """Initialize credit service with database service"""
        self.db = db_service

    def get_customer_credit_balance(self, customer_id: str) -> Decimal:
        """
        Get customer's current credit balance
        Returns Decimal('0.0') if customer has no credit record
        """
        credit = self.db.get_customer_credit(customer_id)
        return credit.current_balance if credit else Decimal("0.0")

    def _change_balance(
        self, customer_id: str, make_transaction: Callable[[Decimal], CreditTransaction | None], is_credit: bool
    ) -> CreditTransaction | None:
        """Read the balance, let make_transaction say what changes, and write the transaction and the new balance
        in one write that only succeeds when the balance is still the one that was read. When another write came
        in between, read again (MAX_ATTEMPTS times).

        Returns the written transaction; None when make_transaction wants no change or the write failed.
        """
        for _ in range(self.MAX_ATTEMPTS):
            transaction = make_transaction(self.get_customer_credit_balance(customer_id))
            if transaction is None:
                return None

            delta = transaction.balance_after - transaction.balance_before
            issued_delta = delta if is_credit and delta > 0 else Decimal("0.0")
            used_delta = -delta if not is_credit and delta < 0 else Decimal("0.0")
            try:
                written = self.db.record_credit_change(
                    transaction, issued_delta, used_delta, datetime.now(UTC).isoformat()
                )
            except CreditBalanceChanged:
                continue
            return transaction if written else None

        logger.error(f"Credit balance of {customer_id} kept changing; gave up after {self.MAX_ATTEMPTS} attempts")
        return None

    def issue_credit(self, customer_id: str, amount: Decimal, reason: str, admin_id: int) -> bool:
        """Issue credit to customer

        Args:
            customer_id: Customer ID
            amount: Credit amount (positive adds credit, negative creates debt)
            reason: Reason for credit (required for negative amounts)
            admin_id: Admin user ID issuing the credit

        Returns:
            True if successful, False otherwise
        """
        # Validate amount
        if not amount.is_finite() or amount == 0:
            return False

        # A debt needs a reason; a credit may go without
        if amount < 0 and not (reason and reason.strip()):
            return False

        def credit_issued(balance: Decimal) -> CreditTransaction:
            return CreditTransaction(
                customer_id=customer_id,
                transaction_type="CREDIT_ISSUED",
                amount=amount,
                balance_before=balance,
                balance_after=balance + amount,
                reason=reason.strip() if reason else "Credit issued",
                created_by=admin_id,
            )

        return self._change_balance(customer_id, credit_issued, is_credit=amount > 0) is not None

    def apply_credit_to_delivery(self, customer_id: str, delivery_total: Decimal) -> dict:
        """Apply credit when orders transition LABELING_COMPLETED → AWAITING_PAYMENT

        Args:
            customer_id: Customer ID
            delivery_total: Total delivery amount

        Returns:
            Dict with original_total, credit_applied, payment_required, remaining_credit. When the credit could
            not be written, nothing is applied: the full total is to be paid and the balance stays.
        """

        def credit_applied(balance: Decimal) -> CreditTransaction | None:
            if balance == 0:
                return None
            if balance < 0:
                # A negative balance (a debt) is charged with the delivery
                return CreditTransaction(
                    customer_id=customer_id,
                    transaction_type="APPLIED",
                    amount=balance,  # Negative amount (charge)
                    balance_before=balance,
                    balance_after=Decimal("0.0"),
                    reason="Applied to delivery (negative balance charge)",
                    created_by=0,
                )
            credit_to_apply = min(balance, delivery_total)
            return CreditTransaction(
                customer_id=customer_id,
                transaction_type="APPLIED",
                amount=-credit_to_apply,  # Negative for usage
                balance_before=balance,
                balance_after=balance - credit_to_apply,
                reason="Applied to delivery",
                created_by=0,  # System operation
            )

        transaction = self._change_balance(customer_id, credit_applied, is_credit=False)
        if transaction is None:
            return {
                "original_total": delivery_total,
                "credit_applied": Decimal("0.0"),
                "payment_required": delivery_total,
                "remaining_credit": self.get_customer_credit_balance(customer_id),
            }

        # credit_applied is positive for credit used, negative for a debt charged
        applied = -transaction.amount if transaction.balance_before > 0 else transaction.amount
        return {
            "original_total": delivery_total,
            "credit_applied": applied,
            "payment_required": delivery_total - applied,
            "remaining_credit": transaction.balance_after,
        }
