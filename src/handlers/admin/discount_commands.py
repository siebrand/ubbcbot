from typing import Dict, Any
from decimal import Decimal
from datetime import datetime, UTC, timedelta
from handlers.base_handler import BaseHandler
from models.entities import DiscountPeriod, DiscountStatus

class DiscountCommands(BaseHandler):
    def handle_create_discount(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /create_discount command"""
        if len(args) < 1:
            self._send_message(chat_id, self._t('usage_create_discount', chat_id))
            return {'status': 'invalid_args'}

        try:
            percentage = float(args[0])
            hours = int(args[1]) if len(args) > 1 else 24  # Default 24 hours
            
            if percentage <= 0 or percentage >= 100:
                self._send_message(chat_id, self._t('discount_percentage_invalid', chat_id))
                return {'status': 'invalid_percentage'}
            
            if hours <= 0:
                self._send_message(chat_id, self._t('discount_duration_invalid', chat_id))
                return {'status': 'invalid_duration'}
            
            # Check for existing active discount
            existing = self.db.get_active_discount()
            if existing:
                self._send_message(chat_id, self._t('discount_already_exists', chat_id, percentage=existing.discount_percentage))
                return {'status': 'discount_exists'}
            
            # Create discount
            end_time = datetime.now(UTC) + timedelta(hours=hours)
            discount = DiscountPeriod(
                discount_percentage=Decimal(str(percentage)),
                end_time=end_time
            )
            
            if self.db.create_discount(discount):
                from utils.timezone import to_cet_string
                self._send_message(chat_id, self._t('discount_created', 
                    percentage=percentage, 
                    end_time=to_cet_string(end_time)
                ))
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_create_discount', chat_id))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_percentage_format', chat_id))
            return {'status': 'invalid_format'}
    
    def handle_cancel_discount(self, chat_id: int) -> Dict[str, Any]:
        """Handle /cancel_discount command"""
        discount = self.db.get_active_discount()
        if not discount:
            self._send_message(chat_id, self._t('no_active_discount', chat_id))
            return {'status': 'no_discount'}
        
        if self.db.update_discount(discount.discount_id, {'status': DiscountStatus.CANCELLED.value}):
            self._send_message(chat_id, self._t('discount_cancelled', chat_id, percentage=discount.discount_percentage))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_cancel_discount', chat_id))
            return {'status': 'error'}
    
    def handle_discount_status(self, chat_id: int) -> Dict[str, Any]:
        """Handle /discount_status command"""
        discount = self.db.get_active_discount()
        if not discount:
            self._send_message(chat_id, self._t('no_active_discount_info', chat_id))
            return {'status': 'no_discount'}
        
        from utils.timezone import to_cet_string
        if discount.end_time:
            self._send_message(chat_id, self._t('active_discount_status',
                percentage=discount.discount_percentage,
                start_time=to_cet_string(discount.start_time),
                end_time=to_cet_string(discount.end_time)
            ))
        else:
            self._send_message(chat_id, self._t('active_discount_unlimited',
                percentage=discount.discount_percentage,
                start_time=to_cet_string(discount.start_time)
            ))
        return {'status': 'success'}