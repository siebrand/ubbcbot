"""Data layer of the personal data export: monthly claim, history by customer, all credit transactions."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from models.entities import CreditTransaction, Customer, OrderHistory
from services.database import DynamoDBService
from services.user_cache import UserCache

MONTH = 30 * 24 * 3600
NOW = 1_800_000_000


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def customer(db):
    return db.create_customer(Customer(telegram_user_id=4242, first_name="Jantje"))


class TestClaimDataExport:
    def test_first_claim_succeeds_and_stores_the_time(self, db, customer):
        claim = db.claim_data_export(customer.customer_id, NOW, MONTH)

        assert claim.claimed is True
        assert claim.previous is None
        assert int(db.get_customer(customer.customer_id).last_data_export_at) == NOW

    def test_second_claim_within_the_interval_is_refused(self, db, customer):
        db.claim_data_export(customer.customer_id, NOW, MONTH)

        claim = db.claim_data_export(customer.customer_id, NOW + MONTH - 1, MONTH)

        assert claim.claimed is False
        assert claim.last_export_at == NOW
        assert int(db.get_customer(customer.customer_id).last_data_export_at) == NOW  # untouched

    def test_claim_is_allowed_again_after_the_interval(self, db, customer):
        db.claim_data_export(customer.customer_id, NOW, MONTH)

        claim = db.claim_data_export(customer.customer_id, NOW + MONTH, MONTH)

        assert claim.claimed is True
        assert claim.previous == NOW
        assert int(db.get_customer(customer.customer_id).last_data_export_at) == NOW + MONTH

    def test_only_the_first_of_two_quick_claims_wins(self, db, customer):
        results = [db.claim_data_export(customer.customer_id, NOW + i, MONTH).claimed for i in range(3)]

        assert results == [True, False, False]

    def test_claims_are_per_customer(self, db, customer):
        other = db.create_customer(Customer(telegram_user_id=1, first_name="Other"))
        db.claim_data_export(customer.customer_id, NOW, MONTH)

        assert db.claim_data_export(other.customer_id, NOW, MONTH).claimed is True

    def test_claim_for_a_missing_customer_is_refused_without_creating_a_record(self, db):
        claim = db.claim_data_export("does-not-exist", NOW, MONTH)

        assert claim.claimed is False
        assert claim.last_export_at is None
        assert db.get_customer("does-not-exist") is None

    def test_a_customer_who_never_exported_has_no_timestamp(self, db, customer):
        assert db.get_customer(customer.customer_id).last_data_export_at is None


class TestReleaseDataExportClaim:
    def test_release_of_a_first_claim_removes_the_timestamp(self, db, customer):
        claim = db.claim_data_export(customer.customer_id, NOW, MONTH)

        assert db.release_data_export_claim(customer.customer_id, NOW, claim.previous) is True

        assert db.get_customer(customer.customer_id).last_data_export_at is None
        assert db.claim_data_export(customer.customer_id, NOW + 1, MONTH).claimed is True

    def test_release_restores_the_previous_timestamp(self, db, customer):
        db.claim_data_export(customer.customer_id, NOW, MONTH)
        claim = db.claim_data_export(customer.customer_id, NOW + MONTH, MONTH)

        assert db.release_data_export_claim(customer.customer_id, NOW + MONTH, claim.previous) is True

        assert int(db.get_customer(customer.customer_id).last_data_export_at) == NOW

    def test_release_does_nothing_when_the_claim_is_no_longer_ours(self, db, customer):
        db.claim_data_export(customer.customer_id, NOW, MONTH)

        assert db.release_data_export_claim(customer.customer_id, NOW - 5, None) is False

        assert int(db.get_customer(customer.customer_id).last_data_export_at) == NOW


class TestOrderHistoryByCustomer:
    def _event(self, db, customer_id, when, event_type="ORDER_CREATED", amount="5.00"):
        assert db.create_order_history(
            OrderHistory(
                customer_id=customer_id,
                offer_name="Pils",
                event_type=event_type,
                changed_at=when,
                amount=Decimal(amount),
            )
        )

    def test_returns_only_this_customers_events_oldest_first(self, db, customer):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        self._event(db, customer.customer_id, base + timedelta(days=2), "PAYMENT_RECEIVED")
        self._event(db, customer.customer_id, base)
        self._event(db, "someone-else", base + timedelta(days=1))

        events = db.get_order_history_by_customer(customer.customer_id)

        assert [e.event_type for e in events] == ["ORDER_CREATED", "PAYMENT_RECEIVED"]
        assert all(e.customer_id == customer.customer_id for e in events)
        assert events[0].amount == Decimal("5.00")

    def test_unknown_customer_has_no_events(self, db):
        assert db.get_order_history_by_customer("nobody") == []


class TestAllCreditTransactions:
    def test_returns_more_than_the_default_limit_in_chronological_order(self, db, customer):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(60):
            assert db.create_credit_transaction(
                CreditTransaction(
                    customer_id=customer.customer_id,
                    transaction_type="ADJUSTMENT",
                    amount=Decimal("1.00"),
                    reason=f"r{i}",
                    created_at=base + timedelta(minutes=i),
                )
            )
        db.create_credit_transaction(CreditTransaction(customer_id="someone-else", amount=Decimal("9.00")))

        limited = db.get_credit_transactions_by_customer(customer.customer_id)
        everything = db.get_all_credit_transactions_by_customer(customer.customer_id)

        assert len(limited) == 50
        assert len(everything) == 60
        assert [t.reason for t in everything] == [f"r{i}" for i in range(60)]
        assert all(t.customer_id == customer.customer_id for t in everything)
