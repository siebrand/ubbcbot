from typing import Dict, Any, Tuple, Optional, List
from models.entities import AuthorizationStatus
from utils.timezone import to_cet_string

class ValidationUtils:
    def __init__(self, db, t_func):
        self.db = db
        self._t = t_func
    
    def validate_order_limit(self, customer_id: int, offer_id: int, quantity: int, limit: int = 5) -> Tuple[bool, Optional[str]]:
        """Validate order quantity against customer limit"""
        existing_orders = [o for o in self.db.get_orders_by_customer(customer_id) 
                         if o.offer_id == offer_id and o.status in ['pending', 'ordered']]
        total_existing = sum(order.quantity for order in existing_orders)
        
        if total_existing + quantity > limit:
            offer = self.db.get_offer(offer_id)
            message = self._t('order_limit_exceeded', 
                            offer_name=offer.name if offer else 'Unknown', 
                            total_existing=total_existing)
            message += "\n\n"
            for order in existing_orders:
                order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
            
            remaining_allowed = limit - total_existing
            if remaining_allowed > 0:
                message += self._t('remaining_units_allowed', remaining=remaining_allowed)
            else:
                message += self._t('limit_reached')
            
            return False, message
        
        return True, None
    
    def match_customers(self, identifier: str, customers: list) -> list:
        """Match customers by identifier (name or username) - shared matching logic"""
        search_lower = identifier.lower()
        matches = []
        for customer in customers:
            first_name = (customer.first_name or "").lower()
            last_name = (customer.last_name or "").lower()
            username = (customer.username or "").lower()
            full_name = f"{first_name} {last_name}".strip()

            if (search_lower in first_name or search_lower in last_name or 
                search_lower in username or search_lower in full_name):
                matches.append(customer)
        return matches
    
    def find_customer_with_disambiguation(self, identifier: str, chat_id: int, callback_prefix: str, status_filter: str = None) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
        """Find customer with disambiguation UI if multiple matches"""
        if status_filter:
            all_customers = self.db.get_customers_by_status(status_filter)
        else:
            all_customers = []
            all_customers.extend(self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value))
            all_customers.extend(self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value))
            all_customers.extend(self.db.get_customers_by_status(AuthorizationStatus.REJECTED.value))
        
        matches = self.match_customers(identifier, all_customers)
        
        if not matches:
            return None, {'status': 'user_not_found', 'message': self._t('user_not_found', identifier=identifier)}
        
        if len(matches) == 1:
            return matches[0], None
        
        # Multiple matches - show disambiguation
        message = self._t('multiple_users_found', identifier=identifier) + "\n\n"
        keyboard_buttons = []
        
        for customer in matches[:10]:  # Limit to 10 matches
            full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            username_part = f" (@{customer.username})" if customer.username else ""
            
            keyboard_buttons.append([{
                "text": f"📝 {full_name}{username_part}",
                "callback_data": f"{callback_prefix}_{customer.customer_id}"
            }])
        
        keyboard_buttons.append([{"text": self._t('cancel'), "callback_data": "cancel_action"}])
        keyboard = {"inline_keyboard": keyboard_buttons}
        
        return None, {'status': 'disambiguation_shown', 'message': message, 'keyboard': keyboard}
    
    def validate_and_get_offer(self, args: List[str]) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
        """Validate offer ID and return offer or error"""
        if not args:
            return None, {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            if not offer:
                return None, {'status': 'offer_not_found', 'message': self._t('offer_not_found')}
            return offer, None
        except ValueError:
            return None, {'status': 'invalid_format', 'message': self._t('invalid_offer_id')}
    
    def validate_and_get_customer(self, args: List[str]) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
        """Validate customer ID and return customer or error"""
        if not args:
            return None, {'status': 'invalid_args'}
        
        try:
            customer_id = int(args[0])
            customer = self.db.get_customer(customer_id)
            if not customer:
                return None, {'status': 'customer_not_found', 'message': self._t('customer_not_found')}
            return customer, None
        except ValueError:
            return None, {'status': 'invalid_format', 'message': self._t('invalid_customer_id')}