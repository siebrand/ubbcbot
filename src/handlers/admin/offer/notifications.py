import time
from models.entities import AuthorizationStatus, NotificationMessage
from .base import OfferBaseHandler

class NotificationHandler(OfferBaseHandler):
    """Handler for offer notifications and announcements"""
    
    def _send_rich_offer_message(self, chat_id: int, offer, preview: bool = False, force_group: bool = False):
        """Send rich offer message using offer_details formatting"""
        # Import here to avoid circular imports
        from handlers.customer.info_commands import InfoCommands
        
        # Send announcement header for non-preview
        if not preview:
            header_message = self._t('new_offer_available')
            self._send_message(chat_id, header_message, force_group=force_group)
        
        # Create info handler instance to reuse offer details formatting
        info_handler = InfoCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        # Use the existing rich offer details method
        info_handler._send_rich_offer_details(chat_id, offer, user_id=999999)  # Use fake non-admin user ID
        
        # Add order buttons for non-preview announcements
        if not preview:
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": self._t('order_1'), "callback_data": f"order_{offer.offer_id}_1"},
                        {"text": self._t('order_2'), "callback_data": f"order_{offer.offer_id}_2"}
                    ]
                ]
            }
            
            # Send order buttons message
            button_message = self._t('order_with_command', offer_id=offer.offer_id)
            self._send_message(chat_id, button_message, reply_markup=reply_markup)

    def _notify_subscribers_rich(self, offer):
        """Send rich offer notification to all subscribers in batches using offer_details formatting"""
        # Get all approved customers
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        subscribers = [c for c in customers if getattr(c, 'subscribed_to_offers', False)]
        
        # Send in batches to avoid rate limits (30 messages per second max)
        batch_size = 25
        for i in range(0, len(subscribers), batch_size):
            batch = subscribers[i:i + batch_size]
            
            for customer in batch:
                try:
                    # Use the same rich offer message method for consistency
                    self._send_rich_offer_message(customer.telegram_user_id, offer, preview=False, force_group=False)
                except Exception as e:
                    # Log error but continue with other subscribers
                    import logging
                    logging.error(f"Failed to notify subscriber {customer.customer_id}: {e}")
            
            # Rate limiting: wait 1 second between batches
            if i + batch_size < len(subscribers):
                time.sleep(1)
