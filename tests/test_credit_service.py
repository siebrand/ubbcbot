"""
Tests for credit service core logic
"""
import pytest
from decimal import Decimal
from datetime import datetime, UTC
from services.credit_service import CreditService
from models.entities import CustomerCredit, CreditTransaction


@pytest.fixture
def credit_service(mocker):
    """Create credit service with mocked database"""
    mock_db = mocker.Mock()
    return CreditService(mock_db)


class TestGetCustomerCreditBalance:
    """Test getting customer credit balance"""
    
    def test_get_balance_existing_credit(self, credit_service, mocker):
        """Test getting balance for customer with existing credit"""
        customer_id = "test-customer-123"
        expected_credit = CustomerCredit(
            customer_id=customer_id,
            current_balance=Decimal('50.00')
        )
        
        credit_service.db.get_customer_credit = mocker.Mock(return_value=expected_credit)
        
        balance = credit_service.get_customer_credit_balance(customer_id)
        
        assert balance == Decimal('50.00')
        credit_service.db.get_customer_credit.assert_called_once_with(customer_id)
    
    def test_get_balance_no_credit_returns_zero(self, credit_service, mocker):
        """Test getting balance for customer with no credit returns 0"""
        customer_id = "test-customer-456"
        
        credit_service.db.get_customer_credit = mocker.Mock(return_value=None)
        
        balance = credit_service.get_customer_credit_balance(customer_id)
        
        assert balance == Decimal('0.0')
        credit_service.db.get_customer_credit.assert_called_once_with(customer_id)


class TestCreateCreditTransaction:
    """Test creating credit transactions"""
    
    def test_create_transaction_success(self, credit_service, mocker):
        """Test successfully creating a credit transaction"""
        transaction = CreditTransaction(
            customer_id="test-customer-123",
            transaction_type="CREDIT_ISSUED",
            amount=Decimal('20.00'),
            balance_before=Decimal('30.00'),
            balance_after=Decimal('50.00'),
            reason="Test credit",
            created_by=123456789
        )
        
        credit_service.db.create_credit_transaction = mocker.Mock(return_value=True)
        
        result = credit_service.create_credit_transaction(transaction)
        
        assert result is True
        credit_service.db.create_credit_transaction.assert_called_once_with(transaction)
    
    def test_create_transaction_failure(self, credit_service, mocker):
        """Test handling transaction creation failure"""
        transaction = CreditTransaction(
            customer_id="test-customer-123",
            transaction_type="CREDIT_ISSUED",
            amount=Decimal('20.00')
        )
        
        credit_service.db.create_credit_transaction = mocker.Mock(return_value=False)
        
        result = credit_service.create_credit_transaction(transaction)
        
        assert result is False


class TestUpdateCustomerCreditBalance:
    """Test updating customer credit balance"""
    
    def test_update_balance_existing_customer(self, credit_service, mocker):
        """Test updating balance for existing customer"""
        customer_id = "test-customer-123"
        new_balance = Decimal('75.00')
        
        existing_credit = CustomerCredit(
            customer_id=customer_id,
            current_balance=Decimal('50.00'),
            total_credits_issued=Decimal('100.00'),
            total_credits_used=Decimal('50.00')
        )
        
        credit_service.db.get_customer_credit = mocker.Mock(return_value=existing_credit)
        credit_service.db.update_customer_credit = mocker.Mock(return_value=True)
        
        result = credit_service._update_customer_credit_balance(customer_id, new_balance)
        
        assert result is True
        credit_service.db.update_customer_credit.assert_called_once()
        
        # Verify update includes new balance and timestamp
        call_args = credit_service.db.update_customer_credit.call_args
        assert call_args[0][0] == customer_id
        assert call_args[0][1]['current_balance'] == new_balance
        assert 'last_updated' in call_args[0][1]
    
    def test_update_balance_new_customer_creates_record(self, credit_service, mocker):
        """Test updating balance for new customer creates credit record"""
        customer_id = "test-customer-new"
        new_balance = Decimal('25.00')
        
        credit_service.db.get_customer_credit = mocker.Mock(return_value=None)
        credit_service.db.create_customer_credit = mocker.Mock(return_value=True)
        
        result = credit_service._update_customer_credit_balance(customer_id, new_balance)
        
        assert result is True
        credit_service.db.create_customer_credit.assert_called_once()
        
        # Verify created credit has correct balance
        call_args = credit_service.db.create_customer_credit.call_args
        created_credit = call_args[0][0]
        assert created_credit.customer_id == customer_id
        assert created_credit.current_balance == new_balance
    
    def test_update_balance_updates_totals_on_credit(self, credit_service, mocker):
        """Test that updating balance also updates total_credits_issued when adding credit"""
        customer_id = "test-customer-123"
        old_balance = Decimal('50.00')
        new_balance = Decimal('70.00')  # Adding 20
        
        existing_credit = CustomerCredit(
            customer_id=customer_id,
            current_balance=old_balance,
            total_credits_issued=Decimal('100.00'),
            total_credits_used=Decimal('50.00')
        )
        
        credit_service.db.get_customer_credit = mocker.Mock(return_value=existing_credit)
        credit_service.db.update_customer_credit = mocker.Mock(return_value=True)
        
        credit_service._update_customer_credit_balance(customer_id, new_balance, is_credit=True)
        
        # Verify total_credits_issued was updated
        call_args = credit_service.db.update_customer_credit.call_args
        updates = call_args[0][1]
        assert updates['total_credits_issued'] == Decimal('120.00')  # 100 + 20
    
    def test_update_balance_updates_totals_on_usage(self, credit_service, mocker):
        """Test that updating balance also updates total_credits_used when using credit"""
        customer_id = "test-customer-123"
        old_balance = Decimal('50.00')
        new_balance = Decimal('30.00')  # Using 20
        
        existing_credit = CustomerCredit(
            customer_id=customer_id,
            current_balance=old_balance,
            total_credits_issued=Decimal('100.00'),
            total_credits_used=Decimal('50.00')
        )
        
        credit_service.db.get_customer_credit = mocker.Mock(return_value=existing_credit)
        credit_service.db.update_customer_credit = mocker.Mock(return_value=True)
        
        credit_service._update_customer_credit_balance(customer_id, new_balance, is_credit=False)
        
        # Verify total_credits_used was updated
        call_args = credit_service.db.update_customer_credit.call_args
        updates = call_args[0][1]
        assert updates['total_credits_used'] == Decimal('70.00')  # 50 + 20


