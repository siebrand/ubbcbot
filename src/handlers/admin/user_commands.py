from typing import Dict, Any, Optional
from handlers.base_handler import BaseHandler
from models.entities import AuthorizationStatus

class UserCommands(BaseHandler):
    def handle_pending_users(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Handle /pending_users command with pagination"""
        customers = self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value)
        
        if not customers:
            self._send_message(chat_id, "No users pending approval")
            return {'status': 'no_pending'}

        # Paginate results
        page_customers, total_pages = self._paginate_list(customers, page, 5)  # Smaller page size for buttons
        
        message = f"📋 Pending Users (Page {page}/{total_pages}):\n\n"
        keyboard_buttons = []
        
        for customer in page_customers:
            display_name = self._escape_html(customer.first_name or "Unknown")
            if customer.last_name:
                display_name += f" {self._escape_html(customer.last_name)}"
            
            username_part = f" (@{self._escape_html(customer.username)})" if customer.username else " (no username)"
            message += f"{display_name}{username_part}\n"
            
            # Add approve/reject buttons for each user
            keyboard_buttons.append([
                {"text": f"✅ Approve {customer.first_name or 'User'}", "callback_data": f"approve_user_{customer.customer_id}"},
                {"text": f"❌ Reject {customer.first_name or 'User'}", "callback_data": f"reject_user_{customer.customer_id}"}
            ])

        # Add pagination buttons if needed
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": "◀️ Previous", "callback_data": f"page_pending_{page - 1}_"})
            nav_buttons.append({"text": f"Page {page}/{total_pages}", "callback_data": "page_info"})
            if page < total_pages:
                nav_buttons.append({"text": "Next ▶️", "callback_data": f"page_pending_{page + 1}_"})
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
            self._send_message(chat_id, "Usage: /approve_user <name_or_username>")
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer = self._find_customer_with_ambiguity_check(identifier, chat_id)
        
        if not customer:
            self._send_message(chat_id, f"❌ User '{identifier}' not found")
            return {'status': 'user_not_found'}

        if customer.authorization_status == AuthorizationStatus.APPROVED.value:
            self._send_message(chat_id, f"❌ User '{identifier}' is already approved")
            return {'status': 'already_approved'}

        # Update user status
        if self.db.update_customer(customer.customer_id, {'authorization_status': AuthorizationStatus.APPROVED.value}):
            # Notify user
            self._send_message(customer.telegram_user_id, "✅ You've been approved! Send /start to begin using the bot.")
            
            # Confirm to admin
            display_name = customer.first_name or "Unknown"
            self._send_message(chat_id, f"✅ User '{display_name}' approved")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to approve user")
            return {'status': 'error'}

    def handle_reject_user(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /reject_user command"""
        if not args:
            self._send_message(chat_id, "Usage: /reject_user <name_or_username>")
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer = self._find_customer_with_ambiguity_check(identifier, chat_id)
        
        if not customer:
            self._send_message(chat_id, f"❌ User '{identifier}' not found")
            return {'status': 'user_not_found'}

        # Update user status
        if self.db.update_customer(customer.customer_id, {'authorization_status': AuthorizationStatus.REJECTED.value}):
            # Notify user
            self._send_message(customer.telegram_user_id, "❌ Your access request has been rejected.")
            
            # Confirm to admin
            display_name = customer.first_name or "Unknown"
            self._send_message(chat_id, f"❌ User '{display_name}' rejected")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to reject user")
            return {'status': 'error'}

    def handle_user_status(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /user_status command"""
        if not args:
            self._send_message(chat_id, "Usage: /user_status <name_or_username>")
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer = self._find_customer_with_ambiguity_check(identifier, chat_id)
        
        if not customer:
            self._send_message(chat_id, f"❌ User '{identifier}' not found")
            return {'status': 'user_not_found'}

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

    def handle_update_user(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_user command"""
        if not args:
            self._send_message(chat_id, "Usage: /update_user <name_or_username>")
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer = self._find_customer_with_ambiguity_check(identifier, chat_id)
        
        if not customer:
            return {'status': 'user_not_found'}
        
        # Show current customer details with edit options
        display_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown"
        username_part = f" (@{customer.username})" if customer.username else ""
        
        message = f"📝 Edit User: {display_name}{username_part}\n\n"
        message += f"First Name: {customer.first_name or 'Not set'}\n"
        message += f"Last Name: {customer.last_name or 'Not set'}\n"
        message += f"Status: {customer.authorization_status}\n\n"
        message += "Select what to edit:"
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "📝 Edit First Name", "callback_data": f"edit_customer_first_name_{customer.customer_id}"}],
                [{"text": "📝 Edit Last Name", "callback_data": f"edit_customer_last_name_{customer.customer_id}"}],
                [{"text": "❌ Cancel", "callback_data": "cancel_action"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_update_user_first_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_user_first_name command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /update_user_first_name [customer_id] [new_first_name]")
            return {'status': 'invalid_args'}
        
        customer_id = args[0]
        new_first_name = ' '.join(args[1:]).strip()
        
        if len(new_first_name) > 100:
            self._send_message(chat_id, "❌ First name too long (max 100 characters)")
            return {'status': 'invalid_name'}
        
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, "❌ User not found")
            return {'status': 'user_not_found'}
        
        if self.db.update_customer(customer_id, {'first_name': new_first_name}):
            old_name = customer.first_name or "Not set"
            self._send_message(chat_id, f"✅ User first name updated: '{old_name}' → '{new_first_name}'")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to update user first name")
            return {'status': 'error'}
    
    def handle_update_user_last_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_user_last_name command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /update_user_last_name [customer_id] [new_last_name]")
            return {'status': 'invalid_args'}
        
        customer_id = args[0]
        new_last_name = ' '.join(args[1:]).strip()
        
        if len(new_last_name) > 100:
            self._send_message(chat_id, "❌ Last name too long (max 100 characters)")
            return {'status': 'invalid_name'}
        
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, "❌ User not found")
            return {'status': 'user_not_found'}
        
        if self.db.update_customer(customer_id, {'last_name': new_last_name}):
            old_name = customer.last_name or "Not set"
            self._send_message(chat_id, f"✅ User last name updated: '{old_name}' → '{new_last_name}'")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to update user last name")
            return {'status': 'error'}

    def _find_customer_by_identifier(self, identifier: str) -> Optional:
        """Find customer by username or display name"""
        # Try by username first (remove @ if present)
        username = identifier.lstrip('@').lower()
        customer = self.db.get_customer_by_username(username)
        if customer:
            return customer
        
        # Try by first name across all customers
        from models.entities import AuthorizationStatus
        all_customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        all_customers.extend(self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value))
        
        matches = []
        for customer in all_customers:
            if customer.first_name and customer.first_name.lower() == identifier.lower():
                matches.append(customer)
            # Try first + last name combination
            full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            if full_name.lower() == identifier.lower():
                return customer  # Exact full name match takes priority
        
        # Return single match or None if multiple/no matches
        return matches[0] if len(matches) == 1 else None
    
    def _find_customer_with_ambiguity_check(self, identifier: str, chat_id: int) -> Optional:
        """Find customer with ambiguity handling for admin commands"""
        # Try by username first (remove @ if present)
        username = identifier.lstrip('@').lower()
        customer = self.db.get_customer_by_username(username)
        if customer:
            return customer
        
        # Try by first name across all customers
        from models.entities import AuthorizationStatus
        all_customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        all_customers.extend(self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value))
        
        matches = []
        exact_full_name_match = None
        partial_matches = []
        
        for customer in all_customers:
            # Check for exact full name match first
            full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            if full_name.lower() == identifier.lower():
                exact_full_name_match = customer
                break
            
            # Check if full name starts with identifier (for partial matches like "Rick H." matching "Rick H. 🍻")
            if full_name.lower().startswith(identifier.lower()):
                partial_matches.append(customer)
            
            # Collect first name matches
            if customer.first_name and customer.first_name.lower() == identifier.lower():
                matches.append(customer)
        
        # Return exact full name match if found
        if exact_full_name_match:
            return exact_full_name_match
        
        # Return single partial match if found
        if len(partial_matches) == 1:
            return partial_matches[0]
        elif len(partial_matches) > 1:
            # Multiple partial matches - show options with buttons
            message = f"📋 Multiple users found starting with '{identifier}'. Select user to edit:\n\n"
            keyboard_buttons = []
            
            for customer in partial_matches:
                full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                username_part = f" (@{customer.username})" if customer.username else ""
                display_text = f"{full_name}{username_part}"
                
                keyboard_buttons.append([{
                    "text": f"📝 {full_name}",
                    "callback_data": f"edit_user_select_{customer.customer_id}"
                }])
            
            keyboard_buttons.append([{"text": "❌ Cancel", "callback_data": "cancel_action"}])
            keyboard = {"inline_keyboard": keyboard_buttons}
            
            self._send_message(chat_id, message, reply_markup=keyboard)
            return None
        
        # Handle first name matches
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            # Multiple first name matches - show options with buttons
            message = f"📋 Multiple users found with name '{identifier}'. Select user to edit:\n\n"
            keyboard_buttons = []
            
            for customer in matches:
                full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                username_part = f" (@{customer.username})" if customer.username else ""
                display_text = f"{full_name}{username_part}"
                
                keyboard_buttons.append([{
                    "text": f"📝 {full_name}",
                    "callback_data": f"edit_user_select_{customer.customer_id}"
                }])
            
            keyboard_buttons.append([{"text": "❌ Cancel", "callback_data": "cancel_action"}])
            keyboard = {"inline_keyboard": keyboard_buttons}
            
            self._send_message(chat_id, message, reply_markup=keyboard)
            return None
        
        return None
    
    def handle_approve_user_by_id(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user approval by customer ID (called from button callback)"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, "❌ User not found")
            return {'status': 'user_not_found'}

        if customer.authorization_status == AuthorizationStatus.APPROVED.value:
            self._send_message(chat_id, f"❌ User is already approved")
            return {'status': 'already_approved'}

        # Update user status
        if self.db.update_customer(customer.customer_id, {'authorization_status': AuthorizationStatus.APPROVED.value}):
            # Notify user
            self._send_message(customer.telegram_user_id, "✅ You've been approved! Send /start to begin using the bot.")
            
            # Confirm to admin
            display_name = customer.first_name or "Unknown"
            self._send_message(chat_id, f"✅ User '{display_name}' approved")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to approve user")
            return {'status': 'error'}

    def handle_reject_user_by_id(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user rejection by customer ID (called from button callback)"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, "❌ User not found")
            return {'status': 'user_not_found'}

        # Update user status
        if self.db.update_customer(customer.customer_id, {'authorization_status': AuthorizationStatus.REJECTED.value}):
            # Notify user
            self._send_message(customer.telegram_user_id, "❌ Your access request has been rejected.")
            
            # Confirm to admin
            display_name = customer.first_name or "Unknown"
            self._send_message(chat_id, f"❌ User '{display_name}' rejected")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to reject user")
            return {'status': 'error'}
    def handle_list_users(self, chat_id: int, page: int = 1, status_filter: str = "all") -> Dict[str, Any]:
        """Handle /list_users command with pagination and filtering"""
        from models.entities import AuthorizationStatus
        
        # Get customers based on filter
        if status_filter == "all":
            customers = []
            customers.extend(self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value))
            customers.extend(self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value))
            customers.extend(self.db.get_customers_by_status(AuthorizationStatus.REJECTED.value))
        else:
            customers = self.db.get_customers_by_status(status_filter)
        
        if not customers:
            self._send_message(chat_id, f"No customers found ({status_filter})")
            return {'status': 'no_customers'}
        
        # Sort by first name
        customers.sort(key=lambda x: (x.first_name or "zzz").lower())
        
        # Paginate results
        page_customers, total_pages = self._paginate_list(customers, page, 10)
        
        message = f"👥 Customers ({status_filter}) - Page {page}/{total_pages}:\n\n"
        
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
            keyboard = self._build_pagination_keyboard(page, total_pages, f"customers_{status_filter}")
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    def handle_edit_user_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user selection from ambiguity resolution buttons"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, "❌ User not found")
            return {'status': 'user_not_found'}
        
        # Show edit interface for selected user
        display_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Unknown"
        username_part = f" (@{customer.username})" if customer.username else ""
        
        message = f"📝 Edit User: {display_name}{username_part}\n\n"
        message += f"First Name: {customer.first_name or 'Not set'}\n"
        message += f"Last Name: {customer.last_name or 'Not set'}\n"
        message += f"Status: {customer.authorization_status}\n\n"
        message += "Select what to edit:"
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "📝 Edit First Name", "callback_data": f"edit_customer_first_name_{customer.customer_id}"}],
                [{"text": "📝 Edit Last Name", "callback_data": f"edit_customer_last_name_{customer.customer_id}"}],
                [{"text": "❌ Cancel", "callback_data": "cancel_action"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    def handle_list_subscribers(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Handle /list_subscribers command with pagination"""
        subscribers = self.db.get_subscribers()
        
        if not subscribers:
            self._send_message(chat_id, "No subscribers found")
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