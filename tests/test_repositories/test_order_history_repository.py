from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from models.entities import OrderHistory
from repositories.order_history_repository import OrderHistoryRepository


@pytest.fixture
def history_repo(dynamodb):
    return OrderHistoryRepository()


class TestOrderHistoryRepository:
    def test_create_order_history(self, history_repo):
        history = OrderHistory(
            customer_id="cust-1",
            offer_name="Test Beer",
            event_type="ORDER_CREATED",
            amount=Decimal("24.00"),
        )
        assert history_repo.create_order_history(history) is True

    def test_create_sets_ttl(self, history_repo):
        history = OrderHistory(
            customer_id="cust-1",
            offer_name="Test Beer",
            event_type="PAYMENT_RECEIVED",
            amount=Decimal("24.00"),
        )
        assert history.ttl is not None and history.ttl > 0

    def test_get_events_by_type_filters_event_and_range(self, history_repo):
        now = datetime.now(UTC)
        history_repo.create_order_history(
            OrderHistory(
                customer_id="cust-2",
                offer_name="A",
                event_type="PAYMENT_RECEIVED",
                changed_at=now,
                amount=Decimal("10.00"),
            )
        )
        history_repo.create_order_history(
            OrderHistory(
                customer_id="cust-3",
                offer_name="B",
                event_type="ORDER_CREATED",
                changed_at=now,
                amount=Decimal("20.00"),
            )
        )

        payments = history_repo.get_events_by_type(
            "PAYMENT_RECEIVED", start_date=now - timedelta(minutes=1), end_date=now + timedelta(minutes=1)
        )
        assert len(payments) == 1
        assert payments[0].customer_id == "cust-2"
        assert payments[0].event_type == "PAYMENT_RECEIVED"
        assert payments[0].amount == Decimal("10.00")

    def test_get_events_by_type_excludes_out_of_range(self, history_repo):
        now = datetime.now(UTC)
        history_repo.create_order_history(
            OrderHistory(
                customer_id="cust-4",
                offer_name="Old",
                event_type="PAYMENT_RECEIVED",
                changed_at=now - timedelta(days=10),
                amount=Decimal("5.00"),
            )
        )
        recent = history_repo.get_events_by_type(
            "PAYMENT_RECEIVED", start_date=now - timedelta(days=1), end_date=now + timedelta(days=1)
        )
        assert recent == []

    def test_item_to_history_tolerates_legacy_attributes(self, history_repo):
        """A legacy row carrying dropped attributes still deserializes cleanly."""
        legacy_item = {
            "history_id": "h1",
            "customer_id": "cust-9",
            "offer_name": "Legacy",
            "event_type": "ORDER_CREATED",
            "changed_at": datetime.now(UTC).isoformat(),
            "amount": Decimal("12.00"),
            # dropped / legacy attributes that must be ignored:
            "order_id": "order-legacy",
            "customer_name": "Should Be Ignored",
            "reason": "old",
            "customer_event": "cust-9#ORDER_CREATED",
        }
        history = history_repo._item_to_history(legacy_item)
        assert history.customer_id == "cust-9"
        assert history.offer_name == "Legacy"
        assert not hasattr(history, "customer_name")
