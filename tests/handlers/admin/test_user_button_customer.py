"""The user buttons (edit, status, approve, reject) read the customer of the button, or say that it is gone."""

from unittest.mock import Mock

import pytest

from handlers.admin.user_commands import UserCommands

ADMIN_ID = 1

# (entry point, what it does with the customer)
BUTTONS = [
    ("handle_edit_user_select", "_show_user_edit_interface"),
    ("handle_user_status_select", "_send_user_status"),
    ("handle_approve_user_select", "_approve_user_by_customer"),
    ("handle_approve_user_by_id", "_approve_user_by_customer"),
    ("handle_reject_user_by_id", "_reject_customer"),
]


@pytest.fixture
def handler():
    db = Mock()
    db.get_customer_by_telegram_id.return_value = None
    handler = UserCommands(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    return handler


@pytest.mark.parametrize("entry,action", BUTTONS)
def test_the_customer_of_the_button_is_handed_on(handler, entry, action):
    customer = Mock()
    handler.db.get_customer.return_value = customer
    setattr(handler, action, Mock(return_value={"status": "success"}))

    assert getattr(handler, entry)(ADMIN_ID, "cust-1") == {"status": "success"}

    handler.db.get_customer.assert_called_once_with("cust-1")
    called = getattr(handler, action).call_args.args
    assert customer in called and ADMIN_ID in called


@pytest.mark.parametrize("entry,action", BUTTONS)
def test_a_customer_that_is_gone_is_reported(handler, entry, action):
    handler.db.get_customer.return_value = None
    setattr(handler, action, Mock())

    assert getattr(handler, entry)(ADMIN_ID, "cust-1") == {"status": "user_not_found"}

    getattr(handler, action).assert_not_called()
    assert "cust-1" in handler._send_message.call_args.args[1]
