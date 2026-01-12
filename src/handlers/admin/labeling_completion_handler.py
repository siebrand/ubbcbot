from typing import Dict, Any, List
import logging
from handlers.admin.base_box_workflow_handler import BaseBoxWorkflowHandler
from models.entities import OrderStatus, BoxStatus, OfferStatus

logger = logging.getLogger()

class LabelingCompletionHandler(BaseBoxWorkflowHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)

    def handle_labeling_completed(self, chat_id: int, user_id: int, args: List[str]) -> Dict[str, Any]:
        """Start labeling completion drill-down interface"""
        if not self._is_admin(user_id):
            return self._send_message(chat_id, self._t('admin_only', user_id))

        suppliers = self.db.get_suppliers_with_ready_for_labeling_offers()
        if not suppliers:
            return self._send_message(chat_id, self._t('no_ready_for_labeling_offers', user_id))

        keyboard = self._build_supplier_keyboard(suppliers, 'lc')
        return self._send_message(
            chat_id,
            self._t('select_supplier_for_labeling', user_id),
            reply_markup=keyboard
        )

    def handle_supplier_selection(self, chat_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Handle supplier selection and show offers"""
        return super().handle_supplier_selection(
            chat_id, supplier_id_short, 'lc',
            self.db.get_suppliers_with_ready_for_labeling_offers,
            self.db.get_ready_for_labeling_offers_by_supplier,
            'select_offer_for_labeling',
            'no_ready_for_labeling_offers_for_supplier'
        )

    def handle_offer_selection(self, chat_id: int, offer_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Handle offer selection and show boxes"""
        return super().handle_offer_selection(
            chat_id, offer_id, supplier_id_short, 'lc',
            self.db.get_boxes_by_offer_with_ready_orders,
            'select_box_for_labeling',
            add_complete_button=True
        )

    def handle_box_selection(self, chat_id: int, box_id_short: str, offer_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Handle box selection and show labeling completion option"""
        return super().handle_box_selection(
            chat_id, box_id_short, offer_id, supplier_id_short,
            self.db.get_boxes_by_offer_with_ready_orders,
            self._build_labeling_keyboard,
            'box_delivery_triage'
        )

    def handle_back_navigation(self, chat_id: int, target: str, *args) -> Dict[str, Any]:
        """Handle back button navigation"""
        return super().handle_back_navigation(
            chat_id, target, 'lc',
            self.db.get_suppliers_with_ready_for_labeling_offers,
            self.db.get_ready_for_labeling_offers_by_supplier,
            self.db.get_boxes_by_offer_with_ready_orders,
            'select_supplier_for_labeling',
            'select_offer_for_labeling', 
            'select_box_for_labeling',
            'no_ready_for_labeling_offers_for_supplier',
            *args
        )

    def _build_labeling_keyboard(self, box_id: str, offer_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Build labeling completion keyboard"""
        box_id_short = box_id[:8]
        keyboard = [
            [{
                "text": self._t('complete_labeling_btn', user_id=None),
                "callback_data": f"lc_action:complete:{box_id_short}:{offer_id}:{supplier_id_short}"
            }],
            [{
                "text": "← Back to Boxes",
                "callback_data": f"lc_back:boxes:{offer_id}:{supplier_id_short}"
            }]
        ]
        
        return {"inline_keyboard": keyboard}

    def handle_labeling_action(self, chat_id: int, action: str, box_id_short: str, offer_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Handle labeling completion action"""
        if action != 'complete':
            return self._send_message(chat_id, self._t('unknown_action'))

        # Find the full box_id from the shortened version
        boxes = self.db.get_boxes_by_offer_with_ready_orders(offer_id)
        box = None
        for b in boxes:
            if b.box_id.startswith(box_id_short):
                box = b
                break
        
        if not box:
            return self._send_message(chat_id, self._t('box_not_found'))

        # Get all orders for this box that are in READY_FOR_LABELING status
        orders = self.db.get_orders_by_box(box.box_id)
        ready_orders = [o for o in orders if o.status == OrderStatus.READY_FOR_LABELING.value]
        
        if not ready_orders:
            return self._send_message(chat_id, self._t('no_labeling_orders', box_id=box.box_id[:8]))

        # Update all ready orders to LABELING_COMPLETED
        updated_count = 0
        for order in ready_orders:
            if self.db.update_order(order.order_id, {'status': OrderStatus.LABELING_COMPLETED.value}, admin_id=self.admin_user_id, reason="Labeling completed"):
                updated_count += 1

        if updated_count > 0:
            # Check if offer should be completed (only if sold out and all boxes delivered)
            self._check_and_update_offer_status(offer_id)
            
            return self._send_message(chat_id, self._t('labeling_completed_success', 
                                                     box_id=box.box_id[:8], 
                                                     updated_count=updated_count))
        else:
            return self._send_message(chat_id, self._t('delivery_processing_failed'))

    def handle_complete_labeling(self, chat_id: int, offer_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Handle complete labeling for all boxes in an offer"""
        all_boxes = self.db.get_boxes_by_offer_with_ready_orders(offer_id)
        
        if not all_boxes:
            return self._send_message(chat_id, self._t('no_ready_for_labeling_offers'))
        
        keyboard = [
            [{
                "text": self._t('confirm', user_id=None),
                "callback_data": f"lc_confirm_complete:{offer_id}:{supplier_id_short}"
            }],
            [{
                "text": self._t('cancel', user_id=None),
                "callback_data": f"lc_back:boxes:{offer_id}:{supplier_id_short}"
            }]
        ]
        
        return self._send_message(
            chat_id,
            self._t('complete_labeling_confirmation', box_count=len(all_boxes)),
            reply_markup={"inline_keyboard": keyboard}
        )

    def handle_confirm_complete_labeling(self, chat_id: int, offer_id: int, supplier_id_short: str) -> Dict[str, Any]:
        """Confirm and execute complete labeling for all boxes"""
        all_boxes = self.db.get_boxes_by_offer_with_ready_orders(offer_id)
        
        if not all_boxes:
            return self._send_message(chat_id, self._t('no_ready_for_labeling_offers'))
        
        processed_count = 0
        for box in all_boxes:
            orders = self.db.get_orders_by_box(box.box_id)
            ready_orders = [o for o in orders if o.status == OrderStatus.READY_FOR_LABELING.value]
            
            for order in ready_orders:
                if self.db.update_order(order.order_id, {'status': OrderStatus.LABELING_COMPLETED.value}, admin_id=self.admin_user_id, reason="Labeling completed - batch"):
                    processed_count += 1
        
        if processed_count > 0:
            self._check_and_update_offer_status(offer_id)
            
            self._send_message(
                chat_id, 
                self._t('complete_labeling_success', box_count=len(all_boxes))
            )
            return self.handle_labeling_completed(chat_id, self.admin_user_id, [])
        else:
            return self._send_message(chat_id, self._t('delivery_processing_failed'))

    def _check_and_update_offer_status(self, offer_id: int):
        """Check if offer should be completed: must be SOLD_OUT and all boxes DELIVERED"""
        try:
            offer = self.db.get_offer(offer_id)
            if not offer or offer.status != OfferStatus.SOLD_OUT.value:
                return  # Only complete offers that are already sold out
            
            boxes = self.db.get_boxes_by_offer(offer_id)
            if not boxes:
                return
            
            # Check if all boxes are delivered
            all_delivered = all(box.status == BoxStatus.DELIVERED.value for box in boxes)
            
            if all_delivered:
                # Update offer status to COMPLETED
                self.db.update_offer(offer_id, {'status': OfferStatus.COMPLETED.value})
                logger.info(f"Updated offer {offer_id} status to COMPLETED - sold out and all boxes delivered")
        except Exception as e:
            logger.error(f"Error checking offer status for offer {offer_id}: {e}")