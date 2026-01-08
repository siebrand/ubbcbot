from typing import Dict, Any
from handlers.base_handler import BaseHandler
from models.entities import OfferStatus

class BaseOrderHandler(BaseHandler):
    """Base class for order-related handlers with shared utilities"""
    
    def _check_offer_status_after_change(self, offer_id: int):
        """Check if offer should be SOLD_OUT or ACTIVE based on box states"""
        offer = self.db.get_offer(offer_id)
        if not offer or offer.status not in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value]:
            return
        
        boxes = self.db.get_boxes_by_offer(offer_id)
        if not boxes:
            return
        
        # Check if there's at least one box that has been ordered
        has_ordered_boxes = any(box.status == 'ordered' for box in boxes)
        
        # Check if there's any available space in ANY box (including ordered boxes)
        has_available_space = any(box.current_quantity < box.max_capacity for box in boxes)
        
        # Offer is sold out if at least one box is ordered AND no available space exists in any box
        if has_ordered_boxes and not has_available_space:
            self.db.update_offer(offer_id, {'status': OfferStatus.SOLD_OUT.value})
        else:
            self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value})