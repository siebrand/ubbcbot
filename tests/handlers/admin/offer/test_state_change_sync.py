"""State changes that must re-render the announcements (RCA offer 933)."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from handlers.admin.offer.boxes import BoxManagementHandler
from handlers.admin.offer.management import OfferManagementHandler
from models.entities import Offer, OfferStatus, Order


def _offer(status=OfferStatus.ACTIVE.value, box_size=12):
    return Offer(
        offer_id=933,
        name="Beer",
        price_per_unit=Decimal("4.00"),
        wholesale_box_size=box_size,
        status=status,
    )


def _order(order_id, quantity, status):
    return Order(
        order_id=order_id,
        offer_id=933,
        box_id="box-1",
        customer_id="c1",
        quantity=quantity,
        status=status,
        created_at=datetime(2026, 11, 9, tzinfo=UTC),
    )


class TestAuditBoxChangesRecomputeStatus:
    def _handler(self):
        h = BoxManagementHandler(MagicMock(), 1, "test", "token")
        h._check_offer_status_after_change = MagicMock()
        h._send_message = MagicMock()
        h.box_status_manager = MagicMock()
        h.db.get_offer.return_value = _offer()
        return h

    def test_fill_boxes_recomputes_status(self):
        h = self._handler()
        box = MagicMock(status="open", max_capacity=12, current_quantity=10, box_id="b1")
        h.db.get_boxes_by_offer.return_value = [box]
        h._execute_fill_boxes(123, 933, 2)
        h._check_offer_status_after_change.assert_called_once_with(933)

    def test_fill_boxes_without_free_capacity_does_not_recompute(self):
        h = self._handler()
        box = MagicMock(status="open", max_capacity=12, current_quantity=12, box_id="b1")
        h.db.get_boxes_by_offer.return_value = [box]
        h._execute_fill_boxes(123, 933, 2)
        h._check_offer_status_after_change.assert_not_called()

    def test_create_boxes_recomputes_status(self):
        h = self._handler()
        h.db.create_box.return_value = MagicMock(box_id="new")
        h._add_box_capacity(123, _offer(), 5)
        h._check_offer_status_after_change.assert_called_once_with(933)


class TestCreateBoxSync:
    def _handler(self, status):
        h = BoxManagementHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_message = MagicMock()
        h.db.get_offer.return_value = _offer(status=status)
        h.db.create_box.return_value = MagicMock()
        return h

    def test_reopening_sold_out_offer_syncs_messages(self):
        h = self._handler(OfferStatus.SOLD_OUT.value)
        h.handle_create_box(123, ["933"])
        h.db.update_offer.assert_called_once_with(933, {"status": "active"})
        h.sync_offer_messages.assert_called_once_with(933)

    def test_box_on_active_offer_does_not_sync(self):
        h = self._handler(OfferStatus.ACTIVE.value)
        h.handle_create_box(123, ["933"])
        h.sync_offer_messages.assert_not_called()


class TestWholesaleConfirmSync:
    def _handler(self, pending_after):
        h = OfferManagementHandler(MagicMock(), 1, "test", "token")
        h.sync_offer_messages = MagicMock()
        h._send_message = MagicMock()
        h.box_status_manager = MagicMock()
        h.box_deletion_service = MagicMock()
        h.box_deletion_service.delete_empty_boxes.return_value = 0
        h._validate_and_get_offer = MagicMock(return_value=(_offer(), None))
        before = [_order("o1", 6, "pending"), _order("o2", 6, "pending")]
        h.db.get_orders_by_offer.side_effect = [before, pending_after, []]
        h.db.get_boxes_by_offer.return_value = []
        h.db.list_offers.return_value = []
        return h

    def test_sold_out_after_wholesale_syncs_messages(self):
        h = self._handler([_order("o1", 6, "ordered"), _order("o2", 6, "ordered")])
        h.handle_confirm_process_wholesale(123, ["933", "1"])
        h.db.update_offer.assert_called_once_with(933, {"status": "sold_out"})
        h.sync_offer_messages.assert_called_once_with(933)

    def test_remaining_capacity_does_not_sync(self):
        h = self._handler([_order("o1", 6, "ordered")])
        h.db.get_orders_by_offer.side_effect = [[_order("o1", 6, "pending")], [_order("o1", 6, "ordered")], []]
        h.handle_confirm_process_wholesale(123, ["933", "1"])
        h.db.update_offer.assert_not_called()
        h.sync_offer_messages.assert_not_called()
