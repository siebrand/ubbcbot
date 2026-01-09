#!/usr/bin/env python3

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from services.box_status_manager import BoxStatusManager
from models.entities import Box, BoxStatus, Offer, OfferStatus

class TestBoxStatusManager:
    """Test BoxStatusManager service"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.manager = BoxStatusManager(self.mock_db)
    
    def test_update_box_after_order_placement_partial_fill(self):
        """Test box update when order partially fills box"""
        # Setup
        box = Box(
            box_id="box1",
            offer_id=1,
            current_quantity=8,
            max_capacity=12,
            status=BoxStatus.OPEN.value
        )
        self.mock_db.get_box.return_value = box
        self.mock_db.update_box.return_value = True
        
        # Execute
        result = self.manager.update_box_after_order_placement("box1", 2)
        
        # Verify
        assert result is True
        self.mock_db.update_box.assert_called_once_with("box1", {
            'current_quantity': 10,
        })
    
    def test_update_box_after_order_placement_fills_box(self):
        """Test box status changes to FULL when capacity reached"""
        # Setup
        box = Box(
            box_id="box1",
            offer_id=1,
            current_quantity=10,
            max_capacity=12,
            status=BoxStatus.OPEN.value
        )
        self.mock_db.get_box.return_value = box
        self.mock_db.update_box.return_value = True
        
        # Execute
        result = self.manager.update_box_after_order_placement("box1", 2)
        
        # Verify
        assert result is True
        self.mock_db.update_box.assert_called_once_with("box1", {
            'current_quantity': 12,
            'status': BoxStatus.FULL.value
        })
    
    def test_update_box_after_order_placement_ordered_box(self):
        """Test box status not changed when already ORDERED"""
        # Setup
        box = Box(
            box_id="box1",
            offer_id=1,
            current_quantity=10,
            max_capacity=12,
            status=BoxStatus.ORDERED.value
        )
        self.mock_db.get_box.return_value = box
        self.mock_db.update_box.return_value = True
        
        # Execute
        result = self.manager.update_box_after_order_placement("box1", 2)
        
        # Verify - status should not be updated
        assert result is True
        self.mock_db.update_box.assert_called_once_with("box1", {
            'current_quantity': 12,
        })
    
    def test_update_box_after_order_placement_box_not_found(self):
        """Test error handling when box not found"""
        # Setup
        self.mock_db.get_box.return_value = None
        
        # Execute
        result = self.manager.update_box_after_order_placement("box1", 2)
        
        # Verify
        assert result is False
        self.mock_db.update_box.assert_not_called()
    
    def test_update_box_after_order_cancellation_partial(self):
        """Test box update when order partially empties box"""
        # Setup
        box = Box(
            box_id="box1",
            offer_id=1,
            current_quantity=10,
            max_capacity=12,
            status=BoxStatus.FULL.value
        )
        self.mock_db.get_box.return_value = box
        self.mock_db.update_box.return_value = True
        
        # Execute
        result = self.manager.update_box_after_order_cancellation("box1", 2)
        
        # Verify - should change to OPEN since 8 < 12
        assert result is True
        self.mock_db.update_box.assert_called_once_with("box1", {
            'current_quantity': 8,
            'status': BoxStatus.OPEN.value
        })
    
    def test_update_box_after_order_cancellation_empties_box(self):
        """Test box status changes to OPEN when no longer full"""
        # Setup
        box = Box(
            box_id="box1",
            offer_id=1,
            current_quantity=12,
            max_capacity=12,
            status=BoxStatus.FULL.value
        )
        self.mock_db.get_box.return_value = box
        self.mock_db.update_box.return_value = True
        
        # Execute - remove 2 units
        result = self.manager.update_box_after_order_cancellation("box1", 2)
        
        # Verify - should become OPEN since 10 < 12
        assert result is True
        self.mock_db.update_box.assert_called_once_with("box1", {
            'current_quantity': 10,
            'status': BoxStatus.OPEN.value
        })
    
    def test_update_box_after_order_cancellation_ordered_box(self):
        """Test box status not changed when already ORDERED"""
        # Setup
        box = Box(
            box_id="box1",
            offer_id=1,
            current_quantity=2,
            max_capacity=12,
            status=BoxStatus.ORDERED.value
        )
        self.mock_db.get_box.return_value = box
        self.mock_db.update_box.return_value = True
        
        # Execute
        result = self.manager.update_box_after_order_cancellation("box1", 2)
        
        # Verify - status should not be updated
        assert result is True
        self.mock_db.update_box.assert_called_once_with("box1", {
            'current_quantity': 0,
        })
    
    def test_mark_boxes_as_ordered(self):
        """Test marking multiple boxes as ORDERED"""
        # Setup
        self.mock_db.update_box.return_value = True
        
        # Execute
        count = self.manager.mark_boxes_as_ordered(["box1", "box2", "box3"])
        
        # Verify
        assert count == 3
        assert self.mock_db.update_box.call_count == 3
    
    def test_mark_boxes_as_ordered_partial_failure(self):
        """Test marking boxes with some failures"""
        # Setup
        self.mock_db.update_box.side_effect = [True, False, True]
        
        # Execute
        count = self.manager.mark_boxes_as_ordered(["box1", "box2", "box3"])
        
        # Verify
        assert count == 2
    
    def test_mark_box_as_delivered(self):
        """Test marking box as DELIVERED"""
        # Setup
        self.mock_db.update_box.return_value = True
        
        # Execute
        result = self.manager.mark_box_as_delivered("box1")
        
        # Verify
        assert result is True
        self.mock_db.update_box.assert_called_once_with("box1", {
            'status': BoxStatus.DELIVERED.value
        })
    
    def test_update_offer_status_to_sold_out(self):
        """Test offer status changes to SOLD_OUT when conditions met"""
        # Setup
        offer = Offer(
            offer_id=1,
            supplier_name="Test",
            name="Test Beer",
            price_per_unit=5.0,
            wholesale_box_size=12,
            status=OfferStatus.ACTIVE.value
        )
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.ORDERED.value),
            Box(box_id="box2", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.FULL.value)
        ]
        self.mock_db.get_offer.return_value = offer
        self.mock_db.get_boxes_by_offer.return_value = boxes
        self.mock_db.update_offer.return_value = True
        
        # Execute
        new_status = self.manager.update_offer_status_after_change(1)
        
        # Verify
        assert new_status == OfferStatus.SOLD_OUT.value
        self.mock_db.update_offer.assert_called_once_with(1, {
            'status': OfferStatus.SOLD_OUT.value
        })
    
    def test_update_offer_status_to_active(self):
        """Test offer status changes to ACTIVE when space available"""
        # Setup
        offer = Offer(
            offer_id=1,
            supplier_name="Test",
            name="Test Beer",
            price_per_unit=5.0,
            wholesale_box_size=12,
            status=OfferStatus.SOLD_OUT.value
        )
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=10, max_capacity=12, status=BoxStatus.ORDERED.value),
            Box(box_id="box2", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.FULL.value)
        ]
        self.mock_db.get_offer.return_value = offer
        self.mock_db.get_boxes_by_offer.return_value = boxes
        self.mock_db.update_offer.return_value = True
        
        # Execute
        new_status = self.manager.update_offer_status_after_change(1)
        
        # Verify
        assert new_status == OfferStatus.ACTIVE.value
        self.mock_db.update_offer.assert_called_once_with(1, {
            'status': OfferStatus.ACTIVE.value
        })
    
    def test_update_offer_status_no_ordered_boxes(self):
        """Test offer stays ACTIVE when no ordered boxes"""
        # Setup
        offer = Offer(
            offer_id=1,
            supplier_name="Test",
            name="Test Beer",
            price_per_unit=5.0,
            wholesale_box_size=12,
            status=OfferStatus.ACTIVE.value
        )
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=12, max_capacity=12, status=BoxStatus.FULL.value)
        ]
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
            status=OfferStatus.INACTIVE.value
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
            status=OfferStatus.ACTIVE.value
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
