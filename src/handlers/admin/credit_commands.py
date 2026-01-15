from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from services.credit_service import CreditService
from utils.validation import ValidationUtils


class CreditCommands(BaseHandler):
    """Admin commands for credit management"""
    
    def __init__(self, db_service, bot_service):
        super().__init__(db_service, bot_service)
        self.credit_service = CreditService(db_service)
        self.validation = ValidationUtils(db_service, self._t)
    
    def handle_credit(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /credit <username> <amount> [reason] command"""
        if len(args) < 2:
            return self._send_error(chat_id, 'usage_credit', 'invalid_format', user_id=chat_id)
        
        username = args[0].lstrip('@')
        
        try:
            amount = Decimal(args[1])
        except (ValueError, TypeError):
            return self._send_error(chat_id, 'invalid_amount', 'invalid_format', user_id=chat_id)
        
        reason = ' '.join(args[2:]) if len(args) > 2 else ''
        
        # Find customer using validation utility
        customer, error = self.validation.find_customer_with_disambiguation(
            username, 
            chat_id, 
            'credit_customer',
            status_filter='approved'
        )
        
        if error:
            if error.get('keyboard'):
                self._send_message(chat_id, error['message'], keyboard=error['keyboard'])
            else:
                self._send_message(chat_id, error['message'])
            return error
        
        # Issue credit
        success = self.credit_service.issue_credit(
            customer.customer_id,
            amount,
            reason,
            chat_id
        )
        
        if success:
            # Get new balance
            new_balance = self.credit_service.get_customer_credit_balance(customer.customer_id)
            
            # Notify customer
            if customer.telegram_user_id > 0:
                customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                self._send_message(
                    customer.telegram_user_id,
                    self._t('credit_notification', customer.telegram_user_id,
                        amount=amount,
                        reason=reason or 'No reason provided',
                        balance=new_balance
                    )
                )
            
            # Confirm to admin
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            return self._send_success(chat_id, 'credit_issued_success', user_id=chat_id,
                amount=amount, customer_name=customer_name)
        else:
            return self._send_error(chat_id, 'failed_issue_credit', 'error', user_id=chat_id)
