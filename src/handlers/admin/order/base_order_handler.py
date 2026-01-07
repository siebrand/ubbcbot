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
        
        # Check if ALL boxes are full+ status (full, ordered, or delivered) AND completely filled
        all_full_and_complete = all(
            box.status in ['full', 'ordered', 'delivered'] and box.current_quantity >= box.max_capacity 
            for box in boxes
        )
        
        if all_full_and_complete:
            self.db.update_offer(offer_id, {'status': OfferStatus.SOLD_OUT.value})
        else:
            self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value})