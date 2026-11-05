import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from services.callback_handler import CallbackHandler


class TestEditOrderCallbackDispatch(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.handler = CallbackHandler(self.db, 15005473, "test", "token", handlers={}, media_handler=Mock())
        self.editing = Mock()
        self.handler.handlers = {"admin_order": Mock(editing=self.editing)}

    def test_box_option_callback_dispatches(self):
        self.handler._handle_edit_callbacks(123, 1, "edit_order_box_oid-123")
        self.editing.show_box_options.assert_called_once_with(123, "oid-123")

    def test_price_prompt_callback_dispatches(self):
        self.handler._handle_edit_callbacks(123, 1, "edit_order_price_oid-123")
        self.editing.prompt_price.assert_called_once_with(123, "oid-123")

    def test_status_options_callback_dispatches(self):
        self.handler._handle_edit_callbacks(123, 1, "edit_order_status_oid-123")
        self.editing.show_status_options.assert_called_once_with(123, "oid-123")

    def test_setbox_callback_splits_order_and_box(self):
        self.handler._handle_edit_callbacks(123, 1, "edit_order_setbox_oid-123_box-456")
        self.editing.confirm_box.assert_called_once_with(123, "oid-123", "box-456")

    def test_applybox_callback_splits_order_and_box(self):
        self.handler._handle_edit_callbacks(123, 1, "edit_order_applybox_oid-123_box-456")
        self.editing.apply_box.assert_called_once_with(123, "oid-123", "box-456")

    def test_setstatus_callback_preserves_underscored_status(self):
        self.handler._handle_edit_callbacks(123, 1, "edit_order_setstatus_oid-123_received_partial_delayed")
        self.editing.confirm_status.assert_called_once_with(123, "oid-123", "received_partial_delayed")

    def test_applystatus_callback_preserves_underscored_status(self):
        self.handler._handle_edit_callbacks(123, 1, "edit_order_applystatus_oid-123_labeling_completed")
        self.editing.apply_status.assert_called_once_with(123, "oid-123", "labeling_completed")

    def test_pick_callback_resolves_order_and_shows_menu(self):
        order = Mock()
        self.db.get_order.return_value = order
        self.handler._handle_edit_callbacks(123, 1, "edit_order_pick_oid-123")
        self.db.get_order.assert_called_once_with("oid-123")
        self.editing._show_aspect_menu.assert_called_once_with(123, order)


if __name__ == "__main__":
    unittest.main()
