from typing import Dict, Any, List, Optional
from handlers.base_handler import BaseHandler
from models.entities import Supplier, Offer, Box, Order, OrderStatus, DeliveryAction
from services.wholesaler_delivery import WholesalerDeliveryService

class WholesaleDeliveryHandler(BaseHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.delivery_service = WholesalerDeliveryService(db)

    async def handle_wholesale_delivery(self, chat_id: int, user_id: int, args: List[str]) -> Dict[str, Any]:
        """Start wholesale delivery drill-down interface"""
        if not self._is_admin(user_id):
            return self._send_message(chat_id, self._t('admin_only', user_id))

        suppliers = self.db.get_suppliers_with_ordered_offers()
        if not suppliers:
            return self._send_message(chat_id, self._t('no_ordered_offers', user_id))

        keyboard = self._build_supplier_keyboard(suppliers)
        return self._send_message(
            chat_id,
            self._t('select_supplier_for_delivery', user_id),
            reply_markup=keyboard
        )

    def _build_supplier_keyboard(self, suppliers: List[Supplier]) -> Dict[str, Any]:
        """Build inline keyboard for supplier selection"""
        keyboard = []
        for supplier in suppliers:
            keyboard.append([{
                "text": supplier.name,
                "callback_data": f"wd_sup:{supplier.supplier_id}"
            }])
        
        return {"inline_keyboard": keyboard}

    async def handle_supplier_selection(self, chat_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle supplier selection and show offers"""
        supplier = self.db.get_supplier(supplier_id)
        if not supplier:
            return self._send_message(chat_id, self._t('supplier_not_found'))

        offers = self.db.get_ordered_offers_by_supplier(supplier.name)
        if not offers:
            return self._send_message(chat_id, self._t('no_ordered_offers_for_supplier', supplier_name=supplier.name))

        keyboard = self._build_offer_keyboard(offers, supplier_id)
        return self._edit_message(
            chat_id,
            self._t('select_offer_for_delivery', supplier_name=supplier.name),
            reply_markup=keyboard
        )

    def _build_offer_keyboard(self, offers: List[Offer], supplier_id: str) -> Dict[str, Any]:
        """Build inline keyboard for offer selection"""
        keyboard = []
        for offer in offers:
            keyboard.append([{
                "text": f"{offer.name} (€{offer.price_per_unit})",
                "callback_data": f"wd_off:{offer.offer_id}:{supplier_id}"
            }])
        
        # Add back button
        keyboard.append([{
            "text": "← Back to Suppliers",
            "callback_data": "wd_back:suppliers"
        }])
        
        return {"inline_keyboard": keyboard}

    async def handle_offer_selection(self, chat_id: int, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle offer selection and show boxes"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            return self._send_message(chat_id, self._t('offer_not_found'))

        boxes = self.db.get_boxes_by_offer_with_orders(offer_id)
        if not boxes:
            return self._send_message(chat_id, self._t('no_boxes_with_orders', offer_name=offer.name))

        keyboard = self._build_box_keyboard(boxes, offer_id, supplier_id)
        return self._edit_message(
            chat_id,
            self._t('select_box_for_delivery', offer_name=offer.name),
            reply_markup=keyboard
        )

    def _build_box_keyboard(self, boxes: List[Box], offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Build inline keyboard for box selection"""
        keyboard = []
        for box in boxes:
            orders = self.db.get_orders_by_box(box.box_id)
            total_units = sum(order.quantity for order in orders)
            
            keyboard.append([{
                "text": f"Box {box.box_id[:8]}... ({total_units} units)",
                "callback_data": f"wd_box:{box.box_id}:{offer_id}:{supplier_id}"
            }])
        
        # Add back button
        keyboard.append([{
            "text": "← Back to Offers",
            "callback_data": f"wd_back:offers:{supplier_id}"
        }])
        
        return {"inline_keyboard": keyboard}

    async def handle_box_selection(self, chat_id: int, box_id: str, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle box selection and show triage options"""
        box = self.db.get_box(box_id)
        if not box:
            return self._send_message(chat_id, self._t('box_not_found'))

        orders = self.db.get_orders_by_box(box_id)
        total_units = sum(order.quantity for order in orders)
        
        keyboard = self._build_triage_keyboard(box_id, offer_id, supplier_id)
        
        message = self._t('box_delivery_triage', 
                         box_id=box_id[:8], 
                         total_units=total_units,
                         order_count=len(orders))
        
        return self._edit_message(chat_id, message, reply_markup=keyboard)

    def _build_triage_keyboard(self, box_id: str, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Build triage interface keyboard"""
        keyboard = [
            [{
                "text": "✅ Full Delivery",
                "callback_data": f"wd_action:{DeliveryAction.FULL.value}:{box_id}:{offer_id}:{supplier_id}"
            }],
            [{
                "text": "⏳ Delayed",
                "callback_data": f"wd_action:{DeliveryAction.DELAYED.value}:{box_id}:{offer_id}:{supplier_id}"
            }],
            [{
                "text": "❌ Cancel",
                "callback_data": f"wd_action:{DeliveryAction.CANCEL.value}:{box_id}:{offer_id}:{supplier_id}"
            }],
            [{
                "text": "⚠️ Incomplete",
                "callback_data": f"wd_action:{DeliveryAction.INCOMPLETE.value}:{box_id}:{offer_id}:{supplier_id}"
            }],
            [{
                "text": "← Back to Boxes",
                "callback_data": f"wd_back:boxes:{offer_id}:{supplier_id}"
            }]
        ]
        
        return {"inline_keyboard": keyboard}

    async def handle_delivery_action(self, chat_id: int, action: str, box_id: str, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle delivery action selection"""
        box = self.db.get_box(box_id)
        orders = self.db.get_orders_by_box(box_id)
        total_units = sum(order.quantity for order in orders)

        if action == DeliveryAction.FULL.value:
            return await self._handle_full_delivery(chat_id, box_id, orders)
        elif action == DeliveryAction.DELAYED.value:
            return await self._handle_delayed_delivery(chat_id, box_id, orders)
        elif action == DeliveryAction.CANCEL.value:
            return await self._handle_cancelled_delivery(chat_id, box_id, orders)
        elif action == DeliveryAction.INCOMPLETE.value:
            return await self._handle_incomplete_delivery(chat_id, box_id, total_units, offer_id, supplier_id)

    async def _handle_full_delivery(self, chat_id: int, box_id: str, orders: List[Order]) -> Dict[str, Any]:
        """Handle full delivery - all units received"""
        success = self.delivery_service.process_wholesaler_delivery(
            box_id, 
            sum(order.quantity for order in orders), 
            False
        )
        
        if success:
            return self._send_message(chat_id, self._t('full_delivery_processed', box_id=box_id[:8]))
        else:
            return self._send_message(chat_id, self._t('delivery_processing_failed'))

    async def _handle_delayed_delivery(self, chat_id: int, box_id: str, orders: List[Order]) -> Dict[str, Any]:
        """Handle delayed delivery - no units received but coming later"""
        success = self.delivery_service.process_wholesaler_delivery(box_id, 0, True)
        
        if success:
            return self._send_message(chat_id, self._t('delayed_delivery_processed', box_id=box_id[:8]))
        else:
            return self._send_message(chat_id, self._t('delivery_processing_failed'))

    async def _handle_cancelled_delivery(self, chat_id: int, box_id: str, orders: List[Order]) -> Dict[str, Any]:
        """Handle cancelled delivery - no units received and won't come"""
        success = self.delivery_service.process_wholesaler_delivery(box_id, 0, False)
        
        if success:
            return self._send_message(chat_id, self._t('cancelled_delivery_processed', box_id=box_id[:8]))
        else:
            return self._send_message(chat_id, self._t('delivery_processing_failed'))

    async def _handle_incomplete_delivery(self, chat_id: int, box_id: str, total_units: int, offer_id: int, supplier_id: str) -> Dict[str, Any]:
        """Handle incomplete delivery - prompt for received quantity"""
        # Store context for processing the reply
        self._store_delivery_context(chat_id, box_id, total_units, offer_id, supplier_id)
        
        return self._send_message(
            chat_id,
            self._t('enter_received_quantity', total_units=total_units),
            reply_markup={"force_reply": True, "input_field_placeholder": f"Enter number (0-{total_units})"}
        )

    def _store_delivery_context(self, chat_id: int, box_id: str, total_units: int, offer_id: int, supplier_id: str):
        """Store delivery context for processing incomplete delivery reply"""
        from models.entities import EditContext
        
        # Delete existing context
        existing = self.db.get_edit_context_by_chat_id(chat_id)
        if existing:
            self.db.delete_edit_context(existing.context_id)
        
        # Create new context with delivery data
        context = EditContext(
            chat_id=chat_id,
            edit_type='incomplete_delivery',
            entity_id=f"{box_id}:{total_units}:{offer_id}:{supplier_id}"
        )
        self.db.create_edit_context(context)

    async def handle_incomplete_delivery_reply(self, chat_id: int, received_text: str, context_data: str) -> Dict[str, Any]:
        """Handle reply for incomplete delivery quantity"""
        try:
            parts = context_data.split(':')
            box_id, total_units, offer_id, supplier_id = parts[0], int(parts[1]), int(parts[2]), parts[3]
            
            received_units = int(received_text.strip())
            
            if received_units < 0 or received_units > total_units:
                return self._send_message(chat_id, self._t('invalid_quantity_range', max_units=total_units))
            
            if received_units == total_units:
                # Full delivery
                return await self._handle_full_delivery(chat_id, box_id, self.db.get_orders_by_box(box_id))
            elif received_units == 0:
                # Show delayed/cancel options
                return await self._show_incomplete_options(chat_id, box_id, offer_id, supplier_id, received_units)
            else:
                # Partial delivery - show delayed/cancel options
                return await self._show_incomplete_options(chat_id, box_id, offer_id, supplier_id, received_units)
                
        except (ValueError, IndexError):
            return self._send_message(chat_id, self._t('invalid_number_format'))

    async def _show_incomplete_options(self, chat_id: int, box_id: str, offer_id: int, supplier_id: str, received_units: int) -> Dict[str, Any]:
        """Show options for handling remaining units after partial delivery"""
        keyboard = [
            [{
                "text": "⏳ Remaining Delayed",
                "callback_data": f"wd_partial:delayed:{box_id}:{received_units}:{offer_id}:{supplier_id}"
            }],
            [{
                "text": "❌ Remaining Cancelled",
                "callback_data": f"wd_partial:cancel:{box_id}:{received_units}:{offer_id}:{supplier_id}"
            }]
        ]
        
        return self._send_message(
            chat_id,
            self._t('choose_remaining_action', received_units=received_units),
            reply_markup={"inline_keyboard": keyboard}
        )

    async def handle_partial_action(self, chat_id: int, action: str, box_id: str, received_units: int) -> Dict[str, Any]:
        """Handle action for remaining units in partial delivery"""
        is_delayed = action == 'delayed'
        success = self.delivery_service.process_wholesaler_delivery(box_id, received_units, is_delayed)
        
        if success:
            action_text = 'delayed' if is_delayed else 'cancelled'
            return self._send_message(
                chat_id, 
                self._t('partial_delivery_processed', 
                       box_id=box_id[:8], 
                       received_units=received_units,
                       action=action_text)
            )
        else:
            return self._send_message(chat_id, self._t('delivery_processing_failed'))

    async def handle_back_navigation(self, chat_id: int, target: str, *args) -> Dict[str, Any]:
        """Handle back button navigation"""
        if target == 'suppliers':
            suppliers = self.db.get_suppliers_with_ordered_offers()
            keyboard = self._build_supplier_keyboard(suppliers)
            return self._edit_message(
                chat_id,
                self._t('select_supplier_for_delivery'),
                reply_markup=keyboard
            )
        elif target == 'offers' and args:
            supplier_id = args[0]
            supplier = self.db.get_supplier(supplier_id)
            offers = self.db.get_ordered_offers_by_supplier(supplier.name)
            keyboard = self._build_offer_keyboard(offers, supplier_id)
            return self._edit_message(
                chat_id,
                self._t('select_offer_for_delivery', supplier_name=supplier.name),
                reply_markup=keyboard
            )
        elif target == 'boxes' and len(args) >= 2:
            offer_id, supplier_id = int(args[0]), args[1]
            offer = self.db.get_offer(offer_id)
            boxes = self.db.get_boxes_by_offer_with_orders(offer_id)
            keyboard = self._build_box_keyboard(boxes, offer_id, supplier_id)
            return self._edit_message(
                chat_id,
                self._t('select_box_for_delivery', offer_name=offer.name),
                reply_markup=keyboard
            )

    def _edit_message(self, chat_id: int, text: str, reply_markup: Dict[str, Any] = None) -> Dict[str, Any]:
        """Edit message with new content and keyboard"""
        # This would be implemented to edit the existing message
        # For now, send a new message (in real implementation, use editMessageText)
        return self._send_message(chat_id, text, reply_markup)