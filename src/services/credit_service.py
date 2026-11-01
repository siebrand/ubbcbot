"""
Credit Service - Core credit system business logic
"""

from datetime import UTC, datetime
from decimal import Decimal

from models.entities import CreditTransaction


class CreditService:
    """Service for managing customer credits and transactions"""

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

    def create_credit_transaction(self, transaction: CreditTransaction) -> bool:
        """Create a credit transaction record"""
        return self.db.create_credit_transaction(transaction)

    def _update_customer_credit_balance(self, customer_id: str, new_balance: Decimal, is_credit: bool = True) -> bool:
        """Adjust a customer's credit balance and totals atomically.

        The caller computes the intended new_balance from the balance it read; we
        turn that into a delta and apply it with an atomic ADD, so two concurrent
        credit operations accumulate correctly instead of overwriting each other.
        The record is created on first use (ADD starts from 0 on a missing item).

        Args:
            customer_id: Customer ID
            new_balance: Intended new balance (relative to the balance the caller read)
            is_credit: True if adding credit, False if using credit

        Returns:
            True if successful, False otherwise
        """
        existing_credit = self.db.get_customer_credit(customer_id)
        previous_balance = existing_credit.current_balance if existing_credit else Decimal("0.0")

        balance_delta = new_balance - previous_balance

        issued_delta = Decimal("0.0")
        used_delta = Decimal("0.0")
        if is_credit and balance_delta > 0:
            issued_delta = balance_delta
        elif not is_credit and balance_delta < 0:
            used_delta = abs(balance_delta)

        now = datetime.now(UTC).isoformat()
        return self.db.increment_customer_credit(
            customer_id, balance_delta, issued_delta, used_delta, last_updated=now, created_at=now
        )

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
        if amount == 0:
            return False

        # Validate reason is required
        if not reason or not reason.strip():
            return False

        # Get current balance
        current_balance = self.get_customer_credit_balance(customer_id)
        new_balance = current_balance + amount

        # Create transaction record
        transaction = CreditTransaction(
            customer_id=customer_id,
            transaction_type="CREDIT_ISSUED",
            amount=amount,
            balance_before=current_balance,
            balance_after=new_balance,
            reason=reason.strip() if reason else "Credit issued",
            created_by=admin_id,
        )

        # Create transaction first (fail fast if this fails)
        if not self.create_credit_transaction(transaction):
            return False

        # Update balance
        is_credit = amount > 0
        return self._update_customer_credit_balance(customer_id, new_balance, is_credit=is_credit)

    def apply_credit_to_delivery(self, customer_id: str, delivery_total: Decimal) -> dict:
        """Apply credit when orders transition LABELING_COMPLETED → AWAITING_PAYMENT

        Args:
            customer_id: Customer ID
            delivery_total: Total delivery amount

        Returns:
            Dict with original_total, credit_applied, payment_required, remaining_credit
        """
        credit_balance = self.get_customer_credit_balance(customer_id)

        # Handle negative balance (charge customer)
        if credit_balance < 0:
            payment_required = delivery_total + abs(credit_balance)

            # Create APPLIED transaction for negative balance
            transaction = CreditTransaction(
                customer_id=customer_id,
                transaction_type="APPLIED",
                amount=credit_balance,  # Negative amount (charge)
                balance_before=credit_balance,
                balance_after=Decimal("0.0"),
                reason="Applied to delivery (negative balance charge)",
                created_by=0,
            )

            self.create_credit_transaction(transaction)
            self._update_customer_credit_balance(customer_id, Decimal("0.0"), is_credit=False)

            return {
                "original_total": delivery_total,
                "credit_applied": credit_balance,  # Negative value
                "payment_required": payment_required,
                "remaining_credit": Decimal("0.0"),
            }

        # Handle zero balance
        if credit_balance == 0:
            return {
                "original_total": delivery_total,
                "credit_applied": Decimal("0.0"),
                "payment_required": delivery_total,
                "remaining_credit": Decimal("0.0"),
            }

        # Handle positive balance
        credit_to_apply = min(credit_balance, delivery_total)
        payment_required = delivery_total - credit_to_apply
        remaining_credit = credit_balance - credit_to_apply

        # Create APPLIED transaction
        transaction = CreditTransaction(
            customer_id=customer_id,
            transaction_type="APPLIED",
            amount=-credit_to_apply,  # Negative for usage
            balance_before=credit_balance,
            balance_after=remaining_credit,
            reason="Applied to delivery",
            created_by=0,  # System operation
        )

        self.create_credit_transaction(transaction)
        self._update_customer_credit_balance(customer_id, remaining_credit, is_credit=False)

        return {
            "original_total": delivery_total,
            "credit_applied": credit_to_apply,
            "payment_required": payment_required,
            "remaining_credit": remaining_credit,
        }
