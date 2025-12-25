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

    def handle_update_customer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_customer command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /update_customer <username> <new_first_name> [new_last_name]")
            return {'status': 'invalid_args'}

        username = args[0]
        new_first_name = args[1]
        new_last_name = args[2] if len(args) > 2 else None
        
        customer = self._find_customer_with_ambiguity_check(username, chat_id)
        
        if not customer:
            self._send_message(chat_id, f"❌ User '{username}' not found")
            return {'status': 'user_not_found'}

        # Update customer name
        updates = {'first_name': new_first_name}
        if new_last_name:
            updates['last_name'] = new_last_name
        
        if self.db.update_customer(customer.customer_id, updates):
            # Update username in all active orders
            active_orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) if o.status in ['pending', 'ordered']]
            updated_orders = 0
            
            for order in active_orders:
                # Note: This assumes orders have a customer_name field to update
                # If orders don't store customer names, this step can be skipped
                try:
                    new_customer_name = f"{new_first_name} {new_last_name or ''}".strip()
                    if hasattr(order, 'customer_name'):
                        self.db.update_order(order.order_id, {'customer_name': new_customer_name})
                        updated_orders += 1
                except Exception:
                    pass  # Continue with other orders if one fails
            
            old_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            new_name = f"{new_first_name} {new_last_name or ''}".strip()
            
            message = f"✅ Customer name updated: '{old_name}' → '{new_name}'"
            if updated_orders > 0:
                message += f"\nUpdated {updated_orders} active orders"
            
            self._send_message(chat_id, message)
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to update customer")
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
        
        for customer in all_customers:
            # Check for exact full name match first
            full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            if full_name.lower() == identifier.lower():
                exact_full_name_match = customer
                break
            
            # Collect first name matches
            if customer.first_name and customer.first_name.lower() == identifier.lower():
                matches.append(customer)
        
        # Return exact full name match if found
        if exact_full_name_match:
            return exact_full_name_match
        
        # Handle first name matches
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            # Multiple matches - show options
            message = f"❌ Multiple users found with name '{identifier}':\n\n"
            for customer in matches:
                full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                username_part = f" (@{customer.username})" if customer.username else " (no username)"
                message += f"• {full_name}{username_part}\n"
            message += "\nUse full name or @username to specify exactly which user."
            self._send_message(chat_id, message)
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
    def handle_list_customers(self, chat_id: int, page: int = 1, status_filter: str = "all") -> Dict[str, Any]:
        """Handle /list_customers command with pagination and filtering"""
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