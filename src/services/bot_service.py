import os
import json
import requests
import logging
from typing import Dict, Any, Optional
from services.database import DynamoDBService
from models.entities import Supplier, Offer, Customer, Box, Order, BoxStatus, OfferStatus, DiscountPeriod, DiscountStatus, AuthorizationStatus

logger = logging.getLogger()

class BotService:
    def __init__(self):
        self.db = DynamoDBService()
        self.admin_user_id = int(os.environ.get('ADMIN_USER_ID', '15005473'))
        self.environment = os.environ.get('ENVIRONMENT', 'test')
        self.telegram_token = self._get_telegram_token()

    def _get_telegram_token(self) -> str:
        """Get Telegram token from Parameter Store"""
        import boto3
        ssm = boto3.client('ssm')
        try:
            response = ssm.get_parameter(
                Name=f'/ubbc-bot/{self.environment}/telegram-bot-token',
                WithDecryption=True
            )
            return response['Parameter']['Value']
        except Exception as e:
            logger.error(f"Error getting Telegram token: {e}")
            return ""

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters to prevent injection"""
        if not text:
            return ""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#x27;')

    def _send_message(self, chat_id: int, text: str, parse_mode: str = None) -> bool:
        """Send message to Telegram chat"""
        if self.environment == 'test':
            text = f"TEST - {text}"
        
        if not self.telegram_token:
            logger.error("Telegram token is empty")
            return False
            
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text
        }
        
        if parse_mode:
            data['parse_mode'] = parse_mode
        
        try:
            if self.environment == 'test':
                logger.info(f"Sending message to chat {chat_id}: {text[:50]}...")
            response = requests.post(url, json=data)
            if self.environment == 'test':
                logger.info(f"Telegram API response: {response.status_code} - {response.text}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id

    def process_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming Telegram update"""
        try:
            if 'message' not in update:
                return {'status': 'ignored'}

            message = update['message']
            chat_id = message['chat']['id']
            user_id = message['from']['id']
            text = message.get('text', '')
            username = message['from'].get('username', 'N/A')
            first_name = message['from'].get('first_name', 'N/A')
            
            # Log incoming command
            if text.startswith('/') and self.environment == 'test':
                logger.info(f"Command: {text.split()[0]} | User: {first_name} (@{username}) | ID: {user_id}")

            # Register customer if not exists
            self._register_customer_if_needed(message['from'])

            # Handle commands
            if text.startswith('/'):
                return self._handle_command(chat_id, user_id, text)
            
            return {'status': 'processed'}

        except Exception as e:
            logger.error(f"Error processing update: {e}")
            return {'status': 'error', 'error': str(e)}

    def _register_customer_if_needed(self, user_data: Dict[str, Any]):
        """Register customer if they don't exist"""
        telegram_user_id = user_data['id']
        existing_customer = self.db.get_customer_by_telegram_id(telegram_user_id)
        
        if not existing_customer:
            # Store original data - sanitization happens at output time
            first_name = user_data.get('first_name', '')
            last_name = user_data.get('last_name', '')
            username = user_data.get('username', '')
            
            # Only limit length to prevent storage issues
            if first_name:
                first_name = first_name[:100]
            if last_name:
                last_name = last_name[:100]
            if username:
                username = username[:100]
            
            customer = Customer(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            self.db.create_customer(customer)

    def _handle_command(self, chat_id: int, user_id: int, text: str) -> Dict[str, Any]:
        """Handle bot commands"""
        parts = text.split()
        command = parts[0].lower()

        # Check user authorization (admin always approved)
        if not self._is_admin(user_id):
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer or customer.authorization_status != AuthorizationStatus.APPROVED.value:
                if command == '/start':
                    return self._handle_unauthorized_start(chat_id)
                else:
                    self._send_message(chat_id, "❌ You are not authorized to use this bot. Send /start for more information.")
                    return {'status': 'unauthorized'}

        # Universal commands (available to everyone)
        if command == '/start' or command == '/help':
            return self._handle_start(chat_id, user_id)
        elif command == '/order':
            return self._handle_order(chat_id, user_id, parts[1:])
        elif command == '/my_orders':
            return self._handle_my_orders(chat_id, user_id)
        elif command == '/list_offers':
            return self._handle_list_offers(chat_id, user_id)
        elif command == '/confirm_order':
            return self._handle_confirm_order(chat_id, user_id, parts[1:])

        # Admin-only commands
        if self._is_admin(user_id):
            if command == '/add_supplier':
                return self._handle_add_supplier(chat_id, parts[1:])
            elif command == '/create_offer':
                return self._handle_create_offer(chat_id, parts[1:])
            elif command == '/box_status':
                return self._handle_box_status(chat_id)
            elif command == '/cancel_order':
                return self._handle_cancel_order(chat_id, parts[1:])
            elif command == '/confirm_cancel':
                return self._handle_confirm_cancel(chat_id, parts[1:])
            elif command == '/list_suppliers':
                return self._handle_list_suppliers(chat_id)
            elif command == '/pending_users':
                return self._handle_pending_users(chat_id)
            elif command == '/approve_user':
                return self._handle_approve_user(chat_id, parts[1:])
            elif command == '/reject_user':
                return self._handle_reject_user(chat_id, parts[1:])
            elif command == '/user_status':
                return self._handle_user_status(chat_id, parts[1:])

        return {'status': 'unknown_command'}

    def _handle_add_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_supplier command"""
        if not args:
            self._send_message(chat_id, "Usage: /add_supplier <name>")
            return {'status': 'invalid_args'}

        supplier_name = ' '.join(args).strip()
        
        # Validate supplier name
        if len(supplier_name) > 50:
            self._send_message(chat_id, "❌ Supplier name too long (max 50 characters)")
            return {'status': 'invalid_name'}
        
        if '<' in supplier_name or '>' in supplier_name:
            self._send_message(chat_id, "❌ Supplier name cannot contain < or > characters")
            return {'status': 'invalid_name'}
        
        # Check for duplicate
        if self.db.get_supplier_by_name(supplier_name):
            self._send_message(chat_id, f"❌ Supplier '{supplier_name}' already exists")
            return {'status': 'duplicate_supplier'}
        
        supplier = Supplier(name=supplier_name)
        
        if self.db.create_supplier(supplier):
            self._send_message(chat_id, f"✅ Supplier '{supplier_name}' added with ID: {supplier.supplier_id}")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to add supplier")
            return {'status': 'error'}

    def _handle_create_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /create_offer command"""
        if len(args) < 4:
            self._send_message(chat_id, "Usage: /create_offer <supplier_name> <name> <price> <box_size>")
            return {'status': 'invalid_args'}

        try:
            # Parse arguments: supplier_name name price box_size
            # Everything except last 2 args is the name
            supplier_name = args[0]
            price = float(args[-2])
            box_size = int(args[-1])
            
            # Validate and sanitize name
            name = ' '.join(args[1:-2]).strip()
            if len(name) > 100:  # Prevent excessively long names
                self._send_message(chat_id, "❌ Product name too long (max 100 characters)")
                return {'status': 'invalid_name'}
            
            if '<' in name or '>' in name:  # Block HTML tags
                self._send_message(chat_id, "❌ Product name cannot contain < or > characters")
                return {'status': 'invalid_name'}

            # Validate box size
            valid_sizes = [1, 2, 6, 8, 10, 12, 15, 16, 18, 20, 24]
            if box_size not in valid_sizes:
                self._send_message(chat_id, f"❌ Invalid box size. Valid sizes: {valid_sizes}")
                return {'status': 'invalid_box_size'}

            # Check supplier exists
            supplier = self.db.get_supplier_by_name(supplier_name)
            if not supplier:
                self._send_message(chat_id, "❌ Supplier not found")
                return {'status': 'supplier_not_found'}

            # Create offer
            from decimal import Decimal
            offer = Offer(
                supplier_name=supplier_name,
                name=name,
                price_per_unit=Decimal(str(price)),
                wholesale_box_size=box_size,
                min_quantity_breakeven=max(1, int(box_size * 0.8))  # 80% of box size
            )

            if self.db.create_offer(offer):
                # Create initial box
                box = Box(
                    offer_id=offer.offer_id,
                    max_capacity=box_size,
                    min_breakeven=offer.min_quantity_breakeven
                )
                self.db.create_box(box)

                # Auto-order 1 unit for admin
                admin_customer = self.db.get_customer_by_telegram_id(self.admin_user_id)
                if admin_customer:
                    admin_order = Order(
                        customer_id=admin_customer.customer_id,
                        box_id=box.box_id,
                        offer_id=offer.offer_id,
                        quantity=1,
                        unit_price=Decimal(str(price)),
                        total_price=Decimal(str(price))
                    )
                    self.db.create_order(admin_order)
                    
                    # Update box quantity
                    updates = {'current_quantity': 1}
                    if 1 >= box.max_capacity:
                        updates['status'] = BoxStatus.FULL.value
                    elif 1 >= box.min_breakeven:
                        updates['status'] = BoxStatus.MINIMUM_REACHED.value
                    if not self.db.update_box(box.box_id, updates):
                        self._send_message(chat_id, "⚠️ Auto-order placed but box update failed")
                    else:
                        # Notify admin about auto-order
                        self._send_message(chat_id, f"✅ Auto-ordered 1 unit for you. Order ID: {admin_order.order_id}")
                    
                    # Announce new offer to default group
                    default_group_id = os.environ.get('DEFAULT_GROUP_ID')
                    if default_group_id:
                        announcement = f"🍺 New offer available!\n\n"
                        announcement += f"[{offer.offer_id}] {offer.name}\n"
                        announcement += f"Price: €{offer.price_per_unit:.2f} per unit\n"
                        announcement += f"Box size: {offer.wholesale_box_size} units\n\n"
                        announcement += f"Order with: /order {offer.offer_id} [quantity]"
                        self._send_message(int(default_group_id), announcement)

                else:
                    self._send_message(chat_id, f"✅ Offer '{name}' created with ID: {offer.offer_id}")
                    self._send_message(chat_id, "⚠️ Auto-order failed: Admin customer not found")
                    
                    # Announce new offer to default group
                    default_group_id = os.environ.get('DEFAULT_GROUP_ID')
                    if default_group_id:
                        announcement = f"🍺 New offer available!\n\n"
                        announcement += f"[{offer.offer_id}] {offer.name}\n"
                        announcement += f"Price: €{offer.price_per_unit:.2f} per unit\n"
                        announcement += f"Box size: {offer.wholesale_box_size} units\n\n"
                        announcement += f"Order with: /order {offer.offer_id} [quantity]"
                        self._send_message(int(default_group_id), announcement)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to create offer")
                return {'status': 'error'}

        except (ValueError, IndexError) as e:
            self._send_message(chat_id, f"❌ Invalid format. Error: {str(e)}")
            return {'status': 'invalid_format'}

        # Announce new offer to default group after successful creation
        default_group_id = os.environ.get('DEFAULT_GROUP_ID')
        if default_group_id:
            logger.info(f"Announcing offer {offer.offer_id} to group {default_group_id}")
            announcement = f"🍺 New offer available!\n\n"
            announcement += f"[{offer.offer_id}] {offer.name}\n"
            announcement += f"Price: €{offer.price_per_unit:.2f} per unit\n"
            announcement += f"Box size: {offer.wholesale_box_size} units\n\n"
            announcement += f"Order with: /order {offer.offer_id} [quantity]"
            success = self._send_message(int(default_group_id), announcement)
            logger.info(f"Group announcement result: {success}")
        else:
            logger.info("DEFAULT_GROUP_ID not set, skipping group announcement")

    def _handle_list_offers(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /list_offers command"""
        offers = self.db.list_offers()
        
        if not offers:
            self._send_message(chat_id, "No offers found")
            return {'status': 'no_offers'}

        # Sort offers by offer_id ascending
        offers.sort(key=lambda x: x.offer_id)

        message = ""
        
        # Check for active discount
        active_discount = self.db.get_active_discount()
        if active_discount:
            message += f"🎉 DISCOUNT ACTIVE: {active_discount.discount_percentage}% OFF!\n"
            if active_discount.end_time:
                message += f"Valid until: {active_discount.end_time.strftime('%Y-%m-%d %H:%M')}\n"
            message += "\n"
        
        message += "📋 Active Offers:\n\n"
        for offer in offers:
            if offer.status == OfferStatus.ACTIVE.value:
                # Get current order count for this offer
                boxes = self.db.get_boxes_by_offer(offer.offer_id)
                total_ordered = sum(box.current_quantity for box in boxes)
                
                original_price = offer.price_per_unit
                display_price = original_price
                
                if active_discount:
                    display_price = original_price * (1 - active_discount.discount_percentage / 100)
                    message += f"🍺 [{offer.offer_id}] {offer.name} €{display_price:.2f} ({total_ordered}/{offer.wholesale_box_size})\n"
                else:
                    message += f"🍺 [{offer.offer_id}] {offer.name} €{display_price:.2f} ({total_ordered}/{offer.wholesale_box_size})\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}

    def _handle_unauthorized_start(self, chat_id: int) -> Dict[str, Any]:
        """Handle /start for unauthorized users"""
        message = "🍺 Welcome to UBBC Bot!\n\n"
        message += "⚠️ Your access is pending admin approval.\n"
        message += "Please wait for approval to use the bot.\n\n"
        message += "Contact admin if you need immediate access."
        
        self._send_message(chat_id, message)
        return {'status': 'unauthorized'}

    def _handle_pending_users(self, chat_id: int) -> Dict[str, Any]:
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

    def _handle_approve_user(self, chat_id: int, args: list) -> Dict[str, Any]:
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

    def _handle_reject_user(self, chat_id: int, args: list) -> Dict[str, Any]:
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

    def _handle_user_status(self, chat_id: int, args: list) -> Dict[str, Any]:
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

    def _find_customer_by_identifier(self, identifier: str) -> Optional[Customer]:
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

    def _handle_list_suppliers(self, chat_id: int) -> Dict[str, Any]:
        """Handle /list_suppliers command"""
        suppliers = self.db.list_suppliers()
        
        if not suppliers:
            self._send_message(chat_id, "No suppliers found")
            return {'status': 'no_suppliers'}

        # Filter active suppliers and sort alphabetically
        active_suppliers = [s for s in suppliers if s.status == "active"]
        active_suppliers.sort(key=lambda x: x.name.lower())

        message = "📋 Registered Suppliers:\n\n"
        for supplier in active_suppliers:
            message += f"{supplier.name}\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}

    def _handle_box_status(self, chat_id: int) -> Dict[str, Any]:
        """Handle /box_status command"""
        offers = self.db.list_offers()
        
        message = "📦 Box Status:\n\n"
        for offer in offers:
            if offer.status == OfferStatus.ACTIVE.value:
                boxes = self.db.get_boxes_by_offer(offer.offer_id)
                
                # Sort boxes by creation time (box_id contains timestamp)
                boxes.sort(key=lambda x: x.box_id)
                
                for box in boxes:
                    status_emoji = {
                        BoxStatus.OPEN.value: "🟢",
                        BoxStatus.MINIMUM_REACHED.value: "🟡",
                        BoxStatus.FULL.value: "🔴",
                        BoxStatus.ORDERED.value: "📦",
                        BoxStatus.DELIVERED.value: "✅"
                    }.get(box.status, "❓")
                    
                    message += f"🍺 {offer.name} €{offer.price_per_unit:.2f}\n   {status_emoji} Box {box.box_id[:8]}: {box.current_quantity}/{box.max_capacity} ({box.status})\n\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}

    def _handle_start(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /start command"""
        if self.environment == 'test':
            logger.info(f"Processing /start command for user {user_id}, chat {chat_id}")
        
        message = "🍺 Welcome to UBBC Bot!\n\n"
        message += "Available commands:\n"
        message += "/start - Show this help\n"
        message += "/list_offers - View available offers\n"
        message += "/order <offer_id> [quantity] - Place an order\n"
        message += "/confirm_order <offer_id> <quantity> - Confirm duplicate order\n"
        message += "/my_orders - View your orders\n"
        
        if self._is_admin(user_id):
            if self.environment == 'test':
                logger.info(f"User {user_id} is admin, adding admin commands")
            message += "\n👑 Admin commands:\n"
            message += "/add_supplier <name> - Add supplier\n"
            message += "/list_suppliers - List all suppliers\n"
            message += "/create_offer <supplier_name> <name> <price> <box_size> - Create offer\n"
            message += "/box_status - View box status\n"
            message += "/cancel_order <order_id> - Cancel customer order\n"
            message += "/confirm_cancel <order_id> - Confirm order cancellation\n"
            message += "/pending_users - View users awaiting approval\n"
            message += "/approve_user <name_or_username> - Approve user\n"
            message += "/reject_user <name_or_username> - Reject user\n"
            message += "/user_status <name_or_username> - Check user status\n"

        success = self._send_message(chat_id, message)
        if self.environment == 'test':
            logger.info(f"Message send result: {success}")
        
        return {'status': 'success'}

    def _handle_cancel_order(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /cancel_order command"""
        if not args:
            self._send_message(chat_id, "Usage: /cancel_order <order_id>")
            return {'status': 'invalid_args'}

        order_id = args[0]
        order = self.db.get_order(order_id)
        
        if not order:
            self._send_message(chat_id, "❌ Order not found")
            return {'status': 'order_not_found'}
        
        if order.status == 'cancelled':
            self._send_message(chat_id, "❌ Order already cancelled")
            return {'status': 'already_cancelled'}

        # Get box info
        box = self.db.get_box(order.box_id)
        if not box:
            self._send_message(chat_id, "❌ Box not found")
            return {'status': 'box_not_found'}

        # Check if box is full - require confirmation
        if box.status == BoxStatus.FULL.value:
            self._send_message(chat_id, 
                f"⚠️ WARNING: This order is from a FULL box!\n"
                f"Order: {order_id}\n"
                f"Quantity: {order.quantity}\n"
                f"Cancelling will affect box status.\n\n"
                f"Confirm with: /confirm_cancel {order_id}")
            return {'status': 'confirmation_required'}

        # Cancel directly for non-full boxes
        return self._execute_cancel(order, box, chat_id)

    def _handle_confirm_cancel(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_cancel command"""
        if not args:
            self._send_message(chat_id, "Usage: /confirm_cancel <order_id>")
            return {'status': 'invalid_args'}

        order_id = args[0]
        order = self.db.get_order(order_id)
        
        if not order:
            self._send_message(chat_id, "❌ Order not found")
            return {'status': 'order_not_found'}

        box = self.db.get_box(order.box_id)
        if not box:
            self._send_message(chat_id, "❌ Box not found")
            return {'status': 'box_not_found'}

        return self._execute_cancel(order, box, chat_id)

    def _execute_cancel(self, order, box, chat_id: int) -> Dict[str, Any]:
        """Execute order cancellation"""
        # Update order status
        if not self.db.update_order(order.order_id, {'status': 'cancelled'}):
            self._send_message(chat_id, "❌ Failed to cancel order")
            return {'status': 'error'}

        # Update box quantity and status
        new_quantity = box.current_quantity - order.quantity
        updates = {'current_quantity': new_quantity}
        
        # Recalculate box status
        if new_quantity == 0:
            updates['status'] = BoxStatus.OPEN.value
        elif new_quantity < box.min_breakeven:
            updates['status'] = BoxStatus.OPEN.value
        elif new_quantity < box.max_capacity:
            updates['status'] = BoxStatus.MINIMUM_REACHED.value
        
        self.db.update_box(box.box_id, updates)

        # Get customer and offer info for notifications
        customer = self.db.get_customer(order.customer_id)
        offer = self.db.get_offer(order.offer_id)
        
        # Notify customer
        if customer:
            customer_message = f"❌ Your order has been cancelled by admin\n"
            customer_message += f"Product: {offer.name if offer else 'Unknown'}\n"
            customer_message += f"Quantity: {order.quantity}\n"
            customer_message += f"Refund: €{order.total_price:.2f}"
            self._send_message(customer.telegram_user_id, customer_message)

        # Confirm to admin
        self._send_message(chat_id, 
            f"✅ Order cancelled\n"
            f"Order ID: {order.order_id}\n"
            f"Customer notified\n"
            f"Box quantity updated: {new_quantity}/{box.max_capacity}")
        
        return {'status': 'success'}

    def _handle_order(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /order command"""
        if len(args) < 1:
            self._send_message(chat_id, "Usage: /order <offer_id> [quantity]")
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            quantity = int(args[1]) if len(args) > 1 else 1

            if quantity <= 0:
                self._send_message(chat_id, "❌ Quantity must be positive")
                return {'status': 'invalid_quantity'}

            # Get offer
            offer = self.db.get_offer(offer_id)
            if not offer or offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, "❌ Offer not found or inactive")
                return {'status': 'offer_not_found'}

            # Get customer
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, "❌ Customer not found")
                return {'status': 'customer_not_found'}

            # Check for existing orders and enforce 5 unit limit
            existing_orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) if o.offer_id == offer_id and o.status != 'cancelled']
            total_existing = sum(order.quantity for order in existing_orders)
            
            if total_existing + quantity > 5:
                message = f"❌ Order exceeds 5 unit limit for {offer.name}\n\n"
                message += f"Your existing orders ({total_existing} units):\n"
                for order in existing_orders:
                    if isinstance(order.created_at, str):
                        from datetime import datetime
                        order_date = datetime.fromisoformat(order.created_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    else:
                        order_date = order.created_at.strftime('%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                remaining_allowed = 5 - total_existing
                if remaining_allowed > 0:
                    message += f"\nMaximum you can still order: {remaining_allowed} units"
                else:
                    message += f"\nYou have reached the 5 unit limit for this offer"
                
                self._send_message(chat_id, message)
                return {'status': 'limit_exceeded'}
            
            # Check for existing orders for duplicate confirmation
            if existing_orders:
                # Show existing orders and request confirmation
                message = f"⚠️ You already have orders for {offer.name}:\n\n"
                for order in existing_orders:
                    if isinstance(order.created_at, str):
                        from datetime import datetime
                        order_date = datetime.fromisoformat(order.created_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    else:
                        order_date = order.created_at.strftime('%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                message += f"\nAre you sure you want to order {quantity}x more?\n"
                message += f"Confirm with: /confirm_order {offer_id} {quantity}"
                
                self._send_message(chat_id, message)
                return {'status': 'confirmation_required'}

            # Execute the order
            return self._execute_order(chat_id, user_id, offer_id, quantity, offer, customer)

        except ValueError:
            self._send_message(chat_id, "❌ Invalid quantity format")
            return {'status': 'invalid_format'}

    def _handle_confirm_order(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /confirm_order command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /confirm_order <offer_id> <quantity>")
            return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            quantity = int(args[1])
            
            if quantity <= 0:
                self._send_message(chat_id, "❌ Quantity must be positive")
                return {'status': 'invalid_quantity'}

            # Get offer and customer
            offer = self.db.get_offer(offer_id)
            if not offer or offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, "❌ Offer not found or inactive")
                return {'status': 'offer_not_found'}

            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, "❌ Customer not found")
                return {'status': 'customer_not_found'}
            
            # Check 5 unit limit for confirmed orders
            existing_orders = [o for o in self.db.get_orders_by_customer(customer.customer_id) if o.offer_id == offer_id and o.status != 'cancelled']
            total_existing = sum(order.quantity for order in existing_orders)
            
            if total_existing + quantity > 5:
                message = f"❌ Order exceeds 5 unit limit for {offer.name}\n\n"
                message += f"Your existing orders ({total_existing} units):\n"
                for order in existing_orders:
                    if isinstance(order.created_at, str):
                        from datetime import datetime
                        order_date = datetime.fromisoformat(order.created_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    else:
                        order_date = order.created_at.strftime('%Y-%m-%d')
                    message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({order.status})\n"
                
                remaining_allowed = 5 - total_existing
                if remaining_allowed > 0:
                    message += f"\nMaximum you can still order: {remaining_allowed} units"
                else:
                    message += f"\nYou have reached the 5 unit limit for this offer"
                
                self._send_message(chat_id, message)
                return {'status': 'limit_exceeded'}
            
            # Execute the order without duplicate check
            return self._execute_order(chat_id, user_id, offer_id, quantity, offer, customer)
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid format")
            return {'status': 'invalid_format'}

    def _execute_order(self, chat_id: int, user_id: int, offer_id: int, quantity: int, offer, customer) -> Dict[str, Any]:
        """Execute order placement"""
        try:
            # Create single order
            from decimal import Decimal
            order = Order(
                customer_id=customer.customer_id,
                box_id="",  # Will be set when assigning to boxes
                offer_id=offer_id,
                quantity=quantity,
                unit_price=Decimal(str(offer.price_per_unit)),
                total_price=Decimal(str(offer.price_per_unit)) * quantity
            )

            if not self.db.create_order(order):
                self._send_message(chat_id, "❌ Failed to place order")
                return {'status': 'error'}

            # Now assign order to boxes and update quantities
            remaining_quantity = quantity
            boxes_used = []
            
            while remaining_quantity > 0:
                # Find available box
                boxes = self.db.get_boxes_by_offer(offer_id)
                available_box = None
                
                for box in boxes:
                    if box.status in [BoxStatus.OPEN.value, BoxStatus.MINIMUM_REACHED.value]:
                        available_space = box.max_capacity - box.current_quantity
                        if available_space > 0:
                            available_box = box
                            break

                # Create new box if needed
                if not available_box:
                    available_box = Box(
                        offer_id=offer_id,
                        max_capacity=offer.wholesale_box_size,
                        min_breakeven=offer.min_quantity_breakeven
                    )
                    self.db.create_box(available_box)

                # Calculate how much can fit in this box
                available_space = available_box.max_capacity - available_box.current_quantity
                box_quantity = min(remaining_quantity, available_space)
                
                # Update box quantity and status
                new_quantity = available_box.current_quantity + box_quantity
                updates = {'current_quantity': new_quantity}
                
                if new_quantity >= available_box.max_capacity:
                    updates['status'] = BoxStatus.FULL.value
                elif new_quantity >= available_box.min_breakeven:
                    updates['status'] = BoxStatus.MINIMUM_REACHED.value

                if not self.db.update_box(available_box.box_id, updates):
                    logger.error(f"Failed to update box {available_box.box_id}")
                    self._send_message(chat_id, "❌ Failed to update box")
                    return {'status': 'error'}
                
                boxes_used.append(available_box.box_id)
                remaining_quantity -= box_quantity
                logger.info(f"Assigned {box_quantity} units to box, remaining: {remaining_quantity}")

            # Update order with first box_id (for reference)
            if boxes_used:
                self.db.update_order(order.order_id, {'box_id': boxes_used[0]})

            # Send confirmation message
            if len(boxes_used) == 1:
                self._send_message(chat_id, 
                    f"✅ Order placed!\n"
                    f"Order ID : {order.order_id}\n"
                    f"Product  : {offer.name}\n"
                    f"Quantity : {quantity}\n"
                    f"Total    : €{order.total_price:.2f}\n"
                    f"Status   : {order.status}")
            else:
                self._send_message(chat_id, 
                    f"✅ Order placed across {len(boxes_used)} boxes!\n"
                    f"Product  : {offer.name}\n"
                    f"Quantity : {quantity}\n"
                    f"Total    : €{order.total_price:.2f}\n"
                    f"Status   : pending")
            
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error in _execute_order: {e}")
            self._send_message(chat_id, "❌ Order processing failed")
            return {'status': 'error'}

    def _handle_my_orders(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /my_orders command"""
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, "❌ Customer not found")
            return {'status': 'customer_not_found'}

        orders = self.db.get_orders_by_customer(customer.customer_id)
        
        if not orders:
            self._send_message(chat_id, "You have no orders")
            return {'status': 'no_orders'}

        # Sort orders by offer_id ascending
        orders.sort(key=lambda x: x.offer_id)
        
        # Aggregate orders by offer, price and status
        from decimal import Decimal
        aggregated = {}
        for order in orders:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else "Unknown"
            
            key = (order.offer_id, order.unit_price, order.status)
            if key not in aggregated:
                aggregated[key] = {
                    'offer_name': offer_name,
                    'unit_price': order.unit_price,
                    'status': order.status,
                    'quantity': 0,
                    'total_price': Decimal('0.0'),
                    'dates': set()
                }
            
            aggregated[key]['quantity'] += order.quantity
            aggregated[key]['total_price'] += order.total_price
            
            # Add date
            if isinstance(order.created_at, str):
                from datetime import datetime
                order_date = datetime.fromisoformat(order.created_at.replace('Z', '+00:00')).strftime('%Y-%m-%d')
            else:
                order_date = order.created_at.strftime('%Y-%m-%d')
            aggregated[key]['dates'].add(order_date)

        message = "📋 Your Orders:\n\n"
        for (offer_id, unit_price, status), data in aggregated.items():
            status_emoji = {
                'pending': '⏳',
                'confirmed': '✅',
                'cancelled': '❌',
                'delivered': '📦'
            }.get(status, '❓')
            
            # Determine date display
            if len(data['dates']) == 1:
                date_display = f"[{list(data['dates'])[0]}]"
            else:
                date_display = "[multiple days]"
            
            message += f"{status_emoji} {date_display} {data['offer_name']} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f} ({status})\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}