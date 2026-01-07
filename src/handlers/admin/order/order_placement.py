from typing import Dict, Any
from models.entities import OfferStatus, EditContext
from .base_order_handler import BaseOrderHandler

class OrderPlacement(BaseOrderHandler):
    """Handles order placement functionality for admin placing orders for customers"""
    
    def handle_order_for(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /order_for command - admin places order for another user"""
        if not args:
            # Show button-based UI to ask for username
            message = self._t('enter_username_for_order_for', chat_id)
            keyboard = {
                "inline_keyboard": [[
                    {"text": "📝 Enter Username", "callback_data": "enter_username_order_for"}
                ]]
            }
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'awaiting_input'}

        # Legacy behavior for direct command usage
        if len(args) >= 2:
            return self._execute_order_for_legacy(chat_id, user_id, args)
        
        # Username provided - find customer and show offers
        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "order_for_user_select")
        
        if error:
            return error
        
        return self._show_offers_for_order_for(chat_id, customer)

    def _execute_order_for_legacy(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Legacy order_for execution for direct command usage"""
        try:
            username = args[0]
            offer_id = int(args[1])
            quantity = int(args[2]) if len(args) > 2 else 1

            if quantity <= 0:
                self._send_message(chat_id, self._t('quantity_must_positive'))
                return {'status': 'invalid_quantity'}

            # Find target customer
            customer, error = self._find_customer_with_disambiguation(username, chat_id, "order_for_user_select")
            if error:
                return error

            return self._execute_order_for_customer(chat_id, customer, offer_id, quantity)

        except ValueError:
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'invalid_format'}
    
    def _show_offers_for_order_for(self, chat_id: int, customer) -> Dict[str, Any]:
        """Show active offers for order_for workflow"""
        offers = [o for o in self.db.list_offers() if o.status == OfferStatus.ACTIVE.value]
        
        if not offers:
            self._send_message(chat_id, self._t('no_offers_available'))
            return {'status': 'no_offers'}
        
        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or "Unknown")
        message = f"🍺 Select offer for {display_name}:\n\n"
        
        keyboard_buttons = []
        for offer in offers[:10]:  # Limit to 10 offers
            supplier = self.db.get_supplier_by_name(offer.supplier_name)
            supplier_name = supplier.name if supplier else "Unknown"
            
            button_text = f"🍺 {offer.name} - €{offer.price_per_unit:.2f} ({supplier_name})"
            keyboard_buttons.append([{
                "text": button_text,
                "callback_data": f"order_for_offer_{customer.customer_id}_{offer.offer_id}"
            }])
        
        keyboard_buttons.append([{"text": self._t('cancel', user_id=None), "callback_data": "cancel_action"}])
        keyboard = {"inline_keyboard": keyboard_buttons}
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def _show_quantity_selection_for_order_for(self, chat_id: int, customer, offer) -> Dict[str, Any]:
        """Show quantity selection for order_for workflow"""
        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or "Unknown")
        message = f"📦 Select quantity for {display_name}:\n\n🍺 {offer.name} - €{offer.price_per_unit:.2f}"
        
        keyboard_buttons = [
            [{"text": self._t('order_1', user_id=None), "callback_data": f"order_for_quantity_{customer.customer_id}_{offer.offer_id}_1"}],
            [{"text": self._t('order_2', user_id=None), "callback_data": f"order_for_quantity_{customer.customer_id}_{offer.offer_id}_2"}],
            [{"text": self._t('other_quantity', user_id=None), "callback_data": f"order_for_other_{customer.customer_id}_{offer.offer_id}"}],
            [{"text": self._t('cancel', user_id=None), "callback_data": "cancel_action"}]
        ]
        
        keyboard = {"inline_keyboard": keyboard_buttons}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def _execute_order_for_customer(self, chat_id: int, customer, offer_id: int, quantity: int) -> Dict[str, Any]:
        """Execute order for customer with validation"""
        # Get offer
        offer = self.db.get_offer(offer_id)
        if not offer or offer.status != OfferStatus.ACTIVE.value:
            self._send_message(chat_id, self._t('offer_not_found_inactive'))
            return {'status': 'offer_not_found'}

        # Check 10-unit admin limit for target customer
        valid, limit_message = self.validator.validate_order_limit(customer.customer_id, offer_id, quantity, 10)
        if not valid:
            # Extract existing orders info for admin message
            existing_orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) 
                             if o.offer_id == offer_id and o.status in ['pending', 'ordered']]
            total_existing = sum(order.quantity for order in existing_orders)
            
            display_name = customer.first_name or "Unknown"
            admin_message = self._t('admin_order_limit_exceeded', user_id=None, 
                                  customer_name=display_name, 
                                  total_existing=total_existing)
            
            # Add order details
            admin_message += "\n\n"
            for order in existing_orders:
                from utils.timezone import to_cet_string
                order_date = to_cet_string(order.created_at, '%Y-%m-%d')
                admin_message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
            
            remaining_allowed = 10 - total_existing
            if remaining_allowed > 0:
                admin_message += self._t('admin_remaining_units_allowed', user_id=None, remaining=remaining_allowed)
            else:
                admin_message += self._t('admin_limit_reached', user_id=None, customer_name=display_name)
            
            self._send_message(chat_id, admin_message)
            return {'status': 'limit_exceeded'}

        # Execute the order for the target customer
        from handlers.customer.order_commands import CustomerOrderCommands
        order_handler = CustomerOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        result = order_handler.execute_order(chat_id, customer.telegram_user_id, offer_id, quantity, offer, customer, placed_by_admin=True)
        
        if result['status'] == 'success':
            order_handler._check_offer_status_after_change(offer_id)

            # Get the actual order to show correct status
            orders = self.db.get_orders_by_customer(customer.customer_id)
            latest_order = max(orders, key=lambda o: o.created_at) if orders else None
            order_status = latest_order.status if latest_order else 'pending'
            
            # Try to notify target customer
            customer_message = self._t('admin_order_placed', customer.telegram_user_id,
                                     product=offer.name,
                                     quantity=quantity,
                                     total=offer.price_per_unit * quantity,
                                     status=order_status)
            pm_result = self._send_message(customer.telegram_user_id, customer_message)
            
            # Send notification to default group (admin orders don't trigger this automatically)
            order_handler._notify_channel_order(customer, offer, quantity)
            
            # Confirm to admin with PM status
            display_name = customer.first_name or "Unknown"
            admin_message = self._t('order_placed_for_user', name=display_name)
            if not pm_result.get('success'):
                admin_message += "\n" + self._t('pm_notification_failed', user_id=None, name=display_name)
            self._send_message(chat_id, admin_message)
        
        return result
    
    def handle_order_for_user_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user selection from disambiguation for order_for"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}
        
        return self._show_offers_for_order_for(chat_id, customer)
    
    def handle_order_for_offer_select(self, chat_id: int, customer_id: str, offer_id: str) -> Dict[str, Any]:
        """Handle offer selection for order_for"""
        import logging
        logger = logging.getLogger()
        logger.info(f"handle_order_for_offer_select called with customer_id: {customer_id}, offer_id: {offer_id}")
        
        customer = self.db.get_customer(customer_id)
        logger.info(f"Customer found: {customer is not None}")
        
        try:
            offer_id_int = int(offer_id)
            logger.info(f"Converted offer_id to int: {offer_id_int}")
            offer = self.db.get_offer(offer_id_int)
            logger.info(f"Offer found: {offer is not None}")
        except ValueError as e:
            logger.error(f"ValueError converting offer_id '{offer_id}' to int: {e}")
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'invalid_format'}
        
        if not customer:
            logger.error(f"Customer not found for ID: {customer_id}")
            self._send_message(chat_id, self._t('invalid_selection'))
            return {'status': 'invalid_selection'}
        
        if not offer:
            logger.error(f"Offer not found for ID: {offer_id_int}")
            self._send_message(chat_id, self._t('invalid_selection'))
            return {'status': 'invalid_selection'}
        
        logger.info(f"Proceeding to quantity selection")
        return self._show_quantity_selection_for_order_for(chat_id, customer, offer)
    
    def handle_order_for_quantity_select(self, chat_id: int, customer_id: str, offer_id: str, quantity: str) -> Dict[str, Any]:
        """Handle quantity selection for order_for"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}
        
        return self._execute_order_for_customer(chat_id, customer, int(offer_id), int(quantity))
    
    def handle_order_for_other_quantity(self, chat_id: int, customer_id: str, offer_id: str) -> Dict[str, Any]:
        """Handle 'Other' quantity selection for order_for"""
        # Store context for text input
        context_data = f"{customer_id}_{offer_id}"
        
        # Store edit context
        context = EditContext(
            chat_id=chat_id,
            edit_type='order_for_quantity_input',
            entity_id=context_data
        )
        self.db.create_edit_context(context)
        
        self._send_message(chat_id, self._t('enter_quantity_1_to_10', chat_id), 
                          reply_markup={"force_reply": True, "input_field_placeholder": "Enter quantity"})
        return {'status': 'awaiting_quantity_input'}