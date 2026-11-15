"""Admin prompts (edit contexts) live in the admin's private chat only.

Admin commands and admin button taps in a group are answered in the private chat, in every environment,
a pending prompt is never read in a group, and a chat has at most one pending prompt.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from models.entities import EditContext
from services.callback_handler import CallbackHandler
from services.command_router import CommandRouter
from services.database import DynamoDBService

ADMIN_ID = 15005473
GROUP_ID = -1003399818858
CUSTOMER_ID = 4242


class TestAdminCommandsAnswerPrivately:
    def _router(self, environment):
        db = Mock()
        db.get_customer_by_telegram_id.return_value = Mock(authorization_status="approved", language="nl")
        handlers = {name: Mock() for name in ("admin_commands", "supplier", "info", "user", "credit")}
        router = CommandRouter(db, ADMIN_ID, environment, handlers)
        router.base_handler._send_message = Mock()
        return router, handlers

    @pytest.mark.parametrize("environment", ["test", "prod"])
    def test_an_admin_command_in_a_group_is_answered_in_the_private_chat(self, environment):
        router, handlers = self._router(environment)

        router.route_command(GROUP_ID, ADMIN_ID, "/admin", message_id=5)

        # prod redirects group commands to a private chat already; test now does the same for the admin
        if environment == "test":
            handlers["admin_commands"].handle_admin.assert_called_once_with(ADMIN_ID, ADMIN_ID)

    def test_a_prompt_starting_command_in_a_test_group_goes_to_the_private_chat(self):
        router, handlers = self._router("test")

        router.route_command(GROUP_ID, ADMIN_ID, "/create_supplier")

        handlers["supplier"].handle_create_supplier.assert_called_once_with(ADMIN_ID, [])

    def test_an_admin_command_in_the_private_chat_is_unchanged(self):
        router, handlers = self._router("test")

        router.route_command(ADMIN_ID, ADMIN_ID, "/create_supplier")

        handlers["supplier"].handle_create_supplier.assert_called_once_with(ADMIN_ID, [])

    def test_cancel_in_a_group_cancels_the_prompt_in_the_private_chat(self):
        router, _ = self._router("test")
        router._handle_cancel_command = Mock(return_value={"status": "cancelled"})

        router.route_command(GROUP_ID, ADMIN_ID, "/cancel")

        router._handle_cancel_command.assert_called_once_with(ADMIN_ID, ADMIN_ID)

    def test_cancel_in_the_private_chat_is_unchanged(self):
        router, _ = self._router("test")
        router._handle_cancel_command = Mock(return_value={"status": "cancelled"})

        router.route_command(CUSTOMER_ID, CUSTOMER_ID, "/cancel")

        router._handle_cancel_command.assert_called_once_with(CUSTOMER_ID, CUSTOMER_ID)


class TestAdminButtonsAnswerPrivately:
    @pytest.fixture
    def handlers(self):
        return {
            name: Mock()
            for name in (
                "admin_commands",
                "user",
                "info",
                "customer_order",
                "admin_order",
                "offer",
                "supplier",
                "credit",
                "wholesale_delivery",
                "labeling",
                "import",
                "test",
            )
        }

    @pytest.fixture
    def callback_handler(self, handlers):
        db = Mock()
        db.get_customer_by_telegram_id.return_value = Mock(authorization_status="approved", language="nl")
        handler = CallbackHandler(db, ADMIN_ID, "test", "token", handlers, Mock())
        handler._answer_callback_query = Mock()
        handler._send_message = Mock()
        handler._edit_message_remove_keyboard = Mock()
        return handler

    @staticmethod
    def _query(data, user_id, chat_id):
        return {
            "id": "q",
            "from": {"id": user_id},
            "message": {"chat": {"id": chat_id}, "message_id": 9},
            "data": data,
        }

    def test_a_router_button_tapped_by_the_admin_in_a_group_continues_privately(self, callback_handler, handlers):
        callback_handler.handle_callback_query(self._query("cancel_action", ADMIN_ID, GROUP_ID))

        handlers["admin_commands"].handle_admin.assert_called_once_with(ADMIN_ID, ADMIN_ID)

    def test_a_panel_button_tapped_by_the_admin_in_a_group_continues_privately(self, callback_handler, handlers):
        callback_handler.handle_callback_query(self._query("cmd:list_pending", ADMIN_ID, GROUP_ID))

        handlers["user"].handle_list_pending.assert_called_once_with(ADMIN_ID)

    def test_the_admin_in_the_private_chat_is_unchanged(self, callback_handler, handlers):
        callback_handler.handle_callback_query(self._query("cmd:list_pending", ADMIN_ID, ADMIN_ID))

        handlers["user"].handle_list_pending.assert_called_once_with(ADMIN_ID)

    def test_the_message_with_the_button_is_still_edited_where_it_is(self, callback_handler):
        callback_handler.handle_callback_query(self._query("cmd:list_pending", ADMIN_ID, GROUP_ID))

        # The keyboard sits on a message in the group, so that is the chat to edit
        callback_handler._edit_message_remove_keyboard.assert_called_once_with(GROUP_ID, 9)

    def test_a_customer_order_tap_in_a_group_still_replies_privately(self, callback_handler, handlers):
        callback_handler.handle_callback_query(self._query("order_7_2", CUSTOMER_ID, GROUP_ID))

        assert handlers["customer_order"].handle_create_order.call_args.args[0] == CUSTOMER_ID


class TestOnePromptPerChat:
    @pytest.fixture
    def db(self, dynamodb):
        return DynamoDBService()

    @staticmethod
    def _context(chat_id, edit_type, minutes_ago=0):
        return EditContext(
            chat_id=chat_id,
            edit_type=edit_type,
            entity_id="x",
            created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )

    def test_a_new_prompt_replaces_the_open_one_in_the_same_chat(self, db):
        db.create_edit_context(self._context(ADMIN_ID, "supplier_name"))
        db.create_edit_context(self._context(ADMIN_ID, "offer_price"))

        assert db.get_edit_context_by_chat_id(ADMIN_ID).edit_type == "offer_price"
        assert len(db.edit_context_repo._contexts_for_chat(ADMIN_ID)) == 1

    def test_other_chats_are_left_alone(self, db):
        db.create_edit_context(self._context(ADMIN_ID, "supplier_name"))
        db.create_edit_context(self._context(111, "offer_price"))

        assert db.get_edit_context_by_chat_id(ADMIN_ID).edit_type == "supplier_name"
        assert db.get_edit_context_by_chat_id(111).edit_type == "offer_price"

    def test_the_latest_prompt_wins_when_older_leftovers_exist(self, db):
        # Contexts written without going through create_edit_context (older data) must not shadow a new one
        for context in (self._context(ADMIN_ID, "old", minutes_ago=30), self._context(ADMIN_ID, "new")):
            db.edit_context_repo.table.put_item(Item=db.edit_context_repo._prepare_item(context.__dict__))

        assert db.get_edit_context_by_chat_id(ADMIN_ID).edit_type == "new"

    def test_no_prompt_means_no_context(self, db):
        assert db.get_edit_context_by_chat_id(ADMIN_ID) is None

    def test_a_consumed_prompt_is_gone(self, db):
        context = self._context(ADMIN_ID, "supplier_name")
        db.create_edit_context(context)

        db.delete_edit_context(context.context_id)

        assert db.get_edit_context_by_chat_id(ADMIN_ID) is None

    def test_recreating_the_same_context_does_not_delete_itself(self, db):
        context = self._context(ADMIN_ID, "supplier_name")

        db.create_edit_context(context)
        db.create_edit_context(context)

        assert db.get_edit_context_by_chat_id(ADMIN_ID).context_id == context.context_id
