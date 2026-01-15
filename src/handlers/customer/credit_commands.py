from typing import Dict, Any
from handlers.base_handler import BaseHandler
from services.credit_service import CreditService


class CustomerCreditCommands(BaseHandler):
    """Customer commands for viewing credit"""
    
    def __init__(self, db_service, bot_service):
        super().__init__(db_service, bot_service)
        self.credit_service = CreditService(db_service)
    
    def handle_my_credit(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /my_credit command"""
        # Get customer
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            return self._send_error(chat_id, 'must_register', 'unauthorized', user_id=user_id)
        
        # Get credit balance
        balance = self.credit_service.get_customer_credit_balance(customer.customer_id)
        
        if balance == 0:
            message = self._t('no_credit_balance', user_id)
        else:
            message = self._t('my_credit_balance', user_id, balance=balance)
        
        self._send_message(chat_id, message)
        return {'status': 'success'}
