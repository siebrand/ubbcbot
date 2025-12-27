import os
from typing import Dict, Any
from decimal import Decimal
from models.entities import Offer, Box, Order, BoxStatus, OfferStatus
from .base import OfferBaseHandler

class OfferCreationHandler(OfferBaseHandler):
    """Handler for offer creation and publishing"""
    
    def handle_create_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /create_offer command - creates draft offer"""
        if len(args) < 4:
            self._send_message(chat_id, self._t('usage_create_offer'))
            return {'status': 'invalid_args'}

        try:
            supplier_name = args[0]
            price = float(args[-2])
            box_size = int(args[-1])
            
            # Validate and sanitize name
            name = ' '.join(args[1:-2]).strip()
            is_valid, error_key = self._validate_offer_name(name)
            if not is_valid:
                self._send_message(chat_id, self._t(error_key))
                return {'status': 'invalid_name'}

            # Validate box size
            if not self._validate_box_size(box_size):
                self._send_message(chat_id, self._t('invalid_box_size', sizes=self.VALID_BOX_SIZES))
                return {'status': 'invalid_box_size'}

            # Check supplier exists and is active
            is_valid, error_key = self._validate_supplier(supplier_name)
            if not is_valid:
                if error_key == 'supplier_retired_cannot_use':
                    self._send_message(chat_id, self._t(error_key, name=supplier_name))
                else:
                    self._send_message(chat_id, self._t(error_key))
                return {'status': error_key}

            # Create draft offer
            offer = Offer(
                supplier_name=supplier_name,
                name=name,
                price_per_unit=Decimal(str(price)),
                wholesale_box_size=box_size,
                min_quantity_breakeven=max(1, int(box_size * 0.8)),
                status=OfferStatus.DRAFT.value
            )

            if self.db.create_offer(offer):
                message = self._t('draft_offer_created', 
                    offer_id=offer.offer_id,
                    name=offer.name,
                    price=offer.price_per_unit,
                    box_size=offer.wholesale_box_size,
                    status=offer.status
                )
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('edit_details'), "callback_data": f"offer_details_{offer.offer_id}_edit"}],
                        [{"text": self._t('view_details'), "callback_data": f"offer_details_{offer.offer_id}"}],
                        [{"text": self._t('publish_offer'), "callback_data": f"publish_offer_{offer.offer_id}"}]
                    ]
                }
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_create_offer'))
                return {'status': 'error'}

        except (ValueError, IndexError) as e:
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'invalid_format'}

    def handle_publish_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /publish_offer command"""
        error = self._validate_args(args, 1, 'usage_publish_offer', chat_id)
        if error:
            return error

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if offer.status != OfferStatus.DRAFT.value:
                self._send_message(chat_id, self._t('offer_not_draft', status=offer.status))
                return {'status': 'offer_not_draft'}
            
            # Update offer status to active
            if self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value}):
                # Create initial box
                box = Box(
                    offer_id=offer_id,
                    max_capacity=int(offer.wholesale_box_size),
                    min_breakeven=int(offer.min_quantity_breakeven)
                )
                self.db.create_box(box)

                # Auto-order 1 unit for admin
                admin_customer = self.db.get_customer_by_telegram_id(self.admin_user_id)
                if admin_customer:
                    admin_order = Order(
                        customer_id=admin_customer.customer_id,
                        box_id=box.box_id,
                        offer_id=offer_id,
                        quantity=1,
                        unit_price=offer.price_per_unit,
                        total_price=offer.price_per_unit
                    )
                    self.db.create_order(admin_order)
                    
                    # Update box quantity
                    updates = {'current_quantity': 1}
                    if 1 >= box.max_capacity:
                        updates['status'] = BoxStatus.FULL.value
                    elif 1 >= box.min_breakeven:
                        updates['status'] = BoxStatus.MINIMUM_REACHED.value
                    
                    self.db.update_box(box.box_id, updates)

                # Update offer object for announcement
                offer.status = OfferStatus.ACTIVE.value
                
                # Announce offer to default group and subscribers
                self._announce_offer(offer)
                
                self._send_message(chat_id, self._t('offer_published_announced', offer_id=offer_id))
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_publish_offer'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}

    def _announce_offer(self, offer):
        """Announce new offer to default group and subscribers using rich format"""
        default_group_id = os.environ.get('DEFAULT_GROUP_ID')
        
        # Send rich offer message to default group
        if default_group_id:
            self._send_rich_offer_message(int(default_group_id), offer, force_group=True)
        
        # Send to subscribers in batches
        self._notify_subscribers_rich(offer)
