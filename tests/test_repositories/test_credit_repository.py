from decimal import Decimal

import pytest

from models.entities import CreditTransaction, CustomerCredit
from repositories.credit_repository import CreditBalanceChanged, CreditRepository

NOW = "2026-01-01T00:00:00+00:00"


@pytest.fixture
def credit_repo(dynamodb):
    return CreditRepository()


class TestCreditRepository:
    def test_create_customer_credit(self, credit_repo):
        credit = CustomerCredit(
            customer_id="cust-1", current_balance=Decimal("50.0"), total_credits_issued=Decimal("50.0")
        )
        assert credit_repo.create_customer_credit(credit) is True

        saved = credit_repo.get_customer_credit("cust-1")
        assert saved is not None
        assert saved.current_balance == Decimal("50.0")

    def test_get_customer_credit(self, credit_repo):
        credit = CustomerCredit(customer_id="cust-2", current_balance=Decimal("100.0"))
        credit_repo.create_customer_credit(credit)

        retrieved = credit_repo.get_customer_credit("cust-2")
        assert retrieved is not None
        assert retrieved.customer_id == "cust-2"

    def test_get_customer_credit_not_found(self, credit_repo):
        result = credit_repo.get_customer_credit("nonexistent")
        assert result is None

    def test_update_customer_credit(self, credit_repo):
        credit = CustomerCredit(customer_id="cust-3", current_balance=Decimal("50.0"))
        credit_repo.create_customer_credit(credit)

        updates = {"current_balance": Decimal("75.0")}
        assert credit_repo.update_customer_credit("cust-3", updates) is True

        updated = credit_repo.get_customer_credit("cust-3")
        assert updated.current_balance == Decimal("75.0")

    @staticmethod
    def _change(customer_id: str, before: str, after: str) -> CreditTransaction:
        return CreditTransaction(
            customer_id=customer_id,
            amount=Decimal(after) - Decimal(before),
            balance_before=Decimal(before),
            balance_after=Decimal(after),
        )

    def test_record_change_creates_the_record_on_first_use(self, credit_repo):
        """ADD upserts: the first change creates the record from 0, with its transaction"""
        change = self._change("cust-inc-1", "0", "30.0")
        assert credit_repo.record_change(change, Decimal("30.0"), Decimal("0.0"), NOW) is True

        saved = credit_repo.get_customer_credit("cust-inc-1")
        assert saved.current_balance == Decimal("30.0")
        assert saved.total_credits_issued == Decimal("30.0")
        assert saved.total_credits_used == Decimal("0.0")
        assert [t.transaction_id for t in credit_repo.get_credit_transactions_by_customer("cust-inc-1")] == [
            change.transaction_id
        ]

    def test_record_change_accumulates(self, credit_repo):
        credit_repo.record_change(self._change("cust-inc-2", "0", "30.0"), Decimal("30.0"), Decimal("0.0"), NOW)
        credit_repo.record_change(self._change("cust-inc-2", "30.0", "10.0"), Decimal("0.0"), Decimal("20.0"), NOW)

        saved = credit_repo.get_customer_credit("cust-inc-2")
        assert saved.current_balance == Decimal("10.0")
        assert saved.total_credits_issued == Decimal("30.0")
        assert saved.total_credits_used == Decimal("20.0")

    @pytest.mark.parametrize("read_before", ["0", "20.0"])
    def test_record_change_refuses_a_balance_that_changed(self, credit_repo, read_before):
        credit_repo.record_change(self._change("cust-inc-3", "0", "30.0"), Decimal("30.0"), Decimal("0.0"), NOW)

        with pytest.raises(CreditBalanceChanged):
            credit_repo.record_change(
                self._change("cust-inc-3", read_before, "50.0"), Decimal("0.0"), Decimal("0.0"), NOW
            )

        assert credit_repo.get_customer_credit("cust-inc-3").current_balance == Decimal("30.0")
        assert len(credit_repo.get_credit_transactions_by_customer("cust-inc-3")) == 1

    def test_create_credit_transaction(self, credit_repo):
        transaction = CreditTransaction(
            customer_id="cust-4",
            transaction_type="CREDIT_ISSUED",
            amount=Decimal("50.0"),
            balance_after=Decimal("50.0"),
        )
        assert credit_repo.create_credit_transaction(transaction) is True

    def test_get_credit_transactions_by_customer(self, credit_repo):
        tx1 = CreditTransaction(customer_id="cust-5", transaction_type="CREDIT_ISSUED", amount=Decimal("50.0"))
        tx2 = CreditTransaction(customer_id="cust-5", transaction_type="APPLIED", amount=Decimal("-10.0"))

        credit_repo.create_credit_transaction(tx1)
        credit_repo.create_credit_transaction(tx2)

        transactions = credit_repo.get_credit_transactions_by_customer("cust-5")
        assert len(transactions) == 2

    def test_get_credit_transactions_with_limit(self, credit_repo):
        for _i in range(5):
            tx = CreditTransaction(customer_id="cust-6", transaction_type="CREDIT_ISSUED", amount=Decimal("10.0"))
            credit_repo.create_credit_transaction(tx)

        transactions = credit_repo.get_credit_transactions_by_customer("cust-6", limit=3)
        assert len(transactions) == 3

    def test_get_customers_with_credit_balance(self, credit_repo):
        credit1 = CustomerCredit(customer_id="cust-7", current_balance=Decimal("50.0"))
        credit2 = CustomerCredit(customer_id="cust-8", current_balance=Decimal("100.0"))

        credit_repo.create_customer_credit(credit1)
        credit_repo.create_customer_credit(credit2)

        customers = credit_repo.get_customers_with_credit_balance()
        assert len(customers) >= 2

    def test_get_customers_with_min_credit_balance(self, credit_repo):
        credit1 = CustomerCredit(customer_id="cust-9", current_balance=Decimal("25.0"))
        credit2 = CustomerCredit(customer_id="cust-10", current_balance=Decimal("75.0"))

        credit_repo.create_customer_credit(credit1)
        credit_repo.create_customer_credit(credit2)

        customers = credit_repo.get_customers_with_credit_balance(min_amount=Decimal("50.0"))
        customer_ids = [c.customer_id for c in customers]
        assert "cust-10" in customer_ids
