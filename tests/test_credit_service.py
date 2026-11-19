"""
Tests for credit service core logic (the database is a mock; tests/test_credit_atomic.py runs against moto)
"""

from decimal import Decimal

import pytest

from models.entities import CustomerCredit
from repositories.credit_repository import CreditBalanceChanged
from services.credit_service import CreditService


@pytest.fixture
def credit_service(mocker):
    """Create credit service with mocked database"""
    mock_db = mocker.Mock()
    mock_db.record_credit_change.return_value = True
    return CreditService(mock_db)


def with_balance(credit_service, *balances: str) -> None:
    """The balance the service reads, one per read"""
    credit_service.db.get_customer_credit.side_effect = [
        CustomerCredit(customer_id="customer-123", current_balance=Decimal(b)) for b in balances
    ]


def written(credit_service):
    """(transaction, issued_delta, used_delta) of the last write"""
    args = credit_service.db.record_credit_change.call_args.args
    return args[0], args[1], args[2]


class TestGetCustomerCreditBalance:
    """Test getting customer credit balance"""

    def test_get_balance_existing_credit(self, credit_service, mocker):
        """Test getting balance for customer with existing credit"""
        customer_id = "test-customer-123"
        expected_credit = CustomerCredit(customer_id=customer_id, current_balance=Decimal("50.00"))

        credit_service.db.get_customer_credit = mocker.Mock(return_value=expected_credit)

        balance = credit_service.get_customer_credit_balance(customer_id)

        assert balance == Decimal("50.00")
        credit_service.db.get_customer_credit.assert_called_once_with(customer_id)

    def test_get_balance_no_credit_returns_zero(self, credit_service, mocker):
        """Test getting balance for customer with no credit returns 0"""
        customer_id = "test-customer-456"

        credit_service.db.get_customer_credit = mocker.Mock(return_value=None)

        balance = credit_service.get_customer_credit_balance(customer_id)

        assert balance == Decimal("0.0")
        credit_service.db.get_customer_credit.assert_called_once_with(customer_id)


