from decimal import Decimal

import pytest
from models.entities import CustomerCredit, CreditTransaction
from repositories.credit_repository import CreditRepository


@pytest.fixture
def credit_repo(dynamodb):
    return CreditRepository()


class TestCreditRepository:
    def test_create_customer_credit(self, credit_repo):
        credit = CustomerCredit(
            customer_id="cust-1",
            current_balance=Decimal('50.0'),
            total_credits_issued=Decimal('50.0')
        )
        assert credit_repo.create_customer_credit(credit) is True

        saved = credit_repo.get_customer_credit("cust-1")
        assert saved is not None
        assert saved.current_balance == Decimal('50.0')

    def test_get_customer_credit(self, credit_repo):
        credit = CustomerCredit(customer_id="cust-2", current_balance=Decimal('100.0'))
        credit_repo.create_customer_credit(credit)

        retrieved = credit_repo.get_customer_credit("cust-2")
        assert retrieved is not None
        assert retrieved.customer_id == "cust-2"

    def test_get_customer_credit_not_found(self, credit_repo):
        result = credit_repo.get_customer_credit("nonexistent")
        assert result is None

    def test_update_customer_credit(self, credit_repo):
        credit = CustomerCredit(customer_id="cust-3", current_balance=Decimal('50.0'))
        credit_repo.create_customer_credit(credit)

        updates = {"current_balance": Decimal('75.0')}
        assert credit_repo.update_customer_credit("cust-3", updates) is True

        updated = credit_repo.get_customer_credit("cust-3")
        assert updated.current_balance == Decimal('75.0')

    def test_increment_balance_creates_record_on_first_use(self, credit_repo):
        """ADD upserts: incrementing a non-existent credit record creates it from 0"""
        now = "2026-01-01T00:00:00+00:00"
        assert credit_repo.increment_balance(
            "cust-inc-1", Decimal('30.0'), Decimal('30.0'), Decimal('0.0'), now, now) is True

        saved = credit_repo.get_customer_credit("cust-inc-1")
        assert saved.current_balance == Decimal('30.0')
        assert saved.total_credits_issued == Decimal('30.0')
        assert saved.total_credits_used == Decimal('0.0')

    def test_increment_balance_accumulates(self, credit_repo):
        """Two sequential increments accumulate rather than overwrite (lost-update guard)"""
        now = "2026-01-01T00:00:00+00:00"
        credit_repo.increment_balance("cust-inc-2", Decimal('30.0'), Decimal('30.0'), Decimal('0.0'), now, now)
        credit_repo.increment_balance("cust-inc-2", Decimal('20.0'), Decimal('20.0'), Decimal('0.0'), now, now)

        saved = credit_repo.get_customer_credit("cust-inc-2")
        assert saved.current_balance == Decimal('50.0')
        assert saved.total_credits_issued == Decimal('50.0')

    def test_increment_balance_negative_delta_records_usage(self, credit_repo):
        """A negative balance delta plus a used_delta tracks credit consumption"""
        now = "2026-01-01T00:00:00+00:00"
        credit_repo.increment_balance("cust-inc-3", Decimal('50.0'), Decimal('50.0'), Decimal('0.0'), now, now)
        credit_repo.increment_balance("cust-inc-3", Decimal('-20.0'), Decimal('0.0'), Decimal('20.0'), now, now)

        saved = credit_repo.get_customer_credit("cust-inc-3")
        assert saved.current_balance == Decimal('30.0')
        assert saved.total_credits_used == Decimal('20.0')

    def test_create_credit_transaction(self, credit_repo):
        transaction = CreditTransaction(
            customer_id="cust-4",
            transaction_type="CREDIT_ISSUED",
            amount=Decimal('50.0'),
            balance_after=Decimal('50.0')
        )
        assert credit_repo.create_credit_transaction(transaction) is True

    def test_get_credit_transactions_by_customer(self, credit_repo):
        tx1 = CreditTransaction(customer_id="cust-5", transaction_type="CREDIT_ISSUED", amount=Decimal('50.0'))
        tx2 = CreditTransaction(customer_id="cust-5", transaction_type="APPLIED", amount=Decimal('-10.0'))

        credit_repo.create_credit_transaction(tx1)
        credit_repo.create_credit_transaction(tx2)

        transactions = credit_repo.get_credit_transactions_by_customer("cust-5")
        assert len(transactions) == 2

    def test_get_credit_transactions_with_limit(self, credit_repo):
        for i in range(5):
            tx = CreditTransaction(customer_id="cust-6", transaction_type="CREDIT_ISSUED", amount=Decimal('10.0'))
            credit_repo.create_credit_transaction(tx)

        transactions = credit_repo.get_credit_transactions_by_customer("cust-6", limit=3)
        assert len(transactions) == 3

    def test_get_customers_with_credit_balance(self, credit_repo):
        credit1 = CustomerCredit(customer_id="cust-7", current_balance=Decimal('50.0'))
        credit2 = CustomerCredit(customer_id="cust-8", current_balance=Decimal('100.0'))

        credit_repo.create_customer_credit(credit1)
        credit_repo.create_customer_credit(credit2)

        customers = credit_repo.get_customers_with_credit_balance()
        assert len(customers) >= 2

    def test_get_customers_with_min_credit_balance(self, credit_repo):
        credit1 = CustomerCredit(customer_id="cust-9", current_balance=Decimal('25.0'))
        credit2 = CustomerCredit(customer_id="cust-10", current_balance=Decimal('75.0'))

        credit_repo.create_customer_credit(credit1)
        credit_repo.create_customer_credit(credit2)

        customers = credit_repo.get_customers_with_credit_balance(min_amount=Decimal('50.0'))
        customer_ids = [c.customer_id for c in customers]
        assert "cust-10" in customer_ids
