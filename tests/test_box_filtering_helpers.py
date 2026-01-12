import unittest
import sys
import os
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.entities import Box, BoxStatus
from services.box_status_manager import BoxStatusManager


class TestBoxFilteringHelpers(unittest.TestCase):
    """Test box filtering helper methods in BoxStatusManager"""
    
    def setUp(self):
        self.mock_db = Mock()
        self.manager = BoxStatusManager(self.mock_db)
    
    def test_get_delivered_boxes_filters_correctly(self):
        """Test that get_delivered_boxes returns only delivered boxes"""
        boxes = [
            Box(box_id="box1", offer_id=1, status=BoxStatus.DELIVERED.value, current_quantity=10, max_capacity=12),
            Box(box_id="box2", offer_id=1, status=BoxStatus.OPEN.value, current_quantity=5, max_capacity=12),
            Box(box_id="box3", offer_id=1, status=BoxStatus.DELIVERED.value, current_quantity=12, max_capacity=12),
            Box(box_id="box4", offer_id=1, status=BoxStatus.ORDERED.value, current_quantity=8, max_capacity=12),
        ]
        
        delivered = self.manager.get_delivered_boxes(boxes)
        
        self.assertEqual(len(delivered), 2)
        self.assertEqual(delivered[0].box_id, "box1")
        self.assertEqual(delivered[1].box_id, "box3")
    
    def test_get_delivered_boxes_empty_list(self):
        """Test get_delivered_boxes with empty list"""
        delivered = self.manager.get_delivered_boxes([])
        self.assertEqual(len(delivered), 0)
    
    def test_get_delivered_boxes_no_delivered(self):
        """Test get_delivered_boxes when no boxes are delivered"""
        boxes = [
            Box(box_id="box1", offer_id=1, status=BoxStatus.OPEN.value, current_quantity=5, max_capacity=12),
            Box(box_id="box2", offer_id=1, status=BoxStatus.ORDERED.value, current_quantity=8, max_capacity=12),
        ]
        
        delivered = self.manager.get_delivered_boxes(boxes)
        self.assertEqual(len(delivered), 0)
    
    def test_get_available_capacity_in_delivered_single_box(self):
        """Test get_available_capacity_in_delivered with single delivered box"""
        boxes = [
            Box(box_id="box1", offer_id=1, status=BoxStatus.DELIVERED.value, current_quantity=10, max_capacity=12),
        ]
        
        capacity = self.manager.get_available_capacity_in_delivered(boxes)
        self.assertEqual(capacity, 2)
    
    def test_get_available_capacity_in_delivered_multiple_boxes(self):
        """Test get_available_capacity_in_delivered with multiple delivered boxes"""
        boxes = [
            Box(box_id="box1", offer_id=1, status=BoxStatus.DELIVERED.value, current_quantity=10, max_capacity=12),
            Box(box_id="box2", offer_id=1, status=BoxStatus.DELIVERED.value, current_quantity=8, max_capacity=12),
            Box(box_id="box3", offer_id=1, status=BoxStatus.OPEN.value, current_quantity=5, max_capacity=12),
        ]
        
        capacity = self.manager.get_available_capacity_in_delivered(boxes)
        self.assertEqual(capacity, 6)  # 2 + 4 from delivered boxes only
    
    def test_get_available_capacity_in_delivered_all_full(self):
        """Test get_available_capacity_in_delivered when all delivered boxes full"""
        boxes = [
            Box(box_id="box1", offer_id=1, status=BoxStatus.DELIVERED.value, current_quantity=12, max_capacity=12),
            Box(box_id="box2", offer_id=1, status=BoxStatus.DELIVERED.value, current_quantity=12, max_capacity=12),
        ]
        
        capacity = self.manager.get_available_capacity_in_delivered(boxes)
        self.assertEqual(capacity, 0)
    
    def test_get_available_capacity_in_delivered_no_delivered(self):
        """Test get_available_capacity_in_delivered when no delivered boxes"""
        boxes = [
            Box(box_id="box1", offer_id=1, status=BoxStatus.OPEN.value, current_quantity=5, max_capacity=12),
            Box(box_id="box2", offer_id=1, status=BoxStatus.ORDERED.value, current_quantity=8, max_capacity=12),
        ]
        
        capacity = self.manager.get_available_capacity_in_delivered(boxes)
        self.assertEqual(capacity, 0)
    
    def test_get_available_capacity_in_delivered_empty_list(self):
        """Test get_available_capacity_in_delivered with empty list"""
        capacity = self.manager.get_available_capacity_in_delivered([])
        self.assertEqual(capacity, 0)
    
    def test_has_space_check_using_capacity(self):
        """Test that capacity > 0 can be used to check for available space"""
        boxes_with_space = [
            Box(box_id="box1", offer_id=1, status=BoxStatus.DELIVERED.value, current_quantity=10, max_capacity=12),
        ]
        boxes_full = [
            Box(box_id="box1", offer_id=1, status=BoxStatus.DELIVERED.value, current_quantity=12, max_capacity=12),
        ]
        
        self.assertTrue(self.manager.get_available_capacity_in_delivered(boxes_with_space) > 0)
        self.assertFalse(self.manager.get_available_capacity_in_delivered(boxes_full) > 0)


if __name__ == '__main__':
    unittest.main()
