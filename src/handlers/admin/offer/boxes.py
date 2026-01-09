from typing import Dict, Any
from models.entities import Box, BoxStatus, OfferStatus
from .base import OfferBaseHandler
from services.box_status_manager import BoxStatusManager

class BoxManagementHandler(OfferBaseHandler):
    """Handler for box management operations"""
    
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)
    
    def handle_add_box(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_box command"""
        error = self._validate_args(args, 1, 'usage_add_box', chat_id)
        if error:
            return error

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found', chat_id))
                return {'status': 'offer_not_found'}
            
            # Create new box
            box = Box(
                offer_id=offer_id,
                max_capacity=offer.wholesale_box_size
            )
            
            if self.db.create_box(box):
                # Update offer status from sold_out to active if needed
                if offer.status == OfferStatus.SOLD_OUT.value:
                    self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value})
                    self._send_message(chat_id, self._t('box_added_offer_active', chat_id, offer_id=offer_id))
                else:
                    self._send_message(chat_id, self._t('box_added', chat_id, offer_id=offer_id))
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_create_box', chat_id))
                return {'status': 'error'}
                
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id', chat_id))
            return {'status': 'invalid_format'}

    def handle_box_status(self, chat_id: int, args: list = None) -> Dict[str, Any]:
        """Handle /box_status command with pagination and optional status filter"""
        # Handle None args for backward compatibility
        if args is None:
            args = []
            
        # Parse arguments
        page = 1
        status_filter = 'active'  # default
        
        if args:
            if args[0].lower() in ['active', 'ordered', 'full', 'delivered', 'all']:
                status_filter = args[0].lower()
                if len(args) > 1:
                    try:
                        page = int(args[1])
                    except ValueError:
                        pass
            else:
                try:
                    page = int(args[0])
                except ValueError:
                    pass
        
        offers = self.db.list_offers()
        
        # Build list of offer-box combinations and filter by box status
        offer_boxes = []
        for offer in offers:
            boxes = self.db.get_boxes_by_offer(offer.offer_id)
            for box in boxes:
                # Filter boxes based on status
                if status_filter == 'active' and box.status in [BoxStatus.OPEN.value, BoxStatus.FULL.value, BoxStatus.ORDERED.value]:
                    offer_boxes.append((offer, box))
                elif status_filter == 'ordered' and box.status == BoxStatus.ORDERED.value:
                    offer_boxes.append((offer, box))
                elif status_filter == 'full' and box.status == BoxStatus.FULL.value:
                    offer_boxes.append((offer, box))
                elif status_filter == 'delivered' and box.status == BoxStatus.DELIVERED.value:
                    offer_boxes.append((offer, box))
                elif status_filter == 'all':
                    offer_boxes.append((offer, box))
        
        if not offer_boxes:
            self._send_message(chat_id, self._t('no_boxes_found', chat_id, status=status_filter))
            return {'status': 'no_boxes'}
        
        # Paginate results
        page_items, total_pages = self._paginate_list(offer_boxes, page, 10)
        
        message = self._t('box_status_header', chat_id, status=status_filter.title(), page=page, total_pages=total_pages) + "\n\n"
        message += "```\n"
        message += self._t('box_status_table_header', chat_id) + "\n"
        message += self._t('box_status_table_separator', chat_id) + "\n"
        
        for offer, box in page_items:
            status_emoji = {
                BoxStatus.OPEN.value: "🟢",
                BoxStatus.FULL.value: "🔴",
                BoxStatus.ORDERED.value: "📦",
                BoxStatus.DELIVERED.value: "✅"
            }.get(box.status, "❓")
            
            # Truncate offer name to fit table
            offer_name = offer.name[:20] if len(offer.name) > 20 else offer.name
            price_str = f"€{offer.price_per_unit:.2f}"
            units_str = f"{box.current_quantity}/{box.max_capacity}"
            box_id_short = box.box_id[:8] if len(box.box_id) > 8 else box.box_id
            
            message += f"{status_emoji}     {str(offer.offer_id):<4}  {box_id_short:<8}  {offer_name:<20}  {price_str:>6}  {units_str:>5}\n"
        
        message += "```"
        
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
                labeling_buttons.append([{"text": self._t('finish_labeling_box', chat_id, box_id=box.box_id[:8]), "callback_data": f"finish_labeling_{box.box_id}"}])
        
        if labeling_buttons:
            if keyboard:
                keyboard["inline_keyboard"].extend(labeling_buttons)
            else:
                keyboard = {"inline_keyboard": labeling_buttons}
        
        self._send_message(chat_id, message, reply_markup=keyboard, parse_mode="Markdown")
        return {'status': 'success'}
    
    def handle_audit_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /audit_offer command - check and fix order/box discrepancies"""
        if not args:
            # Show button interface to select offer
            return self._show_audit_offer_selection(chat_id)
        
        try:
            offer_id = int(args[0])
            return self._execute_audit_offer(chat_id, offer_id)
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id', chat_id))
            return {'status': 'invalid_format'}
    
    def _show_audit_offer_selection(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Show paginated list of offers for audit selection"""
        from models.entities import OfferStatus
        offers = [o for o in self.db.list_offers() if o.status in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value]]
        
        if not offers:
            self._send_message(chat_id, self._t('no_offers_for_audit', chat_id))
            return {'status': 'no_offers'}
        
        # Sort by offer_id for consistent ordering
        offers.sort(key=lambda x: x.offer_id)
        
        # Paginate results
        page_offers, total_pages = self._paginate_list(offers, page, 10)
        
        message = self._t('select_offer_for_audit', chat_id, page=page, total_pages=total_pages) + "\n\n"
        keyboard_buttons = []
        
        for offer in page_offers:
            supplier = self.db.get_supplier_by_name(offer.supplier_name)
            supplier_name = supplier.name if supplier else self._t('unknown', user_id=None)
            button_text = f"🍺 {offer.name} - €{offer.price_per_unit:.2f} ({supplier_name})"
            keyboard_buttons.append([{"text": button_text, "callback_data": f"audit_offer_{offer.offer_id}"}])
        
        # Add pagination if needed
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": self._t('previous', chat_id), "callback_data": f"audit_offers_page_{page - 1}"})
            nav_buttons.append({"text": self._t('page_indicator', chat_id, page=page, total_pages=total_pages), "callback_data": "page_info"})
            if page < total_pages:
                nav_buttons.append({"text": self._t('next', chat_id), "callback_data": f"audit_offers_page_{page + 1}"})
            keyboard_buttons.append(nav_buttons)
        
        # Add cancel button
        keyboard_buttons.append([{"text": self._t('cancel', chat_id), "callback_data": "cancel_action"}])
        
        keyboard = {"inline_keyboard": keyboard_buttons}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def _execute_audit_offer(self, chat_id: int, offer_id: int) -> Dict[str, Any]:
        """Execute audit for specific offer"""
        offer = self.db.get_offer(offer_id)
        
        if not offer:
            self._send_message(chat_id, self._t('offer_not_found', chat_id))
            return {'status': 'offer_not_found'}
        
        # Get active orders for this offer
        all_orders = self.db.get_orders_by_offer(offer_id)
        active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
        total_ordered_units = sum(order.quantity for order in active_orders)
        
        # Get boxes and calculate total capacity
        boxes = self.db.get_boxes_by_offer(offer_id)
        total_box_capacity = sum(box.current_quantity for box in boxes)
        
        # Check if numbers match
        if total_ordered_units == total_box_capacity:
            self._send_message(chat_id, self._t('audit_offer_match', chat_id, 
                offer_id=offer_id, units=total_ordered_units, boxes=len(boxes)))
            return {'status': 'match'}
        
        # Numbers don't match - determine remediation
        discrepancy = total_ordered_units - total_box_capacity
        
        if discrepancy > 0:
            # More orders than box capacity
            self._send_message(chat_id, self._t('audit_excess_orders', chat_id,
                offer_id=offer_id, ordered=total_ordered_units, capacity=total_box_capacity, excess=discrepancy))
            return self._propose_excess_orders_action(chat_id, offer, boxes, active_orders, discrepancy)
        else:
            # More box capacity than orders
            self._send_message(chat_id, self._t('audit_excess_capacity', chat_id,
                offer_id=offer_id, ordered=total_ordered_units, capacity=total_box_capacity, excess=abs(discrepancy)))
            return {'status': 'excess_capacity'}
    
    def _propose_excess_orders_action(self, chat_id: int, offer, boxes, active_orders, excess_units: int) -> Dict[str, Any]:
        """Propose action for excess orders - fill existing boxes first, then create new boxes if needed"""
        # Get unordered and ordered boxes separately
        unordered_boxes = [b for b in boxes if b.status not in [BoxStatus.ORDERED.value, BoxStatus.DELIVERED.value]]
        ordered_boxes = [b for b in boxes if b.status == BoxStatus.ORDERED.value]
        
        # Calculate available capacity in unordered boxes
        unordered_capacity = sum(max(0, b.max_capacity - b.current_quantity) for b in unordered_boxes)
        
        # Calculate available capacity in ordered boxes
        ordered_capacity = sum(max(0, b.max_capacity - b.current_quantity) for b in ordered_boxes)
        
        total_capacity = unordered_capacity + ordered_capacity
        
        if total_capacity >= excess_units:
            # Can fill existing boxes (prioritize unordered, then ordered)
            message = self._t('audit_propose_fill_boxes', chat_id,
                offer_id=offer.offer_id, excess=excess_units, available=total_capacity)
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": self._t('confirm_fill_boxes', chat_id), "callback_data": f"audit_fill_boxes_{offer.offer_id}_{excess_units}"}],
                    [{"text": self._t('cancel', chat_id), "callback_data": "cancel_action"}]
                ]
            }
        elif unordered_boxes and total_capacity > 0:
            # Fill existing boxes and create new ones (only if unordered boxes exist)
            box_size = offer.wholesale_box_size
            remaining_units = excess_units - total_capacity
            boxes_needed = (remaining_units + box_size - 1) // box_size
            
            message = self._t('audit_propose_fill_and_create', chat_id,
                offer_id=offer.offer_id, excess=excess_units, available=total_capacity,
                boxes=boxes_needed, box_size=box_size)
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": self._t('confirm_fill_and_create', chat_id), "callback_data": f"audit_fill_create_{offer.offer_id}_{excess_units}"}],
                    [{"text": self._t('cancel', chat_id), "callback_data": "cancel_action"}]
                ]
            }
        elif not ordered_boxes:
            # No ordered boxes exist - create new boxes instead of canceling orders
            box_size = offer.wholesale_box_size
            boxes_needed = (excess_units + box_size - 1) // box_size
            
            message = self._t('audit_propose_create_boxes', chat_id,
                offer_id=offer.offer_id, excess=excess_units, boxes=boxes_needed, box_size=box_size)
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": self._t('confirm_create_boxes', chat_id), "callback_data": f"audit_create_boxes_{offer.offer_id}_{excess_units}"}],
                    [{"text": self._t('cancel', chat_id), "callback_data": "cancel_action"}]
                ]
            }
        else:
            # No capacity available - need to cancel orders
            sorted_orders = sorted(active_orders, key=lambda x: x.created_at, reverse=True)
            orders_to_cancel = []
            units_to_cancel = excess_units
            
            for order in sorted_orders:
                if units_to_cancel <= 0:
                    break
                orders_to_cancel.append(order)
                units_to_cancel -= order.quantity
            
            order_details = []
            for order in orders_to_cancel:
                customer = self.db.get_customer(order.customer_id)
                customer_name = customer.first_name if customer else self._t('unknown', user_id=None)
                order_details.append(f"{customer_name} ({order.quantity} units)")
            
            message = self._t('audit_propose_cancel_orders', chat_id,
                offer_id=offer.offer_id, count=len(orders_to_cancel), excess=excess_units,
                orders="\n".join(order_details))
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": self._t('confirm_cancel_orders', chat_id), "callback_data": f"audit_cancel_orders_{offer.offer_id}_{excess_units}"}],
                    [{"text": self._t('cancel', chat_id), "callback_data": "cancel_action"}]
                ]
            }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'awaiting_confirmation'}
    
    def _execute_fill_boxes(self, chat_id: int, offer_id: int, excess_units: int) -> Dict[str, Any]:
        """Execute filling existing boxes after confirmation"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t('offer_not_found', chat_id))
            return {'status': 'offer_not_found'}
        
        # Fill existing boxes with available capacity
        boxes = self.db.get_boxes_by_offer(offer_id)
        unordered_boxes = [b for b in boxes if b.status not in [BoxStatus.ORDERED.value, BoxStatus.DELIVERED.value]]
        ordered_boxes = [b for b in boxes if b.status == BoxStatus.ORDERED.value]
        
        filled_units = 0
        
        # Fill unordered boxes first
        for box in unordered_boxes:
            if filled_units >= excess_units:
                break
            available = box.max_capacity - box.current_quantity
            if available > 0:
                fill_amount = min(available, excess_units - filled_units)
                new_quantity = box.current_quantity + fill_amount
                self.db.update_box(box.box_id, {'current_quantity': new_quantity})
                filled_units += fill_amount
        
        # Fill ordered boxes if needed
        for box in ordered_boxes:
            if filled_units >= excess_units:
                break
            available = box.max_capacity - box.current_quantity
            if available > 0:
                fill_amount = min(available, excess_units - filled_units)
                new_quantity = box.current_quantity + fill_amount
                self.db.update_box(box.box_id, {'current_quantity': new_quantity})
                filled_units += fill_amount
        
        self._send_message(chat_id, self._t('audit_boxes_filled', chat_id,
            offer_id=offer_id, filled=filled_units))
        return {'status': 'boxes_filled', 'filled': filled_units}
    
    def _execute_fill_and_create(self, chat_id: int, offer_id: int, excess_units: int) -> Dict[str, Any]:
        """Execute filling existing boxes and creating new ones after confirmation"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t('offer_not_found', chat_id))
            return {'status': 'offer_not_found'}
        
        # First fill existing capacity
        fill_result = self._execute_fill_boxes(chat_id, offer_id, excess_units)
        filled_units = fill_result.get('filled', 0)
        
        # Create new boxes for remaining units
        remaining_units = excess_units - filled_units
        if remaining_units > 0:
            create_result = self._add_box_capacity(chat_id, offer, remaining_units)
            boxes_created = create_result.get('boxes', 0)
            
            self._send_message(chat_id, self._t('audit_filled_and_created', chat_id,
                offer_id=offer_id, filled=filled_units, boxes=boxes_created, remaining=remaining_units))
        
        return {'status': 'filled_and_created', 'filled': filled_units, 'remaining': remaining_units}
    
    def _execute_create_boxes(self, chat_id: int, offer_id: int, excess_units: int) -> Dict[str, Any]:
        """Execute box creation after confirmation"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t('offer_not_found', chat_id))
            return {'status': 'offer_not_found'}
        
        return self._add_box_capacity(chat_id, offer, excess_units)
    
    def _execute_cancel_orders(self, chat_id: int, offer_id: int, excess_units: int) -> Dict[str, Any]:
        """Execute order cancellation after confirmation"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t('offer_not_found', chat_id))
            return {'status': 'offer_not_found'}
        
        all_orders = self.db.get_orders_by_offer(offer_id)
        active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
        
        return self._cancel_excess_orders(chat_id, offer, active_orders, excess_units)
    
    def _add_box_capacity(self, chat_id: int, offer, needed_units: int) -> Dict[str, Any]:
        """Add box capacity by creating new boxes and filling them with needed units"""
        box_size = offer.wholesale_box_size
        boxes_needed = (needed_units + box_size - 1) // box_size
        
        created_boxes = 0
        remaining_units = needed_units
        
        for _ in range(boxes_needed):
            box = Box(
                offer_id=offer.offer_id,
                max_capacity=box_size
            )
            created_box = self.db.create_box(box)
            if created_box:
                # Fill the new box with needed units
                fill_amount = min(remaining_units, box_size)
                if fill_amount > 0:
                    updates = {'current_quantity': fill_amount}
                    if fill_amount >= box_size:
                        updates['status'] = BoxStatus.FULL.value
                    self.db.update_box(created_box.box_id, updates)
                    remaining_units -= fill_amount
                created_boxes += 1
        
        if created_boxes > 0:
            self._send_message(chat_id, self._t('audit_boxes_created', chat_id,
                offer_id=offer.offer_id, boxes=created_boxes, units=needed_units))
            return {'status': 'boxes_created', 'boxes': created_boxes}
        else:
            self._send_message(chat_id, self._t('audit_failed_create_boxes', chat_id))
            return {'status': 'error'}
    
    def _cancel_excess_orders(self, chat_id: int, offer, active_orders, excess_units: int) -> Dict[str, Any]:
        """Cancel excess orders using existing cancellation logic"""
        # Sort orders by creation time (oldest first) for fair cancellation
        sorted_orders = sorted(active_orders, key=lambda x: x.created_at)
        
        cancelled_orders = []
        units_to_cancel = excess_units
        
        # Cancel orders until we've cancelled enough units
        for order in reversed(sorted_orders):  # Cancel newest first
            if units_to_cancel <= 0:
                break
            cancelled_orders.append(order)
            units_to_cancel -= order.quantity
        
        # Execute cancellations using existing method
        from handlers.admin.order_commands import AdminOrderCommands
        order_handler = AdminOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        cancelled_count = 0
        for order in cancelled_orders:
            box = self.db.get_box(order.box_id)
            if box:
                result = order_handler._execute_cancel(order, box, chat_id)
                if result['status'] == 'success':
                    cancelled_count += 1
        
        self._send_message(chat_id, self._t('audit_orders_cancelled', chat_id,
            offer_id=offer.offer_id, cancelled=cancelled_count, ordered=excess_units + sum(box.current_quantity for box in self.db.get_boxes_by_offer(offer.offer_id)), capacity=sum(box.current_quantity for box in self.db.get_boxes_by_offer(offer.offer_id))))
        
        return {'status': 'orders_cancelled', 'cancelled': cancelled_count}
