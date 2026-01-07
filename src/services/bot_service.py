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
from handlers.admin.labeling_commands import LabelingCommands
from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.admin_commands import AdminCommandsHandler
from handlers.customer.order_commands import CustomerOrderCommands
from handlers.customer.info_commands import InfoCommands
from handlers.customer.auth_commands import AuthCommands
from handlers.customer.changelog_commands import ChangelogCommands

logger = logging.getLogger()

class BotService:
    _cached_token = None
    _cached_environment = None
    
    def __init__(self):
        self.db = DynamoDBService()
        self.admin_user_id = int(os.environ.get('ADMIN_USER_ID', '15005473'))
        self.environment = os.environ.get('ENVIRONMENT', 'test')
        
        self.telegram_token = self._get_telegram_token()
        
        if not self.telegram_token:
            logger.error("Telegram token is empty")
            raise ValueError("Telegram token is empty")
        
        # Initialize handlers
        self._init_handlers()
        
        # Initialize services
        self._init_services()

    def _get_telegram_token(self) -> str:
        """Get Telegram token from Parameter Store with caching"""
        # Return cached token if available and environment matches
        if (BotService._cached_token and 
            BotService._cached_environment == self.environment):
            return BotService._cached_token
        
        import boto3
        ssm = boto3.client('ssm')
        
        parameter_name = f'/ubbc-bot/{self.environment}/telegram-bot-token'

        try:
            response = ssm.get_parameter(
                Name=parameter_name,
                WithDecryption=True
            )
            token = response['Parameter']['Value']
            if not token:
                logger.error("Telegram token is empty")
                return ""
            
            # Cache the token and environment
            BotService._cached_token = token
            BotService._cached_environment = self.environment
            
            logger.info("Successfully retrieved and cached Telegram token")
            return token
        except Exception as e:
            logger.error(f"Error getting Telegram token from {parameter_name}: {e}")
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
        self.labeling_commands = LabelingCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.delivery_overview_handler = DeliveryOverviewHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.admin_commands_handler = AdminCommandsHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
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
            'labeling': self.labeling_commands,
            'delivery_overview': self.delivery_overview_handler,
            'admin_commands': self.admin_commands_handler,
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
            created_customer = self.db.create_customer(customer)
            
            if created_customer:
                # Send notification to admin about new user pending authorization
                self._notify_admin_new_user_pending(user_data, created_customer)
            else:
                logger.error(f"Failed to create customer for user_id: {telegram_user_id}")
    
    def _notify_admin_new_user_pending(self, user_data: Dict[str, Any], created_customer):
        """Send notification to admin when new user registration is pending"""
        try:
            first_name = user_data.get('first_name', 'Unknown')
            last_name = user_data.get('last_name', '')
            username = user_data.get('username', 'no_username')
            user_id = user_data.get('id')
            
            logger.debug(f"Starting admin notification for user: {first_name} (@{username}) ID: {user_id}")
            
            # Format display name
            display_name = first_name
            if last_name:
                display_name += f" {last_name}"

            # Create notification message using translation system
            from handlers.base_handler import BaseHandler
            base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)

            message = base_handler._t(
                'new_user_pending_notification',
                self.admin_user_id,
                name=display_name,
                username=username,
                telegram_user_id=user_id
            )

            # Add approve/reject buttons
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": base_handler._t('approve_user', self.admin_user_id, name=first_name), "callback_data": f"approve_user_{created_customer.customer_id}"},
                        {"text": base_handler._t('reject_user', self.admin_user_id, name=first_name), "callback_data": f"reject_user_{created_customer.customer_id}"}
                    ]
                ]
            }
            
            logger.info(f"Admin user ID from environment: {self.admin_user_id}")
            
            # Send notification to admin with buttons
            result = base_handler._send_message(self.admin_user_id, message, reply_markup=keyboard)
            
            logger.info(f"Send message result to admin {self.admin_user_id}: {result}")
            
            if result.get('success'):
                logger.info(f"Successfully sent new user notification to admin for user: {display_name} (@{username})")
            else:
                logger.error(f"Failed to send new user notification to admin for user: {display_name} (@{username})")
            
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
        elif edit_type == 'supplier_full_name':
            return self.supplier_commands.handle_update_supplier_full_name(chat_id, [entity_id, text])
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
        elif edit_type == 'add_supplier_name':
            return self.supplier_commands._create_supplier(chat_id, text)
        elif edit_type == 'user_orders_input':
            return self.admin_order_commands.handle_user_orders(chat_id, [text])
        elif edit_type == 'cancel_order_input':
            return self.admin_order_commands.handle_cancel_order(chat_id, [text])
        elif edit_type == 'incomplete_delivery':
            return self.wholesale_delivery_commands.handle_incomplete_delivery_reply(chat_id, user_id, text, entity_id)
        elif edit_type == 'order_for_input':
            return self.admin_order_commands.handle_order_for(chat_id, user_id, [text])
        elif edit_type == 'approve_user_input':
            result = self.user_commands.handle_approve_user(chat_id, [text])
            if result.get('status') == 'user_not_found':
                # Return to admin users menu
                return self.admin_commands_handler.handle_admin_users(chat_id, user_id)
            return result
        elif edit_type == 'user_status_input':
            result = self.user_commands.handle_user_status(chat_id, [text])
            if result.get('status') == 'user_not_found':
                # Return to admin users menu
                return self.admin_commands_handler.handle_admin_users(chat_id, user_id)
            return result
        elif edit_type == 'order_for_quantity_input':
            # Parse customer_id and offer_id from entity_id
            parts = entity_id.split('_', 1)
            if len(parts) == 2:
                customer_id, offer_id = parts[0], parts[1]
                try:
                    quantity = int(text.strip())
                    if 1 <= quantity <= 10:
                        return self.admin_order_commands.handle_order_for_quantity_select(chat_id, customer_id, offer_id, str(quantity))
                    else:
                        from handlers.base_handler import BaseHandler
                        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                        base_handler._send_message(chat_id, base_handler._t('quantity_must_be_1_to_10', chat_id))
                        return {'status': 'invalid_quantity'}
                except ValueError:
                    from handlers.base_handler import BaseHandler
                    base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                    base_handler._send_message(chat_id, base_handler._t('enter_valid_number', chat_id))
                    return {'status': 'invalid_format'}
            return {'status': 'invalid_context'}
        elif edit_type == 'payment_link_input':
            return self.delivery_overview_handler.handle_payment_link_input(chat_id, text, entity_id)
        elif edit_type == 'custom_wholesale_quantity':
            try:
                boxes = int(text.strip())
                if boxes > 0:
                    return self.offer_commands.handle_confirm_order_wholesale(chat_id, [entity_id, str(boxes)])
                else:
                    from handlers.base_handler import BaseHandler
                    base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                    base_handler._send_message(chat_id, base_handler._t('boxes_must_positive'))
                    return {'status': 'invalid_quantity'}
            except ValueError:
                from handlers.base_handler import BaseHandler
                base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
                base_handler._send_message(chat_id, base_handler._t('invalid_format'))
                return {'status': 'invalid_format'}
        elif edit_type == 'cancel_order_reason':
            # Handle cancellation reason input
            order_id = entity_id
            reason = text.strip() if text.strip() else "No reason provided"
            return self.admin_order_commands.handle_confirm_cancel_with_reason(chat_id, order_id, reason)
        
        return {'status': 'unknown_edit_type'}