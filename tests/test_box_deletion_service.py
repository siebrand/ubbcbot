#!/usr/bin/env python3

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from services.box_deletion_service import BoxDeletionService
from models.entities import Box, BoxStatus, Order

class TestBoxDeletionService:
    """Test BoxDeletionService"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.service = BoxDeletionService(self.mock_db)
    
    def test_delete_offer_boxes_success(self):
        """Test deleting all boxes for an offer"""
        # Setup
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=0, max_capacity=12),
            Box(box_id="box2", offer_id=1, current_quantity=0, max_capacity=12),
            Box(box_id="box3", offer_id=1, current_quantity=0, max_capacity=12)
        ]
        self.mock_db.get_boxes_by_offer.return_value = boxes
        self.mock_db.delete_box.return_value = True
        
        # Execute
        count = self.service.delete_offer_boxes(1)
        
        # Verify
        assert count == 3
        assert self.mock_db.delete_box.call_count == 3
    
    def test_delete_offer_boxes_partial_failure(self):
        """Test deleting boxes with some failures"""
        # Setup
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=0, max_capacity=12),
            Box(box_id="box2", offer_id=1, current_quantity=0, max_capacity=12),
            Box(box_id="box3", offer_id=1, current_quantity=0, max_capacity=12)
        ]
        self.mock_db.get_boxes_by_offer.return_value = boxes
        self.mock_db.delete_box.side_effect = [True, False, True]
        
        # Execute
        count = self.service.delete_offer_boxes(1)
        
        # Verify
        assert count == 2
    
    def test_delete_offer_boxes_no_boxes(self):
        """Test deleting when no boxes exist"""
        # Setup
        self.mock_db.get_boxes_by_offer.return_value = []
        
        # Execute
        count = self.service.delete_offer_boxes(1)
        
        # Verify
        assert count == 0
        self.mock_db.delete_box.assert_not_called()
    
    def test_delete_empty_boxes_success(self):
        """Test deleting empty non-ordered boxes"""
        # Setup
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=0, max_capacity=12, status=BoxStatus.OPEN.value),
            Box(box_id="box2", offer_id=1, current_quantity=10, max_capacity=12, status=BoxStatus.OPEN.value),
            Box(box_id="box3", offer_id=1, current_quantity=0, max_capacity=12, status=BoxStatus.OPEN.value),
            Box(box_id="box4", offer_id=1, current_quantity=0, max_capacity=12, status=BoxStatus.ORDERED.value)
        ]
        self.mock_db.get_boxes_by_offer.return_value = boxes
        self.mock_db.delete_box.return_value = True
        
        # Execute
        count = self.service.delete_empty_boxes(1)
        
        # Verify - should delete 2 empty non-ordered boxes (box1, box3)
        assert count == 2
        assert self.mock_db.delete_box.call_count == 2
    
    def test_delete_empty_boxes_preserves_ordered(self):
        """Test empty ORDERED boxes are not deleted"""
        # Setup
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=0, max_capacity=12, status=BoxStatus.ORDERED.value),
            Box(box_id="box2", offer_id=1, current_quantity=0, max_capacity=12, status=BoxStatus.ORDERED.value)
        ]
        self.mock_db.get_boxes_by_offer.return_value = boxes
        
        # Execute
        count = self.service.delete_empty_boxes(1)
        
        # Verify - no boxes deleted
        assert count == 0
        self.mock_db.delete_box.assert_not_called()
    
    def test_delete_empty_boxes_no_empty(self):
        """Test no deletion when no empty boxes"""
        # Setup
        boxes = [
            Box(box_id="box1", offer_id=1, current_quantity=10, max_capacity=12, status=BoxStatus.OPEN.value),
            Box(box_id="box2", offer_id=1, current_quantity=8, max_capacity=12, status=BoxStatus.OPEN.value)
        ]
        self.mock_db.get_boxes_by_offer.return_value = boxes
        
        # Execute
        count = self.service.delete_empty_boxes(1)
        
        # Verify
        assert count == 0
        self.mock_db.delete_box.assert_not_called()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
