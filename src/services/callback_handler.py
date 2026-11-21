import logging
import re
from typing import Any

from models.entities import AuthorizationStatus
from services.routing.callback_router import DELETE_MESSAGE, KEEP_KEYBOARD, REMOVE_KEYBOARD, CallbackRouter
from services.telegram_client import TelegramClient
from services.translator import Translator
from utils.edit_context import EditContextManager

logger = logging.getLogger()

# Authorization: callback data is client-supplied, so the route a tap matches decides who may trigger it. A route
# registered with customer=True is open to approved customers; every other route, and data that matches no route,
# is admin-only. The customer routes are: order_, confirm_order_, view_offer_, cancel_confirmation and the pages of
# the offer list, the changelog and the customer's own orders.


class CallbackHandler:
    def __init__(
        self, db, admin_user_id: int, environment: str, telegram_token: str, handlers: dict[str, Any], media_handler
    ):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.telegram_token = telegram_token
        self.handlers = handlers
        self.media_handler = media_handler
        self._base_handler = None
        self.edit_context_manager = EditContextManager(db, self._t, self._send_message)

        # Initialize callback router
        self.router = CallbackRouter()
        self._register_routes()

    def _register_routes(self):
        """Register every callback pattern. The first match wins, so specific patterns come before broad ones."""
        # Approve user patterns - register more specific pattern first
        self.router.register(
            r"^approve_user_select_(.+)$",
            lambda match, ctx: self.handlers["user"].handle_approve_user_select(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^approve_user_([^_]+)$",  # Match approve_user_ but not approve_user_select_
            lambda match, ctx: self.handlers["user"].handle_approve_user_by_id(ctx["chat_id"], match.group(1)),
        )

        # Reject user pattern
        self.router.register(
            r"^reject_user_(.+)$",
            lambda match, ctx: self.handlers["user"].handle_reject_user_by_id(ctx["chat_id"], match.group(1)),
        )

        # Cancel patterns - most specific first
        self.router.register(
            r"^cancel_order_user_select_(.+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_cancel_order_user_select(
                ctx["chat_id"], match.group(1)
            ),
        )
        self.router.register(
            r"^cancel_order_confirm_(.+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_cancel_order_by_id(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^cancel_orders_page_([^_]+)_(\d+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_cancel_orders_page(
                ctx["chat_id"], match.group(1), int(match.group(2))
            ),
        )
        self.router.register(
            r"^cancel_confirmation$",
            lambda match, ctx: self._send_message(ctx["chat_id"], self._t("action_cancelled", ctx["user_id"])),
            customer=True,
        )
        self.router.register(
            r"^cancel_action$",
            lambda match, ctx: self.handlers["admin_commands"].handle_admin(ctx["chat_id"], ctx["user_id"]),
        )

        # Confirm patterns - most specific first
        self.router.register(
            r"^confirm_process_wholesale_(\d+)_(\d+)$",
            lambda match, ctx: self._handle_confirm_wholesale_wrapper(ctx["chat_id"], match.group(1), match.group(2)),
        )
        self.router.register(
            r"^confirm_cancel_offer_(\d+)$",
            lambda match, ctx: self.handlers["offer"].handle_confirm_cancel_offer(ctx["chat_id"], [match.group(1)]),
        )
        self.router.register(
            r"^confirm_order_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers["customer_order"].handle_confirm_order(
                ctx["reply_chat_id"], ctx["user_id"], [match.group(1), match.group(2)]
            ),
            customer=True,
        )

        # Edit patterns - most specific first
        self.router.register(
            r"^edit_user_select_(.+)$",
            lambda match, ctx: self.handlers["user"].handle_edit_user_select(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^edit_supplier_select_(.+)$",
            lambda match, ctx: self.handlers["supplier"].show_edit_interface_by_id(ctx["chat_id"], match.group(1)),
        )
        # Generic edit buttons (edit_<entity>_<field>_<id>) and the /edit_order flow
        self._register_edit_routes()

        # Order patterns - most specific first. The order buttons stay: an offer can be ordered more than once.
        self.router.register(
            r"^order_for_quantity_([^_]+)_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_create_order_for_quantity_select(
                ctx["chat_id"], match.group(1), match.group(2), match.group(3)
            ),
            keyboard=KEEP_KEYBOARD,
        )
        self.router.register(
            r"^order_for_other_([^_]+)_(\d+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_create_order_for_other_quantity(
                ctx["chat_id"], match.group(1), match.group(2)
            ),
            keyboard=KEEP_KEYBOARD,
        )
        self.router.register(
            r"^order_for_offer_([^_]+)_(\d+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_create_order_for_offer_select(
                ctx["chat_id"], match.group(1), match.group(2)
            ),
            keyboard=KEEP_KEYBOARD,
        )
        self.router.register(
            r"^order_for_user_select_(.+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_create_order_for_user_select(
                ctx["chat_id"], match.group(1)
            ),
            keyboard=KEEP_KEYBOARD,
        )
        self.router.register(
            r"^order_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers["customer_order"].handle_create_order(
                ctx["reply_chat_id"], ctx["user_id"], [match.group(1), match.group(2)]
            ),
            customer=True,
            keyboard=KEEP_KEYBOARD,
        )

        # Offer/Supplier patterns - most specific first
        self.router.register(
            r"^offer_orders_detail_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_list_offer_orders_detail_page(
                ctx["chat_id"], match.group(1), int(match.group(2))
            ),
        )
        self.router.register(
            r"^offer_orders_page_(\d+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_list_offer_orders_page(
                ctx["chat_id"], int(match.group(1))
            ),
        )
        self.router.register(
            r"^offer_orders_(\d+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_list_offer_orders_select(
                ctx["chat_id"], match.group(1)
            ),
        )
        self.router.register(
            r"^view_offer_(\d+)_edit$",
            lambda match, ctx: self.handlers["offer"].handle_edit_offer_interface(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^view_offer_(\d+)$",
            lambda match, ctx: self.handlers["info"].handle_view_offer(
                ctx["chat_id"], ctx["user_id"], [match.group(1)]
            ),
            customer=True,
        )
        self.router.register(
            r"^wholesale_select_(\d+)$",
            lambda match, ctx: self.handlers["offer"].handle_process_wholesale(ctx["chat_id"], [match.group(1)]),
        )
        self.router.register(
            r"^custom_wholesale_quantity_(\d+)$",
            lambda match, ctx: self.handlers["offer"].handle_custom_wholesale_quantity(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^publish_offer_(\d+)$",
            lambda match, ctx: self.handlers["offer"].handle_publish_offer(ctx["chat_id"], [match.group(1)]),
        )
        self.router.register(
            r"^finalize_import_(\d+)$",
            lambda match, ctx: self.handlers["import"].handle_finalize_import(ctx["chat_id"], [match.group(1)]),
        )
        self.router.register(
            r"^upload_offer_image_(\d+)$",
            lambda match, ctx: self._handle_upload_offer_image(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^clear_offer_images_(\d+)$",
            lambda match, ctx: self._handle_clear_offer_images(ctx["chat_id"], ctx["user_id"], match.group(1)),
        )

        # User/Status patterns
        self.router.register(
            r"^user_orders_select_(.+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_list_user_orders_select(
                ctx["chat_id"], match.group(1)
            ),
        )
        self.router.register(
            r"^user_status_select_(.+)$",
            lambda match, ctx: self.handlers["user"].handle_user_status_select(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^clear_data_export_select_(.+)$",
            lambda match, ctx: self.handlers["data_export"].handle_clear_data_export_select(
                ctx["chat_id"], match.group(1)
            ),
        )
        self.router.register(
            r"^rptc_([^_]+)_(.+)$",  # /report_customer: rptc_<period code>_<customer_id>
            lambda match, ctx: self.handlers["report"].handle_report_customer_select(
                ctx["chat_id"], match.group(2), match.group(1)
            ),
        )
        self.router.register(
            r"^export_user_data_select_(.+)$",
            lambda match, ctx: self.handlers["data_export"].handle_export_user_data_select(
                ctx["chat_id"], match.group(1)
            ),
        )
        self.router.register(
            r"^delete_user_select_(.+)$",
            lambda match, ctx: self.handlers["user"].handle_delete_user_select(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^delete_user_confirm_(.+)$",
            lambda match, ctx: self.handlers["user"].handle_delete_user_confirm(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^credit_customer_(.+)$",
            lambda match, ctx: self.handlers["credit"].handle_credit_customer_select(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^instant_order_supplier_(.+)$",
            lambda match, ctx: self.handlers["offer"].handle_instant_order_supplier(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^instant_order_box_(.+)$",
            lambda match, ctx: self.handlers["offer"].handle_instant_order_box_size(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^instant_order_customer_(.+)$",
            lambda match, ctx: self.handlers["offer"].handle_instant_order_customer_select(
                ctx["chat_id"], match.group(1)
            ),
        )
        self.router.register(
            r"^enter_username_orders$", lambda match, ctx: self._start_user_orders_input(ctx["chat_id"])
        )
        self.router.register(
            r"^enter_username_cancel$", lambda match, ctx: self._start_cancel_order_input(ctx["chat_id"])
        )
        self.router.register(
            r"^enter_username_order_for$", lambda match, ctx: self._start_order_for_input(ctx["chat_id"])
        )

        # Audit patterns
        self.router.register(
            r"^audit_fill_boxes_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers["offer"].execute_fill_boxes(
                ctx["chat_id"], int(match.group(1)), int(match.group(2))
            ),
        )
        self.router.register(
            r"^audit_fill_create_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers["offer"].execute_fill_and_create(
                ctx["chat_id"], int(match.group(1)), int(match.group(2))
            ),
        )
        self.router.register(
            r"^audit_create_boxes_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers["offer"].execute_create_boxes(
                ctx["chat_id"], int(match.group(1)), int(match.group(2))
            ),
        )
        self.router.register(
            r"^audit_cancel_orders_(\d+)_(\d+)$",
            lambda match, ctx: self.handlers["offer"].execute_cancel_orders(
                ctx["chat_id"], int(match.group(1)), int(match.group(2))
            ),
        )
        self.router.register(
            r"^refill_boxes_confirm_(\d+)$",
            lambda match, ctx: self.handlers["offer"].handle_confirm_refill_boxes(ctx["chat_id"], int(match.group(1))),
        )
        self.router.register(
            r"^audit_offers_page_(\d+)$",
            lambda match, ctx: self.handlers["offer"].show_audit_offer_selection(ctx["chat_id"], int(match.group(1))),
        )
        self.router.register(
            r"^audit_offer_(\d+)$",
            lambda match, ctx: self.handlers["offer"].execute_audit_offer(ctx["chat_id"], int(match.group(1))),
        )

        # Delivery/Export patterns
        self.router.register(
            r"^export_orders_(.+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_export_orders_callback(
                ctx["chat_id"], match.group(1)
            ),
        )

        # /edit_order callbacks are dispatched inside _handle_edit_callbacks
        # (the generic ^edit_(.+)$ route registered earlier is the single entry
        # point for all edit_* callbacks).

        self.router.register(
            r"^start_send_overviews$",
            lambda match, ctx: self.handlers["delivery_overview"].start_send_overviews(ctx["chat_id"]),
        )
        self.router.register(
            r"^finish_labeling_(.+)$",
            lambda match, ctx: self.handlers["labeling"].handle_finish_labeling(ctx["chat_id"], match.group(1)),
        )
        self.router.register(
            r"^process_payment_(.+)_(\d+)$",
            lambda match, ctx: self.handlers["delivery_overview"].handle_process_customer_paid(
                ctx["chat_id"], match.group(1), int(match.group(2))
            ),
            # The handler sends the list again; the old one (text and buttons) would be stale
            keyboard=DELETE_MESSAGE,
        )
        self.router.register(
            r"^payment_amount_([^_]+)_(\d+)$",
            lambda match, ctx: self.edit_context_manager.handle_payment_amount_prompt(
                ctx["chat_id"], match.group(1), int(match.group(2))
            ),
        )
        self.router.register(
            r"^payok_([^_]+)_(\d+)_([0-9a-f]{6})_(\d+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_payment_confirm(
                ctx["chat_id"], match.group(1), int(match.group(2)), match.group(3), int(match.group(4))
            ),
            # The handler sends the list again; the proposal must not be confirmed twice
            keyboard=DELETE_MESSAGE,
        )
        self.router.register(
            r"^remind_payment_(.+)_(\d+)$",
            lambda match, ctx: self.handlers["admin_order"].handle_send_payment_reminder_to_customer(
                ctx["chat_id"], match.group(1), int(match.group(2))
            ),
        )
        self.router.register(
            r"^request_cancel_reason_(.+)$",
            lambda match, ctx: self._request_cancellation_reason(ctx["chat_id"], match.group(1)),
        )

        # Navigation patterns
        self.router.register(
            r"^fomo_user_select_(.+)$",
            lambda match, ctx: (
                self.handlers["info"].show_fomo(ctx["chat_id"], ctx["user_id"], c)
                if (c := self.db.get_customer(match.group(1)))
                else self._send_message(ctx["chat_id"], self._t("customer_not_found"))
            ),
        )
        self.router.register(
            r"^back_to_supplier_list$",
            lambda match, ctx: self.handlers["supplier"].handle_list_suppliers(ctx["chat_id"], 1, "active"),
        )
        self.router.register(
            r"^process_wholesale$",
            lambda match, ctx: self.handlers["offer"].handle_process_wholesale(ctx["chat_id"], []),
        )
        self.router.register(
            r"^create_supplier_start$",
            lambda match, ctx: self._start_add_supplier(ctx["chat_id"]),
            keyboard=KEEP_KEYBOARD,
        )

        # Delivery (wd_) and labeling (lc_) workflows
        self._register_workflow_routes()

        # Admin panel navigation (admin:*) and the command buttons on it (cmd:*)
        self._register_admin_panel_routes()
        self._register_panel_command_routes()

        # Pagination of the lists (page_*)
        self._register_pagination_routes()

    def _register_pagination_routes(self):
        """Pagination buttons: ``page_<list>[_<filter>]_<page>``, built by PaginationUtils.

        Every list has its own route, so a filter may contain underscores (``sold_out``) and nothing has to
        be guessed from the number of segments. Customers may only use the three customer lists (and the
        page indicator). Paging keeps the keyboard: it is the way to the next page.
        """

        def register(pattern, handler, customer=False):
            self.router.register(pattern, handler, customer=customer, keyboard=KEEP_KEYBOARD)

        # page_info is the "3/7" indicator in the middle of the keyboard: nothing to do
        register(r"^page_info$", lambda m, ctx: None, customer=True)

        # Customer lists
        register(
            r"^page_list_offers(?:_(\w+))?_(\d+)$",
            lambda m, ctx: self.handlers["info"].handle_list_offers(
                ctx["chat_id"], ctx["user_id"], [m.group(1)] if m.group(1) else None, int(m.group(2))
            ),
            customer=True,
        )
        register(
            r"^page_changelog_(\d+)$",
            lambda m, ctx: self.handlers["changelog"].handle_changelog(ctx["chat_id"], ctx["user_id"], int(m.group(1))),
            customer=True,
        )
        # The user in the button is checked in _my_orders_page
        register(r"^page_(?:list_)?my_orders_(\d+)_(\d+)$", self._my_orders_page, customer=True)

        # Admin lists. Older buttons carry no filter (page_suppliers_2): that was always the active list.
        register(
            r"^page_process_wholesale_(\d+)$",
            lambda m, ctx: self.handlers["offer"].handle_process_wholesale_page(ctx["chat_id"], int(m.group(1))),
        )
        register(
            r"^page_suppliers_(\d+)$",
            lambda m, ctx: self.handlers["supplier"].handle_list_suppliers(ctx["chat_id"], int(m.group(1)), "active"),
        )
        register(
            r"^page_suppliers_(.+)_(\d+)$",
            lambda m, ctx: self.handlers["supplier"].handle_list_suppliers(ctx["chat_id"], int(m.group(2)), m.group(1)),
        )
        register(
            r"^page_boxes_(\d+)$",
            lambda m, ctx: self.handlers["offer"].handle_list_boxes(ctx["chat_id"], ["active", m.group(1)]),
        )
        register(
            r"^page_boxes_offer_(.+)_(\d+)$",
            lambda m, ctx: self.handlers["offer"].handle_list_boxes(ctx["chat_id"], [m.group(1), m.group(2)]),
        )
        register(
            r"^page_boxes_(.+)_(\d+)$",
            lambda m, ctx: self.handlers["offer"].handle_list_boxes(ctx["chat_id"], [m.group(1), m.group(2)]),
        )
        register(
            r"^page_pending_(\d+)_?$",
            lambda m, ctx: self.handlers["user"].handle_list_pending(ctx["chat_id"], int(m.group(1))),
        )
        register(
            r"^page_customers_(.+)_(\d+)$",
            lambda m, ctx: self.handlers["user"].handle_list_users(ctx["chat_id"], int(m.group(2)), m.group(1)),
        )
        register(
            r"^page_guests_(\d+)$",
            lambda m, ctx: self.handlers["user"].handle_list_guests(ctx["chat_id"], int(m.group(1))),
        )
        register(
            r"^page_list_open_payments_(\d+)$",
            lambda m, ctx: self.handlers["admin_order"].handle_list_open_payments(ctx["chat_id"], [], int(m.group(1))),
        )
        register(
            r"^page_process_payment_(\d+)$",
            lambda m, ctx: self.handlers["admin_order"].handle_process_payment(ctx["chat_id"], [], int(m.group(1))),
        )
        register(
            r"^page_remind_payment_(\d+)$",
            lambda m, ctx: self.handlers["admin_order"].handle_send_payment_reminder(
                ctx["chat_id"], [], int(m.group(1))
            ),
        )
        register(r"^page_(?:list_)?user_orders_(.+)_(\d+)$", self._user_orders_page)

        # Anything else that starts with page_ is not a list we know: nothing happens
        register(r"^page_", lambda m, ctx: None)

    def _user_orders_page(self, match, ctx):
        """A page of one customer's orders (admin)"""
        customer = self.db.get_customer(match.group(1))
        if customer:
            return self.handlers["admin_order"].viewing.show_user_orders(ctx["chat_id"], customer, int(match.group(2)))
        return None

    def _my_orders_page(self, match, ctx):
        """A page of your own orders. The id in the button must be the one of the user who taps it."""
        if ctx["user_id"] == int(match.group(1)):
            return self.handlers["info"].handle_list_my_orders(
                ctx["chat_id"], ctx["user_id"], None, int(match.group(2))
            )
        return None

    def _register_admin_panel_routes(self):
        """Admin panel navigation. Both ``admin:main`` and the older ``admin_main`` form are accepted."""

        def panel(method: str):
            return lambda ctx: getattr(self.handlers["admin_commands"], method)(ctx["chat_id"], ctx["user_id"])

        actions = {
            "main": panel("handle_admin"),
            "workflow": panel("handle_admin_workflow"),
            "suppliers": panel("handle_admin_suppliers"),
            "offers": panel("handle_admin_offers"),
            "orders": panel("handle_admin_orders"),
            "users": panel("handle_admin_users"),
            "system": panel("handle_admin_system"),
            "reports": panel("handle_admin_reports"),
            "close": lambda ctx: self._send_message(ctx["chat_id"], self._t("close_panel")),
            # Legacy names of sections that were merged
            "delivery": panel("handle_admin_workflow"),
            "import": panel("handle_admin_offers"),
        }
        for action, run in actions.items():
            self.router.register(rf"^admin[:_]{action}$", lambda match, ctx, run=run: run(ctx))

        # Anything else that starts with "admin" is not a panel action
        self.router.register(r"^admin", self._unknown_callback)

    def _register_panel_command_routes(self):
        """The buttons of the admin panel menus. Both ``cmd:list_pending`` and the older ``cmd_list_pending`` work."""
        # Handlers are looked up when a button is tapped, like in the other routes
        commands = {
            "create_supplier": lambda chat, user: self.handlers["supplier"].handle_create_supplier(chat, []),
            "list_suppliers": lambda chat, user: self.handlers["supplier"].handle_list_suppliers(chat, 1, "active"),
            "update_supplier": lambda chat, user: self.handlers["supplier"].handle_list_suppliers(chat, 1, "active"),
            "create_offer": lambda chat, user: self.handlers["offer"].handle_create_offer(chat, []),
            "instant_order": lambda chat, user: self.handlers["offer"].handle_instant_order(chat, []),
            "publish_offer": lambda chat, user: self._send_usage_message(chat, "usage_publish_offer"),
            "list_offers": lambda chat, user: self.handlers["info"].handle_list_offers(chat, user, []),
            "list_boxes": lambda chat, user: self.handlers["offer"].handle_list_boxes(chat),
            "audit_offer": lambda chat, user: self.handlers["offer"].handle_audit_offer(chat, []),
            "process_wholesale": lambda chat, user: self.handlers["offer"].handle_process_wholesale(chat, []),
            "export_orders": lambda chat, user: self.handlers["admin_order"].handle_export_orders(chat, []),
            "list_user_orders": lambda chat, user: self._start_user_orders_input(chat),
            "list_offer_orders": lambda chat, user: self.handlers["admin_order"].handle_list_offer_orders(chat, []),
            "cancel_order": lambda chat, user: self.handlers["admin_order"].handle_cancel_order(chat, []),
            "create_order_for": lambda chat, user: self.handlers["admin_order"].handle_create_order_for(chat, user, []),
            "list_pending": lambda chat, user: self.handlers["user"].handle_list_pending(chat),
            "list_users": lambda chat, user: self.handlers["user"].handle_list_users(chat, 1, "all"),
            "create_guest": lambda chat, user: self._send_usage_message(chat, "usage_add_guest"),
            "list_guests": lambda chat, user: self.handlers["user"].handle_list_guests(chat),
            "approve_user": lambda chat, user: self._start_approve_user_input(chat),
            "user_status": lambda chat, user: self._start_user_status_input(chat),
            "process_delivery": lambda chat, user: self.handlers["wholesale_delivery"].handle_process_delivery(
                chat, user, []
            ),
            "process_labeling": lambda chat, user: self.handlers["labeling"].handle_process_labeling(chat, user, []),
            "send_delivery_overviews": lambda chat, user: self.handlers["admin_order"].handle_send_delivery_overviews(
                chat, []
            ),
            "process_payment": lambda chat, user: self.handlers["admin_order"].handle_process_payment(chat, []),
            "list_open_payments": lambda chat, user: self.handlers["admin_order"].handle_list_open_payments(chat, []),
            "send_payment_reminder": lambda chat, user: self.handlers["admin_order"].handle_send_payment_reminder(
                chat, []
            ),
            "setup_test_data": lambda chat, user: self.handlers["test"].handle_setup_test_data(chat),
            "failed_notifications": lambda chat, user: self.handlers["admin_order"].handle_failed_notifications(
                chat, []
            ),
            "delete_old_orders": lambda chat, user: self.handlers["admin_order"].handle_delete_old_orders(chat),
            "audit_orders": lambda chat, user: self.handlers["admin_order"].handle_audit_orders(chat),
            "import_orders": lambda chat, user: self.handlers["import"].handle_import_orders(chat, user),
            "finalize_import": lambda chat, user: self.handlers["import"].handle_finalize_import(chat, []),
            "report_top_customers": lambda chat, user: self.handlers["report"].handle_report_top_customers(chat, []),
            "report_sales_month": lambda chat, user: self.handlers["report"].handle_report_sales_by_period(
                chat, ["month"]
            ),
            "report_sales_week": lambda chat, user: self.handlers["report"].handle_report_sales_by_period(
                chat, ["week"]
            ),
            "report_paid_month": lambda chat, user: self.handlers["report"].handle_report_sales_by_period(
                chat, ["month", "paid"]
            ),
            "report_customer": lambda chat, user: self.edit_context_manager.handle_input_prompts(
                chat, "report_customer_input"
            ),
        }
        for action, run in commands.items():
            self.router.register(rf"^cmd[:_]{action}$", lambda match, ctx, run=run: run(ctx["chat_id"], ctx["user_id"]))

        # Anything else that starts with "cmd" is not a panel command
        self.router.register(r"^cmd", self._unknown_callback)

    def _unknown_callback(self, match, ctx):
        """Tell the admin the button is not recognized (used for unknown actions inside a known callback family)"""
        return self._send_message(ctx["chat_id"], self._t("unknown_callback", ctx["user_id"]))

    def _register_edit_routes(self):
        """Edit buttons. ``edit_user_select_`` and ``edit_supplier_select_`` are more specific and registered first.

        Customer, supplier and offer ids have no underscore (UUIDs, numbers), so the id is the last segment and the
        segment before it is the field. Anything starting with ``edit_`` that matches nothing is reported.
        """
        register = self.router.register

        def editing():
            return self.handlers["admin_order"].editing

        # /edit_order: the order id is the first segment (a UUID prefix); a status value may contain underscores
        register(
            r"^edit_order_pick_(.+)$",
            lambda m, ctx: editing().show_aspect_menu(ctx["chat_id"], self.db.get_order(m.group(1))),
        )
        register(r"^edit_order_box_(.+)$", lambda m, ctx: editing().show_box_options(ctx["chat_id"], m.group(1)))
        register(r"^edit_order_price_(.+)$", lambda m, ctx: editing().prompt_price(ctx["chat_id"], m.group(1)))
        register(r"^edit_order_status_(.+)$", lambda m, ctx: editing().show_status_options(ctx["chat_id"], m.group(1)))
        register(
            r"^edit_order_setbox_([^_]+)_(.+)$",
            lambda m, ctx: editing().confirm_box(ctx["chat_id"], m.group(1), m.group(2)),
        )
        register(
            r"^edit_order_applybox_([^_]+)_(.+)$",
            lambda m, ctx: editing().apply_box(ctx["chat_id"], m.group(1), m.group(2)),
        )
        register(
            r"^edit_order_setstatus_([^_]+)_(.+)$",
            lambda m, ctx: editing().confirm_status(ctx["chat_id"], m.group(1), m.group(2)),
        )
        register(
            r"^edit_order_applystatus_([^_]+)_(.+)$",
            lambda m, ctx: editing().apply_status(ctx["chat_id"], m.group(1), m.group(2)),
        )

        # Text-input edits: the manager stores the context and asks for the new value
        register(
            r"^edit_supplier_(full_name|[^_]+)_([^_]+)$",
            lambda m, ctx: self.edit_context_manager.handle_supplier_edit(ctx["chat_id"], m.group(1), m.group(2)),
        )
        register(
            r"^edit_offer_([^_]+)_([^_]+)$",
            lambda m, ctx: self.edit_context_manager.handle_offer_edit(ctx["chat_id"], m.group(1), m.group(2)),
        )
        # The authorization status of a customer (the edit screen of /update_user)
        register(
            r"^edit_customer_status_([^_]+)$",
            lambda m, ctx: self.handlers["user"].handle_customer_status_options(ctx["chat_id"], m.group(1)),
        )
        register(
            # The confirmation of the warning about open orders
            r"^edit_customer_forcestatus_([^_]+)_(.+)$",
            lambda m, ctx: self.handlers["user"].handle_set_customer_status(
                ctx["chat_id"], m.group(1), m.group(2), confirmed=True
            ),
        )
        register(
            r"^edit_customer_setstatus_([^_]+)_(.+)$",
            lambda m, ctx: self.handlers["user"].handle_set_customer_status(ctx["chat_id"], m.group(1), m.group(2)),
        )
        register(
            r"^edit_customer_(first_name|last_name|contact|location)_([^_]+)$",
            lambda m, ctx: self.edit_context_manager.handle_customer_edit(ctx["chat_id"], m.group(1), m.group(2)),
        )

        register(r"^edit_", lambda m, ctx: self._send_message(ctx["chat_id"], self._t("unknown_edit")))

    def _register_workflow_routes(self):
        """The wholesale delivery (wd_) and labeling (lc_) workflows share one grammar: ``<prefix>_<verb>:<arg>:...``.

        Authorization happens before routing (``_authorize_callback``): these are admin-only by default.
        Anything with the prefix that matches no verb gets the "unknown callback" message.
        """
        workflows = (
            (
                "wd",
                "wholesale_delivery",
                "handle_delivery_action",
                "handle_complete_delivery",
                "handle_confirm_complete_delivery",
            ),
            (
                "lc",
                "labeling",
                "handle_labeling_action",
                "handle_complete_labeling",
                "handle_confirm_complete_labeling",
            ),
        )
        for prefix, key, action_method, complete_method, confirm_method in workflows:
            self._register_workflow(prefix, key, action_method, complete_method, confirm_method)

        # Partial deliveries only exist for wholesale delivery
        self.router.register(
            r"^wd_partial:([^:]+):([^:]+):(\d+)$",
            lambda m, ctx: self.handlers["wholesale_delivery"].handle_partial_action(
                ctx["chat_id"], m.group(1), m.group(2), int(m.group(3))
            ),
            keyboard=self._workflow_keyboard("wd"),
        )

        for prefix, *_ in workflows:
            self.router.register(
                rf"^{prefix}_",
                lambda m, ctx: self._send_message(ctx["chat_id"], self._t("unknown_callback", ctx["user_id"])),
                keyboard=self._workflow_keyboard(prefix),
            )

    @staticmethod
    def _workflow_keyboard(prefix: str) -> str:
        """The delivery workflow edits its message step by step, so its keyboard stays; labeling's does not"""
        return KEEP_KEYBOARD if prefix == "wd" else REMOVE_KEYBOARD

    def _register_workflow(self, prefix: str, key: str, action_method: str, complete_method: str, confirm_method: str):
        def register(pattern, handler):
            self.router.register(pattern, handler, keyboard=self._workflow_keyboard(prefix))

        register(
            rf"^{prefix}_sup:([^:]+)$",
            lambda m, ctx: self.handlers[key].handle_supplier_selection(ctx["chat_id"], m.group(1)),
        )
        register(
            rf"^{prefix}_off:(\d+):([^:]+)$",
            lambda m, ctx: self.handlers[key].handle_offer_selection(ctx["chat_id"], int(m.group(1)), m.group(2)),
        )
        register(
            rf"^{prefix}_box:([^:]+):(\d+):([^:]+)$",
            lambda m, ctx: self.handlers[key].handle_box_selection(
                ctx["chat_id"], m.group(1), int(m.group(2)), m.group(3)
            ),
        )
        register(
            rf"^{prefix}_action:([^:]+):([^:]+):(\d+):([^:]+)$",
            lambda m, ctx: getattr(self.handlers[key], action_method)(
                ctx["chat_id"], m.group(1), m.group(2), int(m.group(3)), m.group(4)
            ),
        )
        register(
            rf"^{prefix}_back:([^:]+)(?::(.*))?$",
            lambda m, ctx: self.handlers[key].handle_back_navigation(
                ctx["chat_id"], m.group(1), *(m.group(2).split(":") if m.group(2) is not None else [])
            ),
        )
        register(
            rf"^{prefix}_complete:(\d+):([^:]+)$",
            lambda m, ctx: getattr(self.handlers[key], complete_method)(ctx["chat_id"], int(m.group(1)), m.group(2)),
        )
        register(
            rf"^{prefix}_confirm_complete:(\d+):([^:]+)$",
            lambda m, ctx: getattr(self.handlers[key], confirm_method)(ctx["chat_id"], int(m.group(1)), m.group(2)),
        )
        register(
            rf"^{prefix}_confirm_complete(?::.*)?$",
            lambda m, ctx: self._send_message(ctx["chat_id"], self._t("invalid_format")),
        )

    def _handle_confirm_wholesale_wrapper(self, chat_id: int, offer_id: str, boxes: str) -> dict[str, Any]:
        """Wrapper for confirm_process_wholesale with error handling"""
        try:
            logger.info(f"Calling handle_confirm_process_wholesale with offer_id={offer_id}, boxes={boxes}")
            return self.handlers["offer"].handle_confirm_process_wholesale(chat_id, [offer_id, boxes])
        except Exception as e:
            logger.error(f"Exception in handle_confirm_process_wholesale: {e}")
            self._send_message(chat_id, self._t("invalid_format"))
            return {"status": "exception"}

    def _handle_upload_offer_image(self, chat_id: int, offer_id: str) -> dict[str, Any]:
        """Wrapper for upload_offer_image"""
        self._send_message(chat_id, self._t("awaiting_image", offer_id=offer_id))
        self._store_edit_context(chat_id, "offer_image_upload", offer_id)
        return {"status": "awaiting_image"}

    def _handle_clear_offer_images(self, chat_id: int, user_id: int, offer_id: str) -> dict[str, Any]:
        """Wrapper for clear_offer_images"""
        result = self.media_handler.handle_clear_offer_images(chat_id, offer_id)
        if result.get("return_to_edit"):
            return self.handlers["offer"].handle_edit_offer_interface(chat_id, result["offer_id"])
        return result

    def handle_callback_query(self, callback_query: dict[str, Any]) -> dict[str, Any]:
        """Handle inline button callbacks"""
        try:
            query_id = callback_query["id"]
            user_id = callback_query["from"]["id"]
            chat_id = callback_query["message"]["chat"]["id"]
            message_id = callback_query["message"]["message_id"]
            data = callback_query["data"]

            logger.info(f"Processing callback: {data}")

            # Answer the callback query to remove loading state. For order taps in a
            # group, the personal reply goes to the user's private chat, so the toast
            # tells the user where to look (the group sees no personal message).
            is_group = chat_id < 0
            is_order_tap = bool(re.match(r"^(?:confirm_)?order_\d+_\d+$", data))
            if is_group and is_order_tap:
                self._answer_callback_query(query_id, text=self._t("order_toast_check_dm", user_id))
            else:
                self._answer_callback_query(query_id)

            # Authorize before routing or touching the keyboard of the clicked message
            denied = self._authorize_callback(user_id, data)
            if denied:
                return denied

            # reply_chat_id is where personal responses go: the group button taps
            # must reply in the user's private chat, not the group, to avoid noise.
            reply_chat_id = user_id if is_group else chat_id

            # Admin flows ask for text input in the admin's private chat only (edit contexts are never read
            # in a group), so an admin tapping a button on an old message in a group continues there.
            handler_chat_id = user_id if is_group and self._is_admin(user_id) else chat_id

            context = {
                "chat_id": handler_chat_id,
                "user_id": user_id,
                "message_id": message_id,
                "reply_chat_id": reply_chat_id,
            }
            route, match = self.router.match(data)
            if route:
                route.handler(match, context)

            # The route says what happens to the tapped message: an unknown button loses its keyboard
            keyboard = route.keyboard if route else REMOVE_KEYBOARD
            if keyboard == DELETE_MESSAGE:
                self._delete_message(chat_id, message_id)
            elif keyboard == REMOVE_KEYBOARD:
                self._edit_message_remove_keyboard(chat_id, message_id)

            if route:
                logger.info(f"Callback handled by router: {data}")
                return {"status": "handled_by_router"}
            return {"status": "unknown_callback"}

        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            logger.error(f"Callback data was: {callback_query.get('data', 'NO_DATA')}")
            # The result goes back up to the webhook: the type only, an exception message can hold data
            return {"status": "error", "error": type(e).__name__}

    def _authorize_callback(self, user_id: int, data: str) -> dict[str, Any] | None:
        """Return an error result if user may not trigger this callback, None if allowed"""
        if self._is_admin(user_id):
            return None

        if not self.customer_callback(data):
            logger.warning(f"Blocked admin-only callback from non-admin user {user_id}: {data}")
            self._send_message(user_id, self._t("admin_only", user_id))
            return {"status": "unauthorized"}

        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer or customer.authorization_status != AuthorizationStatus.APPROVED.value:
            logger.info(f"Blocked callback from unapproved user {user_id}: {data}")
            self._send_message(user_id, self._t("unauthorized", user_id))
            return {"status": "unauthorized"}

        return None

    def customer_callback(self, data: str) -> bool:
        """Whether approved customers may trigger this callback: its route is registered with customer=True"""
        route, _ = self.router.match(data)
        return bool(route and route.customer)

    def _store_edit_context(self, chat_id: int, edit_type: str, entity_id: str):
        """Store edit context in DynamoDB for processing replies"""
        self.edit_context_manager.store_edit_context(chat_id, edit_type, entity_id)

    def _answer_callback_query(self, query_id: str, text: str | None = None) -> bool:
        """Answer callback query to remove loading state; optional toast text.

        text shows a short popup to the tapping user only. The group sees nothing.
        """
        data = {"callback_query_id": query_id}
        if text:
            data["text"] = text
        return self.telegram.call("answerCallbackQuery", data).ok

    def _edit_message_remove_keyboard(self, chat_id: int, message_id: int) -> bool:
        """Remove inline keyboard from a message"""
        data = {"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}}
        return self.telegram.call("editMessageReplyMarkup", data).ok

    def _delete_message(self, chat_id: int, message_id: int) -> bool:
        """Delete a message entirely (both text and keyboard)"""
        return self.telegram.call("deleteMessage", {"chat_id": chat_id, "message_id": message_id}).ok

    @property
    def telegram(self) -> TelegramClient:
        return TelegramClient(self.telegram_token)

    def _start_add_supplier(self, chat_id: int) -> dict[str, Any]:
        """Start add supplier process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, "create_supplier_name")

    def _start_user_orders_input(self, chat_id: int) -> dict[str, Any]:
        """Start user orders process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, "list_user_orders_input")

    def _start_cancel_order_input(self, chat_id: int) -> dict[str, Any]:
        """Start cancel order process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, "cancel_order_input")

    def _start_order_for_input(self, chat_id: int) -> dict[str, Any]:
        """Start order_for process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, "order_for_input")

    def _start_approve_user_input(self, chat_id: int) -> dict[str, Any]:
        """Start approve user process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, "approve_user_input")

    def _start_user_status_input(self, chat_id: int) -> dict[str, Any]:
        """Start user status process with text input"""
        return self.edit_context_manager.handle_input_prompts(chat_id, "user_status_input")

    def _send_usage_message(self, chat_id: int, usage_key: str) -> dict[str, Any]:
        """Send usage message for commands that require parameters"""
        self._send_message(chat_id, self._t(usage_key))
        return {"status": "usage_sent"}

    @property
    def base_handler(self):
        """Lazily-created shared BaseHandler for messaging/translation helpers"""
        if self._base_handler is None:
            from handlers.base_handler import BaseHandler

            self._base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        return self._base_handler

    def _t(self, key: str, user_id: int | None = None, **params) -> str:
        """Translation helper for EditContextManager"""
        return Translator(self.db).translate(key, user_id, **params)

    def _send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict | None = None,
        force_group: bool = False,
    ) -> dict:
        """Send message helper for EditContextManager"""
        return self.base_handler._send_message(
            chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, force_group=force_group
        )

    def _request_cancellation_reason(self, chat_id: int, order_id: str) -> dict[str, Any]:
        """Request cancellation reason from admin"""
        self.edit_context_manager.store_edit_context(chat_id, "cancel_order_reason", order_id)
        self.edit_context_manager.prompt_for_text_input(
            chat_id, "enter_cancellation_reason", self._t("placeholder_reason", chat_id)
        )
        return {"status": "awaiting_reason_input"}

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id
