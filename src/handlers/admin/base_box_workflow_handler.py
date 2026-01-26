from typing import Dict, Any, List, Optional
import logging
from handlers.base_handler import BaseHandler
from models.entities import Supplier, Offer, Box, Order

logger = logging.getLogger()

class BaseBoxWorkflowHandler(BaseHandler):
    """Base class for box-based workflow handlers (wholesale delivery, labeling completion)"""
    
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)

    def _build_supplier_keyboard(self, suppliers: List[Supplier], callback_prefix: str) -> Dict[str, Any]:
        """Build inline keyboard for supplier selection"""
        # Sort suppliers alphabetically by name
        sorted_suppliers = sorted(suppliers, key=lambda s: s.name.lower())
        
        keyboard = []
        for supplier in sorted_suppliers:
            keyboard.append([{
                "text": supplier.name,
                "callback_data": f"{callback_prefix}_sup:{supplier.supplier_id[:8]}"
            }])
        
        # Add back to admin menu button
        keyboard.append([{
            "text": self._t('back_to_admin_menu', user_id=None),
            "callback_data": "admin:main"
        }])
        
        return {"inline_keyboard": keyboard}

    def _build_offer_keyboard(self, offers: List[Offer], supplier_id_short: str, callback_prefix: str) -> Dict[str, Any]:
        """Build inline keyboard for offer selection"""
        # Sort offers alphabetically by name
        sorted_offers = sorted(offers, key=lambda o: o.name.lower())
        
        keyboard = []
        for offer in sorted_offers:
            keyboard.append([{
                "text": f"{offer.name} (€{offer.price_per_unit})",
                "callback_data": f"{callback_prefix}_off:{offer.offer_id}:{supplier_id_short}"
            }])
        
        # Add back button
        keyboard.append([{
            "text": self._t('back_to_suppliers', user_id=None),
            "callback_data": f"{callback_prefix}_back:suppliers"
        }])
        
        return {"inline_keyboard": keyboard}

    def _build_box_keyboard(self, boxes: List[Box], offer_id: int, supplier_id_short: str, callback_prefix: str, 
                           add_complete_button: bool = False) -> Dict[str, Any]:
        """Build inline keyboard for box selection"""
        keyboard = []
        
        # Add "Complete delivery" button if requested
        if add_complete_button and boxes:
            keyboard.append([{
                "text": self._t('complete_delivery_btn', user_id=None),
                "callback_data": f"{callback_prefix}_complete:{offer_id}:{supplier_id_short}"
            }])
        
        for box in boxes:
            orders = self.db.get_orders_by_box(box.box_id)
            total_units = sum(order.quantity for order in orders)
            
            keyboard.append([{
                "text": f"Box {box.box_id[:8]}... ({total_units} units)",
                "callback_data": f"{callback_prefix}_box:{box.box_id[:8]}:{offer_id}:{supplier_id_short}"
            }])
        
        # Add back button
        keyboard.append([{
            "text": self._t('back_to_offers', user_id=None),
            "callback_data": f"{callback_prefix}_back:offers:{supplier_id_short}"
        }])
        
        return {"inline_keyboard": keyboard}

    def handle_supplier_selection(self, chat_id: int, supplier_id_short: str, callback_prefix: str, 
                                 get_suppliers_func, get_offers_func, select_offer_msg_key: str, 
                                 no_offers_msg_key: str = 'no_ordered_offers_for_supplier') -> Dict[str, Any]:
        """Handle supplier selection and show offers"""
        # Find full supplier_id from shortened version
        suppliers = get_suppliers_func()
        supplier = None
        for s in suppliers:
            if s.supplier_id.startswith(supplier_id_short):
                supplier = s
                break
        
        if not supplier:
            return self._send_message(chat_id, self._t('supplier_not_found'))

        offers = get_offers_func(supplier.name)
        if not offers:
            return self._send_message(chat_id, self._t(no_offers_msg_key, supplier_name=supplier.name))

        keyboard = self._build_offer_keyboard(offers, supplier_id_short, callback_prefix)
        return self._edit_message(
            chat_id,
            self._t(select_offer_msg_key, supplier_name=supplier.name),
            reply_markup=keyboard
        )

    def handle_offer_selection(self, chat_id: int, offer_id: int, supplier_id_short: str, callback_prefix: str,
                              get_boxes_func, select_box_msg_key: str, add_complete_button: bool = False) -> Dict[str, Any]:
        """Handle offer selection and show boxes"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            return self._send_message(chat_id, self._t('offer_not_found'))

        boxes = get_boxes_func(offer_id)
        if not boxes:
            return self._send_message(chat_id, self._t('no_boxes_with_orders', offer_name=offer.name))

        keyboard = self._build_box_keyboard(boxes, offer_id, supplier_id_short, callback_prefix, add_complete_button)
        return self._edit_message(
            chat_id,
            self._t(select_box_msg_key, offer_name=offer.name),
            reply_markup=keyboard
        )

    def handle_box_selection(self, chat_id: int, box_id_short: str, offer_id: int, supplier_id_short: str,
                           get_boxes_func, build_action_keyboard_func, box_action_msg_key: str) -> Dict[str, Any]:
        """Handle box selection and show action options"""
        # Find the full box_id from the shortened version
        boxes = get_boxes_func(offer_id)
        box = None
        for b in boxes:
            if b.box_id.startswith(box_id_short):
                box = b
                break
        
        if not box:
            return self._send_message(chat_id, self._t('box_not_found'))

        orders = self.db.get_orders_by_box(box.box_id)
        total_units = sum(order.quantity for order in orders)
        
        keyboard = build_action_keyboard_func(box.box_id, offer_id, supplier_id_short)
        
        message = self._t(box_action_msg_key, 
                         box_id=box.box_id[:8], 
                         total_units=total_units,
                         order_count=len(orders))
        
        return self._edit_message(chat_id, message, reply_markup=keyboard)

    def handle_back_navigation(self, chat_id: int, target: str, callback_prefix: str, 
                             get_suppliers_func, get_offers_func, get_boxes_func,
                             select_supplier_msg_key: str, select_offer_msg_key: str, select_box_msg_key: str,
                             no_offers_msg_key: str = 'no_ordered_offers_for_supplier',
                             *args) -> Dict[str, Any]:
        """Handle back button navigation"""
        if target == 'suppliers':
            suppliers = get_suppliers_func()
            keyboard = self._build_supplier_keyboard(suppliers, callback_prefix)
            return self._edit_message(
                chat_id,
                self._t(select_supplier_msg_key),
                reply_markup=keyboard
            )
        elif target == 'offers' and args:
            supplier_id_short = args[0]
            # Find full supplier_id from shortened version
            suppliers = get_suppliers_func()
            supplier = None
            for s in suppliers:
                if s.supplier_id.startswith(supplier_id_short):
                    supplier = s
                    break
            
            if not supplier:
                return self._send_message(chat_id, self._t('supplier_not_found'))
            
            offers = get_offers_func(supplier.name)
            keyboard = self._build_offer_keyboard(offers, supplier.supplier_id[:8], callback_prefix)
            return self._edit_message(
                chat_id,
                self._t(select_offer_msg_key, supplier_name=supplier.name),
                reply_markup=keyboard
            )
        elif target == 'boxes' and len(args) >= 2:
            offer_id, supplier_id_short = int(args[0]), args[1]
            offer = self.db.get_offer(offer_id)
            boxes = get_boxes_func(offer_id)
            keyboard = self._build_box_keyboard(boxes, offer_id, supplier_id_short, callback_prefix, 
                                              add_complete_button=callback_prefix == 'wd')  # Only for wholesale delivery
            return self._edit_message(
                chat_id,
                self._t(select_box_msg_key, offer_name=offer.name),
                reply_markup=keyboard
            )

    def _edit_message(self, chat_id: int, text: str, reply_markup: Dict[str, Any] = None) -> Dict[str, Any]:
        """Edit message with new content and keyboard"""
        return self._send_message(chat_id, text, reply_markup=reply_markup)