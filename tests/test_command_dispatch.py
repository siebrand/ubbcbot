"""Characterization of command dispatch and of every entry point of a Telegram update.

These tests describe behavior, not structure. They must pass unchanged before and after the command dispatch
is centralized: each command is sent as the router receives it, and the test checks which handler method is
called with which arguments, for every kind of sender (admin, approved, not approved, unknown), chat (private,
group) and environment (test, prod).

Every handler is an autospec of the real class. A route to a method that does not exist, or with the wrong
number of arguments, therefore fails here instead of in production.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, create_autospec

import pytest

from handlers.admin.admin_commands import AdminCommandsHandler
from handlers.admin.credit_commands import CreditCommands
from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.import_handler import ImportHandler
from handlers.admin.labeling_commands import LabelingCommands
from handlers.admin.offer_commands import OfferCommands
from handlers.admin.order_commands import AdminOrderCommands
from handlers.admin.report_commands import ReportCommands
from handlers.admin.supplier_commands import SupplierCommands
from handlers.admin.test_commands import TestCommands as SetupDataCommands
from handlers.admin.user_commands import UserCommands
from handlers.admin.wholesale_delivery_commands import WholesaleDeliveryCommands
from handlers.customer.auth_commands import AuthCommands
from handlers.customer.changelog_commands import ChangelogCommands
from handlers.customer.credit_commands import CustomerCreditCommands
from handlers.customer.data_export_commands import DataExportCommands
from handlers.customer.info_commands import InfoCommands
from handlers.customer.order_commands import CustomerOrderCommands
from models.entities import AuthorizationStatus, Customer
from services.bot_service import BotService
from services.command_router import CommandRouter
from services.routing.command_table import COMMAND_ROUTES
from services.routing.edit_reply_table import ANSWER_ROUTES

ROOT = Path(__file__).resolve().parent.parent
ADMIN_ID = 15005473
APPROVED_ID = 4242
UNAUTHORIZED_ID = 5151
REJECTED_ID = 6161
UNKNOWN_ID = 7171
GROUP = -100123
MESSAGE_ID = 77

HANDLER_CLASSES = {
    "admin_commands": AdminCommandsHandler,
    "admin_order": AdminOrderCommands,
    "auth": AuthCommands,
    "changelog": ChangelogCommands,
    "credit": CreditCommands,
    "customer_credit": CustomerCreditCommands,
    "customer_order": CustomerOrderCommands,
    "data_export": DataExportCommands,
    "import": ImportHandler,
    "info": InfoCommands,
    "labeling": LabelingCommands,
    "offer": OfferCommands,
    "report": ReportCommands,
    "supplier": SupplierCommands,
    "test": SetupDataCommands,
    "user": UserCommands,
    "wholesale_delivery": WholesaleDeliveryCommands,
}

UNKNOWN_COMMAND = {"status": "unknown_command"}


# --- which chat a handler is given -----------------------------------------------------------------


class _Marker:
    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return self.name


T = _Marker("target chat")  # the chat itself, except in a production group: then the user's private chat
CH = _Marker("chat")  # always the chat the command came from
AD = _Marker("admin chat")  # the private chat of the admin, also when the command came from a group
P = _Marker("private chat")  # the sender's private chat
U = _Marker("user")  # the sender
ARGS = _Marker("arguments")  # the words after the command
ARGS_OR_NONE = _Marker("arguments or None")


@dataclass(frozen=True)
class Row:
    text: str
    key: str
    method: str
    args: tuple
    admin: bool

    @property
    def command(self) -> str:
        return self.text.split()[0]


def customer_row(text, key, method, *args) -> Row:
    return Row(text, key, method, args, admin=False)


def admin_row(text, key, method, *args) -> Row:
    return Row(text, key, method, args, admin=True)


def where(chat_id: int, user_id: int, environment: str) -> SimpleNamespace:
    group = chat_id < 0
    return SimpleNamespace(
        chat=chat_id,
        user=user_id,
        group=group,
        target=chat_id if not group or environment == "test" else user_id,
        admin=user_id if group else chat_id,
        private=user_id if group else chat_id,
    )


def resolve(row: Row, place: SimpleNamespace) -> tuple:
    rest = row.text.split()[1:]
    values = {T: place.target, CH: place.chat, AD: place.admin, P: place.private, U: place.user}
    resolved = []
    for arg in row.args:
        if arg is ARGS:
            resolved.append(rest)
        elif arg is ARGS_OR_NONE:
            resolved.append(rest or None)
        elif isinstance(arg, _Marker):
            resolved.append(values[arg])
        else:
            resolved.append(arg)
    return tuple(resolved)


# --- every command ----------------------------------------------------------------------------------

CUSTOMER_COMMANDS = [
    customer_row("/start", "info", "handle_start", T, U, ARGS),
    customer_row("/start something", "info", "handle_start", T, U, ARGS),
    customer_row("/help orders", "info", "handle_help", T, U, ARGS),
    customer_row("/privacy", "info", "handle_privacy", T, U, ARGS),
    customer_row("/create_order 7 2", "customer_order", "handle_create_order", CH, U, ARGS),
    customer_row("/order 7 2", "customer_order", "handle_create_order", CH, U, ARGS),
    customer_row("/list_my_orders 3", "info", "handle_list_my_orders", T, U, ARGS),
    customer_row("/my_orders", "info", "handle_list_my_orders", T, U, ARGS),
    customer_row("/list_offers sold_out", "info", "handle_list_offers", T, U, ARGS),
    customer_row("/subscribe", "info", "handle_subscribe", T, U),
    customer_row("/unsubscribe", "info", "handle_unsubscribe", T, U),
    customer_row("/view_offer 7", "info", "handle_view_offer", T, U, ARGS),
    customer_row("/confirm_order 7 2", "customer_order", "handle_confirm_order", CH, U, ARGS),
    customer_row("/delete_cancelled_orders", "customer_order", "handle_delete_cancelled_orders", T, U),
    customer_row("/delete_completed_orders", "customer_order", "handle_delete_completed_orders", T, U),
    customer_row("/payment_info", "customer_order", "handle_payment_info", T, U),
    customer_row("/changelog", "changelog", "handle_changelog", T, U, 1),
    customer_row("/cancel", "info", "_send_success", P, "nothing_to_cancel", "nothing_to_cancel"),
    customer_row("/fomo", "info", "handle_fomo", T, U, ARGS_OR_NONE),
    customer_row("/fomo someone", "info", "handle_fomo", T, U, ARGS_OR_NONE),
    customer_row("/my_credit", "customer_credit", "handle_my_credit", T, U),
    customer_row("/my_data", "data_export", "handle_my_data", U),
]

ADMIN_COMMANDS = [
    admin_row("/setup_test_data", "test", "handle_setup_test_data", AD),
    admin_row("/test_user_message 42 hello there", "test", "handle_test_user_message", AD, ARGS),
    admin_row("/create_supplier Acme Bier", "supplier", "handle_create_supplier", AD, ARGS),
    admin_row("/archive_supplier Acme", "supplier", "handle_archive_supplier", AD, ARGS),
    admin_row("/list_suppliers", "supplier", "handle_list_suppliers", AD, 1, "active"),
    admin_row("/list_suppliers retired", "supplier", "handle_list_suppliers", AD, 1, "retired"),
    admin_row("/list_suppliers all", "supplier", "handle_list_suppliers", AD, 1, "all"),
    admin_row("/list_suppliers bogus", "supplier", "handle_list_suppliers", AD, 1, "active"),
    admin_row("/update_supplier Acme", "supplier", "handle_update_supplier", AD, ARGS),
    admin_row("/update_supplier_name s1 New", "supplier", "handle_update_supplier_name", AD, ARGS),
    admin_row("/update_supplier_contact s1 a@b.c", "supplier", "handle_update_supplier_contact", AD, ARGS),
    admin_row(
        "/update_supplier_full_name s1 Acme Brewery BV", "supplier", "handle_update_supplier_full_name", AD, ARGS
    ),
    admin_row("/create_offer Acme Pils 2.5 24", "offer", "handle_create_offer", AD, ARGS),
    admin_row("/cancel_offer 7", "offer", "handle_cancel_offer", AD, ARGS),
    admin_row("/instant_order DeMolen Tripel 3.50 Jan 4", "offer", "handle_instant_order", AD, ARGS),
    admin_row("/create_box 7", "offer", "handle_create_box", AD, ARGS),
    admin_row("/list_boxes active 2", "offer", "handle_list_boxes", AD, ARGS),
    admin_row("/audit_offer 7", "offer", "handle_audit_offer", AD, ARGS),
    admin_row("/refill_boxes 7", "offer", "handle_refill_boxes", AD, ARGS),
    admin_row("/process_wholesale 7", "offer", "handle_process_wholesale", AD, ARGS),
    admin_row("/confirm_process_wholesale 7 2", "offer", "handle_confirm_process_wholesale", AD, ARGS),
    admin_row("/update_offer_name 7 New", "offer", "handle_update_offer_name", AD, ARGS),
    admin_row("/update_offer_price 7 3.5", "offer", "handle_update_offer_price", AD, ARGS),
    admin_row("/update_offer_description 7 Nice", "offer", "handle_update_offer_description", AD, ARGS),
    admin_row("/offer_status 7 import", "offer", "handle_offer_status", AD, ARGS),
    admin_row("/import_orders", "import", "handle_import_orders", AD, U),
    admin_row("/finalize_import 7", "import", "handle_finalize_import", AD, ARGS),
    admin_row("/publish_offer 7", "offer", "handle_publish_offer", AD, ARGS),
    admin_row("/delete_offer 7", "offer", "handle_delete_offer", AD, ARGS),
    admin_row("/create_order_for jan 7 2", "admin_order", "handle_create_order_for", AD, U, ARGS),
    admin_row("/order_for jan 7 2", "admin_order", "handle_create_order_for", AD, U, ARGS),
    admin_row("/cancel_order abc12345", "admin_order", "handle_cancel_order", AD, ARGS),
    admin_row("/edit_order abc12345", "admin_order", "handle_edit_order", AD, ARGS),
    admin_row("/list_user_orders jan", "admin_order", "handle_list_user_orders", AD, ARGS),
    admin_row("/list_offer_orders 7", "admin_order", "handle_list_offer_orders", AD, ARGS),
    admin_row("/export_orders all", "admin_order", "handle_export_orders", AD, ARGS),
    admin_row("/list_pending", "user", "handle_list_pending", AD),
    admin_row("/approve_user jan", "user", "handle_approve_user", AD, ARGS),
    admin_row("/reject_user jan", "user", "handle_reject_user", AD, ARGS),
    admin_row("/user_status jan", "user", "handle_user_status", AD, ARGS),
    admin_row("/update_user jan Jan Jansen", "user", "handle_update_user", AD, ARGS),
    admin_row("/delete_user jan", "user", "handle_delete_user", AD, ARGS),
    admin_row("/export_user_data jan", "data_export", "handle_export_user_data", AD, ARGS),
    admin_row("/clear_data_export jan", "data_export", "handle_clear_data_export", AD, ARGS),
    admin_row("/update_user_first_name c1 Jan", "user", "handle_update_user_first_name", AD, ARGS),
    admin_row("/update_user_last_name c1 Jansen", "user", "handle_update_user_last_name", AD, ARGS),
    admin_row("/list_users", "user", "handle_list_users", AD, 1, "all", None),
    admin_row("/list_users approved", "user", "handle_list_users", AD, 1, "approved", None),
    admin_row("/list_users subscribers jan", "user", "handle_list_users", AD, 1, "subscribers", "jan"),
    admin_row("/list_users jan de vries", "user", "handle_list_users", AD, 1, "all", "jan de vries"),
    admin_row("/create_guest Piet Puk contact", "user", "handle_create_guest", AD, ARGS),
    admin_row("/list_guests", "user", "handle_list_guests", AD),
    admin_row("/process_delivery", "wholesale_delivery", "handle_process_delivery", AD, U, ARGS),
    admin_row("/process_labeling", "labeling", "handle_process_labeling", AD, U, ARGS),
    admin_row("/send_delivery_overviews", "admin_order", "handle_send_delivery_overviews", AD, ARGS),
    admin_row("/process_payment", "admin_order", "handle_process_payment", AD, ARGS),
    admin_row("/send_payment_reminder", "admin_order", "handle_send_payment_reminder", AD, ARGS),
    admin_row("/failed_notifications", "admin_order", "handle_failed_notifications", AD, ARGS),
    admin_row("/delete_old_orders", "admin_order", "handle_delete_old_orders", AD),
    admin_row("/audit_orders", "admin_order", "handle_audit_orders", AD),
    admin_row("/admin", "admin_commands", "handle_admin", AD, U),
    admin_row("/credit jan 5 reason", "credit", "handle_credit", AD, ARGS),
    admin_row("/report_top_customers 2026", "report", "handle_report_top_customers", AD, ARGS),
    admin_row("/report_sales_by_period 2026 week", "report", "handle_report_sales_by_period", AD, ARGS),
    admin_row("/report_customer jan 2026", "report", "handle_report_customer", AD, ARGS),
]

CORPUS = CUSTOMER_COMMANDS + ADMIN_COMMANDS
NOT_FOMO = [row for row in CORPUS if row.command != "/fomo"]
CUSTOMER_NOT_FOMO = [row for row in CUSTOMER_COMMANDS if row.command != "/fomo"]
NOT_START = [row for row in CORPUS if row.command != "/start"]

# Commands that the router answers differently from a plain "call one handler method"
SPECIAL_COMMANDS = {"/fomo", "/cancel", "/start"}

# In a production group only these commands are answered there. Ordering is not one of them: the bot cannot
# send the customer's confirmation or an error to a production group, so /order and /confirm_order are
# redirected to the private chat.
GROUP_ALLOWED_IN_PROD = {"/start", "/fomo"}

# --- harness ----------------------------------------------------------------------------------------


_SPECS: dict = {}


def _handlers() -> dict:
    """Autospecs are slow to build: build them once and reset them for every test"""
    if not _SPECS:
        _SPECS.update({key: create_autospec(cls, instance=True) for key, cls in HANDLER_CLASSES.items()})
    for handler in _SPECS.values():
        handler.reset_mock()
    return _SPECS


def make_router(environment: str = "test"):
    handlers = _handlers()
    customers = {
        APPROVED_ID: AuthorizationStatus.APPROVED.value,
        UNAUTHORIZED_ID: AuthorizationStatus.UNAUTHORIZED.value,
        REJECTED_ID: AuthorizationStatus.REJECTED.value,
    }
    db = Mock()
    db.get_customer_by_telegram_id.side_effect = lambda user_id: (
        Customer(telegram_user_id=user_id, authorization_status=customers[user_id]) if user_id in customers else None
    )
    db.get_edit_context_by_chat_id.return_value = None

    router = CommandRouter(db, ADMIN_ID, environment, handlers)
    router._base_handler = Mock()
    router._base_handler._t.side_effect = lambda key, **kwargs: key
    return SimpleNamespace(router=router, handlers=handlers, db=db, base=router._base_handler)


def send(env, text: str, user_id: int = ADMIN_ID, chat_id: int | None = None):
    return env.router.route_command(user_id if chat_id is None else chat_id, user_id, text, MESSAGE_ID)


def handler_calls(env) -> list[tuple[str, str]]:
    return [(key, call[0]) for key, handler in env.handlers.items() for call in handler.mock_calls]


def assert_only_call(env, row: Row, place: SimpleNamespace):
    assert handler_calls(env) == [(row.key, row.method)], f"{row.text}: unexpected handler calls"
    getattr(env.handlers[row.key], row.method).assert_called_once_with(*resolve(row, place))


def assert_no_handler_called(env):
    assert handler_calls(env) == []


def ids(rows):
    return [row.text for row in rows]


# --- the corpus, as the right sender ---------------------------------------------------------------


class TestRouting:
    @pytest.mark.parametrize("row", CORPUS, ids=ids(CORPUS))
    def test_admin_in_private_chat(self, row):
        env = make_router()

        send(env, row.text)

        assert_only_call(env, row, where(ADMIN_ID, ADMIN_ID, "test"))

    @pytest.mark.parametrize("row", CUSTOMER_COMMANDS, ids=ids(CUSTOMER_COMMANDS))
    def test_approved_customer_in_private_chat(self, row):
        env = make_router()

        send(env, row.text, APPROVED_ID)

        assert_only_call(env, row, where(APPROVED_ID, APPROVED_ID, "test"))

    @pytest.mark.parametrize("row", NOT_FOMO, ids=ids(NOT_FOMO))
    @pytest.mark.parametrize("environment", ["test", "prod"])
    def test_admin_in_a_group(self, row, environment):
        env = make_router(environment)

        result = send(env, row.text, ADMIN_ID, GROUP)

        place = where(GROUP, ADMIN_ID, environment)
        if environment == "prod" and row.command not in GROUP_ALLOWED_IN_PROD:
            assert result == {"status": "redirected_to_pm"}
            assert_no_handler_called(env)
        else:
            assert_only_call(env, row, place)

    @pytest.mark.parametrize("row", CUSTOMER_NOT_FOMO, ids=ids(CUSTOMER_NOT_FOMO))
    @pytest.mark.parametrize("environment", ["test", "prod"])
    def test_approved_customer_in_a_group(self, row, environment):
        env = make_router(environment)

        result = send(env, row.text, APPROVED_ID, GROUP)

        if environment == "prod" and row.command not in GROUP_ALLOWED_IN_PROD:
            assert result == {"status": "redirected_to_pm"}
            assert_no_handler_called(env)
        else:
            assert_only_call(env, row, where(GROUP, APPROVED_ID, environment))


# --- authorization: who may use which command -------------------------------------------------------


class TestAuthorization:
    @pytest.mark.parametrize("row", ADMIN_COMMANDS, ids=ids(ADMIN_COMMANDS))
    def test_admin_commands_are_refused_for_an_approved_customer(self, row):
        env = make_router()

        result = send(env, row.text, APPROVED_ID)

        assert result == UNKNOWN_COMMAND
        assert_no_handler_called(env)

    @pytest.mark.parametrize("row", ADMIN_COMMANDS, ids=ids(ADMIN_COMMANDS))
    @pytest.mark.parametrize("environment", ["test", "prod"])
    def test_admin_commands_are_refused_for_an_approved_customer_in_a_group(self, row, environment):
        env = make_router(environment)

        result = send(env, row.text, APPROVED_ID, GROUP)

        assert result in (UNKNOWN_COMMAND, {"status": "redirected_to_pm"})
        assert_no_handler_called(env)

    @pytest.mark.parametrize(
        "sender", [UNAUTHORIZED_ID, REJECTED_ID, UNKNOWN_ID], ids=["unauthorized", "rejected", "unknown"]
    )
    @pytest.mark.parametrize(
        "row", [r for r in CORPUS if r.command != "/start"], ids=[r.text for r in CORPUS if r.command != "/start"]
    )
    def test_no_command_works_for_someone_who_is_not_approved(self, row, sender):
        env = make_router()

        result = send(env, row.text, sender)

        assert result == {"status": "unauthorized"}
        assert_no_handler_called(env)
        env.base._send_message.assert_called_once_with(sender, "unauthorized")

    @pytest.mark.parametrize(
        "sender", [UNAUTHORIZED_ID, REJECTED_ID, UNKNOWN_ID], ids=["unauthorized", "rejected", "unknown"]
    )
    def test_start_is_the_only_command_for_someone_who_is_not_approved(self, sender):
        env = make_router()

        send(env, "/start", sender)

        env.handlers["auth"].handle_unauthorized_start.assert_called_once_with(sender)
        assert handler_calls(env) == [("auth", "handle_unauthorized_start")]

    @pytest.mark.parametrize("sender", [UNAUTHORIZED_ID, UNKNOWN_ID], ids=["unauthorized", "unknown"])
    def test_start_with_a_deep_link_does_not_get_past_the_check(self, sender):
        env = make_router()

        send(env, "/start create_order_7_2", sender)

        assert handler_calls(env) == [("auth", "handle_unauthorized_start")]

    @pytest.mark.parametrize("sender", [UNAUTHORIZED_ID, UNKNOWN_ID], ids=["unauthorized", "unknown"])
    @pytest.mark.parametrize("environment", ["test", "prod"])
    def test_not_approved_in_a_group_is_answered_in_the_group_in_test_and_privately_in_prod(self, sender, environment):
        env = make_router(environment)

        send(env, "/start", sender, GROUP)
        env.handlers["auth"].handle_unauthorized_start.assert_called_once_with(
            GROUP if environment == "test" else sender
        )

        env.base._send_message.reset_mock()
        send(env, "/fomo", sender, GROUP)
        env.base._send_message.assert_called_once_with(GROUP if environment == "test" else sender, "unauthorized")
        assert handler_calls(env) == [("auth", "handle_unauthorized_start")]

    @pytest.mark.parametrize("row", CORPUS, ids=ids(CORPUS))
    @pytest.mark.parametrize("sender", [UNAUTHORIZED_ID, UNKNOWN_ID], ids=["unauthorized", "unknown"])
    def test_not_approved_in_a_production_group_is_redirected_not_served(self, row, sender):
        env = make_router("prod")

        result = send(env, row.text, sender, GROUP)

        if row.command == "/start":  # allowed in a group: the welcome for people who are not approved
            assert handler_calls(env) == [("auth", "handle_unauthorized_start")]
        else:
            assert result["status"] in ("redirected_to_pm", "unauthorized")
            assert_no_handler_called(env)

    def test_the_admin_is_never_looked_up_in_the_customer_table(self):
        env = make_router()

        send(env, "/help")

        env.db.get_customer_by_telegram_id.assert_not_called()

    @pytest.mark.parametrize("row", CORPUS, ids=ids(CORPUS))
    def test_a_lookalike_of_the_admin_id_is_not_the_admin(self, row):
        env = make_router()

        send(env, row.text, ADMIN_ID + 1)

        # The only thing a stranger gets from /start is the "not approved" welcome
        assert handler_calls(env) in ([], [("auth", "handle_unauthorized_start")])
        assert row.command == "/start" or handler_calls(env) == []

    def test_the_group_prefixes_of_admin_commands_do_not_make_them_public(self):
        """A bot mention and upper case do not change who may run a command"""
        env = make_router()

        for text in ("/CREDIT@ubbc_bot jan 5 x", "/Admin", "/approve_user@ubbc_bot jan"):
            assert send(env, text, APPROVED_ID) == UNKNOWN_COMMAND
        assert_no_handler_called(env)


# --- special cases -----------------------------------------------------------------------------------


class TestSpecialCases:
    def test_an_unknown_command_is_reported(self):
        env = make_router()

        assert send(env, "/nonsense") == UNKNOWN_COMMAND
        assert_no_handler_called(env)

    @pytest.mark.parametrize("text", ["/LIST_OFFERS", "/List_Offers@ubbc_bot", "/list_offers@ubbc_bot x"])
    def test_case_and_bot_mention_are_ignored(self, text):
        env = make_router()

        send(env, text, APPROVED_ID)

        assert handler_calls(env) == [("info", "handle_list_offers")]

    @pytest.mark.parametrize(
        "alias, command",
        [("/order", "/create_order"), ("/my_orders", "/list_my_orders"), ("/order_for", "/create_order_for")],
    )
    def test_aliases_run_the_same_handler(self, alias, command):
        alias_env, command_env = make_router(), make_router()

        send(alias_env, f"{alias} 7 2")
        send(command_env, f"{command} 7 2")

        assert handler_calls(alias_env) == handler_calls(command_env) != []
        assert alias_env.handlers["info"].mock_calls == command_env.handlers["info"].mock_calls

    def test_fomo_in_a_group_reacts_and_answers_privately(self):
        env = make_router("prod")

        send(env, "/fomo jan", APPROVED_ID, GROUP)

        env.handlers["info"]._set_message_reaction.assert_called_once_with(GROUP, MESSAGE_ID, "👍")
        env.handlers["info"].handle_fomo.assert_called_once_with(APPROVED_ID, APPROVED_ID, ["jan"])

    def test_fomo_in_a_group_without_arguments_passes_none(self):
        env = make_router("test")

        send(env, "/fomo", APPROVED_ID, GROUP)

        env.handlers["info"].handle_fomo.assert_called_once_with(APPROVED_ID, APPROVED_ID, None)

    def test_fomo_in_a_group_is_for_approved_users_only(self):
        env = make_router("test")

        send(env, "/fomo", UNAUTHORIZED_ID, GROUP)

        env.handlers["info"].handle_fomo.assert_not_called()
        env.handlers["info"]._set_message_reaction.assert_not_called()

    @pytest.mark.parametrize(
        "payload, key, method, args",
        [
            ("create_order_7_2", "customer_order", "handle_create_order", (APPROVED_ID, APPROVED_ID, ["7", "2"])),
            ("confirm_7_2", "customer_order", "handle_confirm_order", (APPROVED_ID, APPROVED_ID, ["7", "2"])),
            ("help_orders", "info", "handle_help", (APPROVED_ID, APPROVED_ID, ["orders"])),
            ("view_offer_7", "info", "handle_view_offer", (APPROVED_ID, APPROVED_ID, ["7"])),
        ],
    )
    def test_start_deep_links(self, payload, key, method, args):
        env = make_router()

        send(env, f"/start {payload}", APPROVED_ID)

        assert handler_calls(env) == [(key, method)]
        getattr(env.handlers[key], method).assert_called_once_with(*args)

    @pytest.mark.parametrize("payload", ["create_order_7", "confirm_x", "create_order_1_2_3"])
    def test_a_malformed_deep_link_falls_back_to_a_normal_start(self, payload):
        env = make_router()

        send(env, f"/start {payload}", APPROVED_ID)

        env.handlers["info"].handle_start.assert_called_once_with(APPROVED_ID, APPROVED_ID, [payload])

    def test_deep_links_in_a_production_group_are_answered_privately(self):
        env = make_router("prod")

        send(env, "/start help_orders", APPROVED_ID, GROUP)

        env.handlers["info"].handle_help.assert_called_once_with(APPROVED_ID, APPROVED_ID, ["orders"])


class TestCancelCommand:
    def test_an_admin_with_a_pending_prompt_clears_it(self):
        env = make_router()
        env.db.get_edit_context_by_chat_id.return_value = SimpleNamespace(
            edit_type="offer_name", entity_id="7", context_id="ctx"
        )

        send(env, "/cancel")

        env.db.delete_edit_context.assert_called_once_with("ctx")
        env.handlers["info"]._send_success.assert_called_once_with(ADMIN_ID, "operation_cancelled", "cancelled")

    def test_cancelling_an_image_upload_returns_to_the_offer(self):
        env = make_router()
        env.db.get_edit_context_by_chat_id.return_value = SimpleNamespace(
            edit_type="offer_image_upload", entity_id="7", context_id="ctx"
        )

        send(env, "/cancel")

        env.handlers["offer"].handle_edit_offer_interface.assert_called_once_with(ADMIN_ID, "7")

    def test_a_customer_never_clears_a_prompt(self):
        env = make_router()
        env.db.get_edit_context_by_chat_id.return_value = SimpleNamespace(
            edit_type="offer_name", entity_id="7", context_id="ctx"
        )

        send(env, "/cancel", APPROVED_ID)

        env.db.delete_edit_context.assert_not_called()
        env.handlers["info"]._send_success.assert_called_once_with(
            APPROVED_ID, "nothing_to_cancel", "nothing_to_cancel"
        )

    def test_in_a_group_the_prompt_of_the_private_chat_is_cleared(self):
        env = make_router()

        send(env, "/cancel", ADMIN_ID, GROUP)

        env.db.get_edit_context_by_chat_id.assert_called_once_with(ADMIN_ID)

    def test_an_error_is_reported(self):
        env = make_router()
        env.db.get_edit_context_by_chat_id.side_effect = RuntimeError("boom")

        send(env, "/cancel")

        env.handlers["info"]._send_error.assert_called_once_with(ADMIN_ID, "cancel_failed", "error")


# --- nothing is missing from the table above ----------------------------------------------------------


def _routed_commands() -> set[str]:
    return set(COMMAND_ROUTES) | {"/" + alias for alias in CommandRouter.PERMANENT_ALIASES}


def _commands_offered_in_telegram() -> set[str]:
    menus = json.loads((ROOT / "telegram-commands.json").read_text())
    return {"/" + entry["command"] for menu in menus.values() for entry in menu}


class TestCompleteness:
    def test_the_table_has_the_commands(self):
        assert len(_routed_commands()) > 60
        assert {"/start", "/create_order", "/credit", "/order"} <= _routed_commands()

    def test_every_routed_command_has_a_row_in_the_table(self):
        """A new command must be added to this table, as customer or admin command, with its authorization"""
        in_table = {row.command for row in CORPUS}

        assert sorted(_routed_commands() - in_table) == []

    def test_every_row_is_a_routed_command(self):
        assert sorted({row.command for row in CORPUS} - _routed_commands()) == []

    def test_every_command_in_the_telegram_menu_is_routed(self):
        env = make_router()
        offered = _commands_offered_in_telegram()

        unrouted = sorted(command for command in offered if send(env, f"{command} 1 1") == UNKNOWN_COMMAND)

        assert len(offered) > 60  # the menus were found
        assert unrouted == []

    @pytest.mark.parametrize("command", sorted(COMMAND_ROUTES))
    def test_every_route_points_to_a_method_that_exists(self, command):
        """Also for commands that no row above exercises with every argument shape"""
        route = COMMAND_ROUTES[command]
        target = CommandRouter if route.handler is None else HANDLER_CLASSES[route.handler]

        assert callable(getattr(target, route.method, None)), f"{command} -> {route.handler}.{route.method}"

    def test_the_admin_flag_of_every_command_matches_the_table_above(self):
        flags = {row.command: row.admin for row in CORPUS}

        assert {command: route.admin_only for command, route in COMMAND_ROUTES.items()} == {
            command: flags[command] for command in COMMAND_ROUTES
        }

    def test_the_router_has_no_command_of_its_own_outside_the_table(self):
        """Commands are added to the table, never as a branch in the router: that keeps the check in one place"""
        source = (ROOT / "src" / "services" / "command_router.py").read_text()

        assert sorted(set(re.findall(r'command == "(/[a-z_]+)"', source))) == ["/fomo", "/start"]


# --- every way an update enters the bot ---------------------------------------------------------------


def make_bot(approved_customer_ids=(APPROVED_ID,)):
    bot = BotService.__new__(BotService)
    bot.admin_user_id = ADMIN_ID
    bot.db = Mock()
    bot.db.mark_update_processed.return_value = True
    bot.db.get_edit_context_by_chat_id.return_value = None
    bot.callback_handler = Mock()
    bot.command_router = Mock()
    bot.import_handler = Mock()
    bot.media_handler = Mock()
    bot._expire_exports_on_admin_update = Mock()
    bot._register_customer_if_needed = Mock()
    bot._handle_edit_reply = Mock(return_value={"status": "edit_reply"})
    return bot


def message_update(user_id: int, chat_id: int | None = None, update_id: int = 1, **fields):
    message = {"message_id": 9, "from": {"id": user_id}, "chat": {"id": user_id if chat_id is None else chat_id}}
    message.update(fields)
    return {"update_id": update_id, "message": message}


def prompt(edit_type: str = "offer_name"):
    return SimpleNamespace(edit_type=edit_type, entity_id="7", context_id="ctx")


class TestUpdateEntryPoints:
    def test_a_repeated_update_is_skipped_before_anything_else(self):
        bot = make_bot()
        bot.db.mark_update_processed.return_value = False

        result = bot.process_update(message_update(ADMIN_ID, text="/admin"))

        assert result == {"status": "duplicate"}
        bot.command_router.route_command.assert_not_called()
        bot._register_customer_if_needed.assert_not_called()

    def test_an_update_without_message_or_callback_is_ignored(self):
        bot = make_bot()

        assert bot.process_update({"update_id": 2, "edited_message": {}}) == {"status": "ignored"}

    def test_a_button_goes_to_the_callback_handler_only(self):
        bot = make_bot()
        query = {"id": "q", "from": {"id": APPROVED_ID}, "data": "x"}

        bot.process_update({"update_id": 3, "callback_query": query})

        bot.callback_handler.handle_callback_query.assert_called_once_with(query)
        bot.command_router.route_command.assert_not_called()

    def test_a_command_goes_to_the_router_with_chat_user_text_and_message_id(self):
        bot = make_bot()

        bot.process_update(message_update(APPROVED_ID, GROUP, text="/list_offers"))

        bot.command_router.route_command.assert_called_once_with(GROUP, APPROVED_ID, "/list_offers", 9)

    def test_every_message_registers_its_sender(self):
        bot = make_bot()

        bot.process_update(message_update(UNKNOWN_ID, text="/start"))

        bot._register_customer_if_needed.assert_called_once_with({"id": UNKNOWN_ID})

    def test_an_exception_is_reported_not_raised(self):
        bot = make_bot()
        bot.command_router.route_command.side_effect = RuntimeError("boom")

        result = bot.process_update(message_update(ADMIN_ID, text="/admin"))

        assert result == {"status": "error", "error": "RuntimeError"}

    # --- documents (CSV import) ---

    def test_a_document_from_the_admin_goes_to_the_import(self):
        bot = make_bot()

        bot.process_update(message_update(ADMIN_ID, document={"file_id": "f1", "file_name": "orders.csv"}))

        bot.import_handler.handle_document_upload.assert_called_once_with(ADMIN_ID, ADMIN_ID, "f1", "orders.csv")

    def test_a_document_from_anyone_else_is_not_imported(self):
        bot = make_bot()

        for sender in (APPROVED_ID, UNAUTHORIZED_ID, UNKNOWN_ID):
            result = bot.process_update(message_update(sender, document={"file_id": "f1", "file_name": "orders.csv"}))
            assert result == {"status": "processed"}

        bot.import_handler.handle_document_upload.assert_not_called()

    # --- replies to a prompt (edit contexts) ---

    def test_an_admin_reply_in_the_private_chat_answers_the_prompt(self):
        bot = make_bot()
        bot.db.get_edit_context_by_chat_id.return_value = prompt()

        result = bot.process_update(message_update(ADMIN_ID, text="New name"))

        assert result == {"status": "edit_reply"}
        bot._handle_edit_reply.assert_called_once()
        bot.db.get_edit_context_by_chat_id.assert_called_once_with(ADMIN_ID)

    def test_a_message_in_a_group_never_answers_a_prompt(self):
        bot = make_bot()
        bot.db.get_edit_context_by_chat_id.return_value = prompt()

        result = bot.process_update(message_update(ADMIN_ID, GROUP, text="New name"))

        assert result == {"status": "processed"}
        bot.db.get_edit_context_by_chat_id.assert_not_called()
        bot._handle_edit_reply.assert_not_called()

    @pytest.mark.parametrize("sender", [APPROVED_ID, UNAUTHORIZED_ID, REJECTED_ID, UNKNOWN_ID])
    def test_nobody_but_the_admin_answers_a_prompt(self, sender):
        bot = make_bot()
        bot.db.get_edit_context_by_chat_id.return_value = prompt()

        result = bot.process_update(message_update(sender, text="New name"))

        assert result == {"status": "processed"}
        bot.db.get_edit_context_by_chat_id.assert_not_called()
        bot._handle_edit_reply.assert_not_called()

    def test_without_a_prompt_a_plain_message_is_not_processed_further(self):
        bot = make_bot()

        assert bot.process_update(message_update(ADMIN_ID, text="hello")) == {"status": "processed"}
        bot._handle_edit_reply.assert_not_called()

    # --- photos for an offer ---

    def test_a_photo_from_the_admin_answers_the_image_prompt(self):
        bot = make_bot()
        bot.db.get_edit_context_by_chat_id.return_value = prompt("offer_image_upload")

        bot.process_update(message_update(ADMIN_ID, photo=[{"file_id": "p"}], media_group_id="g1"))

        bot._handle_edit_reply.assert_called_once()
        bot.db.get_edit_context_by_chat_id.assert_called_once_with(ADMIN_ID)

    @pytest.mark.parametrize("sender", [APPROVED_ID, UNAUTHORIZED_ID, UNKNOWN_ID])
    def test_a_photo_from_anyone_else_is_ignored(self, sender):
        bot = make_bot()
        bot.db.get_edit_context_by_chat_id.return_value = prompt("offer_image_upload")

        bot.process_update(message_update(sender, photo=[{"file_id": "p"}], media_group_id="g1"))

        bot.media_handler.handle_media_group_image.assert_not_called()
        bot._handle_edit_reply.assert_not_called()

    def test_a_photo_in_a_group_is_ignored(self):
        bot = make_bot()
        bot.db.get_edit_context_by_chat_id.return_value = prompt("offer_image_upload")

        bot.process_update(message_update(ADMIN_ID, GROUP, photo=[{"file_id": "p"}], media_group_id="g1"))

        bot.media_handler.handle_media_group_image.assert_not_called()
        bot._handle_edit_reply.assert_not_called()


X = _Marker("the typed text")
E = _Marker("the entity of the prompt")


class TestEditReplyTypes:
    """The reply to a prompt goes to the handler that ANSWER_ROUTES names for the type of the prompt. Every
    handler is an autospec of the real class, so a route to a missing method or with the wrong arguments fails."""

    # prompt type: (handler, method, arguments after the chat)
    EXPECTED = {
        "create_supplier_name": ("supplier", "create_supplier", (X,)),
        "supplier_name": ("supplier", "handle_update_supplier_name", ([E, X],)),
        "supplier_contact": ("supplier", "handle_update_supplier_contact", ([E, X],)),
        "supplier_full_name": ("supplier", "handle_update_supplier_full_name", ([E, X],)),
        "offer_name": ("offer", "handle_update_offer_name", ([E, X],)),
        "offer_price": ("offer", "handle_update_offer_price", ([E, X],)),
        "offer_description": ("offer", "handle_offer_description_answer", (E, X, [])),
        "custom_wholesale_quantity": ("offer", "handle_custom_wholesale_quantity_answer", (E, X)),
        "instant_order_name": ("offer", "handle_instant_order_name_answer", (E, X)),
        "instant_order_price": ("offer", "handle_instant_order_price_answer", (E, X)),
        "instant_order_customer": ("offer", "handle_instant_order_customer_answer", (E, X)),
        "customer_first_name": ("user", "handle_update_user_first_name", ([E, X],)),
        "customer_last_name": ("user", "handle_update_user_last_name", ([E, X],)),
        "customer_contact": ("user", "handle_update_user_contact", ([E, X],)),
        "customer_location": ("user", "handle_update_user_location", ([E, X],)),
        "approve_user_input": ("user", "handle_approve_user", ([X],)),
        "user_status_input": ("user", "handle_user_status", ([X],)),
        "list_user_orders_input": ("admin_order", "handle_list_user_orders", ([X],)),
        "cancel_order_input": ("admin_order", "handle_cancel_order", ([X],)),
        "cancel_order_reason": ("admin_order", "handle_confirm_cancel_with_reason", (E, X)),
        "order_for_input": ("admin_order", "handle_create_order_for", (ADMIN_ID, [X])),
        "order_for_quantity_input": ("admin_order", "handle_create_order_for_quantity_answer", (E, X)),
        "edit_order_price_input": ("admin_order", "handle_edit_order_price_answer", (E, X)),
        "incomplete_delivery": ("wholesale_delivery", "handle_incomplete_delivery_reply", (ADMIN_ID, X, E)),
        "payment_link_input": ("delivery_overview", "handle_payment_link_input", (X, E)),
        "report_customer_input": ("report", "handle_report_customer", (["two", "words"],)),
    }
    TEXT = "two words"
    ENTITY = "7"

    def _bot(self):
        bot = BotService.__new__(BotService)
        bot.db = Mock()
        classes = HANDLER_CLASSES | {"delivery_overview": DeliveryOverviewHandler}
        bot.handlers = {key: create_autospec(cls, instance=True) for key, cls in classes.items()}
        for handler in bot.handlers.values():
            for name in dir(handler):
                if name.startswith("handle_") or name == "create_supplier":
                    getattr(handler, name).return_value = {"status": "success"}
        bot.media_handler = Mock()
        return bot

    def _resolve(self, value):
        if value is X:
            return self.TEXT
        if value is E:
            return self.ENTITY
        if isinstance(value, list):
            return [self._resolve(v) for v in value]
        return value

    def test_every_prompt_type_has_its_expected_route(self):
        assert sorted(ANSWER_ROUTES) == sorted(self.EXPECTED)

    @pytest.mark.parametrize("edit_type", sorted(EXPECTED))
    def test_each_prompt_type_reaches_its_handler(self, edit_type):
        key, method, args = self.EXPECTED[edit_type]
        bot = self._bot()

        bot._handle_edit_reply(prompt(edit_type), ADMIN_ID, ADMIN_ID, self.TEXT, {"text": self.TEXT})

        getattr(bot.handlers[key], method).assert_called_once_with(ADMIN_ID, *(self._resolve(a) for a in args))
        bot.db.delete_edit_context.assert_called_once_with("ctx")

    def test_the_formatting_of_a_description_goes_along(self):
        bot = self._bot()
        entities = [{"type": "bold", "offset": 0, "length": 3}]

        bot._handle_edit_reply(prompt("offer_description"), ADMIN_ID, ADMIN_ID, "Pils", {"entities": entities})

        bot.handlers["offer"].handle_offer_description_answer.assert_called_once_with(ADMIN_ID, "7", "Pils", entities)

    def test_an_empty_cancel_reason_gets_a_default(self):
        bot = self._bot()

        bot._handle_edit_reply(prompt("cancel_order_reason"), ADMIN_ID, ADMIN_ID, "  ", {})

        bot.handlers["admin_order"].handle_confirm_cancel_with_reason.assert_called_once_with(
            ADMIN_ID, "7", "No reason provided"
        )

    @pytest.mark.parametrize(
        "edit_type,method", [("approve_user_input", "handle_approve_user"), ("user_status_input", "handle_user_status")]
    )
    def test_an_unknown_user_goes_back_to_the_users_menu(self, edit_type, method):
        bot = self._bot()
        getattr(bot.handlers["user"], method).return_value = {"status": "user_not_found"}
        bot.handlers["admin_commands"].handle_admin_users.return_value = {"status": "users_menu"}

        result = bot._handle_edit_reply(prompt(edit_type), ADMIN_ID, ADMIN_ID, "nobody", {})

        assert result == {"status": "users_menu"}
        bot.handlers["admin_commands"].handle_admin_users.assert_called_once_with(ADMIN_ID, ADMIN_ID)

    def test_an_unknown_prompt_type_is_closed_and_does_nothing(self):
        bot = self._bot()

        assert bot._handle_edit_reply(prompt("no_such_prompt"), ADMIN_ID, ADMIN_ID, "x", {}) == {
            "status": "unknown_edit_type"
        }
        bot.db.delete_edit_context.assert_called_once_with("ctx")

    def test_every_prompt_type_the_source_stores_has_an_answer(self):
        """A prompt without a route throws the admin's answer away. Photos, files and buttons answer the others."""
        stored = set()
        for path in (ROOT / "src").rglob("*.py"):
            source = path.read_text()
            stored |= set(re.findall(r'store_edit_context\(\s*chat_id,\s*"([a-z_]+)"', source))
            stored |= set(re.findall(r'_store_context\(\s*chat_id,\s*"([a-z_]+)"', source))
            stored |= set(re.findall(r'edit_type="([a-z_]+)"', source))
            stored |= set(re.findall(r'"context_type": "([a-z_]+)"', source))

        answered_otherwise = {"offer_image_upload", "import_csv", "credit_customer_select"}
        assert "supplier_name" in stored and "payment_link_input" in stored  # the patterns find something
        assert sorted(stored - set(ANSWER_ROUTES) - answered_otherwise) == []


