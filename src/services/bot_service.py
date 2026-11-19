import logging
import os
from typing import Any

from config import ADMIN_USER_ID
from handlers.admin.admin_commands import AdminCommandsHandler
from handlers.admin.credit_commands import CreditCommands
from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.import_handler import ImportHandler
from handlers.admin.labeling_commands import LabelingCommands
from handlers.admin.offer_commands import OfferCommands
from handlers.admin.order_commands import AdminOrderCommands
from handlers.admin.report_commands import ReportCommands

# Import handlers
from handlers.admin.supplier_commands import SupplierCommands
from handlers.admin.test_commands import TestCommands
from handlers.admin.user_commands import UserCommands
from handlers.admin.wholesale_delivery_commands import WholesaleDeliveryCommands
from handlers.base_handler import BaseHandler
from handlers.customer.auth_commands import AuthCommands
from handlers.customer.changelog_commands import ChangelogCommands
from handlers.customer.credit_commands import CustomerCreditCommands
from handlers.customer.data_export_commands import DataExportCommands
from handlers.customer.info_commands import InfoCommands
from handlers.customer.order_commands import CustomerOrderCommands
from models.entities import Customer
from services.callback_handler import CallbackHandler
from services.command_router import CommandRouter
from services.database import DynamoDBService
from services.media_handler import MediaHandler
from services.routing.edit_reply_table import ANSWER_ROUTES, PromptAnswer

logger = logging.getLogger()