class TestIssueCredit:
    """Test issuing credit to customers"""

    def test_issue_credit_valid_amount(self, credit_service):
        """The transaction and the issued total are written together, from the balance that was read"""
        with_balance(credit_service, "30.00")

        result = credit_service.issue_credit("customer-123", Decimal("20.00"), "Defective product", 123456789)

        assert result is True
        transaction, issued, used = written(credit_service)
        assert transaction.customer_id == "customer-123"
        assert transaction.transaction_type == "CREDIT_ISSUED"
        assert transaction.amount == Decimal("20.00")
        assert transaction.balance_before == Decimal("30.00")
        assert transaction.balance_after == Decimal("50.00")
        assert transaction.reason == "Defective product"
        assert transaction.created_by == 123456789
        assert (issued, used) == (Decimal("20.00"), Decimal("0.0"))

    def test_issue_credit_invalid_amount_zero(self, credit_service):
        """Test issuing credit with zero amount fails"""
        result = credit_service.issue_credit("customer-123", Decimal("0.00"), "Test", 123)
        assert result is False
        credit_service.db.record_credit_change.assert_not_called()

    def test_issue_credit_negative_amount_with_reason_succeeds(self, credit_service):
        """A debt with a reason is written; it counts as credit used"""
        with_balance(credit_service, "0.00")

        result = credit_service.issue_credit("customer-123", Decimal("-10.00"), "Damaged product charge", 123)

        assert result is True
        transaction, issued, used = written(credit_service)
        assert transaction.balance_after == Decimal("-10.00")
        assert (issued, used) == (Decimal("0.0"), Decimal("10.00"))

    def test_issue_credit_empty_reason(self, credit_service):
        """A credit may go without a reason (the usage says [reason]); it is booked as "Credit issued" """
        with_balance(credit_service, "0.00")

        result = credit_service.issue_credit("customer-123", Decimal("10.00"), "", 123)

        assert result is True
        assert written(credit_service)[0].reason == "Credit issued"

    def test_issue_debt_empty_reason(self, credit_service):
        """A debt needs a reason"""
        result = credit_service.issue_credit("customer-123", Decimal("-10.00"), " ", 123)
        assert result is False

    @pytest.mark.parametrize("amount", [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity")])
    def test_issue_credit_not_finite(self, credit_service, amount):
        result = credit_service.issue_credit("customer-123", amount, "Test", 123)
        assert result is False

    def test_issue_credit_write_failure(self, credit_service):
        """When the write fails, the credit is not issued"""
        with_balance(credit_service, "30.00")
        credit_service.db.record_credit_change.return_value = False

        assert credit_service.issue_credit("customer-123", Decimal("20.00"), "Test", 123) is False

    def test_a_changed_balance_is_read_again(self, credit_service):
        """Another write came in between: the change is computed again from the new balance"""
        with_balance(credit_service, "30.00", "35.00")
        credit_service.db.record_credit_change.side_effect = [CreditBalanceChanged("customer-123"), True]

        assert credit_service.issue_credit("customer-123", Decimal("20.00"), "Test", 123) is True

        transaction, _, _ = written(credit_service)
        assert (transaction.balance_before, transaction.balance_after) == (Decimal("35.00"), Decimal("55.00"))

    def test_a_balance_that_keeps_changing_is_given_up(self, credit_service):
        with_balance(credit_service, *["30.00"] * CreditService.MAX_ATTEMPTS)
        credit_service.db.record_credit_change.side_effect = CreditBalanceChanged("customer-123")

        assert credit_service.issue_credit("customer-123", Decimal("20.00"), "Test", 123) is False
        assert credit_service.db.record_credit_change.call_count == CreditService.MAX_ATTEMPTS


class TestApplyCreditToDelivery:
    """Test applying credit to delivery"""

    def test_apply_credit_less_than_total(self, credit_service):
        """Test applying credit when credit < delivery total"""
        with_balance(credit_service, "20.00")

        result = credit_service.apply_credit_to_delivery("customer-123", Decimal("50.00"))

        assert result["original_total"] == Decimal("50.00")
        assert result["credit_applied"] == Decimal("20.00")
        assert result["payment_required"] == Decimal("30.00")
        assert result["remaining_credit"] == Decimal("0.0")

    def test_apply_credit_greater_than_total(self, credit_service):
        """Test applying credit when credit > delivery total"""
        with_balance(credit_service, "50.00")

        result = credit_service.apply_credit_to_delivery("customer-123", Decimal("30.00"))

        assert result["original_total"] == Decimal("30.00")
        assert result["credit_applied"] == Decimal("30.00")
        assert result["payment_required"] == Decimal("0.0")
        assert result["remaining_credit"] == Decimal("20.00")

    def test_apply_credit_equal_to_total(self, credit_service):
        """Test applying credit when credit = delivery total"""
        with_balance(credit_service, "50.00")

        result = credit_service.apply_credit_to_delivery("customer-123", Decimal("50.00"))

        assert result["original_total"] == Decimal("50.00")
        assert result["credit_applied"] == Decimal("50.00")
        assert result["payment_required"] == Decimal("0.0")
        assert result["remaining_credit"] == Decimal("0.0")

    def test_apply_credit_zero_balance(self, credit_service):
        """Test applying credit when customer has no credit: nothing is written"""
        credit_service.db.get_customer_credit.return_value = None

        result = credit_service.apply_credit_to_delivery("customer-123", Decimal("50.00"))

        assert result["original_total"] == Decimal("50.00")
        assert result["credit_applied"] == Decimal("0.0")
        assert result["payment_required"] == Decimal("50.00")
        assert result["remaining_credit"] == Decimal("0.0")
        credit_service.db.record_credit_change.assert_not_called()

    def test_apply_credit_writes_the_applied_transaction_and_the_usage(self, credit_service):
        """Test that applying credit creates APPLIED transaction, with the usage in the same write"""
        with_balance(credit_service, "30.00")

        credit_service.apply_credit_to_delivery("customer-123", Decimal("50.00"))

        transaction, issued, used = written(credit_service)
        assert transaction.transaction_type == "APPLIED"
        assert transaction.amount == Decimal("-30.00")  # Negative for usage
        assert transaction.balance_before == Decimal("30.00")
        assert transaction.balance_after == Decimal("0.0")
        assert (issued, used) == (Decimal("0.0"), Decimal("30.00"))

    def test_apply_credit_negative_balance_adds_charge(self, credit_service):
        """Test applying negative balance adds charge to delivery total"""
        with_balance(credit_service, "-20.00")

        result = credit_service.apply_credit_to_delivery("customer-123", Decimal("50.00"))

        assert result["original_total"] == Decimal("50.00")
        assert result["credit_applied"] == Decimal("-20.00")  # Negative
        assert result["payment_required"] == Decimal("70.00")  # 50 + 20
        assert result["remaining_credit"] == Decimal("0.0")

        transaction, issued, used = written(credit_service)
        assert transaction.amount == Decimal("-20.00")
        assert transaction.balance_before == Decimal("-20.00")
        assert transaction.balance_after == Decimal("0.0")
        assert (issued, used) == (Decimal("0.0"), Decimal("0.0"))

    def test_when_the_write_fails_nothing_is_applied(self, credit_service):
        """The customer pays the full total and keeps the credit: the balance was not changed"""
        with_balance(credit_service, "30.00", "30.00")
        credit_service.db.record_credit_change.return_value = False

        result = credit_service.apply_credit_to_delivery("customer-123", Decimal("50.00"))

        assert result["credit_applied"] == Decimal("0.0")
        assert result["payment_required"] == Decimal("50.00")
        assert result["remaining_credit"] == Decimal("30.00")
