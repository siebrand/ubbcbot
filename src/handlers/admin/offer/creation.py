import os
import logging
from typing import Dict, Any
from decimal import Decimal
from models.entities import Offer, Box, Order, BoxStatus, OfferStatus
from .base import OfferBaseHandler
from services.box_status_manager import BoxStatusManager

logger = logging.getLogger()

class OfferCreationHandler(OfferBaseHandler):
    """Handler for offer creation and publishing"""
    
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)
    
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
                        [{"text": self._t('publish_offer_btn'), "callback_data": f"publish_offer_{offer.offer_id}"}]
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
                # Silently ignore if offer is already published
                return {'status': 'already_published'}
            
            box_size = offer.wholesale_box_size

            # Update offer status to active
            if self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value}):
                # Update offer object for announcement
                offer.status = OfferStatus.ACTIVE.value
                # Create initial box
                box = Box(
                    offer_id=offer_id,
                    max_capacity=box_size
                )
                created_box = self.db.create_box(box)
                
                if not created_box:
                    logger.error(f"Failed to create box for offer {offer_id}")
                    self._send_message(chat_id, self._t('failed_publish_offer'))
                    return {'status': 'error'}
                
                # Auto-order 1 unit for admin
                admin_customer = self.db.get_customer_by_telegram_id(self.admin_user_id)
                if admin_customer:
                    admin_order = Order(
                        customer_id=admin_customer.customer_id,
                        box_id=created_box.box_id,
                        offer_id=offer_id,
                        quantity=1,
                        unit_price=offer.price_per_unit,
                        total_price=offer.price_per_unit
                    )
                    created_admin_order = self.db.create_order(admin_order, admin_id=self.admin_user_id)
                    
                    if not created_admin_order:
                        logger.error(f"Failed to create admin order for offer {offer_id}")
                        self._send_message(chat_id, self._t('failed_publish_offer'))
                        return {'status': 'error'}
                    
                    # Update box quantity via service
                    if not self.box_status_manager.update_box_after_order_placement(created_box.box_id, 1):
                        logger.error(f"Failed to update box {created_box.box_id} for offer {offer_id}")
                        self._send_message(chat_id, self._t('failed_publish_offer'))
                        return {'status': 'error'}
                else:
                    logger.error(f"Admin customer not found for user_id {self.admin_user_id}")
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
        
        box_size = offer.wholesale_box_size

        # Send rich offer message to default group (without buttons)
        if default_group_id:
            group_result = self._send_rich_offer_message(int(default_group_id), offer, force_group=True, include_buttons=False)

        # Send to subscribers in batches
        subscriber_result = self._notify_subscribers_rich(offer)
