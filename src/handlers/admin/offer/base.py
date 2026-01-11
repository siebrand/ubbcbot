import logging
from handlers.base_handler import BaseHandler

logger = logging.getLogger()

class OfferBaseHandler(BaseHandler):
    """Base class for offer-related handlers with common utilities"""
    
    VALID_BOX_SIZES = [1, 2, 3, 4, 5, 6, 8, 9, 10, 12, 15, 16, 18, 20, 24]
    
    def _validate_offer_name(self, name: str) -> tuple[bool, str]:
        """Validate offer name and return (is_valid, error_key)"""
        if len(name) > 100:
            return False, 'product_name_too_long'
        if '<' in name or '>' in name:
            return False, 'product_name_invalid_chars'
        return True, ''
    
    def _validate_box_size(self, box_size: int) -> bool:
        """Validate box size against allowed values"""
        return box_size in self.VALID_BOX_SIZES
    
    def _validate_supplier(self, supplier_name: str) -> tuple[bool, str]:
        """Validate supplier exists and is active. Returns (is_valid, error_key)"""
        supplier = self.db.get_supplier_by_name(supplier_name)
        if not supplier:
            return False, 'supplier_not_found'
        if supplier.status != "active":
            return False, 'supplier_retired_cannot_use'
        return True, ''
