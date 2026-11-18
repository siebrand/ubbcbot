"""/edit_order callbacks, tapped as the admin. The ids here contain hyphens and the statuses contain underscores,
which is how the real values look."""

import unittest
from unittest.mock import Mock

from services.callback_handler import CallbackHandler

ADMIN_ID = 15005473
CHAT_ID = 123


class TestEditOrderCallbackDispatch(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.handler = CallbackHandler(self.db, ADMIN_ID, "test", "token", handlers={}, media_handler=Mock())
        self.editing = Mock()
        self.handler.handlers = {"admin_order": Mock(editing=self.editing)}
        self.handler._answer_callback_query = Mock()
        self.handler._edit_message_remove_keyboard = Mock()
        self.handler._send_message = Mock()

    def tap(self, data):
        return self.handler.handle_callback_query(
            {
                "id": "q",
                "from": {"id": ADMIN_ID},
                "message": {"chat": {"id": CHAT_ID}, "message_id": 1},
                "data": data,
            }
        )

    def test_box_option_callback_dispatches(self):
        self.tap("edit_order_box_oid-123")
        self.editing.show_box_options.assert_called_once_with(CHAT_ID, "oid-123")

    def test_price_prompt_callback_dispatches(self):
        self.tap("edit_order_price_oid-123")
        self.editing.prompt_price.assert_called_once_with(CHAT_ID, "oid-123")

    def test_status_options_callback_dispatches(self):
        self.tap("edit_order_status_oid-123")
        self.editing.show_status_options.assert_called_once_with(CHAT_ID, "oid-123")

    def test_setbox_callback_splits_order_and_box(self):
        self.tap("edit_order_setbox_oid-123_box-456")
        self.editing.confirm_box.assert_called_once_with(CHAT_ID, "oid-123", "box-456")

    def test_applybox_callback_splits_order_and_box(self):
        self.tap("edit_order_applybox_oid-123_box-456")
        self.editing.apply_box.assert_called_once_with(CHAT_ID, "oid-123", "box-456")

    def test_setstatus_callback_preserves_underscored_status(self):
        self.tap("edit_order_setstatus_oid-123_received_partial_delayed")
        self.editing.confirm_status.assert_called_once_with(CHAT_ID, "oid-123", "received_partial_delayed")

    def test_applystatus_callback_preserves_underscored_status(self):
        self.tap("edit_order_applystatus_oid-123_labeling_completed")
        self.editing.apply_status.assert_called_once_with(CHAT_ID, "oid-123", "labeling_completed")

    def test_pick_callback_resolves_order_and_shows_menu(self):
        order = Mock()
        self.db.get_order.return_value = order
        self.tap("edit_order_pick_oid-123")
        self.db.get_order.assert_called_once_with("oid-123")
        self.editing.show_aspect_menu.assert_called_once_with(CHAT_ID, order)

    def test_an_unknown_edit_order_action_is_reported(self):
        self.tap("edit_order_nonsense_oid-123")
        self.handler._send_message.assert_called_once()
        self.assertEqual(self.editing.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
