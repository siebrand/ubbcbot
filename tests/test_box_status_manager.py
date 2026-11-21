#!/usr/bin/env python3

from unittest.mock import Mock

import pytest

from models.entities import Box, BoxStatus, Offer, OfferStatus
from services.box_status_manager import BoxStatusManager


class TestBoxStatusManager:
    """Test BoxStatusManager service"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.manager = BoxStatusManager(self.mock_db)

    def test_update_box_after_order_placement_partial_fill(self):
        """Below capacity after the increment: no status write"""
        box = Box(box_id="box1", offer_id=1, current_quantity=8, max_capacity=12, status=BoxStatus.OPEN.value)
        self.mock_db.get_box.return_value = box
        self.mock_db.add_to_box_quantity.return_value = 10

        result = self.manager.update_box_after_order_placement("box1", 2)

        assert result is True
        self.mock_db.add_to_box_quantity.assert_called_once_with("box1", 2, 12)
        self.mock_db.mark_box_full_if_at_capacity.assert_not_called()
        self.mock_db.update_box.assert_not_called()

    def test_update_box_after_order_placement_fills_box(self):
        """At capacity after the increment: the conditional FULL write"""
        box = Box(box_id="box1", offer_id=1, current_quantity=10, max_capacity=12, status=BoxStatus.OPEN.value)
        self.mock_db.get_box.return_value = box
        self.mock_db.add_to_box_quantity.return_value = 12

        result = self.manager.update_box_after_order_placement("box1", 2)

        assert result is True
        self.mock_db.mark_box_full_if_at_capacity.assert_called_once_with("box1")
        self.mock_db.update_box.assert_not_called()

    def test_update_box_after_order_placement_follows_the_increment_not_the_read(self):
        """The read said 10 of 12, but a cancel came in between: 2 more make 10, not full"""
        box = Box(box_id="box1", offer_id=1, current_quantity=10, max_capacity=12, status=BoxStatus.OPEN.value)
        self.mock_db.get_box.return_value = box
        self.mock_db.add_to_box_quantity.return_value = 10

        assert self.manager.update_box_after_order_placement("box1", 2) is True

        self.mock_db.mark_box_full_if_at_capacity.assert_not_called()

    def test_update_box_after_order_placement_rejected_when_overfill(self):
        """Atomic increment failing (would overfill) aborts without a status write"""
        box = Box(box_id="box1", offer_id=1, current_quantity=11, max_capacity=12, status=BoxStatus.OPEN.value)
        self.mock_db.get_box.return_value = box
        self.mock_db.add_to_box_quantity.return_value = None  # concurrent fill won the race

        result = self.manager.update_box_after_order_placement("box1", 2)

        assert result is False
        self.mock_db.add_to_box_quantity.assert_called_once_with("box1", 2, 12)
        self.mock_db.mark_box_full_if_at_capacity.assert_not_called()
        self.mock_db.update_box.assert_not_called()

    def test_update_box_after_order_placement_box_not_found(self):
        """Test error handling when box not found"""
        self.mock_db.get_box.return_value = None

        result = self.manager.update_box_after_order_placement("box1", 2)

        assert result is False
        self.mock_db.add_to_box_quantity.assert_not_called()
        self.mock_db.update_box.assert_not_called()

    def test_update_box_after_order_cancellation_reopens(self):
        """Below capacity after the decrement: the conditional reopen"""
        box = Box(box_id="box1", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.FULL.value)
        self.mock_db.get_box.return_value = box
        self.mock_db.add_to_box_quantity.return_value = 10

        result = self.manager.update_box_after_order_cancellation("box1", 2)

        assert result is True
        self.mock_db.add_to_box_quantity.assert_called_once_with("box1", -2, 12)
        self.mock_db.reopen_box_if_below_capacity.assert_called_once_with("box1")
        self.mock_db.update_box.assert_not_called()

    def test_update_box_after_order_cancellation_rejected(self):
        """A failed decrement writes no status"""
        box = Box(box_id="box1", offer_id=1, current_quantity=2, max_capacity=12, status=BoxStatus.ORDERED.value)
        self.mock_db.get_box.return_value = box
        self.mock_db.add_to_box_quantity.return_value = None

        assert self.manager.update_box_after_order_cancellation("box1", 2) is False

        self.mock_db.reopen_box_if_below_capacity.assert_not_called()

    def test_mark_boxes_as_ordered(self):
        """Test marking multiple boxes as ORDERED"""
        # Setup
        box1 = Box(box_id="box1", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.ORDERED.value)
        box2 = Box(box_id="box2", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.ORDERED.value)
        box3 = Box(box_id="box3", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.ORDERED.value)
        self.mock_db.update_box.return_value = True
        self.mock_db.get_box.side_effect = [box1, box2, box3]

        # Execute
        boxes = self.manager.mark_boxes_as_ordered(["box1", "box2", "box3"])

        # Verify
        assert len(boxes) == 3
        assert boxes[0].box_id == "box1"
        assert boxes[1].box_id == "box2"
        assert boxes[2].box_id == "box3"
        assert self.mock_db.update_box.call_count == 3

    def test_mark_boxes_as_ordered_partial_failure(self):
        """Test marking boxes with some failures"""
        # Setup
        box1 = Box(box_id="box1", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.ORDERED.value)
        box3 = Box(box_id="box3", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.ORDERED.value)
        self.mock_db.update_box.side_effect = [True, False, True]
        self.mock_db.get_box.side_effect = [box1, box3]

        # Execute
        boxes = self.manager.mark_boxes_as_ordered(["box1", "box2", "box3"])

        # Verify
        assert len(boxes) == 2

    def test_mark_box_as_delivered(self):
        """Test marking box as DELIVERED returns box object"""
        # Setup
        box = Box(box_id="box1", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.DELIVERED.value)
        self.mock_db.update_box.return_value = True
        self.mock_db.get_box.return_value = box

        # Execute
        result = self.manager.mark_box_as_delivered("box1")

        # Verify
        assert result is not None
        assert result.box_id == "box1"
        assert result.status == BoxStatus.DELIVERED.value
        self.mock_db.update_box.assert_called_once_with("box1", {"status": BoxStatus.DELIVERED.value})

    def test_update_offer_status_to_sold_out(self):
        """Test offer status changes to SOLD_OUT when conditions met"""
        # Setup
        offer = Offer(
            offer_id=1,
            supplier_name="Test",
            name="Test Beer",
            price_per_unit=5.0,
            wholesale_box_size=12,
            status=OfferStatus.ACTIVE.value,
        )
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.ORDERED.value),
            Box(box_id="box2", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.FULL.value),
        ]
        self.mock_db.get_offer.return_value = offer
        self.mock_db.get_boxes_by_offer.return_value = boxes
        self.mock_db.update_offer.return_value = True

        # Execute
        new_status = self.manager.update_offer_status_after_change(1)

        # Verify
        assert new_status == OfferStatus.SOLD_OUT.value
        self.mock_db.update_offer.assert_called_once_with(1, {"status": OfferStatus.SOLD_OUT.value})

    def test_update_offer_status_to_active(self):
        """Test offer status changes to ACTIVE when space available"""
        # Setup
        offer = Offer(
            offer_id=1,
            supplier_name="Test",
            name="Test Beer",
            price_per_unit=5.0,
            wholesale_box_size=12,
            status=OfferStatus.SOLD_OUT.value,
        )
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=10, max_capacity=12, status=BoxStatus.ORDERED.value),
            Box(box_id="box2", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.FULL.value),
        ]
        self.mock_db.get_offer.return_value = offer
        self.mock_db.get_boxes_by_offer.return_value = boxes
        self.mock_db.update_offer.return_value = True

        # Execute
        new_status = self.manager.update_offer_status_after_change(1)

        # Verify
        assert new_status == OfferStatus.ACTIVE.value
        self.mock_db.update_offer.assert_called_once_with(1, {"status": OfferStatus.ACTIVE.value})

    def test_update_offer_status_no_ordered_boxes(self):
        """Test offer stays ACTIVE when no ordered boxes"""
        # Setup
        offer = Offer(
            offer_id=1,
            supplier_name="Test",
            name="Test Beer",
            price_per_unit=5.0,
            wholesale_box_size=12,
            status=OfferStatus.ACTIVE.value,
        )
        boxes = [Box(box_id="box1", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.FULL.value)]
        self.mock_db.get_offer.return_value = offer
        self.mock_db.get_boxes_by_offer.return_value = boxes

        # Execute
        new_status = self.manager.update_offer_status_after_change(1)

        # Verify - no status change
        assert new_status is None
        self.mock_db.update_offer.assert_not_called()

    def test_update_offer_status_inactive_offer(self):
        """Test no status change for inactive offers"""
        # Setup
        offer = Offer(
            offer_id=1,
            supplier_name="Test",
            name="Test Beer",
            price_per_unit=5.0,
            wholesale_box_size=12,
            status=OfferStatus.INACTIVE.value,
        )
        self.mock_db.get_offer.return_value = offer

        # Execute
        new_status = self.manager.update_offer_status_after_change(1)

        # Verify
        assert new_status is None
        self.mock_db.update_offer.assert_not_called()

    def test_update_offer_status_no_boxes(self):
        """Test no status change when offer has no boxes"""
        # Setup
        offer = Offer(
            offer_id=1,
            supplier_name="Test",
            name="Test Beer",
            price_per_unit=5.0,
            wholesale_box_size=12,
            status=OfferStatus.ACTIVE.value,
        )
        self.mock_db.get_offer.return_value = offer
        self.mock_db.get_boxes_by_offer.return_value = []

        # Execute
        new_status = self.manager.update_offer_status_after_change(1)

        # Verify
        assert new_status is None
        self.mock_db.update_offer.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
