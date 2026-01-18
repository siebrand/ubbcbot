import logging
from typing import Dict, Any
import requests
from utils.edit_context import EditContextManager
from services.routing.callback_router import CallbackRouter

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
        
        # Initialize callback router
        self.router = CallbackRouter()
        self._register_routes()

    def _register_routes(self):
        """Register callback patterns with router (Phase 3 Batch B: add order patterns)"""
        # Approve user patterns - register more specific pattern first
        self.router.register(
            r"^approve_user_select_(.+)$",
            lambda match, ctx: self.handlers['user'].handle_approve_user_select(ctx['chat_id'], match.group(1))
        )
        self.router.register(
            r"^approve_user_([^_]+)$",  # Match approve_user_ but not approve_user_select_
            lambda match, ctx: self.handlers['user'].handle_approve_user_by_id(ctx['chat_id'], match.group(1))
        )
        
        # Reject user pattern
        self.router.register(
            r"^reject_user_(.+)$",
            lambda match, ctx: self.handlers['user'].handle_reject_user_by_id(ctx['chat_id'], match.group(1))
        )
        
        # Cancel patterns - most specific first
        self.router.register(
            r"^cancel_order_user_select_(.+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_cancel_order_user_select(ctx['chat_id'], match.group(1))
        )
        self.router.register(
            r"^cancel_order_confirm_(.+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_cancel_order_by_id(ctx['chat_id'], match.group(1))
        )
        self.router.register(
            r"^cancel_orders_page_(\w+)_(\d+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_cancel_orders_page(ctx['chat_id'], match.group(1), int(match.group(2)))
        )
        self.router.register(
            r"^cancel_confirmation$",
            lambda match, ctx: self._send_message(ctx['chat_id'], self._t('action_cancelled'))
        )
        self.router.register(
            r"^cancel_action$",
            lambda match, ctx: self.handlers['admin_commands'].handle_admin(ctx['chat_id'], ctx['user_id'])
        )
        
        # Confirm patterns - most specific first
        self.router.register(
            r"^confirm_process_wholesale_(\d+)_(\d+)$",
            lambda match, ctx: self._handle_confirm_wholesale_wrapper(ctx['chat_id'], match.group(1), match.group(2))
        )
        self.router.register(
            r"^confirm_cancel_offer_(\d+)$",
            lambda match, ctx: self.handlers['offer'].handle_confirm_cancel_offer(ctx['chat_id'], [match.group(1)])
        )
        self.router.register(
            r"^confirm_cancel_order_(.+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_confirm_cancel(ctx['chat_id'], [match.group(1)])
        )
        self.router.register(
            r"^confirm_fulfill_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers['offer'].handle_confirm_fulfill(ctx['chat_id'], [match.group(1), match.group(2)])
        )
        self.router.register(
            r"^confirm_order_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers['customer_order'].handle_confirm_order(ctx['chat_id'], ctx['user_id'], [match.group(1), match.group(2)])
        )
        
        # Edit patterns - most specific first (Phase 3 Batch A)
        self.router.register(
            r"^edit_user_select_(.+)$",
            lambda match, ctx: self.handlers['user'].handle_edit_user_select(ctx['chat_id'], match.group(1))
        )
        self.router.register(
            r"^edit_supplier_select_(.+)$",
            lambda match, ctx: self.handlers['supplier'].show_edit_interface_by_id(ctx['chat_id'], match.group(1))
        )
        # Generic edit pattern: edit_{entity}_{field}_{id} - handled by _handle_edit_callbacks wrapper
        self.router.register(
            r"^edit_(.+)$",
            lambda match, ctx: self._handle_edit_callbacks(ctx['chat_id'], ctx['user_id'], f"edit_{match.group(1)}")
        )
        
        # Order patterns - most specific first (Phase 3 Batch B)
        self.router.register(
            r"^order_for_quantity_(\w+)_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_order_for_quantity_select(ctx['chat_id'], match.group(1), match.group(2), match.group(3))
        )
        self.router.register(
            r"^order_for_other_(\w+)_(\d+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_order_for_other_quantity(ctx['chat_id'], match.group(1), match.group(2))
        )
        self.router.register(
            r"^order_for_offer_(\w+)_(\d+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_order_for_offer_select(ctx['chat_id'], match.group(1), match.group(2))
        )
        self.router.register(
            r"^order_for_user_select_(.+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_order_for_user_select(ctx['chat_id'], match.group(1))
        )
        self.router.register(
            r"^order_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers['customer_order'].handle_order(ctx['chat_id'], ctx['user_id'], [match.group(1), match.group(2)])
        )
        
        # Offer/Supplier patterns - most specific first (Phase 3 Batch C)
        self.router.register(
            r"^offer_orders_detail_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_list_offer_orders_detail_page(ctx['chat_id'], match.group(1), int(match.group(2)))
        )
        self.router.register(
            r"^offer_orders_page_(\d+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_list_offer_orders_page(ctx['chat_id'], int(match.group(1)))
        )
        self.router.register(
            r"^offer_orders_(\d+)$",
            lambda match, ctx: self.handlers['admin_order'].handle_list_offer_orders_select(ctx['chat_id'], match.group(1))
        )
        self.router.register(
            r"^offer_details_(\d+)(?:_(edit))?$",
            lambda match, ctx: self.handlers['info'].handle_offer_details(ctx['chat_id'], ctx['user_id'], [match.group(1)] + ([match.group(2)] if match.group(2) else []))
        )
        self.router.register(
            r"^wholesale_select_(\d+)$",
            lambda match, ctx: self.handlers['offer'].handle_process_wholesale(ctx['chat_id'], [match.group(1)])
        )
        self.router.register(
            r"^custom_wholesale_quantity_(\d+)$",
            lambda match, ctx: self.handlers['offer'].handle_custom_wholesale_quantity(ctx['chat_id'], match.group(1))
        )
        self.router.register(
            r"^publish_offer_(\d+)$",
            lambda match, ctx: self.handlers['offer'].handle_publish_offer(ctx['chat_id'], [match.group(1)])
        )
        self.router.register(
            r"^finalize_import_(\d+)$",
            lambda match, ctx: self.handlers['import'].handle_finalize_import(ctx['chat_id'], [match.group(1)])
        )
        self.router.register(
            r"^upload_offer_image_(\d+)$",
            lambda match, ctx: self._handle_upload_offer_image(ctx['chat_id'], match.group(1))
        )
        self.router.register(
            r"^clear_offer_images_(\d+)$",
            lambda match, ctx: self._handle_clear_offer_images(ctx['chat_id'], ctx['user_id'], match.group(1))
        )
    
    def _handle_confirm_wholesale_wrapper(self, chat_id: int, offer_id: str, boxes: str) -> Dict[str, Any]:
        """Wrapper for confirm_process_wholesale with error handling"""
        try:
            logger.info(f"Calling handle_confirm_process_wholesale with offer_id={offer_id}, boxes={boxes}")
            return self.handlers['offer'].handle_confirm_process_wholesale(chat_id, [offer_id, boxes])
        except Exception as e:
            logger.error(f"Exception in handle_confirm_process_wholesale: {e}")
            self._send_message(chat_id, self._t('invalid_format'))
            return {'status': 'exception'}
    
    def _handle_upload_offer_image(self, chat_id: int, offer_id: str) -> Dict[str, Any]:
        """Wrapper for upload_offer_image"""
        self._send_message(chat_id, self._t('awaiting_image', offer_id=offer_id))
        self._store_edit_context(chat_id, 'offer_image_upload', offer_id)
        return {'status': 'awaiting_image'}
    
    def _handle_clear_offer_images(self, chat_id: int, user_id: int, offer_id: str) -> Dict[str, Any]:
        """Wrapper for clear_offer_images"""
        result = self.media_handler.handle_clear_offer_images(chat_id, offer_id)
        if result.get('return_to_edit'):
            return self.handlers['info'].handle_offer_details(chat_id, user_id, [str(result['offer_id']), 'edit'])
        return result
    
    def handle_callback_query(self, callback_query: Dict[str, Any]) -> Dict[str, Any]:
        """Handle inline button callbacks"""
        try:
            query_id = callback_query['id']
            user_id = callback_query['from']['id']
            chat_id = callback_query['message']['chat']['id']
            message_id = callback_query['message']['message_id']
            data = callback_query['data']
            
            logger.info(f"Processing callback: {data}")

            # Answer the callback query to remove loading state
            self._answer_callback_query(query_id)
            
            # Try router first (Phase 3 Batch C: includes offer/supplier patterns)
            context = {'chat_id': chat_id, 'user_id': user_id, 'message_id': message_id}
            router_handled = self.router.dispatch(data, context)
            
            # Determine if we should remove the keyboard
            should_remove_keyboard = True
            if data.startswith('page_') and not data == 'page_info':
                should_remove_keyboard = False
            elif data == 'page_info':  # Keep keyboard for page info display
                should_remove_keyboard = False
            elif data.startswith('wd_'):  # Keep keyboard for wholesale delivery navigation
                should_remove_keyboard = False
            elif data.startswith('order_'):  # Keep keyboard for order buttons so multiple people can order
                should_remove_keyboard = False
            elif data == 'create_supplier_start':  # Keep keyboard for create supplier flow
                should_remove_keyboard = False
            
            if should_remove_keyboard:
                self._edit_message_remove_keyboard(chat_id, message_id)
            
            # If router handled it, return early
            if router_handled:
                logger.info(f"Callback handled by router: {data}")
                return {'status': 'handled_by_router'}
            
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
            elif data.startswith('admin'):
                return self._handle_admin_callbacks(chat_id, user_id, data)
            elif data.startswith('cmd'):
                return self._handle_command_callbacks(chat_id, user_id, data)
            elif data == 'create_supplier_start':
                return self._start_add_supplier(chat_id)
            
            # Order callbacks now handled by router
            # wholesale_select_ callbacks now handled by router
            # confirm_process_wholesale_ callbacks now handled by router
            # custom_wholesale_quantity_ callbacks now handled by router
            # confirm_order_ callbacks now handled by router
            # cancel_confirmation callback now handled by router
            
            # Admin confirmation callbacks
            # confirm_cancel_offer_ callbacks now handled by router
            # confirm_fulfill_ callbacks now handled by router
            elif data.startswith('request_cancel_reason_'):
                order_id = data.split('_')[3]
                return self._request_cancellation_reason(chat_id, order_id)
            # confirm_cancel_order_ callbacks now handled by router
            # approve_user_ callbacks now handled by router
            # reject_user_ callbacks now handled by router
            # edit_user_select_ callbacks now handled by router
            # edit_supplier_select_ callbacks now handled by router
            elif data == 'back_to_supplier_list':
                return self.handlers['supplier'].handle_list_suppliers(chat_id, 1, 'active')
            elif data.startswith('user_orders_select_'):
                customer_id = data.split('_')[3]
                return self.handlers['admin_order'].handle_list_user_orders_select(chat_id, customer_id)
            # cancel_order_ callbacks now handled by router
            # cancel_orders_page_ callbacks now handled by router
            elif data == 'enter_username_orders':
                return self._start_user_orders_input(chat_id)
            elif data == 'enter_username_cancel':
                return self._start_cancel_order_input(chat_id)
            elif data == 'enter_username_order_for':
                return self._start_order_for_input(chat_id)
            # approve_user_select_ callbacks now handled by router
            # order_for_user_select_ callbacks now handled by router
            elif data.startswith('credit_customer_'):
                customer_id = data.split('_')[2]
                return self.handlers['credit'].handle_credit_customer_select(chat_id, customer_id)
            elif data.startswith('user_status_select_'):
                customer_id = data.replace('user_status_select_', '')
                return self.handlers['user'].handle_user_status_select(chat_id, customer_id)

            # cancel_action callback now handled by router
            elif data == 'process_wholesale':
                # Handle process next offer button
                return self.handlers['offer'].handle_process_wholesale(chat_id, [])
            
            # Pagination callbacks
            elif data.startswith('page_'):
                parts = data.split('_')
                if len(parts) >= 3:
                    # Handle list_offers specially (page_list_offers_[filter]_page)
                    if parts[1] == 'list' and len(parts) >= 4 and parts[2] == 'offers':
                        if len(parts) == 5:
                            filter_arg = parts[3]
                            page = int(parts[4])
                        else:
                            filter_arg = None
                            page = int(parts[3])
                        args = [filter_arg] if filter_arg else None
                        return self.handlers['info'].handle_list_offers(chat_id, user_id, args, page)
                    # Handle process_wholesale pagination
                    elif parts[1] == 'process' and parts[2] == 'wholesale':
                        page = int(parts[3])
                        return self.handlers['offer'].handle_process_wholesale_page(chat_id, page)
                    # Handle multi-word entity types like process_payment, list_user_orders, and list_my_orders
                    elif len(parts) >= 4 and parts[1] in ['customers', 'suppliers', 'mark', 'process', 'list', 'user', 'my']:
                        if parts[1] == 'mark' and parts[2] == 'paid':
                            # Legacy: page_mark_paid_{page}
                            entity_type = 'mark_paid'
                            page = int(parts[3])
                        elif parts[1] == 'process' and parts[2] == 'payment':
                            # New: page_process_payment_{page}
                            entity_type = 'process_payment'
                            page = int(parts[3])
                        elif parts[1] == 'list' and parts[2] == 'user' and parts[3] == 'orders':
                            # New: page_list_user_orders_{customer_id}_{page}
                            entity_type = f"list_user_orders_{parts[4]}"
                            page = int(parts[5])
                        elif parts[1] == 'list' and parts[2] == 'my' and parts[3] == 'orders':
                            # New: page_list_my_orders_{user_id}_{page}
                            entity_type = f"list_my_orders_{parts[4]}"
                            page = int(parts[5])
                        elif parts[1] == 'user' and parts[2] == 'orders':
                            # Legacy: page_user_orders_{customer_id}_{page}
                            entity_type = f"user_orders_{parts[3]}"
                            page = int(parts[4])
                        elif parts[1] == 'my' and parts[2] == 'orders':
                            # Legacy: page_my_orders_{user_id}_{page}
                            entity_type = f"my_orders_{parts[3]}"
                            page = int(parts[4])
                        else:
                            entity_type = f"{parts[1]}_{parts[2]}"
                            page = int(parts[3])
                    else:
                        entity_type = parts[1]
                        page = int(parts[2])
                    
                    if entity_type == 'suppliers' or entity_type.startswith('suppliers_'):
                        status_filter = entity_type.split('_', 1)[1] if '_' in entity_type else 'active'
                        return self.handlers['supplier'].handle_list_suppliers(chat_id, page, status_filter)
                    elif entity_type == 'boxes' or entity_type.startswith('boxes_'):
                        filter_part = entity_type.split('_', 1)[1] if '_' in entity_type else 'active'
                        # Check if filter is offer_id (starts with 'offer_') or status
                        if filter_part.startswith('offer_'):
                            offer_id = filter_part.split('_', 1)[1]
                            return self.handlers['offer'].handle_list_boxes(chat_id, [offer_id, str(page)])
                        else:
                            return self.handlers['offer'].handle_list_boxes(chat_id, [filter_part, str(page)])
                    elif entity_type == 'pending':
                        return self.handlers['user'].handle_list_pending(chat_id, page)
                    elif entity_type.startswith('customers_'):
                        status_filter = entity_type.split('_', 1)[1]
                        return self.handlers['user'].handle_list_users(chat_id, page, status_filter)
                    elif entity_type == 'guests':
                        return self.handlers['user'].handle_list_guests(chat_id, page)
                    elif entity_type == 'subscribers':
                        return self.handlers['user'].handle_list_subscribers(chat_id, page)
                    elif entity_type.startswith('user_orders_') or entity_type.startswith('list_user_orders_'):
                        # Handle both legacy (user_orders_) and new (list_user_orders_) formats
                        if entity_type.startswith('list_user_orders_'):
                            customer_id = entity_type.split('_', 3)[3]
                        else:
                            customer_id = entity_type.split('_', 2)[2]
                        customer = self.db.get_customer(customer_id)
                        if customer:
                            return self.handlers['admin_order'].viewing._show_user_orders(chat_id, customer, page)
                        return {'status': 'customer_not_found'}
                    elif entity_type == 'changelog':
                        return self.handlers['changelog'].handle_changelog(chat_id, user_id, page)
                    elif entity_type == 'mark_paid' or entity_type == 'process_payment':
                        # Handle both legacy (mark_paid) and new (process_payment) formats
                        return self.handlers['admin_order'].handle_mark_paid(chat_id, [], page)
                    elif entity_type.startswith('my_orders_') or entity_type.startswith('list_my_orders_'):
                        # Handle both legacy (my_orders_) and new (list_my_orders_) formats
                        if entity_type.startswith('list_my_orders_'):
                            target_user_id = int(entity_type.split('_', 3)[3])
                        else:
                            target_user_id = int(entity_type.split('_', 2)[2])
                        if user_id == target_user_id:
                            return self.handlers['info'].handle_my_orders(chat_id, user_id, None, page)
                        return {'status': 'unauthorized'}
            elif data == 'page_info':
                # Do nothing - this is just a display button
                return {'status': 'page_info', 'no_action': True}
            
            # edit_ callbacks now handled by router
            
            # Offer management callbacks now handled by router
            # offer_details_ callbacks now handled by router
            # upload_offer_image_ callbacks now handled by router
            # clear_offer_images_ callbacks now handled by router
            # publish_offer_ callbacks now handled by router
            
            # Audit offer callbacks
            # finalize_import_ callbacks now handled by router
            # offer_orders_page_ callbacks now handled by router
            # offer_orders_detail_ callbacks now handled by router
            # offer_orders_ callbacks now handled by router
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
            
            # Handle customer contact and location (4 parts: edit_customer_contact_id)
            if parts[1] == 'customer' and len(parts) == 4:
                if parts[2] == 'contact':
                    return self._handle_customer_edit(chat_id, 'contact', parts[3])
                elif parts[2] == 'location':
                    return self._handle_customer_edit(chat_id, 'location', parts[3])
            
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
        
        self._send_message(chat_id, self._t('unknown_edit'))
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
            return self._send_message(chat_id, self._t('admin_only', user_id))
        
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
                return self._send_message(chat_id, self._t('invalid_format'))
        
        return self._send_message(chat_id, self._t('unknown_callback', user_id))
    
    def _handle_labeling_completion_callbacks(self, chat_id: int, user_id: int, data: str) -> Dict[str, Any]:
        """Handle labeling completion callbacks"""
        if not self._is_admin(user_id):
            return self._send_message(chat_id, self._t('admin_only', user_id))
        
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
        elif parts[0] == 'lc_complete':  # Complete labeling
            offer_id, supplier_id_short = int(parts[1]), parts[2]
            return self.handlers['labeling'].handle_complete_labeling(chat_id, offer_id, supplier_id_short)
        elif parts[0] == 'lc_confirm_complete':  # Confirm complete labeling
            if len(parts) >= 3:
                offer_id, supplier_id_short = int(parts[1]), parts[2]
                return self.handlers['labeling'].handle_confirm_complete_labeling(chat_id, offer_id, supplier_id_short)
            else:
                return self._send_message(chat_id, self._t('invalid_format'))
        elif parts[0] == 'lc_back':  # Back navigation
            target = parts[1]
            args = parts[2:] if len(parts) > 2 else []
            return self.handlers['labeling'].handle_back_navigation(chat_id, target, *args)
        
        return self._send_message(chat_id, self._t('unknown_callback', user_id))
    
    def _handle_admin_callbacks(self, chat_id: int, user_id: int, data: str) -> Dict[str, Any]:
        """Handle admin panel navigation callbacks"""
        if not self._is_admin(user_id):
            self._send_message(chat_id, self._t('admin_only', user_id))
            return {'status': 'unauthorized'}
        
        # Support both old format (admin_main) and new format (admin:main)
        if ':' in data:
            parts = data.split(':')
            action = parts[1] if len(parts) > 1 else 'main'
        else:
            action = data.replace('admin_', '')
        
        if action == 'main':
            return self.handlers['admin_commands'].handle_admin(chat_id, user_id)
        elif action == 'close':
            self._send_message(chat_id, self._t('close_panel'))
            return {'status': 'closed'}
        elif action == 'workflow':
            return self.handlers['admin_commands'].handle_admin_workflow(chat_id, user_id)
        elif action == 'suppliers':
            return self.handlers['admin_commands'].handle_admin_suppliers(chat_id, user_id)
        elif action == 'offers':
            return self.handlers['admin_commands'].handle_admin_offers(chat_id, user_id)
        elif action == 'orders':
            return self.handlers['admin_commands'].handle_admin_orders(chat_id, user_id)
        elif action == 'users':
            return self.handlers['admin_commands'].handle_admin_users(chat_id, user_id)
        elif action == 'discounts':
            return self.handlers['admin_commands'].handle_admin_discounts(chat_id, user_id)
        elif action == 'system':
            return self.handlers['admin_commands'].handle_admin_system(chat_id, user_id)
        # Legacy support
        elif action == 'delivery':
            return self.handlers['admin_commands'].handle_admin_workflow(chat_id, user_id)
        elif action == 'import':
            return self.handlers['admin_commands'].handle_admin_offers(chat_id, user_id)
        
        self._send_message(chat_id, self._t('unknown_callback', user_id))
        return {'status': 'unknown_callback'}
    
    def _handle_command_callbacks(self, chat_id: int, user_id: int, data: str) -> Dict[str, Any]:
        """Handle command execution callbacks from admin panel"""
        if not self._is_admin(user_id):
            self._send_message(chat_id, self._t('admin_only', user_id))
            return {'status': 'unauthorized'}
        
        # Support both old format (cmd_action) and new format (cmd:action)
        if ':' in data:
            action = data.split(':', 1)[1]
        else:
            action = data.replace('cmd_', '')
        
        # Map callback data to command handlers
        command_map = {
            'create_supplier': lambda: self.handlers['supplier'].handle_create_supplier(chat_id, []),
            'list_suppliers': lambda: self.handlers['supplier'].handle_list_suppliers(chat_id, 1, 'active'),
            'update_supplier': lambda: self.handlers['supplier'].handle_list_suppliers(chat_id, 1, 'active'),
            'create_offer': lambda: self.handlers['offer'].handle_create_offer(chat_id, []),
            'publish_offer': lambda: self._send_usage_message(chat_id, 'usage_publish_offer'),
            'list_offers': lambda: self.handlers['info'].handle_list_offers(chat_id, user_id, []),
            'list_boxes': lambda: self.handlers['offer'].handle_list_boxes(chat_id),
            'audit_offer': lambda: self.handlers['offer'].handle_audit_offer(chat_id, []),
            'process_wholesale': lambda: self.handlers['offer'].handle_process_wholesale(chat_id, []),
            'export_orders': lambda: self.handlers['admin_order'].handle_export_orders(chat_id, []),
            'list_user_orders': lambda: self._start_user_orders_input(chat_id),
            'list_offer_orders': lambda: self.handlers['admin_order'].handle_list_offer_orders(chat_id, []),
            'cancel_order': lambda: self.handlers['admin_order'].handle_cancel_order(chat_id, []),
            'create_order_for': lambda: self.handlers['admin_order'].handle_create_order_for(chat_id, user_id, []),
            'list_pending': lambda: self.handlers['user'].handle_list_pending(chat_id),
            'list_users': lambda: self.handlers['user'].handle_list_users(chat_id, 1, 'all'),
            'list_subscribers': lambda: self.handlers['user'].handle_list_subscribers(chat_id),
            'create_guest': lambda: self._send_usage_message(chat_id, 'usage_add_guest'),
            'list_guests': lambda: self.handlers['user'].handle_list_guests(chat_id),
            'approve_user': lambda: self._start_approve_user_input(chat_id),
            'user_status': lambda: self._start_user_status_input(chat_id),
            'process_delivery': lambda: self.handlers['wholesale_delivery'].handle_wholesale_delivery(chat_id, user_id, []),
            'process_labeling': lambda: self.handlers['labeling'].handle_labeling_completed(chat_id, user_id, []),
            'send_delivery_overviews': lambda: self.handlers['admin_order'].handle_send_overviews(chat_id, []),
            'process_payment': lambda: self.handlers['admin_order'].handle_mark_paid(chat_id, []),
            'create_discount': lambda: self._send_usage_message(chat_id, 'usage_create_discount'),
            'view_discount': lambda: self.handlers['discount'].handle_view_discount(chat_id),
            'cancel_discount': lambda: self.handlers['discount'].handle_cancel_discount(chat_id),
            'setup_test_data': lambda: self.handlers['test'].handle_setup_test_data(chat_id),
            'failed_notifications': lambda: self.handlers['admin_order'].handle_failed_notifications(chat_id, []),
            'delete_old_orders': lambda: self.handlers['admin_order'].handle_delete_old_orders(chat_id),
            'audit_orders': lambda: self.handlers['admin_order'].handle_audit_orders(chat_id),
            'import_orders': lambda: self.handlers['import'].handle_import_orders(chat_id, user_id),
            'finalize_import': lambda: self.handlers['import'].handle_finalize_import(chat_id, [])
        }

        if action in command_map:
            return command_map[action]()
        
        self._send_message(chat_id, self._t('unknown_callback', user_id))
        return {'status': 'unknown_callback'}
    
    def _start_add_supplier(self, chat_id: int) -> Dict[str, Any]:
        """Start add supplier process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, 'create_supplier_name')
    
    def _start_user_orders_input(self, chat_id: int) -> Dict[str, Any]:
        """Start user orders process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, 'list_user_orders_input')
    
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
        self._send_message(chat_id, self._t(usage_key))
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
        
        self._send_message(chat_id, self._t('enter_cancellation_reason'), 
                                  reply_markup={"force_reply": True, "input_field_placeholder": "Enter reason"})
        return {'status': 'awaiting_reason_input'}
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id