from decimal import Decimal
from typing import Dict, Any

from models.entities import OfferStatus
from .base import OfferBaseHandler


class OfferEditingHandler(OfferBaseHandler):
    """Handler for offer editing operations"""

    VALID_STATUSES = {
        'import': (OfferStatus.IMPORT, [OfferStatus.DRAFT]),
        'active': (OfferStatus.ACTIVE, None),
        'soldout': (OfferStatus.SOLD_OUT, None),
        'completed': (OfferStatus.COMPLETED, None),
    }

    def handle_offer_status(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /offer_status command - change offer status"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_offer_status'))
            return {'status': 'invalid_args'}

        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error

        new_status = args[1].lower()

        if new_status not in self.VALID_STATUSES:
            return self._send_error(chat_id, 'invalid_offer_status', 'invalid_status',
                                    status=new_status)

        target_status, required_from = self.VALID_STATUSES[new_status]

        if required_from and OfferStatus(offer.status) not in required_from:
            return self._send_error(chat_id, 'offer_status_must_be_draft', 'wrong_status',
                                    current_status=offer.status)

        if self.db.update_offer(offer.offer_id, {'status': target_status.value}):
            return self._send_success(chat_id, 'offer_status_changed', 'success',
                                      offer_id=offer.offer_id, name=offer.name, status=target_status.value)
        else:
            return self._send_error(chat_id, 'failed_update_offer_status', 'error')

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
                # Send confirmation and return to edit interface
                message = self._t('offer_name_updated',
                                  old_name=offer.name,
                                  new_name=new_name
                                  )
                self._send_message(chat_id, message)

                # Return to edit interface
                updated_offer = self.db.get_offer(offer_id)
                return self.handlers['info'].handle_view_offer(chat_id, chat_id, [str(offer_id), 'edit'])
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
                # Send confirmation and return to edit interface
                message = self._t('offer_price_updated',
                                  old_price=offer.price_per_unit,
                                  new_price=new_price
                                  )
                self._send_message(chat_id, message)

                # Return to edit interface
                return self.handlers['info'].handle_view_offer(chat_id, chat_id, [str(offer_id), 'edit'])
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
                self._send_message(chat_id, self._t('description_too_long'))
                # Return to edit interface
                return self.handlers['info'].handle_view_offer(chat_id, chat_id, [str(offer_id), 'edit'])

            # Validate HTML in description
            is_valid, error_key = self._validate_html_content(new_description)
            if not is_valid:
                self._send_message(chat_id, self._t(error_key))
                return {'status': 'invalid_description'}

            offer = self.db.get_offer(offer_id)
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}

            if self.db.update_offer(offer_id, {'description': new_description}):
                old_desc = offer.description or self._t('not_set')

                # Send confirmation and return to edit interface
                message = self._t('offer_description_updated',
                                  old_desc=old_desc,
                                  new_desc=new_description
                                  )
                self._send_message(chat_id, message)

                # Return to edit interface
                return self.handlers['info'].handle_view_offer(chat_id, chat_id, [str(offer_id), 'edit'])
            else:
                self._send_message(chat_id, self._t('failed_update_offer_description'))
                return {'status': 'error'}

        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
