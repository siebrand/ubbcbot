import logging
from typing import Optional
from models.entities import Box, BoxStatus, OfferStatus

logger = logging.getLogger()

class BoxStatusManager:
    """Centralized service for all box status updates"""
    
    def __init__(self, db):
        self.db = db
    
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
        if not offer or offer.status not in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value]:
            return None
        
        boxes = self.db.get_boxes_by_offer(offer_id)
        if not boxes:
            return None
        
        # Check if there's at least one box that has been ordered
        has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes)
        
        # Check if there's any available space in ANY box
        has_available_space = any(box.current_quantity < box.max_capacity for box in boxes)
        
        # Offer is sold out if at least one box is ordered AND no available space exists
        new_status = None
        if has_ordered_boxes and not has_available_space:
            if offer.status != OfferStatus.SOLD_OUT.value:
                self.db.update_offer(offer_id, {'status': OfferStatus.SOLD_OUT.value})
                new_status = OfferStatus.SOLD_OUT.value
        else:
            if offer.status != OfferStatus.ACTIVE.value:
                self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value})
                new_status = OfferStatus.ACTIVE.value
        
        return new_status
