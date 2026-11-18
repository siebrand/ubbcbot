from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
from zoneinfo import ZoneInfo

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

    def test_get_events_by_type_follows_pagination(self, history_repo):
        """A result over 1 MB comes in pages; every page must be read"""
        first = {"history_id": "h1", "customer_id": "c1", "event_type": "PAYMENT_RECEIVED", "amount": Decimal("1")}
        second = {"history_id": "h2", "customer_id": "c2", "event_type": "PAYMENT_RECEIVED", "amount": Decimal("2")}
        history_repo.table = Mock()
        history_repo.table.query.side_effect = [
            {"Items": [first], "LastEvaluatedKey": {"history_id": "h1"}},
            {"Items": [second]},
        ]

        events = history_repo.get_events_by_type("PAYMENT_RECEIVED")

        assert [e.history_id for e in events] == ["h1", "h2"]
        assert history_repo.table.query.call_args_list[1].kwargs["ExclusiveStartKey"] == {"history_id": "h1"}

    def test_get_events_by_type_returns_empty_list_on_error(self, history_repo):
        history_repo.table = Mock()
        history_repo.table.query.side_effect = RuntimeError("boom")

        assert history_repo.get_events_by_type("PAYMENT_RECEIVED") == []

    def test_get_events_by_type_strict_raises_on_error(self, history_repo):
        history_repo.table = Mock()
        history_repo.table.query.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            history_repo.get_events_by_type("PAYMENT_RECEIVED", strict=True)

    def test_get_events_by_type_compares_non_utc_bounds_in_utc(self, history_repo):
        """A bound in Amsterdam time is converted to UTC, the zone changed_at is stored in"""
        moment = datetime(2026, 3, 1, 23, 30, tzinfo=UTC)  # 2 March 00:30 in Amsterdam
        history_repo.create_order_history(
            OrderHistory(customer_id="c", event_type="PAYMENT_RECEIVED", changed_at=moment, amount=Decimal("1"))
        )
        amsterdam = ZoneInfo("Europe/Amsterdam")

        march_2 = history_repo.get_events_by_type(
            "PAYMENT_RECEIVED",
            datetime(2026, 3, 2, tzinfo=amsterdam),
            datetime(2026, 3, 2, 23, 59, 59, 999999, tzinfo=amsterdam),
        )

        assert len(march_2) == 1

    def test_get_events_by_customer_limits_to_the_range(self, history_repo):
        now = datetime.now(UTC)
        for days_ago in (1, 40):
            history_repo.create_order_history(
                OrderHistory(
                    customer_id="cust-r",
                    event_type="PAYMENT_RECEIVED",
                    changed_at=now - timedelta(days=days_ago),
                    amount=Decimal("3.00"),
                )
            )

        assert len(history_repo.get_events_by_customer("cust-r")) == 2
        assert len(history_repo.get_events_by_customer("cust-r", now - timedelta(days=7), now)) == 1

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
