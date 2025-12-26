import os
import logging
from typing import Dict, Any
from services.database import DynamoDBService
from services.command_router import CommandRouter
from services.media_handler import MediaHandler
from services.callback_handler import CallbackHandler
from models.entities import Customer, AuthorizationStatus

# Import handlers
from handlers.admin.supplier_commands import SupplierCommands
from handlers.admin.offer_commands import OfferCommands
from handlers.admin.order_commands import AdminOrderCommands
from handlers.admin.user_commands import UserCommands
from handlers.admin.test_commands import TestCommands
from handlers.admin.discount_commands import DiscountCommands
from handlers.admin.wholesale_delivery_commands import WholesaleDeliveryCommands
from handlers.customer.order_commands import CustomerOrderCommands
from handlers.customer.info_commands import InfoCommands
from handlers.customer.auth_commands import AuthCommands
from handlers.customer.changelog_commands import ChangelogCommands

logger = logging.getLogger()

class BotService:
    def __init__(self):
        self.db = DynamoDBService()
        self.admin_user_id = int(os.environ.get('ADMIN_USER_ID', '15005473'))
        self.environment = os.environ.get('ENVIRONMENT', 'test')
        self.telegram_token = self._get_telegram_token()
        
        # Initialize handlers
        self._init_handlers()
        
        # Initialize services
        self._init_services()

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
        self.wholesale_delivery_commands = WholesaleDeliveryCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        # Customer handlers
        self.customer_order_commands = CustomerOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.info_commands = InfoCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.auth_commands = AuthCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.changelog_commands = ChangelogCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
    
    def _init_services(self):
        """Initialize service components"""
        # Create handlers dictionary for services
        handlers = {
            'supplier': self.supplier_commands,
            'offer': self.offer_commands,
            'admin_order': self.admin_order_commands,
            'user': self.user_commands,
            'test': self.test_commands,
            'discount': self.discount_commands,
            'wholesale_delivery': self.wholesale_delivery_commands,
            'changelog': self.changelog_commands,
            'customer_order': self.customer_order_commands,
            'info': self.info_commands,
            'auth': self.auth_commands
        }
        
        # Initialize services
        self.command_router = CommandRouter(self.db, self.admin_user_id, self.environment, handlers)
        self.media_handler = MediaHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.callback_handler = CallbackHandler(self.db, self.admin_user_id, self.environment, self.telegram_token, handlers, self.media_handler)

    def process_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming Telegram update"""
        try:
            # Handle callback queries (inline button presses)
            if 'callback_query' in update:
                return self.callback_handler.handle_callback_query(update['callback_query'])
            
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
                return self.command_router.route_command(chat_id, user_id, text)
            
            # Handle edit replies (when user responds to force reply)
            context = self.db.get_edit_context_by_chat_id(chat_id)
            if context:
                logger.info(f"Found edit context for chat {chat_id}: {context.edit_type}")
                # Handle multiple images in media group
                if context.edit_type == 'offer_image_upload' and 'photo' in message:
                    media_group_id = message.get('media_group_id')
                    if media_group_id:
                        return self.media_handler.handle_media_group_image(chat_id, context.entity_id, message)
                    else:
                        return self._handle_edit_reply(chat_id, user_id, text, message)
                else:
                    return self._handle_edit_reply(chat_id, user_id, text, message)
            
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
            
            # Send notification to admin about new user pending authorization
            self._notify_admin_new_user_pending(user_data)
    
    def _notify_admin_new_user_pending(self, user_data: Dict[str, Any]):
        """Send notification to admin when new user registration is pending"""
        try:
            first_name = user_data.get('first_name', 'Unknown')
            last_name = user_data.get('last_name', '')
            username = user_data.get('username', 'no_username')
            user_id = user_data.get('id')
            
            # Format display name
            display_name = first_name
            if last_name:
                display_name += f" {last_name}"
            
            # Get customer ID for buttons
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                logger.error(f"Customer not found after registration for user_id: {user_id}")
                return
            
            # Create notification message using translation system
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
            
            message = base_handler._t(
                'new_user_pending_notification',
                self.admin_user_id,
                name=display_name,
                username=username,
                user_id=user_id
            )
            
            # Add approve/reject buttons
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": base_handler._t('approve_user', self.admin_user_id, name=first_name), "callback_data": f"approve_user_{customer.customer_id}"},
                        {"text": base_handler._t('reject_user', self.admin_user_id, name=first_name), "callback_data": f"reject_user_{customer.customer_id}"}
                    ]
                ]
            }
            
            # Send notification to admin with buttons
            base_handler._send_message(self.admin_user_id, message, reply_markup=keyboard)
            
            logger.info(f"Sent new user notification to admin for user: {display_name} (@{username})")
            
        except Exception as e:
            logger.error(f"Failed to send new user notification to admin: {e}")
    
    def _handle_edit_reply(self, chat_id: int, user_id: int, text: str, message: Dict[str, Any] = None) -> Dict[str, Any]:
        """Handle reply to edit prompt"""
        context = self.db.get_edit_context_by_chat_id(chat_id)
        if not context:
            return {'status': 'no_context'}
        
        # Delete the context after use
        self.db.delete_edit_context(context.context_id)
        
        edit_type = context.edit_type
        entity_id = context.entity_id
        
        # Log for debugging
        logger.info(f"Processing edit reply: type={edit_type}, entity_id={entity_id}, text={text}")
        
        # Handle image upload for offers
        if edit_type == 'offer_image_upload' and message and 'photo' in message:
            return self.media_handler.handle_offer_image_upload(chat_id, entity_id, message['photo'])
        
        if edit_type == 'supplier_name':
            return self.supplier_commands.handle_update_supplier_name(chat_id, [entity_id, text])
        elif edit_type == 'supplier_contact':
            return self.supplier_commands.handle_update_supplier_contact(chat_id, [entity_id, text])
        elif edit_type == 'offer_name':
            return self.offer_commands.handle_update_offer_name(chat_id, [entity_id, text])
        elif edit_type == 'offer_price':
            return self.offer_commands.handle_update_offer_price(chat_id, [entity_id, text])
        elif edit_type == 'offer_description':
            # For descriptions, convert Telegram entities to HTML format
            if message and 'entities' in message and message['entities']:
                html_text = self.media_handler.convert_entities_to_html(text, message['entities'])
                logger.info(f"Converting description - Original: {text}, HTML: {html_text}, Entities: {message['entities']}")
                return self.offer_commands.handle_update_offer_description(chat_id, [entity_id, html_text])
            else:
                logger.info(f"No entities found - storing plain text: {text}")
                return self.offer_commands.handle_update_offer_description(chat_id, [entity_id, text])
        elif edit_type == 'customer_first_name':
            return self.user_commands.handle_update_user_first_name(chat_id, [entity_id, text])
        elif edit_type == 'customer_last_name':
            return self.user_commands.handle_update_user_last_name(chat_id, [entity_id, text])
        elif edit_type == 'incomplete_delivery':
            return self.wholesale_delivery_commands.handle_incomplete_delivery_reply(chat_id, user_id, text, entity_id)
        
        return {'status': 'unknown_edit_type'}