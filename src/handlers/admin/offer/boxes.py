from typing import Dict, Any
from models.entities import Box, BoxStatus, OfferStatus
from .base import OfferBaseHandler

class BoxManagementHandler(OfferBaseHandler):
    """Handler for box management operations"""
    
    def handle_add_box(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_box command"""
        error = self._validate_args(args, 1, 'usage_add_box', chat_id)
        if error:
            return error

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            # Create new box
            box = Box(
                offer_id=offer_id,
                max_capacity=offer.wholesale_box_size,
                min_breakeven=offer.min_quantity_breakeven
            )
            
            if self.db.create_box(box):
                # Update offer status from sold_out to active if needed
                if offer.status == OfferStatus.SOLD_OUT.value:
                    self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value})
                    self._send_message(chat_id, self._t('box_added_offer_active', offer_id=offer_id))
                else:
                    self._send_message(chat_id, self._t('box_added', offer_id=offer_id))
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_create_box'))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}

    def handle_box_status(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Handle /box_status command with pagination"""
        offers = self.db.list_offers()
        active_offers = [offer for offer in offers if offer.status == OfferStatus.ACTIVE.value]
        
        if not active_offers:
            self._send_message(chat_id, self._t('no_offers'))
            return {'status': 'no_offers'}
        
        # Build list of offer-box combinations for pagination
        offer_boxes = []
        for offer in active_offers:
            boxes = self.db.get_boxes_by_offer(offer.offer_id)
            boxes.sort(key=lambda x: x.box_id)
            for box in boxes:
                offer_boxes.append((offer, box))
        
        # Paginate results
        page_items, total_pages = self._paginate_list(offer_boxes, page, 10)
        
        message = self._t('box_status_title', page=page, total_pages=total_pages)
        for offer, box in page_items:
            status_emoji = {
                BoxStatus.OPEN.value: "🟢",
                BoxStatus.MINIMUM_REACHED.value: "🟡",
                BoxStatus.FULL.value: "🔴",
                BoxStatus.ORDERED.value: "📦",
                BoxStatus.DELIVERED.value: "✅"
            }.get(box.status, "❓")
            
            # Check if box has orders ready for labeling
            orders = self.db.get_orders_by_box(box.box_id)
            ready_for_labeling = any(o.status == 'ready_for_labeling' for o in orders)
            labeling_button = f" [Finish Labeling](tg://btn?data=finish_labeling_{box.box_id})" if ready_for_labeling else ""
            
            message += f"🍺 {offer.name} €{offer.price_per_unit:.2f}\n   {status_emoji} Box {box.box_id[:8]}: {box.current_quantity}/{box.max_capacity} ({box.status}){labeling_button}\n\n"
        
        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_pagination_keyboard(page, total_pages, "boxes")
        
        # Add finish labeling buttons for boxes with ready orders
        labeling_buttons = []
        for offer, box in page_items:
            orders = self.db.get_orders_by_box(box.box_id)
            ready_for_labeling = any(o.status == 'ready_for_labeling' for o in orders)
            if ready_for_labeling:
                labeling_buttons.append([{"text": f"✅ Finish Labeling Box {box.box_id[:8]}", "callback_data": f"finish_labeling_{box.box_id}"}])
        
        if labeling_buttons:
            if keyboard:
                keyboard["inline_keyboard"].extend(labeling_buttons)
            else:
                keyboard = {"inline_keyboard": labeling_buttons}
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