class TestIssueCredit:
    """Test issuing credit to customers"""
    
    def test_issue_credit_valid_amount(self, credit_service, mocker):
        """Test issuing credit with valid amount"""
        customer_id = "test-customer-123"
        amount = Decimal('20.00')
        reason = "Defective product"
        admin_id = 123456789
        
        # Mock existing balance
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=Decimal('30.00'))
        credit_service._update_customer_credit_balance = mocker.Mock(return_value=True)
        credit_service.create_credit_transaction = mocker.Mock(return_value=True)
        
        result = credit_service.issue_credit(customer_id, amount, reason, admin_id)
        
        assert result is True
        
        # Verify balance was updated
        credit_service._update_customer_credit_balance.assert_called_once_with(
            customer_id, Decimal('50.00'), is_credit=True
        )
        
        # Verify transaction was created
        credit_service.create_credit_transaction.assert_called_once()
        transaction = credit_service.create_credit_transaction.call_args[0][0]
        assert transaction.customer_id == customer_id
        assert transaction.transaction_type == "CREDIT_ISSUED"
        assert transaction.amount == amount
        assert transaction.balance_before == Decimal('30.00')
        assert transaction.balance_after == Decimal('50.00')
        assert transaction.reason == reason
        assert transaction.created_by == admin_id
    
    def test_issue_credit_invalid_amount_zero(self, credit_service):
        """Test issuing credit with zero amount fails"""
        result = credit_service.issue_credit("customer-123", Decimal('0.00'), "Test", 123)
        assert result is False
    
    def test_issue_credit_negative_amount_with_reason_succeeds(self, credit_service, mocker):
        """Test issuing negative credit (debt) with reason succeeds"""
        customer_id = "customer-123"
        amount = Decimal('-10.00')
        reason = "Damaged product charge"
        admin_id = 123
        
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=Decimal('0.00'))
        credit_service._update_customer_credit_balance = mocker.Mock(return_value=True)
        credit_service.create_credit_transaction = mocker.Mock(return_value=True)
        
        result = credit_service.issue_credit(customer_id, amount, reason, admin_id)
        assert result is True
    
    def test_issue_credit_empty_reason(self, credit_service):
        """Test issuing credit with empty reason fails"""
        result = credit_service.issue_credit("customer-123", Decimal('10.00'), "", 123)
        assert result is False
    
    def test_issue_credit_transaction_failure_rollback(self, credit_service, mocker):
        """Test that balance update is not committed if transaction creation fails"""
        customer_id = "test-customer-123"
        amount = Decimal('20.00')
        
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=Decimal('30.00'))
        credit_service._update_customer_credit_balance = mocker.Mock(return_value=True)
        credit_service.create_credit_transaction = mocker.Mock(return_value=False)
        
        result = credit_service.issue_credit(customer_id, amount, "Test", 123)
        
        # Should fail if transaction creation fails
        assert result is False


