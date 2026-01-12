import logging
from typing import Optional, List
from models.entities import Box, BoxStatus, OfferStatus

logger = logging.getLogger()

class BoxStatusManager:
    """Centralized service for all box status updates"""
    
    def __init__(self, db):
        self.db = db
    
    def get_delivered_boxes(self, boxes: List[Box]) -> List[Box]:
        """Filter boxes to only delivered status"""
        return [box for box in boxes if box.status == BoxStatus.DELIVERED.value]
    
    def get_available_capacity_in_delivered(self, boxes: List[Box]) -> int:
        """Calculate total available capacity in delivered boxes"""
        delivered_boxes = self.get_delivered_boxes(boxes)
        return sum(
            box.max_capacity - box.current_quantity 
            for box in delivered_boxes 
            if box.current_quantity < box.max_capacity
        )
    
    def update_box_after_order_placement(self, box_id: str, quantity_added: int) -> bool:
        """Update box status after adding an order"""
        box = self.db.get_box(box_id)
        if not box:
            logger.error(f"Box {box_id} not found")
            return False
        
        new_quantity = box.current_quantity + quantity_added
        updates = {'current_quantity': new_quantity}
        
        # Update status if not already ORDERED
        if box.status != BoxStatus.ORDERED.value:
            if new_quantity >= box.max_capacity:
                updates['status'] = BoxStatus.FULL.value
        
        return self.db.update_box(box_id, updates)
    
    def update_box_after_order_cancellation(self, box_id: str, quantity_removed: int) -> bool:
        """Update box status after cancelling an order"""
        box = self.db.get_box(box_id)
        if not box:
            logger.error(f"Box {box_id} not found")
            return False
        
        new_quantity = box.current_quantity - quantity_removed
        updates = {'current_quantity': new_quantity}
        
        # Update status if not already ORDERED
        if box.status != BoxStatus.ORDERED.value:
            if new_quantity < box.max_capacity:
                updates['status'] = BoxStatus.OPEN.value
        
        return self.db.update_box(box_id, updates)
    
    def mark_boxes_as_ordered(self, box_ids: list) -> list:
        """Mark multiple boxes as ORDERED, returns list of updated box objects"""
        updated_boxes = []
        for box_id in box_ids:
            if self.db.update_box(box_id, {'status': BoxStatus.ORDERED.value}):
                box = self.db.get_box(box_id)
                if box:
                    updated_boxes.append(box)
        return updated_boxes
    
    def mark_box_as_delivered(self, box_id: str) -> Optional[Box]:
        """Mark box as DELIVERED, returns updated box object or None"""
        if self.db.update_box(box_id, {'status': BoxStatus.DELIVERED.value}):
            return self.db.get_box(box_id)
        return None
    
    def update_offer_status_after_change(self, offer_id: int) -> Optional[str]:
        """
        Check and update offer status based on box states
        Returns: new status if changed, None otherwise
        """
        offer = self.db.get_offer(offer_id)
        if not offer or offer.status not in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value, OfferStatus.IMPORT.value]:
            return None
        
        boxes = self.db.get_boxes_by_offer(offer_id)
        if not boxes:
            return None
        
        # Check if there are delivered boxes
        delivered_boxes = self.get_delivered_boxes(boxes)
        
        new_status = None
        if delivered_boxes:
            # Use delivered box logic: check capacity in delivered boxes
            capacity = self.get_available_capacity_in_delivered(boxes)
            
            if capacity == 0:
                # All delivered boxes full -> SOLD_OUT
                if offer.status != OfferStatus.SOLD_OUT.value:
                    self.db.update_offer(offer_id, {'status': OfferStatus.SOLD_OUT.value})
                    new_status = OfferStatus.SOLD_OUT.value
            else:
                # Delivered boxes have space -> ACTIVE
                if offer.status != OfferStatus.ACTIVE.value:
                    self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value})
                    new_status = OfferStatus.ACTIVE.value
        else:
            # No delivered boxes: fall back to existing logic
            has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes)
            has_available_space = any(box.current_quantity < box.max_capacity for box in boxes)
            
            if has_ordered_boxes and not has_available_space:
                if offer.status != OfferStatus.SOLD_OUT.value:
                    self.db.update_offer(offer_id, {'status': OfferStatus.SOLD_OUT.value})
                    new_status = OfferStatus.SOLD_OUT.value
            else:
                if offer.status != OfferStatus.ACTIVE.value:
                    self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value})
                    new_status = OfferStatus.ACTIVE.value
        
        return new_status
