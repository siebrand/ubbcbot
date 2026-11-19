"""The table of typed commands: which handler method answers a command, with which arguments, and for whom.

``admin_only`` is the single place that decides who may use a command. A new command is a new line here. The
CommandRouter checks the flag once, before anything is called, so a command cannot become available to customers
by being added in the wrong place.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ROUTER = None  # the "handler" of commands that the CommandRouter answers itself

USER_STATUS_FILTERS = ("approved", "unauthorized", "rejected", "all", "subscribers")
SUPPLIER_STATUS_FILTERS = ("active", "retired", "all")


@dataclass(frozen=True)
class CommandContext:
    """Where a command came from, and the chats an answer may go to"""

    chat_id: int  # the chat the command was typed in
    user_id: int  # the sender
    rest: list[str]  # the words after the command
    target_chat: int  # customer answers: the chat itself, except in a production group (then the sender's private chat)
    private_chat: int  # the sender's private chat. Admin answers always go here: prompts are only read there


ArgumentBuilder = Callable[[CommandContext], tuple[Any, ...]]


@dataclass(frozen=True)
class Route:
    handler: str | None  # key in the handlers dict, or ROUTER for a method of the CommandRouter itself
    method: str
    arguments: ArgumentBuilder
    admin_only: bool = False


# --- argument builders: (chat, ...) as the handler method expects them -----------------------------------


def target_user_rest(c: CommandContext) -> tuple:
    return (c.target_chat, c.user_id, c.rest)


def target_user(c: CommandContext) -> tuple:
    return (c.target_chat, c.user_id)


def chat_user_rest(c: CommandContext) -> tuple:
    """Ordering answers in the chat itself (not target_chat)"""
    return (c.chat_id, c.user_id, c.rest)


def private(c: CommandContext) -> tuple:
    return (c.private_chat,)


def private_rest(c: CommandContext) -> tuple:
    return (c.private_chat, c.rest)


def private_user(c: CommandContext) -> tuple:
    return (c.private_chat, c.user_id)


def private_user_rest(c: CommandContext) -> tuple:
    return (c.private_chat, c.user_id, c.rest)


def user_only(c: CommandContext) -> tuple:
    return (c.user_id,)


def changelog_first_page(c: CommandContext) -> tuple:
    return (c.target_chat, c.user_id, 1)


def fomo_arguments(c: CommandContext) -> tuple:
    return (c.target_chat, c.user_id, c.rest or None)


def cancel_arguments(c: CommandContext) -> tuple:
    """A pending prompt lives in the private chat only, so /cancel works there whatever chat it came from"""
    return (c.private_chat, c.user_id)


def list_suppliers_arguments(c: CommandContext) -> tuple:
    status_filter = c.rest[0] if c.rest and c.rest[0] in SUPPLIER_STATUS_FILTERS else "active"
    return (c.private_chat, 1, status_filter)


def list_users_arguments(c: CommandContext) -> tuple:
    """/list_users [status] [search words]: the first word is a status filter only if it is one"""
    status_filter = "all"
    search_string = None
    if c.rest:
        if c.rest[0] in USER_STATUS_FILTERS:
            status_filter = c.rest[0]
            if len(c.rest) > 1:
                search_string = " ".join(c.rest[1:])
        else:
            search_string = " ".join(c.rest)
    return (c.private_chat, 1, status_filter, search_string)


def customer_command(handler: str | None, method: str, arguments: ArgumentBuilder) -> Route:
    return Route(handler, method, arguments, admin_only=False)


def admin_command(handler: str, method: str, arguments: ArgumentBuilder) -> Route:
    return Route(handler, method, arguments, admin_only=True)


# --- the table ---------------------------------------------------------------------------------------------

COMMAND_ROUTES: dict[str, Route] = {
    # Every approved customer (and the admin)
    "/start": customer_command("info", "handle_start", target_user_rest),
    "/help": customer_command("info", "handle_help", target_user_rest),
    "/privacy": customer_command("info", "handle_privacy", target_user_rest),
    "/create_order": customer_command("customer_order", "handle_create_order", chat_user_rest),
    "/list_my_orders": customer_command("info", "handle_list_my_orders", target_user_rest),
    "/list_offers": customer_command("info", "handle_list_offers", target_user_rest),
    "/subscribe": customer_command("info", "handle_subscribe", target_user),
    "/unsubscribe": customer_command("info", "handle_unsubscribe", target_user),
    "/view_offer": customer_command("info", "handle_view_offer", target_user_rest),
    "/confirm_order": customer_command("customer_order", "handle_confirm_order", chat_user_rest),
    "/delete_cancelled_orders": customer_command("customer_order", "handle_delete_cancelled_orders", target_user),
    "/delete_completed_orders": customer_command("customer_order", "handle_delete_completed_orders", target_user),
    "/payment_info": customer_command("customer_order", "handle_payment_info", target_user),
    "/changelog": customer_command("changelog", "handle_changelog", changelog_first_page),
    "/cancel": customer_command(ROUTER, "_handle_cancel_command", cancel_arguments),
    "/fomo": customer_command("info", "handle_fomo", fomo_arguments),
    "/my_credit": customer_command("customer_credit", "handle_my_credit", target_user),
    "/my_data": customer_command("data_export", "handle_my_data", user_only),
    # The admin only
    "/setup_test_data": admin_command("test", "handle_setup_test_data", private),
    "/test_user_message": admin_command("test", "handle_test_user_message", private_rest),
    "/create_supplier": admin_command("supplier", "handle_create_supplier", private_rest),
    "/archive_supplier": admin_command("supplier", "handle_archive_supplier", private_rest),
    "/list_suppliers": admin_command("supplier", "handle_list_suppliers", list_suppliers_arguments),
    "/update_supplier": admin_command("supplier", "handle_update_supplier", private_rest),
    "/update_supplier_name": admin_command("supplier", "handle_update_supplier_name", private_rest),
    "/update_supplier_contact": admin_command("supplier", "handle_update_supplier_contact", private_rest),
    "/update_supplier_full_name": admin_command("supplier", "handle_update_supplier_full_name", private_rest),
    "/create_offer": admin_command("offer", "handle_create_offer", private_rest),
    "/cancel_offer": admin_command("offer", "handle_cancel_offer", private_rest),
    "/create_box": admin_command("offer", "handle_create_box", private_rest),
    "/list_boxes": admin_command("offer", "handle_list_boxes", private_rest),
    "/audit_offer": admin_command("offer", "handle_audit_offer", private_rest),
    "/refill_boxes": admin_command("offer", "handle_refill_boxes", private_rest),
    "/process_wholesale": admin_command("offer", "handle_process_wholesale", private_rest),
    "/confirm_process_wholesale": admin_command("offer", "handle_confirm_process_wholesale", private_rest),
    "/update_offer_name": admin_command("offer", "handle_update_offer_name", private_rest),
    "/update_offer_price": admin_command("offer", "handle_update_offer_price", private_rest),
    "/update_offer_description": admin_command("offer", "handle_update_offer_description", private_rest),
    "/offer_status": admin_command("offer", "handle_offer_status", private_rest),
    "/import_orders": admin_command("import", "handle_import_orders", private_user),
    "/finalize_import": admin_command("import", "handle_finalize_import", private_rest),
    "/publish_offer": admin_command("offer", "handle_publish_offer", private_rest),
    "/delete_offer": admin_command("offer", "handle_delete_offer", private_rest),
    "/create_order_for": admin_command("admin_order", "handle_create_order_for", private_user_rest),
    "/cancel_order": admin_command("admin_order", "handle_cancel_order", private_rest),
    "/edit_order": admin_command("admin_order", "handle_edit_order", private_rest),
    "/list_user_orders": admin_command("admin_order", "handle_list_user_orders", private_rest),
    "/list_offer_orders": admin_command("admin_order", "handle_list_offer_orders", private_rest),
    "/export_orders": admin_command("admin_order", "handle_export_orders", private_rest),
    "/list_pending": admin_command("user", "handle_list_pending", private),
    "/approve_user": admin_command("user", "handle_approve_user", private_rest),
    "/reject_user": admin_command("user", "handle_reject_user", private_rest),
    "/user_status": admin_command("user", "handle_user_status", private_rest),
    "/update_user": admin_command("user", "handle_update_user", private_rest),
    "/delete_user": admin_command("user", "handle_delete_user", private_rest),
    "/export_user_data": admin_command("data_export", "handle_export_user_data", private_rest),
    "/clear_data_export": admin_command("data_export", "handle_clear_data_export", private_rest),
    "/update_user_first_name": admin_command("user", "handle_update_user_first_name", private_rest),
    "/update_user_last_name": admin_command("user", "handle_update_user_last_name", private_rest),
    "/list_users": admin_command("user", "handle_list_users", list_users_arguments),
    "/create_guest": admin_command("user", "handle_create_guest", private_rest),
    "/list_guests": admin_command("user", "handle_list_guests", private),
    "/process_delivery": admin_command("wholesale_delivery", "handle_process_delivery", private_user_rest),
    "/process_labeling": admin_command("labeling", "handle_process_labeling", private_user_rest),
    "/send_delivery_overviews": admin_command("admin_order", "handle_send_delivery_overviews", private_rest),
    "/process_payment": admin_command("admin_order", "handle_process_payment", private_rest),
    "/send_payment_reminder": admin_command("admin_order", "handle_send_payment_reminder", private_rest),
    "/failed_notifications": admin_command("admin_order", "handle_failed_notifications", private_rest),
    "/delete_old_orders": admin_command("admin_order", "handle_delete_old_orders", private),
    "/audit_orders": admin_command("admin_order", "handle_audit_orders", private),
    "/admin": admin_command("admin_commands", "handle_admin", private_user),
    "/credit": admin_command("credit", "handle_credit", private_rest),
    "/report_top_customers": admin_command("report", "handle_report_top_customers", private_rest),
    "/report_sales_by_period": admin_command("report", "handle_report_sales_by_period", private_rest),
    "/report_customer": admin_command("report", "handle_report_customer", private_rest),
}
