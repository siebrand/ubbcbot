from typing import Dict, Any
from handlers.base_handler import BaseHandler

class AdminCommandsHandler(BaseHandler):
    def handle_admin(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show admin panel with buttons for all admin functions"""
        if not self._is_admin(user_id):
            return self._send_error(chat_id, 'admin_only', 'unauthorized')
        
        message = self._t('admin_panel_title', user_id)
        
        keyboard = {
            "inline_keyboard": [
                # Core Workflow - First Priority
                [
                    {"text": self._t('admin_workflow', user_id), "callback_data": "admin:workflow"}
                ],
                # Management Categories - 2 columns
                [
                    {"text": self._t('admin_offers', user_id), "callback_data": "admin:offers"},
                    {"text": self._t('admin_orders', user_id), "callback_data": "admin:orders"}
                ],
                [
                    {"text": self._t('admin_users', user_id), "callback_data": "admin:users"},
                    {"text": self._t('admin_suppliers', user_id), "callback_data": "admin:suppliers"}
                ],
                # Additional Categories
                [
                    {"text": self._t('admin_discounts', user_id), "callback_data": "admin:discounts"},
                    {"text": self._t('admin_system', user_id), "callback_data": "admin:system"}
                ],
                # Close
                [
                    {"text": self._t('close_panel', user_id), "callback_data": "admin:close"}
                ]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_workflow(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show core workflow commands in sequential order"""
        message = self._t('admin_workflow_menu_enhanced', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('create_offer_btn', user_id), "callback_data": "cmd:create_offer"}],
                [{"text": self._t('publish_offer_btn', user_id), "callback_data": "cmd:publish_offer"}],
                [{"text": self._t('wholesale_order_btn', user_id), "callback_data": "cmd:process_wholesale"}],
                [{"text": self._t('wholesale_delivery_btn', user_id), "callback_data": "cmd:process_delivery"}],
                [{"text": self._t('labeling_completed_btn', user_id), "callback_data": "cmd:process_labeling"}],
                [{"text": self._t('send_overviews_btn', user_id), "callback_data": "cmd:send_delivery_overviews"}],
                [{"text": self._t('process_payment_btn', user_id), "callback_data": "cmd:process_payment"}],
                [{"text": self._t('send_payment_reminder_btn', user_id), "callback_data": "cmd:send_payment_reminder"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin:main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_suppliers(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show supplier management options"""
        message = self._t('admin_suppliers_menu_enhanced', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('add_supplier_btn', user_id), "callback_data": "cmd:create_supplier"}],
                [{"text": self._t('list_suppliers_btn', user_id), "callback_data": "cmd:list_suppliers"}],
                [{"text": self._t('edit_supplier_btn', user_id), "callback_data": "cmd:update_supplier"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin:main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_offers(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show offer management options with import merged in"""
        message = self._t('admin_offers_menu_enhanced', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('create_offer_btn', user_id), "callback_data": "cmd:create_offer"}],
                [{"text": self._t('list_offers_btn', user_id), "callback_data": "cmd:list_offers"}],
                [
                    {"text": self._t('publish_offer_btn', user_id), "callback_data": "cmd:publish_offer"},
                    {"text": self._t('box_status_btn', user_id), "callback_data": "cmd:list_boxes"}
                ],
                [
                    {"text": self._t('audit_offer_btn', user_id), "callback_data": "cmd:audit_offer"},
                    {"text": self._t('wholesale_order_btn', user_id), "callback_data": "cmd:process_wholesale"}
                ],
                # Import section
                [{"text": self._t('import_orders_btn', user_id), "callback_data": "cmd:import_orders"}],
                [{"text": self._t('finalize_import_btn', user_id), "callback_data": "cmd:finalize_import"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin:main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_orders(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show order management options with failed notifications"""
        message = self._t('admin_orders_menu_enhanced', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('all_orders_btn', user_id), "callback_data": "cmd:export_orders"}],
                [
                    {"text": self._t('user_orders_btn', user_id), "callback_data": "cmd:list_user_orders"},
                    {"text": self._t('offer_orders_btn', user_id), "callback_data": "cmd:list_offer_orders"}
                ],
                [
                    {"text": self._t('order_for_user_btn', user_id), "callback_data": "cmd:create_order_for"},
                    {"text": self._t('cancel_order_btn', user_id), "callback_data": "cmd:cancel_order"}
                ],
                [{"text": self._t('failed_notifications_btn', user_id), "callback_data": "cmd:failed_notifications"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin:main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_users(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show user management options with subscribers"""
        message = self._t('admin_users_menu_enhanced', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('pending_users_btn', user_id), "callback_data": "cmd:list_pending"}],
                [
                    {"text": self._t('list_users_btn', user_id), "callback_data": "cmd:list_users"},
                    {"text": self._t('list_subscribers_btn', user_id), "callback_data": "cmd:list_subscribers"}
                ],
                [
                    {"text": self._t('add_guest_btn', user_id), "callback_data": "cmd:create_guest"},
                    {"text": self._t('list_guests_btn', user_id), "callback_data": "cmd:list_guests"}
                ],
                [
                    {"text": self._t('approve_user_btn', user_id), "callback_data": "cmd:approve_user"},
                    {"text": self._t('user_status_btn', user_id), "callback_data": "cmd:user_status"}
                ],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin:main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}

    
    def handle_admin_discounts(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show discount management options"""
        message = self._t('admin_discounts_menu_enhanced', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('create_discount_btn', user_id), "callback_data": "cmd:create_discount"}],
                [{"text": self._t('discount_status_btn', user_id), "callback_data": "cmd:view_discount"}],
                [{"text": self._t('cancel_discount_btn', user_id), "callback_data": "cmd:cancel_discount"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin:main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_system(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show system management options with cleanup and audit"""
        message = self._t('admin_system_menu_enhanced', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('delete_cancelled_btn', user_id), "callback_data": "cmd:delete_old_orders"}],
                [{"text": self._t('audit_orders_btn', user_id), "callback_data": "cmd:audit_orders"}],
                [{"text": self._t('failed_notifications_btn', user_id), "callback_data": "cmd:failed_notifications"}]
            ]
        }
        
        # Add test data button only in test environment
        if self.environment == 'test':
            keyboard["inline_keyboard"].insert(0, [{"text": self._t('setup_test_data_btn', user_id), "callback_data": "cmd:setup_test_data"}])
        
        keyboard["inline_keyboard"].append([{"text": self._t('back_to_admin', user_id), "callback_data": "admin:main"}])
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
