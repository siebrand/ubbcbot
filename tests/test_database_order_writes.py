"""Order writes through the database facade: what they write, what they record, and how often they read."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from models.entities import Order
from services.database import DynamoDBService


@pytest.fixture
def db(dynamodb):
    service = DynamoDBService()
    service.order_repo.create_order(
        Order(order_id="o1", customer_id="c1", offer_id=7, status="awaiting_payment", total_price=Decimal("12.50"))
    )
    return service


def payments(db) -> list:
    return db.get_events_by_type("PAYMENT_RECEIVED")


class TestUpdateOrder:
    def test_a_change_without_a_status_reads_the_order_once(self, db):
        with patch.object(db, "get_order", wraps=db.get_order) as reads:
            assert db.update_order("o1", {"total_price": Decimal("10")}) is True

        assert reads.call_count == 1
        assert db.get_order("o1").total_price == Decimal("10")
        assert payments(db) == []

    def test_paying_records_one_payment_event(self, db):
        assert db.mark_order_paid("o1", admin_id=1) is True

        assert db.get_order("o1").status == "completed"
        events = payments(db)
        assert [(e.customer_id, e.amount) for e in events] == [("c1", Decimal("12.50"))]

    def test_setting_the_same_status_again_records_nothing(self, db):
        with patch.object(db, "get_order", wraps=db.get_order) as reads:
            assert db.update_order("o1", {"status": "awaiting_payment"}) is True

        assert reads.call_count == 1
        assert payments(db) == []

    def test_a_status_change_reads_the_order_back_once(self, db):
        with patch.object(db, "get_order", wraps=db.get_order) as reads:
            db.mark_order_paid("o1", admin_id=1)

        assert reads.call_count == 2  # before, and after to record the payment

    def test_an_unknown_order(self, db):
        assert db.update_order("nope", {"status": "cancelled"}) is False
        assert db.cancel_order("nope", 1, "reason") is False
        assert db.mark_order_paid("nope", 1) is False

    def test_cancelling(self, db):
        assert db.cancel_order("o1", 1, "Customer asked") is True

        assert db.get_order("o1").status == "cancelled"
        assert payments(db) == []
