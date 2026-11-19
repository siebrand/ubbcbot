"""A credit change is one write: the transaction and the balance together, against the balance that was read"""

from decimal import Decimal

import pytest

from models.entities import CustomerCredit
from services.credit_service import CreditService
from services.database import DynamoDBService

CUSTOMER_ID = "c1"
ADMIN_ID = 15005473


@pytest.fixture
def db(dynamodb):
    return DynamoDBService()


def balance(db) -> Decimal:
    credit = db.get_customer_credit(CUSTOMER_ID)
    return credit.current_balance if credit else Decimal("0")


def history(db) -> list:
    return db.get_all_credit_transactions_by_customer(CUSTOMER_ID)


def balance_after_history(db) -> Decimal:
    """What the history says the balance is: every change from its balance before to its balance after"""
    return sum((t.balance_after - t.balance_before for t in history(db)), Decimal("0"))


def credit_issued_after_the_next_read(db, amount: Decimal) -> None:
    """An admin issues a credit (through another container) right after this service reads the balance"""
    read = db.get_customer_credit
    other = CreditService(DynamoDBService())

    def read_then_issue(customer_id, *args, **kwargs):
        db.get_customer_credit = read
        result = read(customer_id, *args, **kwargs)
        assert other.issue_credit(customer_id, amount, "Concurrent", ADMIN_ID)
        return result

    db.get_customer_credit = read_then_issue


class TestConcurrentCredit:
    def test_a_credit_issued_while_credit_is_applied_is_not_wiped(self, db):
        service = CreditService(db)
        assert service.issue_credit(CUSTOMER_ID, Decimal("20"), "Start", ADMIN_ID)
        credit_issued_after_the_next_read(db, Decimal("5"))

        result = service.apply_credit_to_delivery(CUSTOMER_ID, Decimal("50"))

        assert result["credit_applied"] + result["remaining_credit"] == Decimal("25")
        assert balance(db) == result["remaining_credit"]
        assert balance(db) == balance_after_history(db)

    def test_a_credit_issued_while_credit_is_issued_is_not_lost(self, db):
        service = CreditService(db)
        credit_issued_after_the_next_read(db, Decimal("5"))

        assert service.issue_credit(CUSTOMER_ID, Decimal("10"), "Mine", ADMIN_ID)

        assert balance(db) == Decimal("15")
        assert balance(db) == balance_after_history(db)
        assert sorted((t.balance_before, t.balance_after) for t in history(db)) == [
            (Decimal("0"), Decimal("5")),
            (Decimal("5"), Decimal("15")),
        ]


class TestOneWrite:
    def test_when_the_balance_cannot_be_written_no_transaction_is_recorded(self, db):
        # A record the ADD cannot add to: the balance write fails
        assert db.create_customer_credit(CustomerCredit(customer_id=CUSTOMER_ID, current_balance=Decimal("0")))
        db.credit_repo.table.update_item(
            Key={"customer_id": CUSTOMER_ID},
            UpdateExpression="SET total_credits_issued = :s",
            ExpressionAttributeValues={":s": "not a number"},
        )

        assert not CreditService(db).issue_credit(CUSTOMER_ID, Decimal("10"), "Mine", ADMIN_ID)

        assert history(db) == []
        assert balance(db) == Decimal("0")
