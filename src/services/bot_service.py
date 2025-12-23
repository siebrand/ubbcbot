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
            data = callback_query['data']
            
            # Answer the callback query to remove loading state
            self._answer_callback_query(query_id)
            
            if data.startswith('confirm_order_'):
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
            
            return {'status': 'unknown_callback'}
            
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            return {'status': 'error', 'error': str(e)}
    
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

        # Check user authorization (admin always approved)
        if not self._is_admin(user_id):
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer or customer.authorization_status != AuthorizationStatus.APPROVED.value:
                if command == '/start':
                    return self.auth_commands.handle_unauthorized_start(chat_id)
                else:
                    # Use auth handler to send unauthorized message
                    from handlers.base_handler import BaseHandler
                    base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                    base_handler._send_message(chat_id, "❌ You are not authorized to use this bot. Send /start for more information.")
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
        if command == '/start' or command == '/help':
            return self.info_commands.handle_start(chat_id, user_id)
        elif command == '/order':
            return self.customer_order_commands.handle_order(chat_id, user_id, parts[1:])
        elif command == '/my_orders':
            return self.info_commands.handle_my_orders(chat_id, user_id)
        elif command == '/list_offers':
            return self.info_commands.handle_list_offers(chat_id, user_id)
        elif command == '/confirm_order':
            return self.customer_order_commands.handle_confirm_order(chat_id, user_id, parts[1:])

        # Admin-only commands
        if self._is_admin(user_id):
            # Test commands
            if command == '/setup_test_data':
                return self.test_commands.handle_setup_test_data(chat_id)
            
            # Supplier commands
            elif command == '/add_supplier':
                return self.supplier_commands.handle_add_supplier(chat_id, parts[1:])
            elif command == '/list_suppliers':
                return self.supplier_commands.handle_list_suppliers(chat_id)
            
            # Offer commands
            elif command == '/create_offer':
                return self.offer_commands.handle_create_offer(chat_id, parts[1:])
            elif command == '/box_status':
                return self.offer_commands.handle_box_status(chat_id)
            
            # Admin order commands
            elif command == '/order_for':
                return self.admin_order_commands.handle_order_for(chat_id, user_id, parts[1:])
            elif command == '/cancel_order':
                return self.admin_order_commands.handle_cancel_order(chat_id, parts[1:])
            elif command == '/confirm_cancel':
                return self.admin_order_commands.handle_confirm_cancel(chat_id, parts[1:])
            
            # User management commands
            elif command == '/pending_users':
                return self.user_commands.handle_pending_users(chat_id)
            elif command == '/approve_user':
                return self.user_commands.handle_approve_user(chat_id, parts[1:])
            elif command == '/reject_user':
                return self.user_commands.handle_reject_user(chat_id, parts[1:])
            elif command == '/user_status':
                return self.user_commands.handle_user_status(chat_id, parts[1:])

        return {'status': 'unknown_command'}