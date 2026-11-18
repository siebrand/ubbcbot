"""Characterization of callback dispatch: what every inline button does, at the handle_callback_query boundary.

These tests describe behavior, not structure. They must pass unchanged before and after the dispatch is
centralized on the CallbackRouter: each callback is tapped as the real bot receives it, and the test checks
which handler is called with which arguments (every handler is a mock, so nothing else can happen).

Rows marked "BUG" record behavior that is wrong today. They are expected failures (strict), so they turn
into errors the moment the behavior is fixed, which is the signal to remove the mark.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from handler_classes import handler_mock_spec

from services.callback_handler import CUSTOMER_CALLBACK_PATTERN, CallbackHandler
from utils.pagination import PaginationUtils

ADMIN_ID = 15005473
CUSTOMER_ID = 4242
OTHER_USER_ID = 999
CHAT = ADMIN_ID  # the admin taps in the private chat
CID = "11111111-2222-3333-4444-555555555555"
CUSTOMER_OBJ = SimpleNamespace(name="customer")
ORDER_OBJ = SimpleNamespace(name="order")

HANDLER_KEYS = (
    "admin_commands",
    "admin_order",
    "changelog",
    "credit",
    "customer_order",
    "data_export",
    "delivery_overview",
    "import",
    "info",
    "labeling",
    "offer",
    "report",
    "supplier",
    "test",
    "user",
    "wholesale_delivery",
)


# --- expectations -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Calls:
    """Exactly these calls on one handler, and nothing else happens"""

    key: str
    calls: tuple


@dataclass(frozen=True)
class Prompt:
    """The text-input prompt `name` is started (edit_context_manager.handle_input_prompts)"""

    name: str


@dataclass(frozen=True)
class EditCtx:
    """edit_context_manager.<method>(chat, field, entity_id)"""

    method: str
    field: str
    entity_id: str


@dataclass(frozen=True)
class Says:
    """One message with the translation `key` goes to the chat, nothing else happens"""

    key: str


@dataclass(frozen=True)
class Silent:
    """Recognized, but no handler is called and nothing is sent"""


@dataclass(frozen=True)
class Fails:
    """Malformed data: the bot reports an error status and calls no handler"""


def C(key: str, *calls) -> Calls:
    return Calls(key, tuple(calls))


# --- harness ----------------------------------------------------------------------------------------


def make_env(approved: bool = True):
    # A mock that only has the methods of the real class: a route to a method that does not exist fails here
    handlers = {key: Mock(name=key, spec=handler_mock_spec(key)) for key in HANDLER_KEYS}
    db = Mock()
    status = "approved" if approved else "unauthorized"
    db.get_customer_by_telegram_id.return_value = Mock(authorization_status=status, language="nl")
    db.get_customer.return_value = CUSTOMER_OBJ
    db.get_order.return_value = ORDER_OBJ
    media_handler = Mock()
    media_handler.handle_clear_offer_images.return_value = {"status": "cleared"}
    handler = CallbackHandler(db, ADMIN_ID, "test", "token", handlers, media_handler)
    handler._answer_callback_query = Mock()
    handler._edit_message_remove_keyboard = Mock()
    handler._delete_message = Mock()
    handler._send_message = Mock()
    handler.edit_context_manager = Mock()
    return SimpleNamespace(handler=handler, handlers=handlers, db=db)


def tap(env, data: str, user_id: int = ADMIN_ID, chat_id: int | None = None):
    chat = user_id if chat_id is None else chat_id
    query = {"id": "q", "from": {"id": user_id}, "message": {"chat": {"id": chat}, "message_id": 9}, "data": data}
    return env.handler.handle_callback_query(query)


def all_handler_calls(env) -> dict:
    return {key: mock.mock_calls for key, mock in env.handlers.items() if mock.mock_calls}


def assert_effect(env, effect, result, chat: int = CHAT):
    handler = env.handler
    if isinstance(effect, Calls):
        assert all_handler_calls(env) == {effect.key: list(effect.calls)}
        handler._send_message.assert_not_called()
        assert handler.edit_context_manager.mock_calls == []
    elif isinstance(effect, Prompt):
        assert all_handler_calls(env) == {}
        handler.edit_context_manager.handle_input_prompts.assert_called_once_with(chat, effect.name)
        handler._send_message.assert_not_called()
    elif isinstance(effect, EditCtx):
        assert all_handler_calls(env) == {}
        getattr(handler.edit_context_manager, effect.method).assert_called_once_with(
            chat, effect.field, effect.entity_id
        )
        handler._send_message.assert_not_called()
    elif isinstance(effect, Says):
        assert all_handler_calls(env) == {}
        handler._send_message.assert_called_once_with(chat, handler._t(effect.key, ADMIN_ID))
        assert handler.edit_context_manager.mock_calls == []
    elif isinstance(effect, Silent):
        assert all_handler_calls(env) == {}
        handler._send_message.assert_not_called()
        assert handler.edit_context_manager.mock_calls == []
    elif isinstance(effect, Fails):
        assert all_handler_calls(env) == {}
        assert result["status"] == "error"
    else:  # pragma: no cover
        raise AssertionError(f"unknown effect {effect!r}")


# --- the corpus: admin-only groups ------------------------------------------------------------------

WD = [
    ("wd_sup:abc", C("wholesale_delivery", call.handle_supplier_selection(CHAT, "abc"))),
    ("wd_off:7:abc", C("wholesale_delivery", call.handle_offer_selection(CHAT, 7, "abc"))),
    ("wd_box:box1:7:abc", C("wholesale_delivery", call.handle_box_selection(CHAT, "box1", 7, "abc"))),
    (
        "wd_action:full:box1:7:abc",
        C("wholesale_delivery", call.handle_delivery_action(CHAT, "full", "box1", 7, "abc")),
    ),
    ("wd_partial:delayed:box1:5", C("wholesale_delivery", call.handle_partial_action(CHAT, "delayed", "box1", 5))),
    ("wd_back:boxes:7:abc", C("wholesale_delivery", call.handle_back_navigation(CHAT, "boxes", "7", "abc"))),
    ("wd_back:suppliers", C("wholesale_delivery", call.handle_back_navigation(CHAT, "suppliers"))),
    ("wd_complete:7:abc", C("wholesale_delivery", call.handle_complete_delivery(CHAT, 7, "abc"))),
    (
        "wd_confirm_complete:7:abc",
        C("wholesale_delivery", call.handle_confirm_complete_delivery(CHAT, 7, "abc")),
    ),
    ("wd_confirm_complete:7", Says("invalid_format")),
    ("wd_unknown:1", Says("unknown_callback")),
    ("wd_sup", Says("unknown_callback")),  # no value after the prefix
    ("wd_off:notanumber:abc", Says("unknown_callback")),
]

LC = [
    ("lc_sup:abc", C("labeling", call.handle_supplier_selection(CHAT, "abc"))),
    ("lc_off:7:abc", C("labeling", call.handle_offer_selection(CHAT, 7, "abc"))),
    ("lc_box:box1:7:abc", C("labeling", call.handle_box_selection(CHAT, "box1", 7, "abc"))),
    ("lc_action:complete:box1:7:abc", C("labeling", call.handle_labeling_action(CHAT, "complete", "box1", 7, "abc"))),
    ("lc_complete:7:abc", C("labeling", call.handle_complete_labeling(CHAT, 7, "abc"))),
    ("lc_confirm_complete:7:abc", C("labeling", call.handle_confirm_complete_labeling(CHAT, 7, "abc"))),
    ("lc_confirm_complete:7", Says("invalid_format")),
    ("lc_back:boxes:7:abc", C("labeling", call.handle_back_navigation(CHAT, "boxes", "7", "abc"))),
    ("lc_back:offers", C("labeling", call.handle_back_navigation(CHAT, "offers"))),
    ("lc_unknown:1", Says("unknown_callback")),
    ("lc_off:notanumber:abc", Says("unknown_callback")),
]

ADMIN_PANEL = [
    ("admin:main", C("admin_commands", call.handle_admin(CHAT, ADMIN_ID))),
    ("admin:workflow", C("admin_commands", call.handle_admin_workflow(CHAT, ADMIN_ID))),
    ("admin:suppliers", C("admin_commands", call.handle_admin_suppliers(CHAT, ADMIN_ID))),
    ("admin:offers", C("admin_commands", call.handle_admin_offers(CHAT, ADMIN_ID))),
    ("admin:orders", C("admin_commands", call.handle_admin_orders(CHAT, ADMIN_ID))),
    ("admin:users", C("admin_commands", call.handle_admin_users(CHAT, ADMIN_ID))),
    ("admin:system", C("admin_commands", call.handle_admin_system(CHAT, ADMIN_ID))),
    ("admin:reports", C("admin_commands", call.handle_admin_reports(CHAT, ADMIN_ID))),
    ("admin:close", Says("close_panel")),
    ("admin:delivery", C("admin_commands", call.handle_admin_workflow(CHAT, ADMIN_ID))),  # legacy
    ("admin:import", C("admin_commands", call.handle_admin_offers(CHAT, ADMIN_ID))),  # legacy
    ("admin_main", C("admin_commands", call.handle_admin(CHAT, ADMIN_ID))),  # old format
    ("admin_users", C("admin_commands", call.handle_admin_users(CHAT, ADMIN_ID))),  # old format
    ("admin_close", Says("close_panel")),  # old format
    ("admin:nonsense", Says("unknown_callback")),
    ("admin:", Says("unknown_callback")),
    ("admin", Says("unknown_callback")),
]

CMD = [
    ("cmd:create_supplier", C("supplier", call.handle_create_supplier(CHAT, []))),
    ("cmd:list_suppliers", C("supplier", call.handle_list_suppliers(CHAT, 1, "active"))),
    ("cmd:update_supplier", C("supplier", call.handle_list_suppliers(CHAT, 1, "active"))),
    ("cmd:create_offer", C("offer", call.handle_create_offer(CHAT, []))),
    ("cmd:publish_offer", Says("usage_publish_offer")),
    ("cmd:list_offers", C("info", call.handle_list_offers(CHAT, ADMIN_ID, []))),
    ("cmd:list_boxes", C("offer", call.handle_list_boxes(CHAT))),
    ("cmd:audit_offer", C("offer", call.handle_audit_offer(CHAT, []))),
    ("cmd:process_wholesale", C("offer", call.handle_process_wholesale(CHAT, []))),
    ("cmd:export_orders", C("admin_order", call.handle_export_orders(CHAT, []))),
    ("cmd:list_user_orders", Prompt("list_user_orders_input")),
    ("cmd:list_offer_orders", C("admin_order", call.handle_list_offer_orders(CHAT, []))),
    ("cmd:cancel_order", C("admin_order", call.handle_cancel_order(CHAT, []))),
    ("cmd:create_order_for", C("admin_order", call.handle_create_order_for(CHAT, ADMIN_ID, []))),
    ("cmd:list_pending", C("user", call.handle_list_pending(CHAT))),
    ("cmd:list_users", C("user", call.handle_list_users(CHAT, 1, "all"))),
    ("cmd:create_guest", Says("usage_add_guest")),
    ("cmd:list_guests", C("user", call.handle_list_guests(CHAT))),
    ("cmd:approve_user", Prompt("approve_user_input")),
    ("cmd:user_status", Prompt("user_status_input")),
    ("cmd:process_delivery", C("wholesale_delivery", call.handle_process_delivery(CHAT, ADMIN_ID, []))),
    ("cmd:process_labeling", C("labeling", call.handle_process_labeling(CHAT, ADMIN_ID, []))),
    ("cmd:send_delivery_overviews", C("admin_order", call.handle_send_delivery_overviews(CHAT, []))),
    ("cmd:process_payment", C("admin_order", call.handle_process_payment(CHAT, []))),
    ("cmd:send_payment_reminder", C("admin_order", call.handle_send_payment_reminder(CHAT, []))),
    ("cmd:setup_test_data", C("test", call.handle_setup_test_data(CHAT))),
    ("cmd:failed_notifications", C("admin_order", call.handle_failed_notifications(CHAT, []))),
    ("cmd:delete_old_orders", C("admin_order", call.handle_delete_old_orders(CHAT))),
    ("cmd:audit_orders", C("admin_order", call.handle_audit_orders(CHAT))),
    ("cmd:import_orders", C("import", call.handle_import_orders(CHAT, ADMIN_ID))),
    ("cmd:finalize_import", C("import", call.handle_finalize_import(CHAT, []))),
    ("cmd:report_top_customers", C("report", call.handle_report_top_customers(CHAT, []))),
    ("cmd:report_sales_month", C("report", call.handle_report_sales_by_period(CHAT, ["month"]))),
    ("cmd:report_sales_week", C("report", call.handle_report_sales_by_period(CHAT, ["week"]))),
    ("cmd:report_paid_month", C("report", call.handle_report_sales_by_period(CHAT, ["month", "paid"]))),
    ("cmd:report_customer", Prompt("report_customer_input")),
    (
        f"rptc_20260101-20261118_{CID}",
        C("report", call.handle_report_customer_select(CHAT, CID, "20260101-20261118")),
    ),
    ("cmd_list_pending", C("user", call.handle_list_pending(CHAT))),  # old format
    ("cmd_list_guests", C("user", call.handle_list_guests(CHAT))),  # old format
    ("cmd:nonsense", Says("unknown_callback")),
    ("cmd", Says("unknown_callback")),
]

EDIT = [
    ("edit_offer_name_7", EditCtx("handle_offer_edit", "name", "7")),
    ("edit_offer_price_7", EditCtx("handle_offer_edit", "price", "7")),
    ("edit_offer_description_7", EditCtx("handle_offer_edit", "description", "7")),
    ("edit_supplier_name_s1", EditCtx("handle_supplier_edit", "name", "s1")),
    ("edit_supplier_contact_s1", EditCtx("handle_supplier_edit", "contact", "s1")),
    ("edit_supplier_status_s1", EditCtx("handle_supplier_edit", "status", "s1")),
    ("edit_supplier_full_name_s1", EditCtx("handle_supplier_edit", "full_name", "s1")),
    ("edit_customer_first_name_c1", EditCtx("handle_customer_edit", "first_name", "c1")),
    ("edit_customer_last_name_c1", EditCtx("handle_customer_edit", "last_name", "c1")),
    ("edit_customer_contact_c1", EditCtx("handle_customer_edit", "contact", "c1")),
    ("edit_customer_location_c1", EditCtx("handle_customer_edit", "location", "c1")),
    ("edit_order_pick_abc12345", C("admin_order", call.editing._show_aspect_menu(CHAT, ORDER_OBJ))),
    ("edit_order_box_abc12345", C("admin_order", call.editing.show_box_options(CHAT, "abc12345"))),
    ("edit_order_price_abc12345", C("admin_order", call.editing.prompt_price(CHAT, "abc12345"))),
    ("edit_order_status_abc12345", C("admin_order", call.editing.show_status_options(CHAT, "abc12345"))),
    ("edit_order_setbox_abc12345_def67890", C("admin_order", call.editing.confirm_box(CHAT, "abc12345", "def67890"))),
    ("edit_order_applybox_abc12345_def67890", C("admin_order", call.editing.apply_box(CHAT, "abc12345", "def67890"))),
    (
        "edit_order_setstatus_abc12345_ready_for_labeling",
        C("admin_order", call.editing.confirm_status(CHAT, "abc12345", "ready_for_labeling")),
    ),
    (
        "edit_order_applystatus_abc12345_awaiting_payment",
        C("admin_order", call.editing.apply_status(CHAT, "abc12345", "awaiting_payment")),
    ),
    ("edit_user_select_c1", C("user", call.handle_edit_user_select(CHAT, "c1"))),  # already on the router
    ("edit_supplier_select_s1", C("supplier", call.show_edit_interface_by_id(CHAT, "s1"))),  # already on the router
    ("edit_order_zzz_abc12345", Says("unknown_edit")),
    ("edit_foo", Says("unknown_edit")),
    ("edit_offer_name", Says("unknown_edit")),  # too few parts
    ("edit_widget_name_7", Says("unknown_edit")),  # unknown entity
]

PAGE_ADMIN = [
    ("page_info", Silent()),
    ("page_process_wholesale_2", C("offer", call.handle_process_wholesale_page(CHAT, 2))),
    ("page_suppliers_active_2", C("supplier", call.handle_list_suppliers(CHAT, 2, "active"))),
    ("page_suppliers_retired_3", C("supplier", call.handle_list_suppliers(CHAT, 3, "retired"))),
    # Older buttons carry no filter: the list was always the active one
    ("page_suppliers_2", C("supplier", call.handle_list_suppliers(CHAT, 2, "active"))),
    ("page_boxes_2", C("offer", call.handle_list_boxes(CHAT, ["active", "2"]))),
    ("page_pending_2_", C("user", call.handle_list_pending(CHAT, 2))),
    ("page_customers_all_2", C("user", call.handle_list_users(CHAT, 2, "all"))),
    ("page_customers_subscribers_1", C("user", call.handle_list_users(CHAT, 1, "subscribers"))),
    ("page_guests_2", C("user", call.handle_list_guests(CHAT, 2))),
    ("page_process_payment_2", C("admin_order", call.handle_process_payment(CHAT, [], 2))),
    ("page_remind_payment_2", C("admin_order", call.handle_send_payment_reminder(CHAT, [], 2))),
    (f"page_user_orders_{CID}_2", C("admin_order", call.viewing._show_user_orders(CHAT, CUSTOMER_OBJ, 2))),
    (f"page_list_user_orders_{CID}_3", C("admin_order", call.viewing._show_user_orders(CHAT, CUSTOMER_OBJ, 3))),
    ("page_foo_2", Silent()),  # unknown type
    ("page_x", Silent()),  # too short
]

# Customer-facing pagination, tapped by an approved customer (chat = the customer's private chat)
PAGE_CUSTOMER = [
    ("page_info", Silent()),
    ("page_list_offers_2", C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, None, 2))),
    ("page_list_offers_active_2", C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, ["active"], 2))),
    ("page_list_offers_soldout_3", C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, ["soldout"], 3))),
    ("page_list_offers_user_2", C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, ["user"], 2))),
    ("page_changelog_2", C("changelog", call.handle_changelog(CUSTOMER_ID, CUSTOMER_ID, 2))),
    (
        f"page_my_orders_{CUSTOMER_ID}_2",
        C("info", call.handle_list_my_orders(CUSTOMER_ID, CUSTOMER_ID, None, 2)),
    ),
    (
        f"page_list_my_orders_{CUSTOMER_ID}_3",
        C("info", call.handle_list_my_orders(CUSTOMER_ID, CUSTOMER_ID, None, 3)),
    ),
    (f"page_my_orders_{OTHER_USER_ID}_2", Silent()),  # somebody else's orders: refused
    ("page_list_offers_sold_out_2", C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, ["sold_out"], 2))),
]

# /list_boxes pagination. These were broken before the pagination moved onto the router.
PAGE_BOXES = [
    ("page_boxes_active_2", C("offer", call.handle_list_boxes(CHAT, ["active", "2"]))),
    ("page_boxes_all_3", C("offer", call.handle_list_boxes(CHAT, ["all", "3"]))),
    ("page_boxes_offer_7_2", C("offer", call.handle_list_boxes(CHAT, ["7", "2"]))),
]


def _params(rows):
    return [pytest.param(data, effect, id=data) for data, effect in rows]


ADMIN_ONLY_ROWS = [row for row in WD + LC + ADMIN_PANEL + CMD + EDIT + PAGE_ADMIN if row[0] != "page_info"]


# --- behavior as the admin ----------------------------------------------------------------------------


class TestAdminDispatch:
    @pytest.mark.parametrize(
        "data, effect", _params(WD) + _params(LC) + _params(ADMIN_PANEL) + _params(CMD) + _params(EDIT)
    )
    def test_callback(self, data, effect):
        env = make_env()

        result = tap(env, data)

        assert_effect(env, effect, result)

    @pytest.mark.parametrize("data, effect", _params(PAGE_ADMIN + PAGE_BOXES))
    def test_pagination(self, data, effect):
        env = make_env()

        result = tap(env, data)

        assert_effect(env, effect, result)

    def test_a_missing_customer_in_user_orders_pagination_does_nothing(self):
        env = make_env()
        env.db.get_customer.return_value = None

        tap(env, f"page_user_orders_{CID}_2")

        assert all_handler_calls(env) == {}


class TestCustomerPagination:
    @pytest.mark.parametrize("data, effect", _params(PAGE_CUSTOMER))
    def test_an_approved_customer(self, data, effect):
        env = make_env()

        result = tap(env, data, user_id=CUSTOMER_ID)

        assert_effect(env, effect, result, chat=CUSTOMER_ID)


# --- authorization ------------------------------------------------------------------------------------


class TestAuthorization:
    @pytest.mark.parametrize("data", [pytest.param(d, id=d) for d, _ in ADMIN_ONLY_ROWS])
    @pytest.mark.parametrize("approved", [True, False], ids=["approved customer", "unapproved customer"])
    def test_non_admins_cannot_trigger_an_admin_callback(self, data, approved):
        env = make_env(approved=approved)

        result = tap(env, data, user_id=CUSTOMER_ID)

        assert result == {"status": "unauthorized"}
        assert all_handler_calls(env) == {}
        assert env.handler.edit_context_manager.mock_calls == []

    # page_info (the "3/7" indicator) is on the allow-list and does nothing, so there is nothing to refuse
    @pytest.mark.parametrize("data", [pytest.param(d, id=d) for d, _ in PAGE_CUSTOMER if d != "page_info"])
    def test_unapproved_customers_cannot_use_customer_callbacks_either(self, data):
        env = make_env(approved=False)

        result = tap(env, data, user_id=CUSTOMER_ID)

        assert result == {"status": "unauthorized"}
        assert all_handler_calls(env) == {}

    def test_the_customer_allowlist_covers_exactly_the_customer_pagination(self):
        for data, _ in PAGE_CUSTOMER:
            assert CUSTOMER_CALLBACK_PATTERN.match(data), data

    @pytest.mark.parametrize("data", [d for d, _ in ADMIN_ONLY_ROWS if d != "page_info"])
    def test_no_admin_callback_is_on_the_customer_allowlist(self, data):
        assert not CUSTOMER_CALLBACK_PATTERN.match(data), data


# --- the keyboard of the tapped message ----------------------------------------------------------------


class TestKeyboardRemoval:
    """After a tap the keyboard of the message is removed, except for navigation that keeps it"""

    KEEP = ["wd_sup:abc", "wd_back:suppliers", "page_info", "page_suppliers_active_2", "page_customers_all_2"]
    REMOVE = ["lc_sup:abc", "admin:main", "cmd:list_pending", "edit_offer_name_7", "admin_main", "cmd_list_pending"]

    @pytest.mark.parametrize("data", KEEP)
    def test_keyboard_stays(self, data):
        env = make_env()

        tap(env, data)

        env.handler._edit_message_remove_keyboard.assert_not_called()

    @pytest.mark.parametrize("data", REMOVE)
    def test_keyboard_is_removed(self, data):
        env = make_env()

        tap(env, data)

        env.handler._edit_message_remove_keyboard.assert_called_once_with(CHAT, 9)


# --- the route table itself -------------------------------------------------------------------------


class TestRouteTable:
    """The router takes the first pattern that matches, so a route can be dead because an earlier one shadows it"""

    MIGRATED = re.compile(r"^\^(wd_|lc_|admin|cmd|edit_|page_)")

    @staticmethod
    def _samples() -> list[str]:
        rows = WD + LC + ADMIN_PANEL + CMD + EDIT + PAGE_ADMIN + PAGE_BOXES + PAGE_CUSTOMER
        samples = [data for data, _ in rows] + _callback_literals()
        for param in ROUND_TRIPS:
            prefix, enhanced = param.values[0], param.values[1]
            keyboard = PaginationUtils.build_pagination_keyboard(3, 7, prefix, enhanced=enhanced)
            samples += [b["callback_data"] for row in keyboard["inline_keyboard"] for b in row]
        return samples

    def test_every_migrated_route_is_the_first_match_for_some_real_callback(self):
        routes = make_env().handler.router.routes
        first_matches = set()
        for data in self._samples():
            for regex, _, pattern in routes:
                if regex.match(data):
                    first_matches.add(pattern)
                    break

        migrated = [pattern for _, _, pattern in routes if self.MIGRATED.match(pattern)]
        assert len(migrated) > 90
        assert [pattern for pattern in migrated if pattern not in first_matches] == []

    def test_no_pattern_is_registered_twice(self):
        patterns = [pattern for _, _, pattern in make_env().handler.router.routes]

        assert len(patterns) == len(set(patterns))


# --- startup ----------------------------------------------------------------------------------------


class TestStartup:
    def test_the_handler_builds_with_all_its_routes(self):
        env = make_env()

        assert len(env.handler.router.routes) > 40
        assert all(regex.pattern for regex, _, _ in env.handler.router.routes)

    def test_unknown_data_is_reported_not_raised(self):
        env = make_env()

        assert tap(env, "completely_unknown_thing") == {"status": "unknown_callback"}
        assert all_handler_calls(env) == {}


# --- every pagination keyboard the bot builds must be dispatchable ---------------------------------------

# (entity prefix as passed to the keyboard builder, enhanced?, as who, expected call for page p)
ROUND_TRIPS = [
    pytest.param(
        "suppliers_active", False, ADMIN_ID, lambda p: C("supplier", call.handle_list_suppliers(CHAT, p, "active"))
    ),
    pytest.param(
        "suppliers_retired", False, ADMIN_ID, lambda p: C("supplier", call.handle_list_suppliers(CHAT, p, "retired"))
    ),
    pytest.param("customers_all", True, ADMIN_ID, lambda p: C("user", call.handle_list_users(CHAT, p, "all"))),
    pytest.param(
        "customers_approved", True, ADMIN_ID, lambda p: C("user", call.handle_list_users(CHAT, p, "approved"))
    ),
    pytest.param("guests", True, ADMIN_ID, lambda p: C("user", call.handle_list_guests(CHAT, p))),
    pytest.param(
        "process_payment", True, ADMIN_ID, lambda p: C("admin_order", call.handle_process_payment(CHAT, [], p))
    ),
    pytest.param(
        "remind_payment", True, ADMIN_ID, lambda p: C("admin_order", call.handle_send_payment_reminder(CHAT, [], p))
    ),
    pytest.param("changelog", False, ADMIN_ID, lambda p: C("changelog", call.handle_changelog(CHAT, ADMIN_ID, p))),
    pytest.param(
        f"user_orders_{CID}",
        True,
        ADMIN_ID,
        lambda p: C("admin_order", call.viewing._show_user_orders(CHAT, CUSTOMER_OBJ, p)),
    ),
    pytest.param(
        f"my_orders_{CUSTOMER_ID}",
        True,
        CUSTOMER_ID,
        lambda p: C("info", call.handle_list_my_orders(CUSTOMER_ID, CUSTOMER_ID, None, p)),
    ),
    pytest.param(
        "list_offers",
        True,
        CUSTOMER_ID,
        lambda p: C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, None, p)),
    ),
    pytest.param(
        "list_offers_active",
        True,
        CUSTOMER_ID,
        lambda p: C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, ["active"], p)),
    ),
    pytest.param(
        "list_offers_user",
        True,
        CUSTOMER_ID,
        lambda p: C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, ["user"], p)),
    ),
    pytest.param(
        "list_offers_soldout",
        True,
        CUSTOMER_ID,
        lambda p: C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, ["soldout"], p)),
    ),
    pytest.param(
        "list_offers_sold_out",
        True,
        CUSTOMER_ID,
        lambda p: C("info", call.handle_list_offers(CUSTOMER_ID, CUSTOMER_ID, ["sold_out"], p)),
    ),
    pytest.param(
        "boxes_active",
        True,
        ADMIN_ID,
        lambda p: C("offer", call.handle_list_boxes(CHAT, ["active", str(p)])),
    ),
    pytest.param(
        "boxes_offer_7",
        True,
        ADMIN_ID,
        lambda p: C("offer", call.handle_list_boxes(CHAT, ["7", str(p)])),
    ),
]


class TestPaginationRoundTrip:
    """Build the real keyboard, tap every button of it: each must reach the handler with the right page"""

    @pytest.mark.parametrize("prefix, enhanced, user_id, expected", ROUND_TRIPS)
    def test_every_button_of_the_keyboard_works(self, prefix, enhanced, user_id, expected):
        keyboard = PaginationUtils.build_pagination_keyboard(3, 7, prefix, enhanced=enhanced)
        buttons = [
            b["callback_data"] for row in keyboard["inline_keyboard"] for b in row if b["callback_data"] != "page_info"
        ]
        assert buttons, "the keyboard has no navigation buttons"

        for data in buttons:
            env = make_env()
            page = int(data.rsplit("_", 1)[-1])

            result = tap(env, data, user_id=user_id)

            assert_effect(env, expected(page), result, chat=user_id)


# --- every button the source builds must lead somewhere --------------------------------------------------

SRC = Path(__file__).resolve().parent.parent / "src"
LITERAL = re.compile(r'"callback_data":\s*(f?)"((?:[^"\\]|\\.)*)"')

# Callback prefix variable used by the shared delivery/labeling workflow builder
WORKFLOW_PREFIXES = ("wd", "lc")

# Buttons that are not routed on purpose. "Done" has no action: the tap removes the keyboard (the handler
# does that after every tap) and the dispatcher then reports "unknown", which is harmless.
NO_ACTION_BUTTONS = {"done_action"}

# pagination.py builds page_{prefix}_{n} for every list; those are covered by TestPaginationRoundTrip.
# validation.py builds {prefix}_{customer_id} for the disambiguation buttons; see TestDisambiguationButtons.
SKIPPED_FILES = {"pagination.py", "validation.py"}


UUID = "aaaaaaaa-1111-4111-8111-111111111111"  # what customer, order, box and supplier IDs look like for real
ID_STYLES = ("abc12345", UUID)  # an 8-character partial ID, and a full ID with hyphens


def _sample(expression: str, id_style: str) -> str:
    e = expression.lower()
    if "page" in e:
        return "2"
    if any(word in e for word in ("offer_id", "quantity", "units", "total", "count", "boxes")):
        return "7"
    return id_style


def _expand(text: str) -> list[str]:
    """Fill the placeholders of an f-string with plausible values (both workflow prefixes, short and full IDs)"""
    variants = [text]
    if "{callback_prefix}" in text:
        variants = [text.replace("{callback_prefix}", prefix) for prefix in WORKFLOW_PREFIXES]
    return [
        re.sub(r"\{([^}]*)\}", lambda m, style=style: _sample(m.group(1), style), variant)
        for variant in variants
        for style in ID_STYLES
    ]


def _callback_literals() -> list[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        if path.name in SKIPPED_FILES:
            continue
        for is_f, text in LITERAL.findall(path.read_text()):
            for expanded in _expand(text) if is_f else [text]:
                if expanded and "{" not in expanded:
                    found.add(expanded)
    return sorted(found)


UNKNOWN_STATUSES = {"unknown_callback", "unknown_edit", "unknown_pagination_type", "invalid_pagination", "error"}


class TestRoutesCallExistingMethods:
    def test_every_handler_method_that_a_route_calls_exists_on_the_real_class(self):
        """A route to a method that does not exist only fails when a button is tapped, and the error is just logged"""
        source = (SRC / "services" / "callback_handler.py").read_text()

        called = set(re.findall(r'self\.handlers\["(\w+)"\]\.(\w+)', source))

        assert len(called) > 50
        assert sorted(f"{key}.{method}" for key, method in called if method not in handler_mock_spec(key)) == []


class TestRoutesMatchRealIds:
    """Customer IDs are UUIDs, with hyphens. Routes that captured them with \\w+ never matched a real button."""

    @pytest.mark.parametrize(
        "data, expected",
        [
            (f"cancel_orders_page_{UUID}_2", call.handle_cancel_orders_page(CHAT, UUID, 2)),
            (f"order_for_offer_{UUID}_7", call.handle_create_order_for_offer_select(CHAT, UUID, "7")),
            (f"order_for_other_{UUID}_7", call.handle_create_order_for_other_quantity(CHAT, UUID, "7")),
            (f"order_for_quantity_{UUID}_7_2", call.handle_create_order_for_quantity_select(CHAT, UUID, "7", "2")),
            ("order_for_quantity_cust1_7_2", call.handle_create_order_for_quantity_select(CHAT, "cust1", "7", "2")),
        ],
        ids=["cancel page", "order_for offer", "order_for other", "order_for quantity", "short id"],
    )
    def test_the_button_reaches_its_handler_with_the_id_and_numbers(self, data, expected):
        env = make_env()

        tap(env, data)

        assert env.handlers["admin_order"].mock_calls == [expected]


class TestEveryBuiltButtonIsDispatched:
    def test_the_scan_finds_the_buttons(self):
        literals = _callback_literals()

        assert len(literals) > 60
        assert "admin:main" in literals and "cmd:list_pending" in literals
        assert "wd_sup:abc12345" in literals and "lc_sup:abc12345" in literals  # both workflow prefixes

    @pytest.mark.parametrize("data", [d for d in _callback_literals() if d not in NO_ACTION_BUTTONS])
    def test_button(self, data):
        env = make_env()

        result = tap(env, data)

        unknown_texts = {
            env.handler._t(key, ADMIN_ID) for key in ("unknown_callback", "unknown_edit", "invalid_format")
        }
        sent = [c.args[1] for c in env.handler._send_message.call_args_list]
        assert not set(sent) & unknown_texts, f"{data} ends in an 'unknown' message"
        if isinstance(result, dict):
            assert result.get("status") not in UNKNOWN_STATUSES, f"{data} -> {result}"

    def test_the_done_button_only_removes_the_keyboard(self):
        env = make_env()

        tap(env, "done_action")

        assert all_handler_calls(env) == {}
        env.handler._edit_message_remove_keyboard.assert_called_once_with(CHAT, 9)


# The prefix of a disambiguation button is chosen by the command that asks "which customer do you mean?"
DISAMBIGUATION_CALL = re.compile(r'find_customer_with_disambiguation\(\s*[^,()]+,\s*[^,()]+,\s*"([a-z_]+)"')


def _disambiguation_prefixes() -> list[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        found.update(DISAMBIGUATION_CALL.findall(path.read_text()))
    return sorted(found)


class TestDisambiguationButtons:
    def test_the_scan_finds_the_prefixes(self):
        prefixes = _disambiguation_prefixes()

        assert len(prefixes) >= 8
        assert {"approve_user_select", "delete_user_select", "edit_user_select"} <= set(prefixes)

    @pytest.mark.parametrize("prefix", _disambiguation_prefixes())
    def test_every_prefix_leads_to_a_handler(self, prefix):
        env = make_env()

        result = tap(env, f"{prefix}_{CID}")

        calls = all_handler_calls(env)
        assert calls, f"{prefix}_<id> reaches no handler: {result}"
        assert len(calls) == 1

    def test_the_csv_import_shows_no_buttons(self):
        """Nobody can answer 'which customer?' during an import: it refuses the file instead"""
        assert "import" not in _disambiguation_prefixes()
