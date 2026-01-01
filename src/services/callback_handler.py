import logging
from typing import Dict, Any
import requests
from utils.edit_context import EditContextManager

logger = logging.getLogger()

class CallbackHandler:
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str, handlers: Dict[str, Any], media_handler):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.telegram_token = telegram_token
        self.handlers = handlers
        self.media_handler = media_handler
        self.edit_context_manager = EditContextManager(db, self._t, self._send_message)

    def handle_callback_query(self, callback_query: Dict[str, Any]) -> Dict[str, Any]:
        """Handle inline button callbacks"""
        try:
            query_id = callback_query['id']
            user_id = callback_query['from']['id']
            chat_id = callback_query['message']['chat']['id']
            message_id = callback_query['message']['message_id']
            data = callback_query['data']
            
            logger.info(f"Processing callback: {data}")
            logger.info(f"Callback data starts with confirm_order_wholesale_: {data.startswith('confirm_order_wholesale_')}")
            
            # Answer the callback query to remove loading state
            self._answer_callback_query(query_id)
            
            # Determine if we should remove the keyboard
            should_remove_keyboard = True
            if data.startswith('page_') and not data == 'page_info':
                should_remove_keyboard = False
            elif data.startswith('wd_'):  # Keep keyboard for wholesale delivery navigation
                should_remove_keyboard = False
            elif data.startswith('order_'):  # Keep keyboard for order buttons so multiple people can order
                should_remove_keyboard = False
            elif data == 'add_supplier_start':  # Keep keyboard for add supplier flow
                should_remove_keyboard = False
            
            if should_remove_keyboard:
                self._edit_message_remove_keyboard(chat_id, message_id)
            
            # Wholesale delivery callbacks
            if data.startswith('wd_'):
                return self._handle_wholesale_delivery_callbacks(chat_id, user_id, data)
            
            # Labeling completion callbacks
            elif data.startswith('lc_'):
                return self._handle_labeling_completion_callbacks(chat_id, user_id, data)
            
            # Export orders callbacks
            elif data.startswith('export_orders_'):
                status_filter = data.replace('export_orders_', '')
                return self.handlers['admin_order'].handle_export_orders_callback(chat_id, status_filter)
            
            # Delivery overview callbacks
            elif data == 'start_send_overviews':
                return self.handlers['delivery_overview'].start_send_overviews(chat_id)
            
            # Labeling completion callbacks
            elif data.startswith('finish_labeling_'):
                box_id = data.split('_', 2)[2]
                return self.handlers['labeling'].handle_finish_labeling(chat_id, box_id)
            
            # Payment marking callbacks
            elif data.startswith('mark_paid_'):
                customer_id = data.split('_', 2)[2]
                return self.handlers['delivery_overview'].handle_mark_customer_paid(chat_id, customer_id)
            
            # Admin panel callbacks
            elif data.startswith('admin_'):
                return self._handle_admin_callbacks(chat_id, user_id, data)
            elif data.startswith('cmd_'):
                return self._handle_command_callbacks(chat_id, user_id, data)
            elif data == 'add_supplier_start':
                return self._start_add_supplier(chat_id)
            
            # Order callbacks
            if data.startswith('order_'):
                if data.startswith('order_for_offer_'):
                    parts = data.split('_')
                    logger.info(f"order_for_offer callback parts: {parts}")
                    if len(parts) >= 5:
                        customer_id, offer_id = parts[3], parts[4]
                        logger.info(f"Parsed customer_id: {customer_id}, offer_id: {offer_id}")
                        return self.handlers['admin_order'].handle_order_for_offer_select(chat_id, customer_id, offer_id)
                    else:
                        logger.error(f"Invalid order_for_offer callback format: {data}, parts: {parts}")
                        return {'status': 'invalid_format'}
                elif data.startswith('order_for_quantity_'):
                    parts = data.split('_')
                    customer_id, offer_id, quantity = parts[3], parts[4], parts[5]
                    return self.handlers['admin_order'].handle_order_for_quantity_select(chat_id, customer_id, offer_id, quantity)
                elif data.startswith('order_for_other_'):
                    parts = data.split('_')
                    customer_id, offer_id = parts[3], parts[4]
                    return self.handlers['admin_order'].handle_order_for_other_quantity(chat_id, customer_id, offer_id)
                elif len(data.split('_')) >= 3:
                    parts = data.split('_')
                    offer_id = parts[1]
                    quantity = parts[2]
                    return self.handlers['customer_order'].handle_order(chat_id, user_id, [offer_id, quantity])
            elif data.startswith('wholesale_select_'):
                offer_id = data.split('_')[2]
                return self.handlers['offer'].handle_order_wholesale(chat_id, [offer_id])
            elif data.startswith('confirm_order_wholesale_'):
                logger.info(f"Matched confirm_order_wholesale_ pattern")
                parts = data.split('_')
                logger.info(f"Wholesale callback parts: {parts}")
                logger.info(f"Parts length: {len(parts)}")
                if len(parts) >= 5:
                    offer_id = parts[3]
                    boxes = parts[4]
                    logger.info(f"Calling handle_confirm_order_wholesale with offer_id={offer_id}, boxes={boxes}")
                    try:
                        return self.handlers['offer'].handle_confirm_order_wholesale(chat_id, [offer_id, boxes])
                    except Exception as e:
                        logger.error(f"Exception in handle_confirm_order_wholesale: {e}")
                        from handlers.base_handler import BaseHandler
                        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                        base_handler._send_message(chat_id, base_handler._t('invalid_format'))
                        return {'status': 'exception'}
                else:
                    logger.error(f"Invalid wholesale callback format: {data}, expected at least 5 parts, got {len(parts)}")
                    from handlers.base_handler import BaseHandler
                    base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                    base_handler._send_message(chat_id, base_handler._t('invalid_format'))
                    return {'status': 'invalid_format'}
            elif data.startswith('custom_wholesale_quantity_'):
                offer_id = data.split('_')[3]
                return self.handlers['offer'].handle_custom_wholesale_quantity(chat_id, offer_id)
            elif data.startswith('confirm_order_'):
                parts = data.split('_')
                if len(parts) >= 4:
                    offer_id = parts[2]
                    quantity = parts[3]
                    return self.handlers['customer_order'].handle_confirm_order(chat_id, user_id, [offer_id, quantity])
            elif data == 'cancel_confirmation':
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, base_handler._t('action_cancelled'))
                return {'status': 'cancelled'}
            
            # Admin confirmation callbacks
            elif data.startswith('confirm_cancel_offer_'):
                offer_id = data.split('_')[3]
                return self.handlers['offer'].handle_confirm_cancel_offer(chat_id, [offer_id])
            elif data.startswith('confirm_fulfill_'):
                parts = data.split('_')
                if len(parts) >= 4:
                    offer_id = parts[2]
                    boxes = parts[3]
                    return self.handlers['offer'].handle_confirm_fulfill(chat_id, [offer_id, boxes])
            elif data.startswith('request_cancel_reason_'):
                order_id = data.split('_')[3]
                return self._request_cancellation_reason(chat_id, order_id)
            elif data.startswith('confirm_cancel_order_'):
                order_id = data.split('_')[3]
                return self.handlers['admin_order'].handle_confirm_cancel(chat_id, [order_id])
            elif data.startswith('approve_user_'):
                customer_id = data.split('_')[2]
                return self.handlers['user'].handle_approve_user_by_id(chat_id, customer_id)
            elif data.startswith('reject_user_'):
                customer_id = data.split('_')[2]
                return self.handlers['user'].handle_reject_user_by_id(chat_id, customer_id)
            elif data.startswith('edit_user_select_'):
                customer_id = data.split('_')[3]
                return self.handlers['user'].handle_edit_user_select(chat_id, customer_id)
            elif data.startswith('edit_supplier_select_'):
                supplier_id = data.split('_')[3]
                return self.handlers['supplier']._show_edit_interface_by_id(chat_id, supplier_id)
            elif data == 'back_to_supplier_list':
                return self.handlers['supplier'].handle_list_suppliers(chat_id, 1, 'active')
            elif data.startswith('user_orders_select_'):
                customer_id = data.split('_')[3]
                return self.handlers['admin_order'].handle_user_orders_select(chat_id, customer_id)
            elif data.startswith('cancel_order_user_select_'):
                customer_id = data.split('_')[4]
                return self.handlers['admin_order'].handle_cancel_order_user_select(chat_id, customer_id)
            elif data.startswith('cancel_order_confirm_'):
                order_id = data.split('_')[3]
                return self.handlers['admin_order']._handle_cancel_order_by_id(chat_id, order_id)
            elif data.startswith('cancel_orders_page_'):
                parts = data.split('_')
                customer_id, page = parts[3], int(parts[4])
                return self.handlers['admin_order'].handle_cancel_orders_page(chat_id, customer_id, page)
            elif data == 'enter_username_orders':
                return self._start_user_orders_input(chat_id)
            elif data == 'enter_username_cancel':
                return self._start_cancel_order_input(chat_id)
            elif data == 'enter_username_order_for':
                return self._start_order_for_input(chat_id)
            elif data.startswith('approve_user_select_'):
                customer_id = data.replace('approve_user_select_', '')
                return self.handlers['user'].handle_approve_user_select(chat_id, customer_id)
            elif data.startswith('order_for_user_select_'):
                customer_id = data.split('_')[4]
                return self.handlers['admin_order'].handle_order_for_user_select(chat_id, customer_id)
            elif data.startswith('user_status_select_'):
                customer_id = data.replace('user_status_select_', '')
                return self.handlers['user'].handle_user_status_select(chat_id, customer_id)

            elif data == 'done_editing':
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, base_handler._t('done'))
                return {'status': 'done'}
            elif data == 'cancel_action':
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, base_handler._t('done'))
                return {'status': 'done'}
            
            # Pagination callbacks
            elif data.startswith('page_'):
                parts = data.split('_')
                if len(parts) >= 3:
                    if len(parts) == 4 and parts[1] in ['customers', 'suppliers']:
                        entity_type = f"{parts[1]}_{parts[2]}"
                        page = int(parts[3])
                    else:
                        entity_type = parts[1]
                        page = int(parts[2])
                    
                    if entity_type == 'suppliers' or entity_type.startswith('suppliers_'):
                        status_filter = entity_type.split('_', 1)[1] if '_' in entity_type else 'active'
                        return self.handlers['supplier'].handle_list_suppliers(chat_id, page, status_filter)
                    elif entity_type == 'boxes':
                        return self.handlers['offer'].handle_box_status(chat_id, [str(page)])
                    elif entity_type == 'pending':
                        return self.handlers['user'].handle_pending_users(chat_id, page)
                    elif entity_type.startswith('customers_'):
                        status_filter = entity_type.split('_', 1)[1]
                        return self.handlers['user'].handle_list_users(chat_id, page, status_filter)
                    elif entity_type == 'subscribers':
                        return self.handlers['user'].handle_list_subscribers(chat_id, page)
                    elif entity_type == 'changelog':
                        return self.handlers['changelog'].handle_changelog(chat_id, user_id, page)
            elif data == 'page_info':
                return {'status': 'page_info'}
            
            # Edit callbacks
            elif data.startswith('edit_'):
                return self._handle_edit_callbacks(chat_id, user_id, data)
            
            # Offer management callbacks
            elif data.startswith('offer_details_'):
                parts = data.split('_')
                if len(parts) >= 3:
                    offer_id = parts[2]
                    edit_mode = len(parts) > 3 and parts[3] == 'edit'
                    args = [offer_id, 'edit'] if edit_mode else [offer_id]
                    return self.handlers['info'].handle_offer_details(chat_id, user_id, args)
            elif data.startswith('upload_offer_image_'):
                offer_id = data.split('_')[3]
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, base_handler._t('awaiting_image', offer_id=offer_id))
                self._store_edit_context(chat_id, 'offer_image_upload', offer_id)
                return {'status': 'awaiting_image'}
            elif data.startswith('clear_offer_images_'):
                offer_id = data.split('_')[3]
                return self.media_handler.handle_clear_offer_images(chat_id, offer_id)
            elif data.startswith('publish_offer_'):
                offer_id = data.split('_')[2]
                return self.handlers['offer'].handle_publish_offer(chat_id, [offer_id])
            
            # Audit offer callbacks
            elif data.startswith('offer_orders_page_'):
                page = int(data.split('_')[3])
                return self.handlers['admin_order'].handle_offer_orders_page(chat_id, page)
            elif data.startswith('offer_orders_detail_'):
                parts = data.split('_')
                offer_id, page = int(parts[3]), int(parts[4])
                return self.handlers['admin_order'].handle_offer_orders_detail_page(chat_id, str(offer_id), page)
            elif data.startswith('offer_orders_'):
                offer_id = data.split('_')[2]
                return self.handlers['admin_order'].handle_offer_orders_select(chat_id, offer_id)
            elif data.startswith('audit_offers_page_'):
                page = int(data.split('_')[3])
                return self.handlers['offer']._show_audit_offer_selection(chat_id, page)
            elif data.startswith('audit_fill_boxes_'):
                parts = data.split('_')
                offer_id, excess_units = int(parts[3]), int(parts[4])
                return self.handlers['offer']._execute_fill_boxes(chat_id, offer_id, excess_units)
            elif data.startswith('audit_fill_create_'):
                parts = data.split('_')
                offer_id, excess_units = int(parts[3]), int(parts[4])
                return self.handlers['offer']._execute_fill_and_create(chat_id, offer_id, excess_units)
            elif data.startswith('audit_create_boxes_'):
                parts = data.split('_')
                offer_id, excess_units = int(parts[3]), int(parts[4])
                return self.handlers['offer']._execute_create_boxes(chat_id, offer_id, excess_units)
            elif data.startswith('audit_cancel_orders_'):
                parts = data.split('_')
                offer_id, excess_units = int(parts[3]), int(parts[4])
                return self.handlers['offer']._execute_cancel_orders(chat_id, offer_id, excess_units)
            elif data.startswith('audit_offer_'):
                offer_id = data.split('_')[2]
                return self.handlers['offer']._execute_audit_offer(chat_id, int(offer_id))
            
            return {'status': 'unknown_callback'}
            
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            logger.error(f"Callback data was: {callback_query.get('data', 'NO_DATA')}")
            return {'status': 'error', 'error': str(e)}
    
    def _handle_edit_callbacks(self, chat_id: int, user_id: int, data: str) -> Dict[str, Any]:
        """Handle edit-related callbacks"""
        parts = data.split('_')
        
        if len(parts) >= 4:
            # Handle special case for customer first/last name editing
            if parts[1] == 'customer' and len(parts) == 5:
                if parts[2] == 'first' and parts[3] == 'name':
                    return self._handle_customer_edit(chat_id, 'first_name', parts[4])
                elif parts[2] == 'last' and parts[3] == 'name':
                    return self._handle_customer_edit(chat_id, 'last_name', parts[4])
            
            # Handle special case for supplier full_name editing
            if parts[1] == 'supplier' and len(parts) == 5 and parts[2] == 'full' and parts[3] == 'name':
                return self._handle_supplier_edit(chat_id, 'full_name', parts[4])
            
            # Handle offer_details callback with edit mode
            if parts[1] == 'offer' and parts[2] == 'details':
                offer_id = parts[3]
                edit_mode = len(parts) > 4 and parts[4] == 'edit'
                args = [offer_id, 'edit'] if edit_mode else [offer_id]
                return self.handlers['info'].handle_offer_details(chat_id, user_id, args)
            
            # Standard format: edit_{entity}_{field}_{id}
            entity_type = parts[1]
            field = parts[2]
            entity_id = parts[3]
            
            if entity_type == 'supplier':
                return self._handle_supplier_edit(chat_id, field, entity_id)
            elif entity_type == 'offer':
                return self._handle_offer_edit(chat_id, field, entity_id)
        
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        base_handler._send_message(chat_id, base_handler._t('unknown_edit'))
        return {'status': 'unknown_edit'}
    
    def _handle_supplier_edit(self, chat_id: int, field: str, supplier_id: str) -> Dict[str, Any]:
        """Handle supplier edit callbacks"""
        return self.edit_context_manager.handle_supplier_edit(chat_id, field, supplier_id)
    
    def _handle_offer_edit(self, chat_id: int, field: str, offer_id: str) -> Dict[str, Any]:
        """Handle offer edit callbacks"""
        return self.edit_context_manager.handle_offer_edit(chat_id, field, offer_id)
    
    def _handle_customer_edit(self, chat_id: int, field: str, customer_id: str) -> Dict[str, Any]:
        """Handle customer edit callbacks"""
        return self.edit_context_manager.handle_customer_edit(chat_id, field, customer_id)
    
    def _store_edit_context(self, chat_id: int, edit_type: str, entity_id: str):
        """Store edit context in DynamoDB for processing replies"""
        self.edit_context_manager.store_edit_context(chat_id, edit_type, entity_id)
    
    def _answer_callback_query(self, query_id: str) -> bool:
        """Answer callback query to remove loading state"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/answerCallbackQuery"
            data = {'callback_query_id': query_id}
            response = requests.post(url, json=data, timeout=20)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error answering callback query: {e}")
            return False
    
    def _edit_message_remove_keyboard(self, chat_id: int, message_id: int) -> bool:
        """Remove inline keyboard from a message"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/editMessageReplyMarkup"
            data = {
                'chat_id': chat_id,
                'message_id': message_id,
                'reply_markup': {'inline_keyboard': []}
            }
            response = requests.post(url, json=data, timeout=20)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error removing keyboard: {e}")
            return False
    
    def _handle_wholesale_delivery_callbacks(self, chat_id: int, user_id: int, data: str) -> Dict[str, Any]:
        """Handle wholesale delivery callbacks"""
        if not self._is_admin(user_id):
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
            return base_handler._send_message(chat_id, base_handler._t('admin_only', user_id))
        
        parts = data.split(':')
        
        if parts[0] == 'wd_sup':  # Supplier selection
            supplier_id = parts[1]
            return self.handlers['wholesale_delivery'].handle_supplier_selection(chat_id, supplier_id)
        elif parts[0] == 'wd_off':  # Offer selection
            offer_id, supplier_id = int(parts[1]), parts[2]
            return self.handlers['wholesale_delivery'].handle_offer_selection(chat_id, offer_id, supplier_id)
        elif parts[0] == 'wd_box':  # Box selection
            box_id, offer_id, supplier_id = parts[1], int(parts[2]), parts[3]
            return self.handlers['wholesale_delivery'].handle_box_selection(chat_id, box_id, offer_id, supplier_id)
        elif parts[0] == 'wd_action':  # Delivery action
            action, box_id, offer_id, supplier_id = parts[1], parts[2], int(parts[3]), parts[4]
            return self.handlers['wholesale_delivery'].handle_delivery_action(chat_id, action, box_id, offer_id, supplier_id)
        elif parts[0] == 'wd_partial':  # Partial delivery action
            action, box_id, received_units = parts[1], parts[2], int(parts[3])
            return self.handlers['wholesale_delivery'].handle_partial_action(chat_id, action, box_id, received_units)
        elif parts[0] == 'wd_back':  # Back navigation
            target = parts[1]
            args = parts[2:] if len(parts) > 2 else []
            return self.handlers['wholesale_delivery'].handle_back_navigation(chat_id, target, *args)
        elif parts[0] == 'wd_complete':  # Complete delivery
            offer_id, supplier_id_short = int(parts[1]), parts[2]
            return self.handlers['wholesale_delivery'].handle_complete_delivery(chat_id, offer_id, supplier_id_short)
        elif parts[0] == 'wd_confirm_complete':  # Confirm complete delivery
            if len(parts) >= 3:
                offer_id, supplier_id_short = int(parts[1]), parts[2]
                return self.handlers['wholesale_delivery'].handle_confirm_complete_delivery(chat_id, offer_id, supplier_id_short)
            else:
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                return base_handler._send_message(chat_id, base_handler._t('invalid_format'))
        
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        return base_handler._send_message(chat_id, base_handler._t('unknown_callback', user_id))
    
    def _handle_labeling_completion_callbacks(self, chat_id: int, user_id: int, data: str) -> Dict[str, Any]:
        """Handle labeling completion callbacks"""
        if not self._is_admin(user_id):
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
            return base_handler._send_message(chat_id, base_handler._t('admin_only', user_id))
        
        parts = data.split(':')
        
        if parts[0] == 'lc_sup':  # Supplier selection
            supplier_id_short = parts[1]
            return self.handlers['labeling'].handle_supplier_selection(chat_id, supplier_id_short)
        elif parts[0] == 'lc_off':  # Offer selection
            offer_id, supplier_id_short = int(parts[1]), parts[2]
            return self.handlers['labeling'].handle_offer_selection(chat_id, offer_id, supplier_id_short)
        elif parts[0] == 'lc_box':  # Box selection
            box_id_short, offer_id, supplier_id_short = parts[1], int(parts[2]), parts[3]
            return self.handlers['labeling'].handle_box_selection(chat_id, box_id_short, offer_id, supplier_id_short)
        elif parts[0] == 'lc_action':  # Labeling action
            action, box_id_short, offer_id, supplier_id_short = parts[1], parts[2], int(parts[3]), parts[4]
            return self.handlers['labeling'].handle_labeling_action(chat_id, action, box_id_short, offer_id, supplier_id_short)
        elif parts[0] == 'lc_back':  # Back navigation
            target = parts[1]
            args = parts[2:] if len(parts) > 2 else []
            return self.handlers['labeling'].handle_back_navigation(chat_id, target, *args)
        
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        return base_handler._send_message(chat_id, base_handler._t('unknown_callback', user_id))
    
    def _handle_admin_callbacks(self, chat_id: int, user_id: int, data: str) -> Dict[str, Any]:
        """Handle admin panel navigation callbacks"""
        if not self._is_admin(user_id):
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
            base_handler._send_message(chat_id, base_handler._t('admin_only', user_id))
            return {'status': 'unauthorized'}
        
        if data == 'admin_main':
            return self.handlers['admin_commands'].handle_admin(chat_id, user_id)
        elif data == 'admin_workflow':
            return self.handlers['admin_commands'].handle_admin_workflow(chat_id, user_id)
        elif data == 'admin_suppliers':
            return self.handlers['admin_commands'].handle_admin_suppliers(chat_id, user_id)
        elif data == 'admin_offers':
            return self.handlers['admin_commands'].handle_admin_offers(chat_id, user_id)
        elif data == 'admin_orders':
            return self.handlers['admin_commands'].handle_admin_orders(chat_id, user_id)
        elif data == 'admin_users':
            return self.handlers['admin_commands'].handle_admin_users(chat_id, user_id)
        elif data == 'admin_delivery':
            return self.handlers['admin_commands'].handle_admin_delivery(chat_id, user_id)
        elif data == 'admin_discounts':
            return self.handlers['admin_commands'].handle_admin_discounts(chat_id, user_id)
        elif data == 'admin_system':
            return self.handlers['admin_commands'].handle_admin_system(chat_id, user_id)
        
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        base_handler._send_message(chat_id, base_handler._t('unknown_callback', user_id))
        return {'status': 'unknown_callback'}
    
    def _handle_command_callbacks(self, chat_id: int, user_id: int, data: str) -> Dict[str, Any]:
        """Handle command execution callbacks from admin panel"""
        if not self._is_admin(user_id):
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
            base_handler._send_message(chat_id, base_handler._t('admin_only', user_id))
            return {'status': 'unauthorized'}
        
        # Map callback data to command handlers
        command_map = {
            'cmd_add_supplier': lambda: self.handlers['supplier'].handle_add_supplier(chat_id, []),
            'cmd_list_suppliers': lambda: self.handlers['supplier'].handle_list_suppliers(chat_id, 1, 'active'),
            'cmd_edit_supplier': lambda: self.handlers['supplier'].handle_list_suppliers(chat_id, 1, 'active'),
            'cmd_create_offer': lambda: self.handlers['offer'].handle_create_offer(chat_id, []),
            'cmd_publish_offer': lambda: self._send_usage_message(chat_id, 'usage_publish_offer'),
            'cmd_list_offers': lambda: self.handlers['info'].handle_list_offers(chat_id, user_id, []),
            'cmd_box_status': lambda: self.handlers['offer'].handle_box_status(chat_id),
            'cmd_audit_offer': lambda: self.handlers['offer'].handle_audit_offer(chat_id, []),
            'cmd_order_wholesale': lambda: self.handlers['offer'].handle_order_wholesale(chat_id, []),
            'cmd_all_orders': lambda: self.handlers['admin_order'].handle_all_orders(chat_id, []),
            'cmd_user_orders': lambda: self._start_user_orders_input(chat_id),
            'cmd_offer_orders': lambda: self.handlers['admin_order'].handle_offer_orders(chat_id, []),
            'cmd_cancel_order': lambda: self.handlers['admin_order'].handle_cancel_order(chat_id, []),
            'cmd_order_for': lambda: self.handlers['admin_order'].handle_order_for(chat_id, user_id, []),
            'cmd_pending_users': lambda: self.handlers['user'].handle_pending_users(chat_id),
            'cmd_list_users': lambda: self.handlers['user'].handle_list_users(chat_id, 1, 'all'),
            'cmd_approve_user': lambda: self._start_approve_user_input(chat_id),
            'cmd_user_status': lambda: self._start_user_status_input(chat_id),
            'cmd_wholesale_delivery': lambda: self.handlers['wholesale_delivery'].handle_wholesale_delivery(chat_id, user_id, []),
            'cmd_labeling_completed': lambda: self.handlers['labeling'].handle_labeling_completed(chat_id, user_id, []),
            'cmd_send_overviews': lambda: self.handlers['admin_order'].handle_send_overviews(chat_id, []),
            'cmd_mark_paid': lambda: self.handlers['admin_order'].handle_mark_paid(chat_id, []),
            'cmd_create_discount': lambda: self._send_usage_message(chat_id, 'usage_create_discount'),
            'cmd_discount_status': lambda: self.handlers['discount'].handle_discount_status(chat_id),
            'cmd_cancel_discount': lambda: self.handlers['discount'].handle_cancel_discount(chat_id),
            'cmd_setup_test_data': lambda: self.handlers['test'].handle_setup_test_data(chat_id),
            'cmd_failed_notifications': lambda: self.handlers['admin_order'].handle_failed_notifications(chat_id, []),
            'cmd_delete_old_cancelled': lambda: self.handlers['admin_order'].handle_delete_cancelled(chat_id),
            'cmd_audit_orders': lambda: self.handlers['admin_order'].handle_audit_orders(chat_id),
            'add_supplier_start': lambda: self._start_add_supplier(chat_id)
        }
        
        if data in command_map:
            return command_map[data]()
        
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        base_handler._send_message(chat_id, base_handler._t('unknown_callback', user_id))
        return {'status': 'unknown_callback'}
    
    def _start_add_supplier(self, chat_id: int) -> Dict[str, Any]:
        """Start add supplier process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, 'add_supplier_name')
    
    def _start_user_orders_input(self, chat_id: int) -> Dict[str, Any]:
        """Start user orders process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, 'user_orders_input')
    
    def _start_cancel_order_input(self, chat_id: int) -> Dict[str, Any]:
        """Start cancel order process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, 'cancel_order_input')
    
    def _start_order_for_input(self, chat_id: int) -> Dict[str, Any]:
        """Start order_for process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, 'order_for_input')
    
    def _start_edit_supplier_input(self, chat_id: int) -> Dict[str, Any]:
        """Start edit supplier process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, 'edit_supplier_input')
    
    def _start_approve_user_input(self, chat_id: int) -> Dict[str, Any]:
        """Start approve user process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, 'approve_user_input')
    
    def _start_user_status_input(self, chat_id: int) -> Dict[str, Any]:
        """Start user status process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, 'user_status_input')
    
    def _send_usage_message(self, chat_id: int, usage_key: str) -> Dict[str, Any]:
        """Send usage message for commands that require parameters"""
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        base_handler._send_message(chat_id, base_handler._t(usage_key))
        return {'status': 'usage_sent'}
    
    def _t(self, key: str, **params) -> str:
        """Translation helper for EditContextManager"""
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        return base_handler._t(key, **params)
    
    def _send_message(self, chat_id: int, text: str, parse_mode: str = None, reply_markup: dict = None, force_group: bool = False) -> dict:
        """Send message helper for EditContextManager"""
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        return base_handler._send_message(chat_id, text, parse_mode, reply_markup, force_group)
    
    def _request_cancellation_reason(self, chat_id: int, order_id: str) -> Dict[str, Any]:
        """Request cancellation reason from admin"""
        from models.entities import EditContext
        
        # Store edit context for cancellation reason
        context = EditContext(
            chat_id=chat_id,
            edit_type='cancel_order_reason',
            entity_id=order_id
        )
        self.db.create_edit_context(context)
        
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        base_handler._send_message(chat_id, base_handler._t('enter_cancellation_reason'), 
                                  reply_markup={"force_reply": True, "input_field_placeholder": "Enter reason"})
        return {'status': 'awaiting_reason_input'}
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id