class BotService:
    _cached_token: str | None = None
    _cached_environment: str | None = None
    _instance: BotService | None = None

    @classmethod
    def get_instance(cls) -> BotService:
        """Return a per-container cached BotService, rebuilding only on env change.

        The Lambda execution environment is reused across warm invocations, so
        building all handlers and services once per container (instead of once
        per request) avoids repeated object allocation. The instance holds no
        per-request state: every request's chat_id/user_id stays local to
        process_update, so sharing the instance is safe.
        """
        environment = os.environ.get("ENVIRONMENT", "test")
        if cls._instance is None or cls._instance.environment != environment:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.db = DynamoDBService()
        self.admin_user_id = ADMIN_USER_ID
        self.environment = os.environ.get("ENVIRONMENT", "test")

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
        if BotService._cached_token and BotService._cached_environment == self.environment:
            return BotService._cached_token

        import boto3

        ssm = boto3.client("ssm")

        parameter_name = f"/ubbc-bot/{self.environment}/telegram-bot-token"

        try:
            response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
            token = response["Parameter"]["Value"]
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
        self.admin_order_commands = AdminOrderCommands(
            self.db, self.admin_user_id, self.environment, self.telegram_token
        )
        self.user_commands = UserCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.test_commands = TestCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.wholesale_delivery_commands = WholesaleDeliveryCommands(
            self.db, self.admin_user_id, self.environment, self.telegram_token
        )
        self.labeling_commands = LabelingCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.delivery_overview_handler = DeliveryOverviewHandler(
            self.db, self.admin_user_id, self.environment, self.telegram_token
        )
        self.admin_commands_handler = AdminCommandsHandler(
            self.db, self.admin_user_id, self.environment, self.telegram_token
        )
        self.import_handler = ImportHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.credit_commands = CreditCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.report_commands = ReportCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)

        # Customer handlers
        self.customer_order_commands = CustomerOrderCommands(
            self.db, self.admin_user_id, self.environment, self.telegram_token
        )
        self.info_commands = InfoCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.auth_commands = AuthCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.changelog_commands = ChangelogCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.customer_credit_commands = CustomerCreditCommands(
            self.db, self.admin_user_id, self.environment, self.telegram_token
        )
        self.data_export_commands = DataExportCommands(
            self.db, self.admin_user_id, self.environment, self.telegram_token
        )

    def _init_services(self):
        """Initialize service components"""
        # Create handlers dictionary for services
        handlers = {
            "supplier": self.supplier_commands,
            "offer": self.offer_commands,
            "admin_order": self.admin_order_commands,
            "user": self.user_commands,
            "test": self.test_commands,
            "wholesale_delivery": self.wholesale_delivery_commands,
            "labeling": self.labeling_commands,
            "delivery_overview": self.delivery_overview_handler,
            "admin_commands": self.admin_commands_handler,
            "import": self.import_handler,
            "changelog": self.changelog_commands,
            "customer_order": self.customer_order_commands,
            "info": self.info_commands,
            "auth": self.auth_commands,
            "credit": self.credit_commands,
            "customer_credit": self.customer_credit_commands,
            "data_export": self.data_export_commands,
            "report": self.report_commands,
        }

        self.handlers = handlers
        # Inject handlers into offer_commands for cross-handler calls
        self.offer_commands.handlers = handlers

        # Initialize services
        self.command_router = CommandRouter(self.db, self.admin_user_id, self.environment, handlers)
        self.media_handler = MediaHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        self.callback_handler = CallbackHandler(
            self.db, self.admin_user_id, self.environment, self.telegram_token, handlers, self.media_handler
        )

        # Shared BaseHandler for ad-hoc messaging/translation helpers in this service
        self.base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)

    def process_update(self, update: dict[str, Any]) -> dict[str, Any]:
        """Process incoming Telegram update"""
        try:
            # Idempotency: Telegram re-delivers an update after a 5xx/timeout. Record
            # the update_id once (conditional write); a repeat is skipped so retries
            # cannot create duplicate orders. Fails open if the dedup store errors.
            update_id = update.get("update_id")
            if update_id is not None and not self.db.mark_update_processed(update_id):
                return {"status": "duplicate"}

            self._expire_exports_on_admin_update(update)

            # Handle callback queries (inline button presses)
            if "callback_query" in update:
                return self.callback_handler.handle_callback_query(update["callback_query"])

            if "message" not in update:
                return {"status": "ignored"}

            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            message_id = message.get("message_id")
            text = message.get("text", "")

            # Log incoming command
            if text.startswith("/"):
                logger.info(f"Command: {text.split()[0]} | User ID: {user_id}")

            # Register customer if not exists
            self._register_customer_if_needed(message["from"])

            if "document" in message and user_id == self.admin_user_id:
                return self._handle_document(chat_id, user_id, message["document"])

            if text.startswith("/"):
                return self.command_router.route_command(chat_id, user_id, text, message_id)

            # Edit contexts are only created by admin flows and only ever read in the admin's private chat
            # (positive chat id). In a group nothing is consumed, so a stray message there cannot be taken
            # for the answer to an open prompt.
            context = (
                self.db.get_edit_context_by_chat_id(chat_id) if user_id == self.admin_user_id and chat_id > 0 else None
            )
            if context:
                return self._handle_edit_reply(context, chat_id, user_id, text, message)

            return {"status": "processed"}

        except Exception as e:
            logger.error(f"Error processing update: {e}")
            # The result goes back to the webhook: the type only, an exception message can hold data
            return {"status": "error", "error": type(e).__name__}

    def _expire_exports_on_admin_update(self, update: dict[str, Any]) -> None:
        """Delete expired exports when the admin does something. Customer updates skip this check."""
        try:
            sender = (update.get("callback_query") or update.get("message") or {}).get("from") or {}
            if sender.get("id") == self.admin_user_id:
                self.base_handler.expire_exports()
        except Exception as e:
            logger.error(f"Error expiring exports: {e}")

    def _register_customer_if_needed(self, user_data: dict[str, Any]):
        """Register customer if they don't exist"""
        telegram_user_id = user_data["id"]
        existing_customer = self.db.get_customer_by_telegram_id(telegram_user_id)

        if not existing_customer:
            # Store original data - sanitization happens at output time
            first_name = user_data.get("first_name", "")
            last_name = user_data.get("last_name", "")
            username = user_data.get("username", "")

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
                last_name=last_name,
                is_guest=False,
                contact_info=None,
            )
            created_customer = self.db.create_customer(customer)

            if created_customer:
                # Send notification to admin about new user pending authorization
                self._notify_admin_new_user_pending(user_data, created_customer)
            else:
                logger.error(f"Failed to create customer for user_id: {telegram_user_id}")

    def _notify_admin_new_user_pending(self, user_data: dict[str, Any], created_customer):
        """Send notification to admin when new user registration is pending"""
        try:
            base_handler = self.base_handler

            first_name = user_data.get("first_name", base_handler._t("unknown", user_id=None))
            last_name = user_data.get("last_name", "")
            username = user_data.get("username", "no_username")
            user_id = user_data.get("id")

            logger.debug(f"Starting admin notification for user ID: {user_id}")

            # Format display name
            display_name = first_name
            if last_name:
                display_name += f" {last_name}"

            # Create notification message using translation system
            message = base_handler._t(
                "new_user_pending_notification",
                self.admin_user_id,
                name=display_name,
                username=username,
                telegram_user_id=user_id,
            )

            # Add approve/reject buttons
            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": base_handler._t("approve_user", self.admin_user_id, name=first_name),
                            "callback_data": f"approve_user_{created_customer.customer_id}",
                        },
                        {
                            "text": base_handler._t("reject_user", self.admin_user_id, name=first_name),
                            "callback_data": f"reject_user_{created_customer.customer_id}",
                        },
                    ]
                ]
            }

            logger.info(f"Admin user ID from environment: {self.admin_user_id}")

            # Send notification to admin with buttons
            result = base_handler._send_message(self.admin_user_id, message, reply_markup=keyboard)

            logger.info(f"Send message result to admin {self.admin_user_id}: {result}")

            if result.get("success"):
                logger.info(f"Successfully sent new user notification to admin for user ID: {user_id}")
            else:
                logger.error(f"Failed to send new user notification to admin for user ID: {user_id}")

        except Exception as e:
            logger.error(f"Failed to send new user notification to admin: {e}")

    def _handle_document(self, chat_id: int, user_id: int, document: dict[str, Any]) -> dict[str, Any]:
        """A file from the admin is a CSV import"""
        file_id = document["file_id"]
        file_name = document.get("file_name", "unknown")
        logger.info(f"Document upload detected: file_id={file_id}, file_name={file_name}")
        result = self.import_handler.handle_document_upload(chat_id, user_id, file_id, file_name)
        logger.info(f"Document upload result: {result}")
        return result

    def _handle_edit_reply(
        self, context, chat_id: int, user_id: int, text: str, message: dict[str, Any]
    ) -> dict[str, Any]:
        """The admin's answer to an open prompt: sent to the handler that ANSWER_ROUTES names for its type"""
        logger.info(
            f"Processing edit reply: type={context.edit_type}, entity_id={context.entity_id}, "
            f"text_length={len(text or '')}"
        )
        if context.edit_type == "offer_image_upload" and "photo" in message:
            return self._handle_offer_image(context, chat_id, user_id, message)

        # The prompt is answered: whatever the answer, it is not read again
        self.db.delete_edit_context(context.context_id)

        route = ANSWER_ROUTES.get(context.edit_type)
        if route is None:
            return {"status": "unknown_edit_type"}
        answer = PromptAnswer(chat_id, user_id, text, context.entity_id, message)
        result = getattr(self.handlers[route.handler], route.method)(*route.arguments(answer))
        if route.users_menu_when_not_found and result.get("status") == "user_not_found":
            return self.handlers["admin_commands"].handle_admin_users(chat_id, user_id)
        return result

    def _handle_offer_image(self, context, chat_id: int, user_id: int, message: dict[str, Any]) -> dict[str, Any]:
        """A photo for an offer. The prompt stays open for the other photos of an album (media group)."""
        if message.get("media_group_id"):
            return self.media_handler.handle_media_group_image(chat_id, context.entity_id, message)

        result = self.media_handler.handle_offer_image_upload(chat_id, context.entity_id, message["photo"])
        logger.info(f"Image upload result: {result}")
        if result.get("return_to_edit"):
            self.db.delete_edit_context(context.context_id)
            return self.handlers["offer"].handle_edit_offer_interface(chat_id, result["offer_id"])
        return result
