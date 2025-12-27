import logging
from typing import Dict, Any
import requests

logger = logging.getLogger()

class CallbackHandler:
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str, handlers: Dict[str, Any], media_handler):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.telegram_token = telegram_token
        self.handlers = handlers
        self.media_handler = media_handler

    def handle_callback_query(self, callback_query: Dict[str, Any]) -> Dict[str, Any]:
        """Handle inline button callbacks"""
        try:
            query_id = callback_query['id']
            user_id = callback_query['from']['id']
            chat_id = callback_query['message']['chat']['id']
            message_id = callback_query['message']['message_id']
            data = callback_query['data']
            
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
            
            # Order callbacks
            if data.startswith('order_'):
                parts = data.split('_')
                if len(parts) >= 3:
                    offer_id = parts[1]
                    quantity = parts[2]
                    return self.handlers['customer_order'].handle_order(chat_id, user_id, [offer_id, quantity])
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
            elif data.startswith('confirm_order_wholesale_'):
                parts = data.split('_')
                if len(parts) >= 5:
                    offer_id = parts[3]
                    boxes = parts[4]
                    return self.handlers['offer'].handle_confirm_order_wholesale(chat_id, [offer_id, boxes])
            elif data.startswith('confirm_fulfill_'):
                parts = data.split('_')
                if len(parts) >= 4:
                    offer_id = parts[2]
                    boxes = parts[3]
                    return self.handlers['offer'].handle_confirm_fulfill(chat_id, [offer_id, boxes])
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
            elif data.startswith('user_orders_select_'):
                customer_id = data.split('_')[3]
                return self.handlers['admin_order'].handle_user_orders_select(chat_id, customer_id)
            elif data == 'done_editing':
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, base_handler._t('done'))
                return {'status': 'done'}
            elif data == 'cancel_action':
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, base_handler._t('action_cancelled'))
                return {'status': 'cancelled'}
            
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
                        return self.handlers['offer'].handle_box_status(chat_id, page)
                    elif entity_type == 'pending':
                        return self.handlers['user'].handle_pending_users(chat_id, page)
                    elif entity_type.startswith('customers_'):
                        status_filter = entity_type.split('_', 1)[1]
                        return self.handlers['user'].handle_list_users(chat_id, page, status_filter)
                    elif entity_type == 'subscribers':
                        return self.handlers['user'].handle_list_subscribers(chat_id, page)
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
            
            return {'status': 'unknown_callback'}
            
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
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
        supplier = self.db.get_supplier(supplier_id)
        if not supplier:
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
            base_handler._send_message(chat_id, base_handler._t('supplier_not_found', user_id=None))
            return {'status': 'supplier_not_found'}
        
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        if field == 'status':
            new_status = 'retired' if supplier.status == 'active' else 'active'
            if self.db.update_supplier(supplier_id, {'status': new_status}):
                base_handler._send_message(chat_id, base_handler._t('supplier_status_updated', user_id=None, 
                                                                 name=supplier.name, status=new_status))
                return {'status': 'success'}
            else:
                base_handler._send_message(chat_id, base_handler._t('failed_update_supplier_status', user_id=None))
                return {'status': 'error'}
        elif field == 'name':
            self._store_edit_context(chat_id, 'supplier_name', supplier_id)
            base_handler._send_message(chat_id, base_handler._t('enter_new_supplier_name', user_id=None, name=supplier.name), 
                                     reply_markup={"force_reply": True, "input_field_placeholder": "Enter supplier name"})
        elif field == 'contact':
            self._store_edit_context(chat_id, 'supplier_contact', supplier_id)
            base_handler._send_message(chat_id, base_handler._t('enter_supplier_contact', user_id=None, name=supplier.name), 
                                     reply_markup={"force_reply": True, "input_field_placeholder": "Enter email address"})
        else:
            base_handler._send_message(chat_id, base_handler._t('unknown_edit_field', user_id=None))
            return {'status': 'unknown_field'}
        
        return {'status': 'text_input_required'}
    
    def _handle_offer_edit(self, chat_id: int, field: str, offer_id: str) -> Dict[str, Any]:
        """Handle offer edit callbacks"""
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        if field == 'name':
            self._store_edit_context(chat_id, 'offer_name', offer_id)
            base_handler._send_message(chat_id, base_handler._t('enter_new_offer_name', user_id=None, offer_id=offer_id), 
                                     reply_markup={"force_reply": True, "input_field_placeholder": "Enter offer name"})
        elif field == 'price':
            self._store_edit_context(chat_id, 'offer_price', offer_id)
            base_handler._send_message(chat_id, base_handler._t('enter_new_offer_price', user_id=None, offer_id=offer_id), 
                                     reply_markup={"force_reply": True, "input_field_placeholder": "Enter price (e.g. 12.50)"})
        elif field == 'description':
            self._store_edit_context(chat_id, 'offer_description', offer_id)
            base_handler._send_message(chat_id, base_handler._t('enter_new_offer_description', user_id=None, offer_id=offer_id), 
                                     reply_markup={"force_reply": True, "input_field_placeholder": "Enter description"})
        else:
            base_handler._send_message(chat_id, base_handler._t('unknown_edit_field', user_id=None))
            return {'status': 'unknown_field'}
        
        return {'status': 'text_input_required'}
    
    def _handle_customer_edit(self, chat_id: int, field: str, customer_id: str) -> Dict[str, Any]:
        """Handle customer edit callbacks"""
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        if field == 'first_name':
            self._store_edit_context(chat_id, 'customer_first_name', customer_id)
            base_handler._send_message(chat_id, base_handler._t('enter_new_first_name', user_id=None), 
                                     reply_markup={"force_reply": True, "input_field_placeholder": "Enter first name"})
        elif field == 'last_name':
            self._store_edit_context(chat_id, 'customer_last_name', customer_id)
            base_handler._send_message(chat_id, base_handler._t('enter_new_last_name', user_id=None), 
                                     reply_markup={"force_reply": True, "input_field_placeholder": "Enter last name"})
        else:
            base_handler._send_message(chat_id, base_handler._t('unknown_edit_field', user_id=None))
            return {'status': 'unknown_field'}
        
        return {'status': 'text_input_required'}
    
    def _store_edit_context(self, chat_id: int, edit_type: str, entity_id: str):
        """Store edit context in DynamoDB for processing replies"""
        from models.entities import EditContext
        logger.info(f"Storing edit context: chat_id={chat_id}, type={edit_type}, entity_id={entity_id}")
        
        # Delete any existing context for this chat
        existing = self.db.get_edit_context_by_chat_id(chat_id)
        if existing:
            self.db.delete_edit_context(existing.context_id)
        
        # Cleanup old contexts periodically
        import random
        if random.randint(1, 20) == 1:
            cleaned = self.db.cleanup_old_edit_contexts()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} old edit contexts")
        
        # Create new context
        context = EditContext(
            chat_id=chat_id,
            edit_type=edit_type,
            entity_id=entity_id
        )
        self.db.create_edit_context(context)
    
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
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id