class TestApplyCreditToDelivery:
    """Test applying credit to delivery"""
    
    def test_apply_credit_less_than_total(self, credit_service, mocker):
        """Test applying credit when credit < delivery total"""
        customer_id = "test-customer-123"
        delivery_total = Decimal('50.00')
        credit_balance = Decimal('20.00')
        
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=credit_balance)
        credit_service.create_credit_transaction = mocker.Mock(return_value=True)
        credit_service._update_customer_credit_balance = mocker.Mock(return_value=True)
        
        result = credit_service.apply_credit_to_delivery(customer_id, delivery_total)
        
        assert result['original_total'] == delivery_total
        assert result['credit_applied'] == Decimal('20.00')
        assert result['payment_required'] == Decimal('30.00')
        assert result['remaining_credit'] == Decimal('0.0')
    
    def test_apply_credit_greater_than_total(self, credit_service, mocker):
        """Test applying credit when credit > delivery total"""
        customer_id = "test-customer-123"
        delivery_total = Decimal('30.00')
        credit_balance = Decimal('50.00')
        
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=credit_balance)
        credit_service.create_credit_transaction = mocker.Mock(return_value=True)
        credit_service._update_customer_credit_balance = mocker.Mock(return_value=True)
        
        result = credit_service.apply_credit_to_delivery(customer_id, delivery_total)
        
        assert result['original_total'] == delivery_total
        assert result['credit_applied'] == Decimal('30.00')
        assert result['payment_required'] == Decimal('0.0')
        assert result['remaining_credit'] == Decimal('20.00')
    
    def test_apply_credit_equal_to_total(self, credit_service, mocker):
        """Test applying credit when credit = delivery total"""
        customer_id = "test-customer-123"
        delivery_total = Decimal('50.00')
        credit_balance = Decimal('50.00')
        
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=credit_balance)
        credit_service.create_credit_transaction = mocker.Mock(return_value=True)
        credit_service._update_customer_credit_balance = mocker.Mock(return_value=True)
        
        result = credit_service.apply_credit_to_delivery(customer_id, delivery_total)
        
        assert result['original_total'] == delivery_total
        assert result['credit_applied'] == Decimal('50.00')
        assert result['payment_required'] == Decimal('0.0')
        assert result['remaining_credit'] == Decimal('0.0')
    
    def test_apply_credit_zero_balance(self, credit_service, mocker):
        """Test applying credit when customer has no credit"""
        customer_id = "test-customer-123"
        delivery_total = Decimal('50.00')
        
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=Decimal('0.0'))
        
        result = credit_service.apply_credit_to_delivery(customer_id, delivery_total)
        
        assert result['original_total'] == delivery_total
        assert result['credit_applied'] == Decimal('0.0')
        assert result['payment_required'] == delivery_total
        assert result['remaining_credit'] == Decimal('0.0')
    
    def test_apply_credit_creates_transaction(self, credit_service, mocker):
        """Test that applying credit creates APPLIED transaction"""
        customer_id = "test-customer-123"
        delivery_total = Decimal('50.00')
        credit_balance = Decimal('30.00')
        
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=credit_balance)
        credit_service.create_credit_transaction = mocker.Mock(return_value=True)
        credit_service._update_customer_credit_balance = mocker.Mock(return_value=True)
        
        credit_service.apply_credit_to_delivery(customer_id, delivery_total)
        
        # Verify transaction was created
        credit_service.create_credit_transaction.assert_called_once()
        transaction = credit_service.create_credit_transaction.call_args[0][0]
        assert transaction.transaction_type == "APPLIED"
        assert transaction.amount == Decimal('-30.00')  # Negative for usage
        assert transaction.balance_before == credit_balance
        assert transaction.balance_after == Decimal('0.0')
    
    def test_apply_credit_updates_balance(self, credit_service, mocker):
        """Test that applying credit updates customer balance"""
        customer_id = "test-customer-123"
        delivery_total = Decimal('50.00')
        credit_balance = Decimal('30.00')
        
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=credit_balance)
        credit_service.create_credit_transaction = mocker.Mock(return_value=True)
        credit_service._update_customer_credit_balance = mocker.Mock(return_value=True)
        
        credit_service.apply_credit_to_delivery(customer_id, delivery_total)
        
        # Verify balance was updated
        credit_service._update_customer_credit_balance.assert_called_once_with(
            customer_id, Decimal('0.0'), is_credit=False
        )
    
    def test_apply_credit_negative_balance_adds_charge(self, credit_service, mocker):
        """Test applying negative balance adds charge to delivery total"""
        customer_id = "test-customer-123"
        delivery_total = Decimal('50.00')
        negative_balance = Decimal('-20.00')
        
        credit_service.get_customer_credit_balance = mocker.Mock(return_value=negative_balance)
        credit_service.create_credit_transaction = mocker.Mock(return_value=True)
        credit_service._update_customer_credit_balance = mocker.Mock(return_value=True)
        
        result = credit_service.apply_credit_to_delivery(customer_id, delivery_total)
        
        assert result['original_total'] == delivery_total
        assert result['credit_applied'] == Decimal('-20.00')  # Negative
        assert result['payment_required'] == Decimal('70.00')  # 50 + 20
        assert result['remaining_credit'] == Decimal('0.0')
        
        # Verify transaction created with negative amount
        transaction = credit_service.create_credit_transaction.call_args[0][0]
        assert transaction.amount == Decimal('-20.00')
        assert transaction.balance_before == Decimal('-20.00')
        assert transaction.balance_after == Decimal('0.0')
