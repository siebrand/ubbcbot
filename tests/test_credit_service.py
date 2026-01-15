"""
Tests for credit service core logic
"""
import pytest
from decimal import Decimal
from datetime import datetime, UTC
from src.services.credit_service import CreditService
from src.models.entities import CustomerCredit, CreditTransaction


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
