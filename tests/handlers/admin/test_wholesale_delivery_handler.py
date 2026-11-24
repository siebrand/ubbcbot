"""Wholesale delivery handler: paths that used to fall through and return None.

Every handler must return a result dict.
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from handlers.admin.wholesale_delivery_handler import WholesaleDeliveryHandler
from models.entities import DeliveryAction

CHAT_ID = 1
BOX_ID = "abcdef12-0000-0000-0000-000000000000"


class WholesaleDeliveryHandlerTestBase(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.handler = WholesaleDeliveryHandler(self.db, 15005473, "test", "test_token")
        self.box = SimpleNamespace(box_id=BOX_ID)
        self.db.get_boxes_by_offer_with_orders.return_value = [self.box]


class TestHandleDeliveryAction(WholesaleDeliveryHandlerTestBase):
    def setUp(self):
        super().setUp()
        self.orders = [SimpleNamespace(quantity=3, status="ordered")]
        self.db.get_orders_by_box.return_value = self.orders

    def test_full_delivery_is_delegated(self):
        with patch.object(self.handler, "_handle_full_delivery", return_value={"status": "ok"}) as full:
            result = self.handler.handle_delivery_action(CHAT_ID, DeliveryAction.FULL.value, "abcdef12", 1, "sup")

        full.assert_called_once_with(CHAT_ID, BOX_ID)
        self.assertEqual(result, {"status": "ok"})

    def test_unknown_box_is_reported(self):
        self.db.get_boxes_by_offer_with_orders.return_value = []
        with patch.object(self.handler, "_send_message", return_value={"status": "sent"}) as send:
            result = self.handler.handle_delivery_action(CHAT_ID, DeliveryAction.FULL.value, "abcdef12", 1, "sup")

        send.assert_called_once_with(CHAT_ID, self.handler._t("box_not_found", CHAT_ID))
        self.assertEqual(result, {"status": "sent"})

    def test_unknown_action_returns_status(self):
        with patch.object(self.handler, "_send_message") as send:
            result = self.handler.handle_delivery_action(CHAT_ID, "bogus", "abcdef12", 1, "sup")

        self.assertEqual(result, {"status": "unknown_action"})
        send.assert_not_called()


class TestHandlePartialAction(WholesaleDeliveryHandlerTestBase):
    def setUp(self):
        super().setUp()
        self.db.get_all_boxes.return_value = [self.box]

    def test_success_continues_workflow(self):
        with (
            patch.object(self.handler, "_process_box_delivery", return_value=True),
            patch.object(self.handler, "_send_message"),
            patch.object(self.handler, "_continue_workflow_after_action", return_value={"status": "continued"}) as cont,
        ):
            result = self.handler.handle_partial_action(CHAT_ID, "delayed", "abcdef12", 5)

        cont.assert_called_once_with(CHAT_ID, BOX_ID)
        self.assertEqual(result, {"status": "continued"})

    def test_unknown_box_is_reported(self):
        self.db.get_all_boxes.return_value = []
        with patch.object(self.handler, "_send_message", return_value={"status": "sent"}) as send:
            result = self.handler.handle_partial_action(CHAT_ID, "delayed", "abcdef12", 5)

        send.assert_called_once_with(CHAT_ID, self.handler._t("box_not_found", CHAT_ID))
        self.assertEqual(result, {"status": "sent"})

    def test_failed_delivery_is_reported_to_admin(self):
        with (
            patch.object(self.handler, "_process_box_delivery", return_value=False),
            patch.object(self.handler, "_send_message", return_value={"status": "sent"}) as send,
        ):
            result = self.handler.handle_partial_action(CHAT_ID, "delayed", "abcdef12", 5)

        send.assert_called_once_with(CHAT_ID, self.handler._t("delivery_processing_failed", CHAT_ID))
        self.assertEqual(result, {"status": "sent"})


class TestHandleBackNavigation(WholesaleDeliveryHandlerTestBase):
    def test_back_to_suppliers_edits_message(self):
        self.db.get_suppliers_with_ordered_offers.return_value = []
        with patch.object(self.handler, "_edit_message", return_value={"status": "edited"}) as edit:
            result = self.handler.handle_back_navigation(CHAT_ID, "suppliers")

        edit.assert_called_once()
        self.assertEqual(result, {"status": "edited"})

    def test_unknown_target_returns_status(self):
        with patch.object(self.handler, "_edit_message") as edit, patch.object(self.handler, "_send_message") as send:
            result = self.handler.handle_back_navigation(CHAT_ID, "nowhere")

        self.assertEqual(result, {"status": "unknown_target"})
        edit.assert_not_called()
        send.assert_not_called()

    def test_target_with_missing_arguments_returns_status(self):
        for target in ("offers", "boxes"):
            with self.subTest(target), patch.object(self.handler, "_edit_message"):
                result = self.handler.handle_back_navigation(CHAT_ID, target)
                self.assertEqual(result, {"status": "unknown_target"})


if __name__ == "__main__":
    unittest.main()
