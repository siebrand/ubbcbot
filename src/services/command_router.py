import logging
from typing import Any

from models.entities import AuthorizationStatus

logger = logging.getLogger()


class CommandRouter:
    # Permanent aliases for high-frequency commands
    PERMANENT_ALIASES = {
        "order": "create_order",
        "my_orders": "list_my_orders",
        "order_for": "create_order_for",
    }

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

    def route_command(self, chat_id: int, user_id: int, text: str, message_id: int = None) -> dict[str, Any]:
        """Route commands to appropriate handlers"""
        parts = text.split()
        command = parts[0].lower()

        # Remove bot mention from command if present
        if "@" in command:
            command = command.split("@")[0]

        # Remove leading slash for alias lookup
        command_name = command[1:] if command.startswith("/") else command

        # Apply permanent aliases
        if command_name in self.PERMANENT_ALIASES:
            command = "/" + self.PERMANENT_ALIASES[command_name]

        # In production, redirect group commands to PM (except group-specific ones).
        # /fomo is handled specially for groups below (react 👍 + reply in 1:1).
        is_group_chat = chat_id < 0
        group_allowed_commands = {"/start", "/order", "/confirm_order", "/fomo"}

        if self.environment == "prod" and is_group_chat and command not in group_allowed_commands:
            base_handler = self.base_handler
            base_handler._send_message(user_id, base_handler._t("redirected_to_pm", command=command))
            return {"status": "redirected_to_pm"}

        # Check user authorization (admin always approved)
        if not self._is_admin(user_id):
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer or customer.authorization_status != AuthorizationStatus.APPROVED.value:
                if command == "/start":
                    return self.handlers["auth"].handle_unauthorized_start(
                        chat_id if not is_group_chat or self.environment == "test" else user_id
                    )
                else:
                    base_handler = self.base_handler
                    target_chat = chat_id if not is_group_chat or self.environment == "test" else user_id
                    base_handler._send_message(target_chat, base_handler._t("unauthorized"))
                    return {"status": "unauthorized"}

        # /fomo in a group (by a registered, approved user): react 👍 on the
        # triggering message and send the fomo output to the user in 1:1.
        if command == "/fomo" and is_group_chat:
            if message_id is not None:
                self.handlers["info"]._set_message_reaction(chat_id, message_id, "👍")
            return self.handlers["info"].handle_fomo(user_id, user_id, parts[1:] or None)

        # Handle deep link start parameters
        if command == "/start" and len(parts) > 1:
            if parts[1].startswith("create_order_"):
                try:
                    _, _, offer_id_str, quantity_str = parts[1].split("_")
                    return self.handlers["customer_order"].handle_create_order(
                        chat_id, user_id, [offer_id_str, quantity_str]
                    )
                except ValueError:
                    pass
            elif parts[1].startswith("confirm_"):
                try:
                    _, offer_id_str, quantity_str = parts[1].split("_")
                    return self.handlers["customer_order"].handle_confirm_order(
                        chat_id, user_id, [offer_id_str, quantity_str]
                    )
                except ValueError:
                    pass
            elif parts[1].startswith("help_"):
                section = parts[1][5:]
                target_chat = chat_id if not is_group_chat or self.environment == "test" else user_id
                return self.handlers["info"].handle_help(target_chat, user_id, [section])
            elif parts[1].startswith("view_offer_"):
                try:
                    offer_id_str = parts[1][11:]
                    target_chat = chat_id if not is_group_chat or self.environment == "test" else user_id
                    return self.handlers["info"].handle_view_offer(target_chat, user_id, [offer_id_str])
                except ValueError:
                    pass

        # Universal commands
        target_chat = chat_id if not is_group_chat or self.environment == "test" else user_id

        if command == "/start":
            return self.handlers["info"].handle_start(target_chat, user_id, parts[1:])
        elif command == "/help":
            return self.handlers["info"].handle_help(target_chat, user_id, parts[1:])
        elif command == "/create_order":
            return self.handlers["customer_order"].handle_create_order(chat_id, user_id, parts[1:])
        elif command == "/list_my_orders":
            return self.handlers["info"].handle_list_my_orders(target_chat, user_id, parts[1:])
        elif command == "/list_offers":
            return self.handlers["info"].handle_list_offers(target_chat, user_id, parts[1:])
        elif command == "/subscribe":
            return self.handlers["info"].handle_subscribe(target_chat, user_id)
        elif command == "/unsubscribe":
            return self.handlers["info"].handle_unsubscribe(target_chat, user_id)
        elif command == "/view_offer":
            return self.handlers["info"].handle_view_offer(target_chat, user_id, parts[1:])
        elif command == "/confirm_order":
            return self.handlers["customer_order"].handle_confirm_order(chat_id, user_id, parts[1:])
        elif command == "/delete_cancelled_orders":
            return self.handlers["customer_order"].handle_delete_cancelled_orders(target_chat, user_id)
        elif command == "/delete_completed_orders":
            return self.handlers["customer_order"].handle_delete_completed_orders(target_chat, user_id)
        elif command == "/payment_info":
            return self.handlers["customer_order"].handle_payment_info(target_chat, user_id)
        elif command == "/changelog":
            return self.handlers["changelog"].handle_changelog(target_chat, user_id, 1)
        elif command == "/cancel":
            return self._handle_cancel_command(target_chat, user_id)
        elif command == "/fomo":
            return self.handlers["info"].handle_fomo(target_chat, user_id, parts[1:] or None)
        elif command == "/my_credit":
            return self.handlers["customer_credit"].handle_my_credit(target_chat, user_id)

        # Admin-only commands
        if self._is_admin(user_id):
            admin_target_chat = chat_id if not is_group_chat or self.environment == "test" else user_id

            if command == "/setup_test_data":
                return self.handlers["test"].handle_setup_test_data(admin_target_chat)
            elif command == "/test_user_message":
                return self.handlers["test"].handle_test_user_message(
                    admin_target_chat, int(parts[1]), " ".join(parts[2:])
                )
            elif command == "/create_supplier":
                return self.handlers["supplier"].handle_create_supplier(admin_target_chat, parts[1:])
            elif command == "/archive_supplier":
                return self.handlers["supplier"].handle_archive_supplier(admin_target_chat, parts[1:])
            elif command == "/list_suppliers":
                status_filter = parts[1] if len(parts) > 1 and parts[1] in ["active", "retired", "all"] else "active"
                return self.handlers["supplier"].handle_list_suppliers(admin_target_chat, 1, status_filter)
            elif command == "/update_supplier":
                return self.handlers["supplier"].handle_update_supplier(admin_target_chat, parts[1:])
            elif command == "/update_supplier_name":
                return self.handlers["supplier"].handle_update_supplier_name(admin_target_chat, parts[1:])
            elif command == "/update_supplier_contact":
                return self.handlers["supplier"].handle_update_supplier_contact(admin_target_chat, parts[1:])
            elif command == "/create_offer":
                return self.handlers["offer"].handle_create_offer(admin_target_chat, parts[1:])
            elif command == "/cancel_offer":
                return self.handlers["offer"].handle_cancel_offer(admin_target_chat, parts[1:])
            elif command == "/create_box":
                return self.handlers["offer"].handle_create_box(admin_target_chat, parts[1:])
            elif command == "/list_boxes":
                return self.handlers["offer"].handle_list_boxes(admin_target_chat, parts[1:])
            elif command == "/audit_offer":
                return self.handlers["offer"].handle_audit_offer(admin_target_chat, parts[1:])
            elif command == "/process_wholesale":
                return self.handlers["offer"].handle_process_wholesale(admin_target_chat, parts[1:])
            elif command == "/confirm_process_wholesale":
                return self.handlers["offer"].handle_confirm_process_wholesale(admin_target_chat, parts[1:])
            elif command == "/update_offer_name":
                return self.handlers["offer"].handle_update_offer_name(admin_target_chat, parts[1:])
            elif command == "/update_offer_price":
                return self.handlers["offer"].handle_update_offer_price(admin_target_chat, parts[1:])
            elif command == "/update_offer_description":
                return self.handlers["offer"].handle_update_offer_description(admin_target_chat, parts[1:])
            elif command == "/offer_status":
                return self.handlers["offer"].handle_offer_status(admin_target_chat, parts[1:])
            elif command == "/import_orders":
                return self.handlers["import"].handle_import_orders(admin_target_chat, user_id)
            elif command == "/finalize_import":
                return self.handlers["import"].handle_finalize_import(admin_target_chat, parts[1:])
            elif command == "/publish_offer":
                return self.handlers["offer"].handle_publish_offer(admin_target_chat, parts[1:])
            elif command == "/delete_offer":
                return self.handlers["offer"].handle_delete_offer(admin_target_chat, parts[1:])
            elif command == "/create_order_for":
                return self.handlers["admin_order"].handle_create_order_for(admin_target_chat, user_id, parts[1:])
            elif command == "/cancel_order":
                return self.handlers["admin_order"].handle_cancel_order(admin_target_chat, parts[1:])
            elif command == "/list_user_orders":
                return self.handlers["admin_order"].handle_list_user_orders(admin_target_chat, parts[1:])
            elif command == "/list_offer_orders":
                return self.handlers["admin_order"].handle_list_offer_orders(admin_target_chat, parts[1:])
            elif command == "/export_orders":
                return self.handlers["admin_order"].handle_export_orders(admin_target_chat, parts[1:])
            elif command == "/list_pending":
                return self.handlers["user"].handle_list_pending(admin_target_chat)
            elif command == "/approve_user":
                return self.handlers["user"].handle_approve_user(admin_target_chat, parts[1:])
            elif command == "/reject_user":
                return self.handlers["user"].handle_reject_user(admin_target_chat, parts[1:])
            elif command == "/user_status":
                return self.handlers["user"].handle_user_status(admin_target_chat, parts[1:])
            elif command == "/update_user":
                return self.handlers["user"].handle_update_user(admin_target_chat, parts[1:])
            elif command == "/update_user_first_name":
                return self.handlers["user"].handle_update_user_first_name(admin_target_chat, parts[1:])
            elif command == "/update_user_last_name":
                return self.handlers["user"].handle_update_user_last_name(admin_target_chat, parts[1:])
            elif command == "/list_users":
                status_filter = "all"
                search_string = None

                if len(parts) > 1:
                    if parts[1] in ["approved", "unauthorized", "rejected", "all", "subscribers"]:
                        status_filter = parts[1]
                        if len(parts) > 2:
                            search_string = " ".join(parts[2:])
                    else:
                        search_string = " ".join(parts[1:])

                return self.handlers["user"].handle_list_users(admin_target_chat, 1, status_filter, search_string)
            elif command == "/create_guest":
                return self.handlers["user"].handle_create_guest(admin_target_chat, parts[1:])
            elif command == "/list_guests":
                return self.handlers["user"].handle_list_guests(admin_target_chat)
            elif command == "/process_delivery":
                return self.handlers["wholesale_delivery"].handle_process_delivery(
                    admin_target_chat, user_id, parts[1:]
                )
            elif command == "/process_labeling":
                return self.handlers["labeling"].handle_process_labeling(admin_target_chat, user_id, parts[1:])
            elif command == "/send_delivery_overviews":
                return self.handlers["admin_order"].handle_send_delivery_overviews(admin_target_chat, parts[1:])
            elif command == "/process_payment":
                return self.handlers["admin_order"].handle_process_payment(admin_target_chat, parts[1:])
            elif command == "/send_payment_reminder":
                return self.handlers["admin_order"].handle_send_payment_reminder(admin_target_chat, parts[1:])
            elif command == "/failed_notifications":
                return self.handlers["admin_order"].handle_failed_notifications(admin_target_chat, parts[1:])
            elif command == "/delete_old_orders":
                return self.handlers["admin_order"].handle_delete_old_orders(admin_target_chat)
            elif command == "/audit_orders":
                return self.handlers["admin_order"].handle_audit_orders(admin_target_chat)
            elif command == "/admin":
                return self.handlers["admin_commands"].handle_admin(admin_target_chat, user_id)
            elif command == "/credit":
                return self.handlers["credit"].handle_credit(admin_target_chat, parts[1:])

        return {"status": "unknown_command"}

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
