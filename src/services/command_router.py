import logging
from typing import Any

from models.entities import AuthorizationStatus
from services.routing.command_table import COMMAND_ROUTES, CommandContext

logger = logging.getLogger()


class CommandRouter:
    """Routes a typed command to its handler: group redirect, authorization, special cases, then the command table"""

    # Permanent aliases for high-frequency commands
    PERMANENT_ALIASES = {
        "order": "create_order",
        "my_orders": "list_my_orders",
        "order_for": "create_order_for",
    }

    # In a production group only these commands are answered there. /fomo is handled specially in a group
    # (react 👍 + reply in 1:1). Ordering is not allowed: the bot does not send messages to a production group
    # (see BaseHandler._send_message), so the customer would get no confirmation and no error.
    GROUP_ALLOWED_COMMANDS = {"/start", "/fomo"}

    def __init__(self, db, admin_user_id: int, environment: str, handlers: dict[str, Any]):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.handlers = handlers
        self._base_handler = None

    @property
    def base_handler(self):
        """Lazily-created shared BaseHandler for messaging/translation helpers"""
        if self._base_handler is None:
            from handlers.base_handler import BaseHandler

            self._base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, "")
        return self._base_handler

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id

    def route_command(self, chat_id: int, user_id: int, text: str, message_id: int | None = None) -> dict[str, Any]:
        """Route commands to appropriate handlers"""
        parts = text.split()
        command = self._normalize(parts[0])
        is_group_chat = chat_id < 0
        context = CommandContext(
            chat_id=chat_id,
            user_id=user_id,
            rest=parts[1:],
            target_chat=chat_id if not is_group_chat or self.environment == "test" else user_id,
            private_chat=user_id if is_group_chat else chat_id,
        )

        # In production, redirect group commands to PM (except group-specific ones)
        if self.environment == "prod" and is_group_chat and command not in self.GROUP_ALLOWED_COMMANDS:
            base_handler = self.base_handler
            base_handler._send_message(user_id, base_handler._t("redirected_to_pm", command=command))
            return {"status": "redirected_to_pm"}

        # Check user authorization (admin always approved)
        blocked = self._check_authorization(command, context)
        if blocked is not None:
            return blocked

        special = self._special_case(command, context, message_id, is_group_chat)
        if special is not None:
            return special

        route = COMMAND_ROUTES.get(command)
        if route is None or (route.admin_only and not self._is_admin(user_id)):
            # Reached for a command that does not exist, and for an admin command typed by anyone but the admin.
            # Both get no reply at all, so the bot does not reveal which admin commands exist.
            return {"status": "unknown_command"}

        receiver = self if route.handler is None else self.handlers[route.handler]
        return getattr(receiver, route.method)(*route.arguments(context))

    def _normalize(self, raw_command: str) -> str:
        """Lower case, without bot mention, with permanent aliases resolved"""
        command = raw_command.lower()

        # Remove bot mention from command if present
        if "@" in command:
            command = command.split("@")[0]

        # Apply permanent aliases
        command_name = command[1:] if command.startswith("/") else command
        if command_name in self.PERMANENT_ALIASES:
            command = "/" + self.PERMANENT_ALIASES[command_name]
        return command

    def _check_authorization(self, command: str, context: CommandContext) -> dict[str, Any] | None:
        """None when the sender may continue. Everyone who is not approved gets the welcome (/start) or a refusal."""
        if self._is_admin(context.user_id):
            return None

        customer = self.db.get_customer_by_telegram_id(context.user_id)
        if customer and customer.authorization_status == AuthorizationStatus.APPROVED.value:
            return None

        if command == "/start":
            return self.handlers["auth"].handle_unauthorized_start(context.target_chat)
        base_handler = self.base_handler
        base_handler._send_message(context.target_chat, base_handler._t("unauthorized"))
        return {"status": "unauthorized"}

    def _special_case(
        self, command: str, context: CommandContext, message_id: int | None, is_group_chat: bool
    ) -> dict[str, Any] | None:
        """Commands that are not a plain call of one handler method. None when the command is not one of them."""
        # /fomo in a group (by a registered, approved user): react 👍 on the triggering message and send the
        # fomo output to the user in 1:1.
        if command == "/fomo" and is_group_chat:
            if message_id is not None:
                self.handlers["info"]._set_message_reaction(context.chat_id, message_id, "👍")
            return self.handlers["info"].handle_fomo(context.user_id, context.user_id, context.rest or None)

        if command == "/start" and context.rest:
            return self._deep_link(context)
        return None

    def _deep_link(self, context: CommandContext) -> dict[str, Any] | None:
        """/start <payload> from a link in an announcement. A malformed payload falls back to a normal /start."""
        chat_id, user_id, payload = context.chat_id, context.user_id, context.rest[0]

        if payload.startswith("create_order_"):
            try:
                _, _, offer_id_str, quantity_str = payload.split("_")
                return self.handlers["customer_order"].handle_create_order(
                    chat_id, user_id, [offer_id_str, quantity_str]
                )
            except ValueError:
                pass
        elif payload.startswith("confirm_"):
            try:
                _, offer_id_str, quantity_str = payload.split("_")
                return self.handlers["customer_order"].handle_confirm_order(
                    chat_id, user_id, [offer_id_str, quantity_str]
                )
            except ValueError:
                pass
        elif payload.startswith("help_"):
            return self.handlers["info"].handle_help(context.target_chat, user_id, [payload[5:]])
        elif payload.startswith("view_offer_"):
            try:
                return self.handlers["info"].handle_view_offer(context.target_chat, user_id, [payload[11:]])
            except ValueError:
                pass
        return None

    def _handle_cancel_command(self, chat_id: int, user_id: int) -> dict[str, Any]:
        """Handle /cancel command to clear any pending edit contexts"""
        try:
            # Check if user has any pending edit contexts (only admin flows create them)
            context = self.db.get_edit_context_by_chat_id(chat_id) if self._is_admin(user_id) else None
            if context:
                # Store context info before deleting
                edit_type = context.edit_type
                entity_id = context.entity_id

                # Delete the edit context
                self.db.delete_edit_context(context.context_id)

                # If canceling image upload, return to edit interface
                if edit_type == "offer_image_upload":
                    return self.handlers["info"].handle_view_offer(chat_id, user_id, [entity_id, "edit"])

                # Use existing info handler instead of creating new BaseHandler
                return self.handlers["info"]._send_success(chat_id, "operation_cancelled", "cancelled")
            else:
                # Use existing info handler instead of creating new BaseHandler
                return self.handlers["info"]._send_success(chat_id, "nothing_to_cancel", "nothing_to_cancel")
        except Exception:
            # Use existing info handler instead of creating new BaseHandler
            return self.handlers["info"]._send_error(chat_id, "cancel_failed", "error")
