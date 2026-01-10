from typing import Dict, Any
from decimal import Decimal
from .base import OfferBaseHandler

class OfferEditingHandler(OfferBaseHandler):
    """Handler for offer editing operations"""
    
    def handle_update_offer_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_offer_name command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_update_offer_name'))
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            new_name = ' '.join(args[1:]).strip()
            
            is_valid, error_key = self._validate_offer_name(new_name)
            if not is_valid:
                self._send_message(chat_id, self._t(error_key))
                return {'status': 'invalid_name'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if self.db.update_offer(offer_id, {'name': new_name}):
                # Send confirmation and return to edit menu
                message = self._t('offer_name_updated',
                    old_name=offer.name,
                    new_name=new_name
                )
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('continue_editing'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('view_details'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('done_editing'), "callback_data": "done_editing"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_update_offer_name'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
    
    def handle_update_offer_price(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_offer_price command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_update_offer_price'))
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            new_price = float(args[1])
            
            if new_price <= 0:
                self._send_message(chat_id, self._t('price_must_positive'))
                return {'status': 'invalid_price'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if self.db.update_offer(offer_id, {'price_per_unit': Decimal(str(new_price))}):
                # Send confirmation and return to edit menu
                message = self._t('offer_price_updated',
                    old_price=offer.price_per_unit,
                    new_price=new_price
                )
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('continue_editing'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('view_details'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('done_editing'), "callback_data": "done_editing"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_update_offer_price'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_price_format'))
            return {'status': 'invalid_format'}
    
    def handle_update_offer_description(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_offer_description command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_update_offer_description'))
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            new_description = ' '.join(args[1:]).strip()
            
            if len(new_description) > 1000:
                # Return to edit interface instead of exiting
                self._send_message(chat_id, self._t('description_too_long'))
                
                # Show edit interface again
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('continue_editing'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('done_editing'), "callback_data": "done_editing"}]
                    ]
                }
                self._send_message(chat_id, self._t('select_edit', chat_id), reply_markup=keyboard)
                return {'status': 'invalid_description'}
            
            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if self.db.update_offer(offer_id, {'description': new_description}):
                old_desc = offer.description or self._t('not_set')
                
                # Send confirmation with button to continue editing
                message = self._t('offer_description_updated',
                    old_desc=old_desc,
                    new_desc=new_description
                )
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('continue_editing'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('view_details'), "callback_data": f"offer_details_{offer_id}"}],
                        [{"text": self._t('done_editing'), "callback_data": "done_editing"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_update_offer_description'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