class TestImagePrompt:
    def _bot(self):
        bot = BotService.__new__(BotService)
        bot.db = Mock()
        bot.media_handler = Mock()
        bot.handlers = {"offer": create_autospec(OfferCommands, instance=True)}
        return bot

    def test_a_photo_of_an_album_keeps_the_prompt_open(self):
        bot = self._bot()
        message = {"photo": [{"file_id": "p"}], "media_group_id": "g1"}

        bot._handle_edit_reply(prompt("offer_image_upload"), ADMIN_ID, ADMIN_ID, "", message)

        bot.media_handler.handle_media_group_image.assert_called_once_with(ADMIN_ID, "7", message)
        bot.db.delete_edit_context.assert_not_called()

    def test_a_single_photo_closes_the_prompt_and_shows_the_offer(self):
        bot = self._bot()
        bot.media_handler.handle_offer_image_upload.return_value = {"return_to_edit": True, "offer_id": 7}

        bot._handle_edit_reply(prompt("offer_image_upload"), ADMIN_ID, ADMIN_ID, "", {"photo": [{"file_id": "p"}]})

        bot.media_handler.handle_offer_image_upload.assert_called_once_with(ADMIN_ID, "7", [{"file_id": "p"}])
        bot.db.delete_edit_context.assert_called_once_with("ctx")
        bot.handlers["offer"].handle_edit_offer_interface.assert_called_once_with(ADMIN_ID, 7)

    def test_a_failed_upload_keeps_the_prompt_open(self):
        bot = self._bot()
        bot.media_handler.handle_offer_image_upload.return_value = {"status": "upload_failed"}

        result = bot._handle_edit_reply(prompt("offer_image_upload"), ADMIN_ID, ADMIN_ID, "", {"photo": [{}]})

        assert result == {"status": "upload_failed"}
        bot.db.delete_edit_context.assert_not_called()
