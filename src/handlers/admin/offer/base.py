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
        return self._validate_html_content(name)
    
    def _validate_html_content(self, content: str) -> tuple[bool, str]:
        """Validate HTML content to prevent parse errors. Returns (is_valid, error_key)"""
        # Test if Telegram would accept this HTML by checking tag balance
        import re
        
        # Find all HTML tags
        tags = re.findall(r'<(/?)([a-zA-Z]+)[^>]*>', content)
        stack = []
        
        for is_closing, tag_name in tags:
            if is_closing == '/':
                # Closing tag
                if not stack or stack[-1] != tag_name:
                    return False, 'product_name_invalid_chars'
                stack.pop()
            else:
                # Opening tag
                stack.append(tag_name)
        
        # Check if all tags are closed
        if stack:
            return False, 'product_name_invalid_chars'
        
        # Check for malformed patterns like "<0,3%"
        if re.search(r'<(?![a-zA-Z/])', content):
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
