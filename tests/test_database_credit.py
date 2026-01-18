"""
Tests for credit system database operations
"""
import pytest
from decimal import Decimal
from datetime import datetime, UTC
from models.entities import CustomerCredit, CreditTransaction
from services.database import DynamoDBService


@pytest.fixture
def db_service(dynamodb):
    """Create database service instance"""
    return DynamoDBService()


@pytest.fixture
def sample_customer_credit():
    """Create sample customer credit"""
    return CustomerCredit(
        customer_id="test-customer-123",
        current_balance=Decimal('50.00'),
        total_credits_issued=Decimal('100.00'),
        total_credits_used=Decimal('50.00')
    )


@pytest.fixture
def sample_credit_transaction():
    """Create sample credit transaction"""
    return CreditTransaction(
        customer_id="test-customer-123",
        transaction_type="CREDIT_ISSUED",
        amount=Decimal('20.00'),
        balance_before=Decimal('30.00'),
        balance_after=Decimal('50.00'),
        reason="Test credit",
        created_by=123456789
    )


class TestCustomerCreditOperations:
    """Test customer credit CRUD operations"""
    
    def test_create_customer_credit(self, db_service, sample_customer_credit):
        """Test creating a new customer credit record"""
        result = db_service.create_customer_credit(sample_customer_credit)
        assert result is True
        
    def test_get_customer_credit_exists(self, db_service, sample_customer_credit):
        """Test retrieving existing customer credit"""
        db_service.create_customer_credit(sample_customer_credit)
        credit = db_service.get_customer_credit(sample_customer_credit.customer_id)
        
        assert credit is not None
        assert credit.customer_id == sample_customer_credit.customer_id
        assert credit.current_balance == Decimal('50.00')
        assert credit.total_credits_issued == Decimal('100.00')
        assert credit.total_credits_used == Decimal('50.00')
        
    def test_get_customer_credit_not_exists(self, db_service):
        """Test retrieving non-existent customer credit returns None"""
        credit = db_service.get_customer_credit("non-existent-customer")
        assert credit is None
        
    def test_update_customer_credit(self, db_service, sample_customer_credit):
        """Test updating customer credit balance"""
        db_service.create_customer_credit(sample_customer_credit)
        
        updates = {
            'current_balance': Decimal('75.00'),
            'total_credits_issued': Decimal('125.00'),
            'last_updated': datetime.now(UTC)
        }
        
        result = db_service.update_customer_credit(
            sample_customer_credit.customer_id,
            updates
        )
        assert result is True
        
        # Verify update
        credit = db_service.get_customer_credit(sample_customer_credit.customer_id)
        assert credit.current_balance == Decimal('75.00')
        assert credit.total_credits_issued == Decimal('125.00')


class TestCreditTransactionOperations:
    """Test credit transaction CRUD operations"""
    
    def test_create_credit_transaction(self, db_service, sample_credit_transaction):
        """Test creating a new credit transaction"""
        result = db_service.create_credit_transaction(sample_credit_transaction)
        assert result is True
        
    def test_get_credit_transactions_by_customer(self, db_service):
        """Test retrieving credit transactions for a customer"""
        # Create multiple transactions
        customer_id = "test-customer-456"
        
        for i in range(3):
            transaction = CreditTransaction(
                customer_id=customer_id,
                transaction_type="CREDIT_ISSUED",
                amount=Decimal(f'{(i+1)*10}.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal(f'{(i+1)*10}.00'),
                reason=f"Test credit {i+1}",
                created_by=123456789
            )
            db_service.create_credit_transaction(transaction)
        
        # Retrieve transactions
        transactions = db_service.get_credit_transactions_by_customer(customer_id)
        
        assert len(transactions) == 3
        assert all(t.customer_id == customer_id for t in transactions)
        
    def test_get_credit_transactions_empty(self, db_service):
        """Test retrieving transactions for customer with no transactions"""
        transactions = db_service.get_credit_transactions_by_customer("no-transactions")
        assert transactions == []


class TestCustomerCreditQueries:
    """Test customer credit query operations"""
    
    def test_get_customers_with_credit_balance(self, db_service):
        """Test retrieving all customers with credit balance"""
        # Create customers with credits
        customers = [
            CustomerCredit(customer_id=f"customer-{i}", current_balance=Decimal(f'{i*10}.00'))
            for i in range(1, 4)
        ]
        
        for customer in customers:
            db_service.create_customer_credit(customer)
        
        # Retrieve customers with credit
        results = db_service.get_customers_with_credit_balance(min_amount=Decimal('0.01'))
        
        assert len(results) >= 3
        assert all(c.current_balance > Decimal('0.00') for c in results)
        
    def test_get_customers_with_credit_min_amount_filter(self, db_service):
        """Test filtering customers by minimum credit amount"""
        # Create customers with varying balances
        customers = [
            CustomerCredit(customer_id="customer-low", current_balance=Decimal('5.00')),
            CustomerCredit(customer_id="customer-high", current_balance=Decimal('50.00'))
        ]
        
        for customer in customers:
            db_service.create_customer_credit(customer)
        
        # Filter by min amount
        results = db_service.get_customers_with_credit_balance(min_amount=Decimal('20.00'))
        
        assert all(c.current_balance >= Decimal('20.00') for c in results)
        assert any(c.customer_id == "customer-high" for c in results)
