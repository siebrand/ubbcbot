import logging
from typing import List
from models.entities import Box

logger = logging.getLogger()

class BoxDeletionService:
    """Centralized service for all box deletion operations"""
    
    def __init__(self, db):
        self.db = db
    
    def delete_offer_boxes(self, offer_id: int) -> int:
        """Delete all boxes for an offer, returns count deleted"""
        boxes = self.db.get_boxes_by_offer(offer_id)
        deleted_count = 0
        for box in boxes:
            if self.db.delete_box(box.box_id):
                deleted_count += 1
        return deleted_count

    # @todo Check whether this is really necessary, or maybe only when processing delivery?
    def delete_excess_boxes(self, offer_id: int, keep_count: int) -> int:
        """Delete excess boxes beyond keep_count, returns count deleted"""
        boxes = self.db.get_boxes_by_offer(offer_id)
        
        # Sort boxes: keep ORDERED boxes first, then by creation date
        from models.entities import BoxStatus
        ordered_boxes = [b for b in boxes if b.status == BoxStatus.ORDERED.value]
        non_ordered_boxes = [b for b in boxes if b.status != BoxStatus.ORDERED.value]
        
        # Calculate how many to delete
        current_count = len(boxes)
        if current_count <= keep_count:
            return 0
        
        # Delete from non-ordered boxes first
        to_delete = current_count - keep_count
        deleted_count = 0
        
        for box in non_ordered_boxes:
            if deleted_count >= to_delete:
                break
            if self.db.delete_box(box.box_id):
                deleted_count += 1
        
        return deleted_count
    
    def delete_empty_boxes(self, offer_id: int) -> int:
        """Delete boxes with 0 quantity that are not ORDERED, returns count deleted"""
        from models.entities import BoxStatus
        boxes = self.db.get_boxes_by_offer(offer_id)
        empty_boxes = [b for b in boxes if b.current_quantity == 0 and b.status != BoxStatus.ORDERED.value]
        
        deleted_count = 0
        for box in empty_boxes:
            if self.db.delete_box(box.box_id):
                deleted_count += 1
        
        return deleted_count
