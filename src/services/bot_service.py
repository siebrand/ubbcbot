import os
import logging
from typing import Dict, Any
from services.database import DynamoDBService
from models.entities import Customer, AuthorizationStatus

# Import handlers
from handlers.admin.supplier_commands import SupplierCommands
from handlers.admin.offer_commands import OfferCommands
from handlers.admin.order_commands import AdminOrderCommands
from handlers.admin.user_commands import UserCommands
from handlers.admin.test_commands import TestCommands
from handlers.admin.discount_commands import DiscountCommands
from handlers.customer.order_commands import CustomerOrderCommands
from handlers.customer.info_commands import InfoCommands
from handlers.customer.auth_commands import AuthCommands

logger = logging.getLogger()

class BotService:
    def __init__(self):
        self.db = DynamoDBService()
        self.admin_user_id = int(os.environ.get('ADMIN_USER_ID', '15005473'))
        self.environment = os.environ.get('ENVIRONMENT', 'test')
        self.telegram_token = self._get_telegram_token()
        
        # Initialize handlers
        self._init_handlers()

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

    def _init_handlers(self):
        """Initialize command handlers"""
        # Admin handlers
        self.supplier_commands = SupplierCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.offer_commands = OfferCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.admin_order_commands = AdminOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.user_commands = UserCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.test_commands = TestCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.discount_commands = DiscountCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        # Customer handlers
        self.customer_order_commands = CustomerOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.info_commands = InfoCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.auth_commands = AuthCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id

    def process_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming Telegram update"""
        try:
            # Handle callback queries (inline button presses)
            if 'callback_query' in update:
                return self._handle_callback_query(update['callback_query'])
            
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

    def _handle_callback_query(self, callback_query: Dict[str, Any]) -> Dict[str, Any]:
        """Handle inline button callbacks"""
        try:
            query_id = callback_query['id']
            user_id = callback_query['from']['id']
            chat_id = callback_query['message']['chat']['id']
            message_id = callback_query['message']['message_id']
            data = callback_query['data']
            
            # Answer the callback query to remove loading state
            self._answer_callback_query(query_id)
            
            # Determine if we should remove the keyboard based on the callback type
            should_remove_keyboard = True
            
            # Don't remove keyboard for pagination callbacks (user might want to navigate more)
            if data.startswith('page_') and not data == 'page_info':
                should_remove_keyboard = False
            
            # Remove keyboard for most actions, but not for pagination
            if should_remove_keyboard:
                self._edit_message_remove_keyboard(chat_id, message_id)
            
            # Order callbacks
            if data.startswith('order_'):
                # Parse order_<offer_id>_<quantity>
                parts = data.split('_')
                if len(parts) >= 3:
                    offer_id = parts[1]
                    quantity = parts[2]
                    return self.customer_order_commands.handle_order(chat_id, user_id, [offer_id, quantity])
            elif data.startswith('confirm_order_'):
                # Parse confirm_order_<offer_id>_<quantity>
                parts = data.split('_')
                if len(parts) >= 4:
                    offer_id = parts[2]
                    quantity = parts[3]
                    return self.customer_order_commands.handle_confirm_order(chat_id, user_id, [offer_id, quantity])
            elif data == 'cancel_confirmation':
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, "Order confirmation cancelled.")
                return {'status': 'cancelled'}
            
            # Admin confirmation callbacks
            elif data.startswith('confirm_cancel_offer_'):
                offer_id = data.split('_')[3]
                return self.offer_commands.handle_confirm_cancel_offer(chat_id, [offer_id])
            elif data.startswith('confirm_fulfill_'):
                # Parse confirm_fulfill_<offer_id>_<boxes>
                parts = data.split('_')
                if len(parts) >= 4:
                    offer_id = parts[2]
                    boxes = parts[3]
                    return self.offer_commands.handle_confirm_fulfill(chat_id, [offer_id, boxes])
            elif data.startswith('confirm_cancel_order_'):
                order_id = data.split('_')[3]
                return self.admin_order_commands.handle_confirm_cancel(chat_id, [order_id])
            elif data.startswith('approve_user_'):
                customer_id = data.split('_')[2]
                return self.user_commands.handle_approve_user_by_id(chat_id, customer_id)
            elif data.startswith('reject_user_'):
                customer_id = data.split('_')[2]
                return self.user_commands.handle_reject_user_by_id(chat_id, customer_id)
            elif data == 'cancel_action':
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, "Action cancelled.")
                return {'status': 'cancelled'}
            
            # Pagination callbacks
            elif data.startswith('page_'):
                parts = data.split('_')
                if len(parts) >= 3:
                    entity_type = parts[1]
                    page = int(parts[2])
                    
                    if entity_type == 'suppliers':
                        return self.supplier_commands.handle_list_suppliers(chat_id, page)
                    elif entity_type == 'boxes':
                        return self.offer_commands.handle_box_status(chat_id, page)
                    elif entity_type == 'pending':
                        return self.user_commands.handle_pending_users(chat_id, page)
                    elif entity_type.startswith('customers_'):
                        status_filter = entity_type.split('_', 1)[1]
                        return self.user_commands.handle_list_customers(chat_id, page, status_filter)
            elif data == 'page_info':
                # Do nothing for page info button
                return {'status': 'page_info'}
            
            # Edit callbacks
            elif data.startswith('edit_'):
                parts = data.split('_')
                if len(parts) >= 4:
                    entity_type = parts[1]  # supplier, offer
                    field = parts[2]       # name, contact, status, price
                    entity_id = parts[3]   # supplier_id or offer_id
                    
                    if entity_type == 'supplier':
                        return self._handle_supplier_edit(chat_id, field, entity_id)
                    elif entity_type == 'offer':
                        return self._handle_offer_edit(chat_id, field, entity_id)
                
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, "❌ Unknown edit action")
                return {'status': 'unknown_edit'}
            
            return {'status': 'unknown_callback'}
            
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _handle_supplier_edit(self, chat_id: int, field: str, supplier_id: str) -> Dict[str, Any]:
        """Handle supplier edit callbacks"""
        supplier = self.db.get_supplier(supplier_id)
        if not supplier:
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
            base_handler._send_message(chat_id, "❌ Supplier not found")
            return {'status': 'supplier_not_found'}
        
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        if field == 'status':
            # Toggle status
            new_status = 'retired' if supplier.status == 'active' else 'active'
            if self.db.update_supplier(supplier_id, {'status': new_status}):
                base_handler._send_message(chat_id, f"✅ Supplier '{supplier.name}' status changed to {new_status}")
                return {'status': 'success'}
            else:
                base_handler._send_message(chat_id, "❌ Failed to update supplier status")
                return {'status': 'error'}
        elif field == 'name':
            base_handler._send_message(chat_id, f"To change supplier name, use:\n/update_supplier_name {supplier_id} [new_name]")
        elif field == 'contact':
            base_handler._send_message(chat_id, f"To change supplier contact, use:\n/update_supplier_contact {supplier_id} [email]")
        else:
            base_handler._send_message(chat_id, "❌ Unknown edit field")
            return {'status': 'unknown_field'}
        
        return {'status': 'text_input_required'}
    
    def _handle_offer_edit(self, chat_id: int, field: str, offer_id: str) -> Dict[str, Any]:
        """Handle offer edit callbacks"""
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        if field == 'name':
            base_handler._send_message(chat_id, f"To change offer name, use:\n/update_offer_name {offer_id} [new_name]")
        elif field == 'price':
            base_handler._send_message(chat_id, f"To change offer price, use:\n/update_offer_price {offer_id} [new_price]")
        elif field == 'description':
            base_handler._send_message(chat_id, f"To change offer description, use:\n/update_offer_description {offer_id} [new_description]")
        else:
            base_handler._send_message(chat_id, "❌ Unknown edit field")
            return {'status': 'unknown_field'}
        
        return {'status': 'text_input_required'}
    
    def _answer_callback_query(self, query_id: str) -> bool:
        """Answer callback query to remove loading state"""
        import requests
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/answerCallbackQuery"
            data = {'callback_query_id': query_id}
            response = requests.post(url, json=data)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error answering callback query: {e}")
            return False
    
    def _edit_message_remove_keyboard(self, chat_id: int, message_id: int) -> bool:
        """Remove inline keyboard from a message"""
        import requests
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/editMessageReplyMarkup"
            data = {
                'chat_id': chat_id,
                'message_id': message_id,
                'reply_markup': {'inline_keyboard': []}
            }
            response = requests.post(url, json=data)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error removing keyboard: {e}")
            return False

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
        
        # Remove bot mention from command if present
        if '@' in command:
            command = command.split('@')[0]
        
        # In production, redirect group commands to PM (except group-specific ones)
        is_group_chat = chat_id < 0
        group_allowed_commands = {'/start', '/order', '/confirm_order'}  # Commands allowed in groups
        
        if (self.environment == 'prod' and is_group_chat and 
            command not in group_allowed_commands):
            # Send PM redirect message
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
            base_handler._send_message(user_id, f"Please use commands in private messages. Send {command} here.")
            return {'status': 'redirected_to_pm'}

        # Check user authorization (admin always approved)
        if not self._is_admin(user_id):
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer or customer.authorization_status != AuthorizationStatus.APPROVED.value:
                if command == '/start':
                    return self.auth_commands.handle_unauthorized_start(chat_id if not is_group_chat or self.environment == 'test' else user_id)
                else:
                    # Use auth handler to send unauthorized message
                    from handlers.base_handler import BaseHandler
                    base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                    target_chat = chat_id if not is_group_chat or self.environment == 'test' else user_id
                    base_handler._send_message(target_chat, "❌ You are not authorized to use this bot. Send /start for more information.")
                    return {'status': 'unauthorized'}

        # Handle deep link start parameters
        if command == '/start' and len(parts) > 1:
            if parts[1].startswith('order_'):
                # Parse order_<offer_id>_<quantity>
                try:
                    _, offer_id_str, quantity_str = parts[1].split('_')
                    return self.customer_order_commands.handle_order(chat_id, user_id, [offer_id_str, quantity_str])
                except ValueError:
                    pass  # Fall through to normal start handling
            elif parts[1].startswith('confirm_'):
                # Parse confirm_<offer_id>_<quantity>
                try:
                    _, offer_id_str, quantity_str = parts[1].split('_')
                    return self.customer_order_commands.handle_confirm_order(chat_id, user_id, [offer_id_str, quantity_str])
                except ValueError:
                    pass  # Fall through to normal start handling
        
        # Universal commands (available to everyone)
        target_chat = chat_id if not is_group_chat or self.environment == 'test' else user_id
        
        if command == '/start' or command == '/help':
            return self.info_commands.handle_start(target_chat, user_id)
        elif command == '/order':
            return self.customer_order_commands.handle_order(chat_id, user_id, parts[1:])  # Keep in group
        elif command == '/my_orders':
            return self.info_commands.handle_my_orders(target_chat, user_id, parts[1:])
        elif command == '/list_offers':
            return self.info_commands.handle_list_offers(target_chat, user_id)
        elif command == '/subscribe':
            return self.info_commands.handle_subscribe(target_chat, user_id)
        elif command == '/unsubscribe':
            return self.info_commands.handle_unsubscribe(target_chat, user_id)
        elif command == '/confirm_order':
            return self.customer_order_commands.handle_confirm_order(chat_id, user_id, parts[1:])  # Keep in group

        # Admin-only commands
        if self._is_admin(user_id):
            admin_target_chat = chat_id if not is_group_chat or self.environment == 'test' else user_id
            
            # Test commands
            if command == '/setup_test_data':
                return self.test_commands.handle_setup_test_data(admin_target_chat)
            
            # Supplier commands
            elif command == '/add_supplier':
                return self.supplier_commands.handle_add_supplier(admin_target_chat, parts[1:])
            elif command == '/retire_supplier':
                return self.supplier_commands.handle_retire_supplier(admin_target_chat, parts[1:])
            elif command == '/list_suppliers':
                return self.supplier_commands.handle_list_suppliers(admin_target_chat)
            elif command == '/edit_supplier':
                return self.supplier_commands.handle_edit_supplier(admin_target_chat, parts[1:])
            elif command == '/update_supplier_name':
                return self.supplier_commands.handle_update_supplier_name(admin_target_chat, parts[1:])
            elif command == '/update_supplier_contact':
                return self.supplier_commands.handle_update_supplier_contact(admin_target_chat, parts[1:])
            
            # Offer commands
            elif command == '/create_offer':
                return self.offer_commands.handle_create_offer(admin_target_chat, parts[1:])
            elif command == '/cancel_offer':
                return self.offer_commands.handle_cancel_offer(admin_target_chat, parts[1:])
            elif command == '/add_box':
                return self.offer_commands.handle_add_box(admin_target_chat, parts[1:])
            elif command == '/box_status':
                return self.offer_commands.handle_box_status(admin_target_chat)
            elif command == '/fulfill_offer':
                return self.offer_commands.handle_fulfill_offer(admin_target_chat, parts[1:])
            elif command == '/edit_offer':
                return self.offer_commands.handle_edit_offer(admin_target_chat, parts[1:])
            elif command == '/update_offer_name':
                return self.offer_commands.handle_update_offer_name(admin_target_chat, parts[1:])
            elif command == '/update_offer_price':
                return self.offer_commands.handle_update_offer_price(admin_target_chat, parts[1:])
            elif command == '/update_offer_description':
                return self.offer_commands.handle_update_offer_description(admin_target_chat, parts[1:])
            
            # Admin order commands
            elif command == '/order_for':
                return self.admin_order_commands.handle_order_for(admin_target_chat, user_id, parts[1:])
            elif command == '/cancel_order':
                return self.admin_order_commands.handle_cancel_order(admin_target_chat, parts[1:])
            elif command == '/user_orders':
                return self.admin_order_commands.handle_user_orders(admin_target_chat, parts[1:])
            elif command == '/all_orders':
                return self.admin_order_commands.handle_all_orders(admin_target_chat, parts[1:])
            
            # User management commands
            elif command == '/pending_users':
                return self.user_commands.handle_pending_users(admin_target_chat)
            elif command == '/approve_user':
                return self.user_commands.handle_approve_user(admin_target_chat, parts[1:])
            elif command == '/reject_user':
                return self.user_commands.handle_reject_user(admin_target_chat, parts[1:])
            elif command == '/user_status':
                return self.user_commands.handle_user_status(admin_target_chat, parts[1:])
            elif command == '/update_customer':
                return self.user_commands.handle_update_customer(admin_target_chat, parts[1:])
            elif command == '/list_customers':
                # Parse optional status filter
                status_filter = parts[1] if len(parts) > 1 and parts[1] in ['approved', 'unauthorized', 'rejected', 'all'] else 'all'
                return self.user_commands.handle_list_customers(admin_target_chat, 1, status_filter)
            
            # Discount management commands
            elif command == '/create_discount':
                return self.discount_commands.handle_create_discount(admin_target_chat, parts[1:])
            elif command == '/cancel_discount':
                return self.discount_commands.handle_cancel_discount(admin_target_chat)
            elif command == '/discount_status':
                return self.discount_commands.handle_discount_status(admin_target_chat)

        return {'status': 'unknown_command'}