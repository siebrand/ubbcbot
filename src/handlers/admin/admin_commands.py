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
                    {"text": self._t('admin_workflow', user_id), "callback_data": "admin_workflow"}
                ],
                # Management Categories
                [
                    {"text": self._t('admin_suppliers', user_id), "callback_data": "admin_suppliers"},
                    {"text": self._t('admin_offers', user_id), "callback_data": "admin_offers"}
                ],
                # Order Management
                [
                    {"text": self._t('admin_orders', user_id), "callback_data": "admin_orders"},
                    {"text": self._t('admin_users', user_id), "callback_data": "admin_users"}
                ],
                # Delivery Management
                [
                    {"text": self._t('admin_delivery', user_id), "callback_data": "admin_delivery"},
                    {"text": self._t('admin_discounts', user_id), "callback_data": "admin_discounts"}
                ],
                # System
                [
                    {"text": self._t('admin_system', user_id), "callback_data": "admin_system"}
                ]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_workflow(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show core workflow commands in sequential order"""
        message = self._t('admin_workflow_menu', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('create_offer_btn', user_id), "callback_data": "cmd_create_offer"}],
                [{"text": self._t('publish_offer_btn', user_id), "callback_data": "cmd_publish_offer"}],
                [{"text": self._t('wholesale_order_btn', user_id), "callback_data": "cmd_order_wholesale"}],
                [{"text": self._t('wholesale_delivery_btn', user_id), "callback_data": "cmd_wholesale_delivery"}],
                [{"text": self._t('labeling_completed_btn', user_id), "callback_data": "cmd_labeling_completed"}],
                [{"text": self._t('send_overviews_btn', user_id), "callback_data": "cmd_send_overviews"}],
                [{"text": self._t('mark_paid_btn', user_id), "callback_data": "cmd_mark_paid"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin_main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_suppliers(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show supplier management options"""
        message = self._t('admin_suppliers_menu', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('add_supplier_btn', user_id), "callback_data": "cmd_add_supplier"}],
                [{"text": self._t('list_suppliers_btn', user_id), "callback_data": "cmd_list_suppliers"}],
                [{"text": self._t('edit_supplier_btn', user_id), "callback_data": "cmd_edit_supplier"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin_main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_offers(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show offer management options"""
        message = self._t('admin_offers_menu', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('create_offer_btn', user_id), "callback_data": "cmd_create_offer"}],
                [{"text": self._t('list_offers_btn', user_id), "callback_data": "cmd_list_offers"}],
                [{"text": self._t('box_status_btn', user_id), "callback_data": "cmd_box_status"}],
                [{"text": self._t('audit_offer_btn', user_id), "callback_data": "cmd_audit_offer"}],
                [{"text": self._t('wholesale_order_btn', user_id), "callback_data": "cmd_order_wholesale"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin_main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_orders(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show order management options"""
        message = self._t('admin_orders_menu', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('all_orders_btn', user_id), "callback_data": "cmd_all_orders"}],
                [{"text": self._t('user_orders_btn', user_id), "callback_data": "cmd_user_orders"}],
                [{"text": self._t('offer_orders_btn', user_id), "callback_data": "cmd_offer_orders"}],
                [{"text": self._t('cancel_order_btn', user_id), "callback_data": "cmd_cancel_order"}],
                [{"text": self._t('order_for_user_btn', user_id), "callback_data": "cmd_order_for"}],
                [{"text": self._t('delete_cancelled_btn', user_id), "callback_data": "cmd_delete_old_cancelled"}],
                [{"text": self._t('audit_orders_btn', user_id), "callback_data": "cmd_audit_orders"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin_main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_users(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show user management options"""
        message = self._t('admin_users_menu', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('pending_users_btn', user_id), "callback_data": "cmd_pending_users"}],
                [{"text": self._t('list_users_btn', user_id), "callback_data": "cmd_list_users"}],
                [{"text": self._t('approve_user_btn', user_id), "callback_data": "cmd_approve_user"}],
                [{"text": self._t('user_status_btn', user_id), "callback_data": "cmd_user_status"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin_main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_delivery(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show delivery management options"""
        message = self._t('admin_delivery_menu', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('wholesale_delivery_btn', user_id), "callback_data": "cmd_wholesale_delivery"}],
                [{"text": self._t('labeling_completed_btn', user_id), "callback_data": "cmd_labeling_completed"}],
                [{"text": self._t('send_overviews_btn', user_id), "callback_data": "cmd_send_overviews"}],
                [{"text": self._t('mark_paid_btn', user_id), "callback_data": "cmd_mark_paid"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin_main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_discounts(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show discount management options"""
        message = self._t('admin_discounts_menu', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('create_discount_btn', user_id), "callback_data": "cmd_create_discount"}],
                [{"text": self._t('discount_status_btn', user_id), "callback_data": "cmd_discount_status"}],
                [{"text": self._t('cancel_discount_btn', user_id), "callback_data": "cmd_cancel_discount"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin_main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_admin_system(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Show system management options"""
        message = self._t('admin_system_menu', user_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('setup_test_data_btn', user_id), "callback_data": "cmd_setup_test_data"}],
                [{"text": self._t('failed_notifications_btn', user_id), "callback_data": "cmd_failed_notifications"}],
                [{"text": self._t('back_to_admin', user_id), "callback_data": "admin_main"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}