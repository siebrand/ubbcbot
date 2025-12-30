import os
import logging
from typing import Dict, Any
from models.entities import AuthorizationStatus

logger = logging.getLogger()

class CommandRouter:
    def __init__(self, db, admin_user_id: int, environment: str, handlers: Dict[str, Any]):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.handlers = handlers

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id

    def route_command(self, chat_id: int, user_id: int, text: str) -> Dict[str, Any]:
        """Route commands to appropriate handlers"""
        parts = text.split()
        command = parts[0].lower()
        
        # Remove bot mention from command if present
        if '@' in command:
            command = command.split('@')[0]
        
        # In production, redirect group commands to PM (except group-specific ones)
        is_group_chat = chat_id < 0
        group_allowed_commands = {'/start', '/order', '/confirm_order'}
        
        if (self.environment == 'prod' and is_group_chat and 
            command not in group_allowed_commands):
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, "")
            base_handler._send_message(user_id, base_handler._t('redirected_to_pm', command=command))
            return {'status': 'redirected_to_pm'}

        # Check user authorization (admin always approved)
        if not self._is_admin(user_id):
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer or customer.authorization_status != AuthorizationStatus.APPROVED.value:
                if command == '/start':
                    return self.handlers['auth'].handle_unauthorized_start(chat_id if not is_group_chat or self.environment == 'test' else user_id)
                else:
                    from handlers.base_handler import BaseHandler
                    base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, "")
                    target_chat = chat_id if not is_group_chat or self.environment == 'test' else user_id
                    base_handler._send_message(target_chat, base_handler._t('unauthorized'))
                    return {'status': 'unauthorized'}

        # Handle deep link start parameters
        if command == '/start' and len(parts) > 1:
            if parts[1].startswith('order_'):
                try:
                    _, offer_id_str, quantity_str = parts[1].split('_')
                    return self.handlers['customer_order'].handle_order(chat_id, user_id, [offer_id_str, quantity_str])
                except ValueError:
                    pass
            elif parts[1].startswith('confirm_'):
                try:
                    _, offer_id_str, quantity_str = parts[1].split('_')
                    return self.handlers['customer_order'].handle_confirm_order(chat_id, user_id, [offer_id_str, quantity_str])
                except ValueError:
                    pass
            elif parts[1].startswith('help_'):
                section = parts[1][5:]
                target_chat = chat_id if not is_group_chat or self.environment == 'test' else user_id
                return self.handlers['info'].handle_help(target_chat, user_id, [section])
            elif parts[1].startswith('offer_details_'):
                try:
                    offer_id_str = parts[1][14:]
                    target_chat = chat_id if not is_group_chat or self.environment == 'test' else user_id
                    return self.handlers['info'].handle_offer_details(target_chat, user_id, [offer_id_str])
                except ValueError:
                    pass
        
        # Universal commands
        target_chat = chat_id if not is_group_chat or self.environment == 'test' else user_id
        
        if command == '/start':
            return self.handlers['info'].handle_start(target_chat, user_id, parts[1:])
        elif command == '/help':
            return self.handlers['info'].handle_help(target_chat, user_id, parts[1:])
        elif command == '/order':
            return self.handlers['customer_order'].handle_order(chat_id, user_id, parts[1:])
        elif command == '/my_orders':
            return self.handlers['info'].handle_my_orders(target_chat, user_id, parts[1:])
        elif command == '/list_offers':
            return self.handlers['info'].handle_list_offers(target_chat, user_id, parts[1:])
        elif command == '/subscribe':
            return self.handlers['info'].handle_subscribe(target_chat, user_id)
        elif command == '/unsubscribe':
            return self.handlers['info'].handle_unsubscribe(target_chat, user_id)
        elif command == '/offer_details':
            return self.handlers['info'].handle_offer_details(target_chat, user_id, parts[1:])
        elif command == '/confirm_order':
            return self.handlers['customer_order'].handle_confirm_order(chat_id, user_id, parts[1:])
        elif command == '/delete_cancelled':
            return self.handlers['customer_order'].handle_delete_cancelled(target_chat, user_id)
        elif command == '/changelog':
            return self.handlers['changelog'].handle_changelog(target_chat, user_id, 1)
        elif command == '/cancel':
            return self._handle_cancel_command(target_chat, user_id)

        # Admin-only commands
        if self._is_admin(user_id):
            admin_target_chat = chat_id if not is_group_chat or self.environment == 'test' else user_id
            
            if command == '/setup_test_data':
                return self.handlers['test'].handle_setup_test_data(admin_target_chat)
            elif command == '/add_supplier':
                return self.handlers['supplier'].handle_add_supplier(admin_target_chat, parts[1:])
            elif command == '/retire_supplier':
                return self.handlers['supplier'].handle_retire_supplier(admin_target_chat, parts[1:])
            elif command == '/list_suppliers':
                status_filter = parts[1] if len(parts) > 1 and parts[1] in ['active', 'retired', 'all'] else 'active'
                return self.handlers['supplier'].handle_list_suppliers(admin_target_chat, 1, status_filter)
            elif command == '/edit_supplier':
                return self.handlers['supplier'].handle_edit_supplier(admin_target_chat, parts[1:])
            elif command == '/update_supplier_name':
                return self.handlers['supplier'].handle_update_supplier_name(admin_target_chat, parts[1:])
            elif command == '/update_supplier_contact':
                return self.handlers['supplier'].handle_update_supplier_contact(admin_target_chat, parts[1:])
            elif command == '/create_offer':
                return self.handlers['offer'].handle_create_offer(admin_target_chat, parts[1:])
            elif command == '/cancel_offer':
                return self.handlers['offer'].handle_cancel_offer(admin_target_chat, parts[1:])
            elif command == '/add_box':
                return self.handlers['offer'].handle_add_box(admin_target_chat, parts[1:])
            elif command == '/box_status':
                return self.handlers['offer'].handle_box_status(admin_target_chat, parts[1:])
            elif command == '/audit_offer':
                return self.handlers['offer'].handle_audit_offer(admin_target_chat, parts[1:])
            elif command == '/order_wholesale':
                return self.handlers['offer'].handle_order_wholesale(admin_target_chat, parts[1:])
            elif command == '/confirm_order_wholesale':
                return self.handlers['offer'].handle_confirm_order_wholesale(admin_target_chat, parts[1:])
            elif command == '/update_offer_name':
                return self.handlers['offer'].handle_update_offer_name(admin_target_chat, parts[1:])
            elif command == '/update_offer_price':
                return self.handlers['offer'].handle_update_offer_price(admin_target_chat, parts[1:])
            elif command == '/update_offer_description':
                return self.handlers['offer'].handle_update_offer_description(admin_target_chat, parts[1:])
            elif command == '/publish_offer':
                return self.handlers['offer'].handle_publish_offer(admin_target_chat, parts[1:])
            elif command == '/preview_offer':
                return self.handlers['info'].handle_offer_details(admin_target_chat, user_id, parts[1:] + ['user'])
            elif command == '/order_for':
                return self.handlers['admin_order'].handle_order_for(admin_target_chat, user_id, parts[1:])
            elif command == '/cancel_order':
                return self.handlers['admin_order'].handle_cancel_order(admin_target_chat, parts[1:])
            elif command == '/user_orders':
                return self.handlers['admin_order'].handle_user_orders(admin_target_chat, parts[1:])
            elif command == '/offer_orders':
                return self.handlers['admin_order'].handle_offer_orders(admin_target_chat, parts[1:])
            elif command == '/all_orders':
                return self.handlers['admin_order'].handle_all_orders(admin_target_chat, parts[1:])
            elif command == '/pending_users':
                return self.handlers['user'].handle_pending_users(admin_target_chat)
            elif command == '/approve_user':
                return self.handlers['user'].handle_approve_user(admin_target_chat, parts[1:])
            elif command == '/reject_user':
                return self.handlers['user'].handle_reject_user(admin_target_chat, parts[1:])
            elif command == '/user_status':
                return self.handlers['user'].handle_user_status(admin_target_chat, parts[1:])
            elif command == '/update_user':
                return self.handlers['user'].handle_update_user(admin_target_chat, parts[1:])
            elif command == '/update_user_first_name':
                return self.handlers['user'].handle_update_user_first_name(admin_target_chat, parts[1:])
            elif command == '/update_user_last_name':
                return self.handlers['user'].handle_update_user_last_name(admin_target_chat, parts[1:])
            elif command == '/list_users':
                status_filter = 'all'
                search_string = None
                
                if len(parts) > 1:
                    if parts[1] in ['approved', 'unauthorized', 'rejected', 'all']:
                        status_filter = parts[1]
                        if len(parts) > 2:
                            search_string = ' '.join(parts[2:])
                    else:
                        search_string = ' '.join(parts[1:])
                
                return self.handlers['user'].handle_list_users(admin_target_chat, 1, status_filter, search_string)
            elif command == '/list_subscribers':
                return self.handlers['user'].handle_list_subscribers(admin_target_chat)
            elif command == '/create_discount':
                return self.handlers['discount'].handle_create_discount(admin_target_chat, parts[1:])
            elif command == '/cancel_discount':
                return self.handlers['discount'].handle_cancel_discount(admin_target_chat)
            elif command == '/discount_status':
                return self.handlers['discount'].handle_discount_status(admin_target_chat)
            elif command == '/wholesale_delivery':
                return self.handlers['wholesale_delivery'].handle_wholesale_delivery(admin_target_chat, user_id, parts[1:])
            elif command == '/labeling_completed':
                return self.handlers['labeling'].handle_labeling_completed(admin_target_chat, user_id, parts[1:])
            elif command == '/send_overviews':
                return self.handlers['admin_order'].handle_send_overviews(admin_target_chat, parts[1:])
            elif command == '/mark_paid':
                return self.handlers['admin_order'].handle_mark_paid(admin_target_chat, parts[1:])
            elif command == '/failed_notifications':
                return self.handlers['admin_order'].handle_failed_notifications(admin_target_chat, parts[1:])
            elif command == '/admin':
                return self.handlers['admin_commands'].handle_admin(admin_target_chat, user_id)

        return {'status': 'unknown_command'}
    
    def _handle_cancel_command(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /cancel command to clear any pending edit contexts"""
        try:
            # Check if user has any pending edit contexts
            context = self.db.get_edit_context_by_chat_id(chat_id)
            if context:
                # Delete the edit context
                self.db.delete_edit_context(context.context_id)
                
                # Use existing info handler instead of creating new BaseHandler
                return self.handlers['info']._send_success(chat_id, 'operation_cancelled', 'cancelled')
            else:
                # Use existing info handler instead of creating new BaseHandler
                return self.handlers['info']._send_success(chat_id, 'nothing_to_cancel', 'nothing_to_cancel')
        except Exception as e:
            # Use existing info handler instead of creating new BaseHandler
            return self.handlers['info']._send_error(chat_id, 'cancel_failed', 'error')