from typing import Dict, Any, Optional
from handlers.base_handler import BaseHandler
from models.entities import AuthorizationStatus

class UserCommands(BaseHandler):
    def handle_pending_users(self, chat_id: int) -> Dict[str, Any]:
        """Handle /pending_users command"""
        customers = self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value)
        
        if not customers:
            self._send_message(chat_id, "No users pending approval")
            return {'status': 'no_pending'}

        message = "📋 Pending Users:\n\n"
        for customer in customers:
            display_name = self._escape_html(customer.first_name or "Unknown")
            if customer.last_name:
                display_name += f" {self._escape_html(customer.last_name)}"
            
            username_part = f" (@{self._escape_html(customer.username)})" if customer.username else " (no username)"
            message += f"{display_name}{username_part}\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}

    def handle_approve_user(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /approve_user command"""
        if not args:
            self._send_message(chat_id, "Usage: /approve_user <name_or_username>")
            return {'status': 'invalid_args'}

        identifier = ' '.join(args)
        customer = self._find_customer_by_identifier(identifier)
        
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
        customer = self._find_customer_by_identifier(identifier)
        
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
        customer = self._find_customer_by_identifier(identifier)
        
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

    def _find_customer_by_identifier(self, identifier: str) -> Optional:
        """Find customer by username or display name"""
        # Try by username first (remove @ if present)
        username = identifier.lstrip('@').lower()
        customer = self.db.get_customer_by_username(username)
        if customer:
            return customer
        
        # Try by first name
        customers = self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value)
        for customer in customers:
            if customer.first_name and customer.first_name.lower() == identifier.lower():
                return customer
            # Try first + last name combination
            full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            if full_name.lower() == identifier.lower():
                return customer
        
        return None