from typing import Dict, Any
from decimal import Decimal
from datetime import datetime, UTC, timedelta
from handlers.base_handler import BaseHandler
from models.entities import DiscountPeriod, DiscountStatus

class DiscountCommands(BaseHandler):
    def handle_create_discount(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /create_discount command"""
        if len(args) < 1:
            self._send_message(chat_id, "Usage: /create_discount <percentage> [hours]")
            return {'status': 'invalid_args'}

        try:
            percentage = float(args[0])
            hours = int(args[1]) if len(args) > 1 else 24  # Default 24 hours
            
            if percentage <= 0 or percentage >= 100:
                self._send_message(chat_id, "❌ Discount percentage must be between 0 and 100")
                return {'status': 'invalid_percentage'}
            
            if hours <= 0:
                self._send_message(chat_id, "❌ Duration must be positive")
                return {'status': 'invalid_duration'}
            
            # Check for existing active discount
            existing = self.db.get_active_discount()
            if existing:
                self._send_message(chat_id, f"❌ Active discount already exists: {existing.discount_percentage}% OFF")
                return {'status': 'discount_exists'}
            
            # Create discount
            end_time = datetime.now(UTC) + timedelta(hours=hours)
            discount = DiscountPeriod(
                discount_percentage=Decimal(str(percentage)),
                end_time=end_time
            )
            
            if self.db.create_discount(discount):
                from utils.timezone import to_cet_string
                message = f"✅ Discount created: {percentage}% OFF\n"
                message += f"Valid until: {to_cet_string(end_time)}"
                self._send_message(chat_id, message)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to create discount")
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, "❌ Invalid percentage or duration format")
            return {'status': 'invalid_format'}
    
    def handle_cancel_discount(self, chat_id: int) -> Dict[str, Any]:
        """Handle /cancel_discount command"""
        discount = self.db.get_active_discount()
        if not discount:
            self._send_message(chat_id, "❌ No active discount found")
            return {'status': 'no_discount'}
        
        if self.db.update_discount(discount.discount_id, {'status': DiscountStatus.CANCELLED.value}):
            self._send_message(chat_id, f"✅ Discount cancelled: {discount.discount_percentage}% OFF")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to cancel discount")
            return {'status': 'error'}
    
    def handle_discount_status(self, chat_id: int) -> Dict[str, Any]:
        """Handle /discount_status command"""
        discount = self.db.get_active_discount()
        if not discount:
            self._send_message(chat_id, "No active discount")
            return {'status': 'no_discount'}
        
        from utils.timezone import to_cet_string
        message = f"🎉 Active Discount: {discount.discount_percentage}% OFF\n"
        message += f"Started: {to_cet_string(discount.start_time)}\n"
        if discount.end_time:
            message += f"Ends: {to_cet_string(discount.end_time)}"
        else:
            message += "Duration: Unlimited"
        
        self._send_message(chat_id, message)
        return {'status': 'success'}