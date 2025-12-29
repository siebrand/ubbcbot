from typing import Dict, Any, List, Tuple

class PaginationUtils:
    @staticmethod
    def paginate_list(items: List, page: int, page_size: int = 10) -> Tuple[List, int]:
        """Paginate a list of items"""
        total_pages = (len(items) + page_size - 1) // page_size if items else 1
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = items[start_idx:end_idx]
        return page_items, total_pages
    
    @staticmethod
    def build_pagination_keyboard(current_page: int, total_pages: int, entity_type: str, 
                                filters: str = "", enhanced: bool = False) -> Dict[str, Any]:
        """Build pagination keyboard for list commands"""
        keyboard = []
        
        if total_pages <= 1:
            return {"inline_keyboard": keyboard}
        
        # Build callback data with filters
        callback_prefix = f"{entity_type}_{filters}" if filters else entity_type
        
        nav_buttons = []
        
        if enhanced:
            # Enhanced pagination with first/last buttons
            if current_page > 1:
                nav_buttons.append({"text": "⏮️", "callback_data": f"page_{callback_prefix}_1"})
                nav_buttons.append({"text": "◀️", "callback_data": f"page_{callback_prefix}_{current_page - 1}"})
            
            nav_buttons.append({"text": f"{current_page}/{total_pages}", "callback_data": "page_info"})
            
            if current_page < total_pages:
                nav_buttons.append({"text": "▶️", "callback_data": f"page_{callback_prefix}_{current_page + 1}"})
                nav_buttons.append({"text": "⏭️", "callback_data": f"page_{callback_prefix}_{total_pages}"})
            
            keyboard.append(nav_buttons)
            
            # Add jump buttons for larger lists
            if total_pages > 5:
                jump_buttons = []
                start_page = max(1, current_page - 2)
                end_page = min(total_pages, current_page + 2)
                
                for p in range(start_page, end_page + 1):
                    if p != current_page:
                        jump_buttons.append({"text": str(p), "callback_data": f"page_{callback_prefix}_{p}"})
                
                if jump_buttons:
                    keyboard.append(jump_buttons)
        else:
            # Standard pagination
            if current_page > 1:
                nav_buttons.append({"text": "◀️ Previous", "callback_data": f"page_{callback_prefix}_{current_page - 1}"})
            
            nav_buttons.append({"text": f"Page {current_page}/{total_pages}", "callback_data": "page_info"})
            
            if current_page < total_pages:
                nav_buttons.append({"text": "Next ▶️", "callback_data": f"page_{callback_prefix}_{current_page + 1}"})
            
            keyboard.append(nav_buttons)
        
        return {"inline_keyboard": keyboard}