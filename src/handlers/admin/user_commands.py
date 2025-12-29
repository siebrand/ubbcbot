from typing import Dict, Any, Optional
from handlers.base_handler import BaseHandler
from models.entities import AuthorizationStatus
from utils.update_utils import UpdateUtils

class UserCommands(BaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_utils = UpdateUtils(self.db, self._t, self._send_message)
        self.update_utils._show_customer_edit_interface = self._show_user_edit_interface
    def _approve_user_by_customer(self, chat_id: int, customer) -> Dict[str, Any]:
        """Shared approval logic for customer object"""
        if customer.authorization_status == AuthorizationStatus.APPROVED.value:
            display_name = customer.first_name or "Unknown"
            self._send_message(chat_id, self._t('user_already_approved', chat_id, name=display_name))
            return {'status': 'already_approved'}

        # Update user status
        if self.db.update_customer(customer.customer_id, {'authorization_status': AuthorizationStatus.APPROVED.value}):
            # Notify user
            self._send_message(customer.telegram_user_id, self._t('user_authorized', customer.telegram_user_id))
            
            # Confirm to admin
            display_name = customer.first_name or "Unknown"
            self._send_message(chat_id, self._t('user_approved', chat_id, name=display_name))
            
            # Enter update user dialog
            return self._show_user_edit_interface(customer, chat_id)
        else:
            self._send_message(chat_id, self._t('failed_approve_user', chat_id))
            return {'status': 'error'}

    def handle_pending_users(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Handle /pending_users command with pagination"""
        customers = self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value)
        
        if not customers:
            self._send_message(chat_id, self._t('no_pending_users', chat_id))
            return {'status': 'no_pending'}

        # Paginate results
        page_customers, total_pages = self._paginate_list(customers, page, 5)  # Smaller page size for buttons
        
        message = self._t('pending_users_title', chat_id, page=page, total_pages=total_pages) + "\n\n"
        keyboard_buttons = []
        
        for customer in page_customers:
            display_name = self._escape_html(customer.first_name or "Unknown")
            if customer.last_name:
                display_name += f" {self._escape_html(customer.last_name)}"
            
            username_part = f" (@{self._escape_html(customer.username)})" if customer.username else " (no username)"
            message += f"{display_name}{username_part}\n"
            
            # Add approve/reject buttons for each user
            keyboard_buttons.append([
                {"text": self._t('approve_user', chat_id, name=customer.first_name or 'User'), "callback_data": f"approve_user_{customer.customer_id}"},
                {"text": self._t('reject_user', chat_id, name=customer.first_name or 'User'), "callback_data": f"reject_user_{customer.customer_id}"}
            ])

        # Add pagination buttons if needed
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": self._t('previous', chat_id), "callback_data": f"page_pending_{page - 1}_"})
            nav_buttons.append({"text": self._t('page_indicator', chat_id, page=page, total_pages=total_pages), "callback_data": "page_info"})
            if page < total_pages:
                nav_buttons.append({"text": self._t('next', chat_id), "callback_data": f"page_pending_{page + 1}_"})
            keyboard_buttons.append(nav_buttons)

        if keyboard_buttons:
            keyboard = {"inline_keyboard": keyboard_buttons}
            self._send_message(chat_id, message, reply_markup=keyboard)
        else:
            self._send_message(chat_id, message)
        
        return {'status': 'success'}

    def handle_approve_user(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /approve_user command"""
        if not args:
            self._send_message(chat_id, self._t('usage_approve_user', chat_id))
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "edit_user_select")
        
        if error:
            return error

        return self._approve_user_by_customer(chat_id, customer)

    def handle_reject_user(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /reject_user command"""
        if not args:
            self._send_message(chat_id, self._t('usage_reject_user', chat_id))
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "edit_user_select")
        
        if error:
            return error

        # Update user status
        if self.db.update_customer(customer.customer_id, {'authorization_status': AuthorizationStatus.REJECTED.value}):
            # Notify user
            self._send_message(customer.telegram_user_id, self._t('access_rejected', customer.telegram_user_id))
            
            # Confirm to admin
            display_name = customer.first_name or "Unknown"
            self._send_message(chat_id, self._t('user_rejected', chat_id, name=display_name))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_reject_user', chat_id))
            return {'status': 'error'}

    def handle_user_status(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /user_status command"""
        if not args:
            self._send_message(chat_id, self._t('usage_user_status', chat_id))
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "edit_user_select")
        
        if error:
            return error

        display_name = self._escape_html(customer.first_name or "Unknown")
        if customer.last_name:
            display_name += f" {self._escape_html(customer.last_name)}"
        
        username_part = f" (@{self._escape_html(customer.username)})" if customer.username else ""
        status_emoji = {
            AuthorizationStatus.UNAUTHORIZED.value: "⚠️",
            AuthorizationStatus.APPROVED.value: "✅",
            AuthorizationStatus.REJECTED.value: "❌"
        }.get(customer.authorization_status, "❓")
        
        message = f"{status_emoji} {display_name}{username_part}\n"
        message += f"Status: {customer.authorization_status}"
        
        self._send_message(chat_id, message)
        return {'status': 'success'}

    def _show_user_edit_interface(self, customer, chat_id: int) -> Dict[str, Any]:
        """Show edit interface for a customer"""
        display_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown"
        username_part = f" (@{customer.username})" if customer.username else ""
        
        message = self._t('edit_user', chat_id, name=display_name, username=username_part) + "\n\n"
        message += self._t('first_name', chat_id, value=customer.first_name or self._t('not_set', chat_id)) + "\n"
        message += self._t('last_name', chat_id, value=customer.last_name or self._t('not_set', chat_id)) + "\n"
        message += self._t('select_edit', chat_id)
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('edit_first_name', chat_id), "callback_data": f"edit_customer_first_name_{customer.customer_id}"}],
                [{"text": self._t('edit_last_name', chat_id), "callback_data": f"edit_customer_last_name_{customer.customer_id}"}],
                [{"text": self._t('done', chat_id), "callback_data": "done_action"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}

    def handle_update_user(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_user command"""
        if not args:
            self._send_message(chat_id, self._t('usage_update_user', chat_id))
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "edit_user_select")
        
        if error:
            return error
        
        return self._show_user_edit_interface(customer, chat_id)
    
    def handle_update_user_first_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_user_first_name command"""
        return self.update_utils.handle_customer_update(chat_id, args, 'first_name')
    
    def handle_update_user_last_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_user_last_name command"""
        return self.update_utils.handle_customer_update(chat_id, args, 'last_name')



    def handle_list_users(self, chat_id: int, page: int = 1, status_filter: str = "all", search_string: str = None) -> Dict[str, Any]:
        """Handle /list_users command with pagination, filtering, and optional search"""
        from models.entities import AuthorizationStatus

        # Get customers based on filter
        if status_filter == "all":
            customers = []
            customers.extend(self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value))
            customers.extend(self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value))
            customers.extend(self.db.get_customers_by_status(AuthorizationStatus.REJECTED.value))
        else:
            customers = self.db.get_customers_by_status(status_filter)

        # Apply search filter if provided
        if search_string:
            # Extract search logic from _find_customer_with_disambiguation
            search_lower = search_string.lower()
            filtered_customers = []
            for customer in customers:
                first_name = (customer.first_name or "").lower()
                last_name = (customer.last_name or "").lower()
                username = (customer.username or "").lower()
                full_name = f"{first_name} {last_name}".strip()

                if (search_lower in first_name or
                        search_lower in last_name or
                        search_lower in username or
                        search_lower in full_name):
                    filtered_customers.append(customer)
            customers = filtered_customers

        if not customers:
            search_text = f" matching '{search_string}'" if search_string else ""
            self._send_message(chat_id, self._t('no_customers_found', chat_id, status=status_filter, search=search_text))
            return {'status': 'no_customers'}

        # Sort by first name
        customers.sort(key=lambda x: (x.first_name or "zzz").lower())

        # Paginate results
        page_customers, total_pages = self._paginate_list(customers, page, 20)

        search_text = f" matching '{search_string}'" if search_string else ""
        message = f"👥 Customers ({status_filter}){search_text} - Page {page}/{total_pages}:\n\n"

        for customer in page_customers:
            display_name = self._escape_html(customer.first_name or "Unknown")
            if customer.last_name:
                display_name += f" {self._escape_html(customer.last_name)}"

            username_part = f" (@{self._escape_html(customer.username)})" if customer.username else ""
            status_emoji = {
                AuthorizationStatus.UNAUTHORIZED.value: "⚠️",
                AuthorizationStatus.APPROVED.value: "✅",
                AuthorizationStatus.REJECTED.value: "❌"
            }.get(customer.authorization_status, "❓")

            message += f"{status_emoji} {display_name}{username_part}\n"

        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_user_pagination_keyboard(page, total_pages, f"customers_{status_filter}")

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}

    def _build_user_pagination_keyboard(self, current_page: int, total_pages: int, entity_type: str) -> Dict[str, Any]:
        """Build enhanced pagination keyboard for user lists"""
        keyboard = []

        if total_pages > 1:
            nav_buttons = []

            # First page button (if not on first page)
            if current_page > 1:
                nav_buttons.append({
                    "text": "⏮️",
                    "callback_data": f"page_{entity_type}_1"
                })

            # Previous page button
            if current_page > 1:
                nav_buttons.append({
                    "text": "◀️",
                    "callback_data": f"page_{entity_type}_{current_page - 1}"
                })

            # Page indicator
            nav_buttons.append({
                "text": f"{current_page}/{total_pages}",
                "callback_data": "page_info"
            })

            # Next page button
            if current_page < total_pages:
                nav_buttons.append({
                    "text": "▶️",
                    "callback_data": f"page_{entity_type}_{current_page + 1}"
                })

            # Last page button (if not on last page)
            if current_page < total_pages:
                nav_buttons.append({
                    "text": "⏭️",
                    "callback_data": f"page_{entity_type}_{total_pages}"
                })

            keyboard.append(nav_buttons)

            # Add jump buttons for larger lists (show ±2 pages)
            if total_pages > 5:
                jump_buttons = []

                # Show a few page numbers around current page
                start_page = max(1, current_page - 2)
                end_page = min(total_pages, current_page + 2)

                for p in range(start_page, end_page + 1):
                    if p != current_page:
                        jump_buttons.append({
                            "text": str(p),
                            "callback_data": f"page_{entity_type}_{p}"
                        })

                if jump_buttons:
                    keyboard.append(jump_buttons)

        return {"inline_keyboard": keyboard}

    def handle_edit_user_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user selection from ambiguity resolution buttons"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}
        
        return self._show_user_edit_interface(customer, chat_id)

    def handle_approve_user_by_id(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user approval by customer ID (called from button callback)"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}

        return self._approve_user_by_customer(chat_id, customer)

    def handle_reject_user_by_id(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user rejection by customer ID (called from button callback)"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}

        # Update user status
        if self.db.update_customer(customer.customer_id, {'authorization_status': AuthorizationStatus.REJECTED.value}):
            # Notify user
            self._send_message(customer.telegram_user_id, self._t('access_rejected', customer.telegram_user_id))
            
            # Confirm to admin
            display_name = customer.first_name or "Unknown"
            self._send_message(chat_id, self._t('user_rejected', chat_id, name=display_name))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_reject_user', chat_id))
            return {'status': 'error'}

    def handle_list_subscribers(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Handle /list_subscribers command with pagination"""
        subscribers = self.db.get_subscribers()
        
        if not subscribers:
            self._send_message(chat_id, self._t('no_subscribers', chat_id))
            return {'status': 'no_subscribers'}
        
        # Sort by first name
        subscribers.sort(key=lambda x: (x.first_name or "zzz").lower())
        
        # Paginate results
        page_subscribers, total_pages = self._paginate_list(subscribers, page, 10)
        
        message = f"🔔 Subscribers - Page {page}/{total_pages}:\n\n"
        
        for customer in page_subscribers:
            display_name = self._escape_html(customer.first_name or "Unknown")
            if customer.last_name:
                display_name += f" {self._escape_html(customer.last_name)}"
            
            username_part = f" (@{self._escape_html(customer.username)})" if customer.username else ""
            message += f"✅ {display_name}{username_part}\n"
        
        message += f"\nTotal subscribers: {len(subscribers)}"
        
        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_pagination_keyboard(page, total_pages, "subscribers")
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}