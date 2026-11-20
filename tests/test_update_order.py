"""DynamoDBService.update_order and batch_update_order_status: the purchase analytics events of a status change."""

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from models.entities import Offer, Order
from services.database import DynamoDBService
from services.purchase_events import PurchaseEvents


@pytest.fixture
def db():
    # Bypass __init__ (it creates AWS resources); only the order and analytics repositories are used.
    service = DynamoDBService.__new__(DynamoDBService)
    service.order_repo = Mock()
    service.order_repo.update_order.return_value = True
    service.order_history_repo = Mock()
    offer_repo = Mock()
    offer_repo.get_offer.return_value = Offer(offer_id=3, name="Pils")
    service.purchase_events = PurchaseEvents(service.order_history_repo, offer_repo)
    return service


def awaiting(order_id="o1"):
    return Order(order_id=order_id, offer_id=3, status="awaiting_payment", total_price=Decimal("7.00"))


def update(db, orders_returned, updates):
    with patch.object(DynamoDBService, "get_order", side_effect=orders_returned) as get_order:
        result = db.update_order("o1", updates, admin_id=5)
    return result, get_order


class TestUpdateOrder:
    def test_a_payment_records_the_amount_as_stored(self, db):
        paid = Order(order_id="o1", offer_id=3, status="completed", total_price=Decimal("6.50"))

        result, _ = update(db, [awaiting(), paid], {"status": "completed"})

        assert result is True
        event = db.order_history_repo.create_order_history.call_args.args[0]
        assert (event.event_type, event.amount, event.offer_name) == ("PAYMENT_RECEIVED", Decimal("6.50"), "Pils")

    @pytest.mark.parametrize(
        "old_status,updates",
        [
            ("ordered", {"status": "completed"}),
            ("awaiting_payment", {"status": "cancelled"}),
            ("ordered", {"quantity": 3}),
        ],
    )
    def test_any_other_change_records_nothing_and_is_not_read_back(self, db, old_status, updates):
        old = Order(order_id="o1", status=old_status)

        result, get_order = update(db, [old], updates)

        assert result is True
        assert get_order.call_count == 1
        db.order_history_repo.create_order_history.assert_not_called()

    def test_unknown_order_fails_without_updating(self, db):
        result, _ = update(db, [None], {"status": "completed"})

        assert result is False
        db.order_repo.update_order.assert_not_called()

    def test_repository_failure_is_reported(self, db):
        db.order_repo.update_order.return_value = False

        result, _ = update(db, [awaiting()], {"status": "completed"})

        assert result is False
        db.order_history_repo.create_order_history.assert_not_called()

    def test_order_missing_after_successful_update_still_succeeds(self, db):
        """The update already happened; failing to re-read the order for the event must not report a failure"""
        result, _ = update(db, [awaiting(), None], {"status": "completed"})

        assert result is True
        db.order_history_repo.create_order_history.assert_not_called()


class TestBatchUpdate:
    def test_only_the_orders_that_were_awaiting_payment_are_paid(self, db):
        db.order_repo.batch_get_orders.return_value = [awaiting("o1"), Order(order_id="o2", status="ordered")]
        db.order_repo.batch_update_order_status.return_value = ["o1", "o2"]

        assert db.batch_update_order_status(["o1", "o2"], "completed") == ["o1", "o2"]

        events = db.order_history_repo.batch_create_order_history.call_args.args[0]
        assert [e.amount for e in events] == [Decimal("7.00")]

    def test_an_order_that_was_not_updated_is_no_payment(self, db):
        o2 = Order(order_id="o2", offer_id=3, status="awaiting_payment", total_price=Decimal("3.00"))
        db.order_repo.batch_get_orders.return_value = [awaiting("o1"), o2]
        db.order_repo.batch_update_order_status.return_value = ["o2"]

        assert db.batch_update_order_status(["o1", "o2"], "completed", from_status="awaiting_payment") == ["o2"]

        events = db.order_history_repo.batch_create_order_history.call_args.args[0]
        assert [e.amount for e in events] == [Decimal("3.00")]

    def test_moving_orders_to_awaiting_payment_records_nothing(self, db):
        db.order_repo.batch_get_orders.return_value = [Order(order_id="o1", status="ready_for_labeling")]
        db.order_repo.batch_update_order_status.return_value = ["o1"]

        db.batch_update_order_status(["o1"], "awaiting_payment")

        db.order_history_repo.batch_create_order_history.assert_not_called()
