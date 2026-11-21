import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from handlers.admin.order.order_editing import OrderEditing
from models.entities import Box, BoxStatus, Order


class TestOrderEditingBox(unittest.TestCase):
    def setUp(self):
        self.mock_db = Mock()
        self.mock_db.get_boxes_by_offer.return_value = []  # no delivered stock to show
        self.handler = OrderEditing(self.mock_db, 15005473, "test", "token")
        self.handler.box_status_manager = Mock()
        self.handler.box_status_manager.update_offer_status_after_change.return_value = None

    def _order(self, **kw):
        defaults = {
            "order_id": "abc12345-1111",
            "customer_id": "c1",
            "offer_id": 724,
            "box_id": "box-old",
            "quantity": 2,
        }
        defaults.update(kw)
        return Order(**defaults)

    def _box(self, box_id, qty, cap=12, status=BoxStatus.OPEN.value, offer_id=724):
        return Box(box_id=box_id, offer_id=offer_id, current_quantity=qty, max_capacity=cap, status=status)

    # --- box-space listing ---
    def test_boxes_with_space_filters_full_and_sorts_by_creation(self):
        # Two boxes with space, one full; must list only those with room, in creation order.
        import datetime

        b1 = self._box("box-1", 10, cap=12)
        b1.created_at = datetime.datetime(2026, 1, 2)
        b2 = self._box("box-2", 12, cap=12, status=BoxStatus.FULL.value)  # full, excluded
        b2.created_at = datetime.datetime(2026, 1, 1)
        b3 = self._box("box-3", 0, cap=12)
        b3.created_at = datetime.datetime(2026, 1, 3)
        self.mock_db.get_boxes_by_offer.return_value = [b1, b2, b3]

        order = self._order(box_id="box-old", quantity=1)
        boxes = self.handler._boxes_with_space(order)
        # box-2 is full -> excluded; box-old excluded; sorted by created_at
        self.assertEqual([b.box_id for b in boxes], ["box-1", "box-3"])

    def test_boxes_with_space_needs_room_for_order_quantity(self):
        import datetime

        b1 = self._box("box-1", 11, cap=12)  # only 1 free, order needs 2 -> excluded
        b1.created_at = datetime.datetime(2026, 1, 1)
        b2 = self._box("box-2", 5, cap=12)  # 7 free -> ok
        b2.created_at = datetime.datetime(2026, 1, 2)
        self.mock_db.get_boxes_by_offer.return_value = [b1, b2]

        order = self._order(quantity=2)
        boxes = self.handler._boxes_with_space(order)
        self.assertEqual([b.box_id for b in boxes], ["box-2"])

    # --- apply box move ---
    def test_apply_box_change_moves_quantity_atomically(self):
        order = self._order(box_id="box-old", quantity=2, offer_id=724)
        new_box = self._box("box-new", 0, cap=12, offer_id=724)
        self.mock_db.get_order.return_value = order
        self.mock_db.get_box.return_value = new_box
        self.mock_db.move_order_to_box.return_value = True

        ok, _msg = self.handler._apply_box_change(order, "box-new")
        self.assertTrue(ok)
        # the order and both boxes in one transaction: a pending order between boxes not yet ordered
        self.mock_db.move_order_to_box.assert_called_once_with(
            order.order_id, 2, "box-old", "box-new", 12, "pending", ("open", "full")
        )
        self.mock_db.update_order.assert_not_called()
        self.handler.box_status_manager.update_box_after_order_placement.assert_not_called()

    def test_apply_box_change_rejects_overfill_without_touching_old_box(self):
        order = self._order(box_id="box-old", quantity=5, offer_id=724)
        new_box = self._box("box-new", 10, cap=12, offer_id=724)  # only 2 free
        self.mock_db.get_box.return_value = new_box
        self.handler.box_status_manager.update_box_after_order_placement.return_value = False  # overfill guard

        ok, _msg = self.handler._apply_box_change(order, "box-new")
        self.assertFalse(ok)
        self.handler.box_status_manager.update_box_after_order_cancellation.assert_not_called()
        self.mock_db.update_order.assert_not_called()

    def test_apply_box_change_rejects_box_from_other_offer(self):
        order = self._order(offer_id=724)
        other = self._box("box-new", 0, cap=12, offer_id=999)
        self.mock_db.get_box.return_value = other

        ok, _msg = self.handler._apply_box_change(order, "box-new")
        self.assertFalse(ok)
        self.handler.box_status_manager.update_box_after_order_placement.assert_not_called()

    def test_apply_box_change_rejects_same_box(self):
        order = self._order(box_id="box-old")
        same = self._box("box-old", 0, offer_id=724)
        self.mock_db.get_box.return_value = same

        ok, _msg = self.handler._apply_box_change(order, "box-old")
        self.assertFalse(ok)

    def test_apply_box_change_changes_nothing_when_the_transaction_is_rejected(self):
        order = self._order(box_id="box-old", quantity=2, offer_id=724)
        new_box = self._box("box-new", 0, cap=12, offer_id=724)
        self.mock_db.get_box.return_value = new_box
        self.mock_db.move_order_to_box.return_value = False  # the order or a box changed in between

        ok, msg = self.handler._apply_box_change(order, "box-new")
        self.assertFalse(ok)
        self.assertEqual(msg, "edit_order_move_failed")
        # nothing to roll back: no other write was made
        self.handler.box_status_manager.update_box_status_after_change.assert_not_called()
        self.mock_db.update_order.assert_not_called()


if __name__ == "__main__":
    unittest.main()
