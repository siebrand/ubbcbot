"""
Credit Service - Core credit system business logic
"""
from decimal import Decimal
from datetime import datetime, UTC
from typing import Optional
from models.entities import CustomerCredit, CreditTransaction


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
        return credit.current_balance if credit else Decimal('0.0')
    
    def create_credit_transaction(self, transaction: CreditTransaction) -> bool:
        """Create a credit transaction record"""
        return self.db.create_credit_transaction(transaction)
    
    def _update_customer_credit_balance(self, customer_id: str, new_balance: Decimal, 
                                       is_credit: bool = True) -> bool:
        """
        Update customer credit balance and totals
        
        Args:
            customer_id: Customer ID
            new_balance: New balance to set
            is_credit: True if adding credit, False if using credit
        
        Returns:
            True if successful, False otherwise
        """
        existing_credit = self.db.get_customer_credit(customer_id)
        
        if existing_credit:
            # Calculate change amount
            change = new_balance - existing_credit.current_balance
            
            # Update existing credit
            updates = {
                'current_balance': new_balance,
                'last_updated': datetime.now(UTC)
            }
            
            # Update totals based on whether adding or using credit
            if is_credit and change > 0:
                updates['total_credits_issued'] = existing_credit.total_credits_issued + change
            elif not is_credit and change < 0:
                updates['total_credits_used'] = existing_credit.total_credits_used + abs(change)
            
            return self.db.update_customer_credit(customer_id, updates)
        else:
            # Create new credit record
            new_credit = CustomerCredit(
                customer_id=customer_id,
                current_balance=new_balance,
                total_credits_issued=new_balance if is_credit else Decimal('0.0'),
                total_credits_used=Decimal('0.0')
            )
            return self.db.create_customer_credit(new_credit)
    
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
        # Validate reason is required for negative amounts
        if amount < 0 and (not reason or not reason.strip()):
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
            created_by=admin_id
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
                balance_after=Decimal('0.0'),
                reason="Applied to delivery (negative balance charge)",
                created_by=0
            )
            
            self.create_credit_transaction(transaction)
            self._update_customer_credit_balance(customer_id, Decimal('0.0'), is_credit=False)
            
            return {
                'original_total': delivery_total,
                'credit_applied': credit_balance,  # Negative value
                'payment_required': payment_required,
                'remaining_credit': Decimal('0.0')
            }
        
        # Handle zero balance
        if credit_balance == 0:
            return {
                'original_total': delivery_total,
                'credit_applied': Decimal('0.0'),
                'payment_required': delivery_total,
                'remaining_credit': Decimal('0.0')
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
            created_by=0  # System operation
        )
        
        self.create_credit_transaction(transaction)
        self._update_customer_credit_balance(customer_id, remaining_credit, is_credit=False)
        
        return {
            'original_total': delivery_total,
            'credit_applied': credit_to_apply,
            'payment_required': payment_required,
            'remaining_credit': remaining_credit
        }
