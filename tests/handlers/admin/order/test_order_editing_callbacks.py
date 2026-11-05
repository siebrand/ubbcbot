import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from handlers.admin.order.order_editing import OrderEditing
from models.entities import Box, BoxStatus, Order


class TestOrderEditingCallbacks(unittest.TestCase):
    def setUp(self):
        self.mock_db = Mock()
        self.handler = OrderEditing(self.mock_db, 15005473, "test", "token")
        self.handler.box_status_manager = Mock()
        self.order = Order(order_id="abc12345-1111", customer_id="c1", offer_id=724, box_id="box-old", quantity=2)
        self.mock_db.get_order.return_value = self.order

    @patch.object(OrderEditing, "_send_message")
    def test_show_box_options_lists_boxes_with_space(self, mock_send):
        import datetime

        b = Box(box_id="box-1", offer_id=724, current_quantity=0, max_capacity=12, status=BoxStatus.OPEN.value)
        b.created_at = datetime.datetime(2026, 1, 1)
        self.mock_db.get_boxes_by_offer.return_value = [b]
        result = self.handler.show_box_options(123, self.order.order_id)
        self.assertEqual(result["status"], "box_options_shown")
        keyboard = mock_send.call_args[1]["reply_markup"]["inline_keyboard"]
        # callback_data uses short order + short box ids (<= 64 bytes)
        callbacks = [btn["callback_data"] for row in keyboard for btn in row]
        self.assertIn(f"edit_order_setbox_{self.order.order_id[:8]}_{b.box_id[:8]}", callbacks)
        self.assertTrue(all(len(c.encode()) <= 64 for c in callbacks))

    @patch.object(OrderEditing, "_send_message")
    def test_show_box_options_when_none_available(self, mock_send):
        self.mock_db.get_boxes_by_offer.return_value = []
        result = self.handler.show_box_options(123, self.order.order_id)
        self.assertEqual(result["status"], "no_boxes_available")

    @patch.object(OrderEditing, "_send_message")
    def test_show_status_options_lists_statuses_in_order(self, mock_send):
        result = self.handler.show_status_options(123, self.order.order_id)
        self.assertEqual(result["status"], "status_options_shown")
        keyboard = mock_send.call_args[1]["reply_markup"]["inline_keyboard"]
        callbacks = [btn["callback_data"] for row in keyboard for btn in row if "setstatus" in btn["callback_data"]]
        oid = self.order.order_id[:8]
        self.assertEqual(callbacks[0], f"edit_order_setstatus_{oid}_pending")
        self.assertEqual(callbacks[-1], f"edit_order_setstatus_{oid}_cancelled")
        # every status callback must stay within Telegram's 64-byte limit
        self.assertTrue(all(len(c.encode()) <= 64 for c in callbacks))

    @patch.object(OrderEditing, "_send_message")
    def test_confirm_box_shows_confirmation(self, mock_send):
        new_box = Box(box_id="box-1", offer_id=724, current_quantity=0, max_capacity=12)
        self.mock_db.get_boxes_by_offer.return_value = [new_box]
        result = self.handler.confirm_box(123, self.order.order_id, "box-1")
        self.assertEqual(result["status"], "confirm_shown")
        keyboard = mock_send.call_args[1]["reply_markup"]["inline_keyboard"]
        callbacks = [btn["callback_data"] for row in keyboard for btn in row]
        self.assertIn(f"edit_order_applybox_{self.order.order_id[:8]}_{new_box.box_id[:8]}", callbacks)

    @patch.object(OrderEditing, "_send_message")
    def test_apply_box_success_sends_confirmation(self, mock_send):
        new_box = Box(box_id="box-1", offer_id=724, current_quantity=0, max_capacity=12)
        self.mock_db.get_boxes_by_offer.return_value = [new_box]
        self.mock_db.get_box.return_value = new_box
        self.handler.box_status_manager.update_box_after_order_placement.return_value = True
        self.handler.box_status_manager.update_box_after_order_cancellation.return_value = True
        self.mock_db.update_order.return_value = True
        result = self.handler.apply_box(123, self.order.order_id, "box-1")
        self.assertEqual(result["status"], "edit_order_box_success")

    @patch.object(OrderEditing, "_send_message")
    def test_prompt_price_stores_edit_context(self, mock_send):
        result = self.handler.prompt_price(123, self.order.order_id)
        self.assertEqual(result["status"], "awaiting_price")
        self.mock_db.create_edit_context.assert_called_once()
        ctx = self.mock_db.create_edit_context.call_args[0][0]
        self.assertEqual(ctx.edit_type, "edit_order_price_input")
        self.assertEqual(ctx.entity_id, self.order.order_id)

    @patch.object(OrderEditing, "_send_message")
    def test_apply_price_input_recomputes_and_confirms(self, mock_send):
        self.mock_db.update_order.return_value = True
        result = self.handler.apply_price_input(123, self.order.order_id, "2.50")
        self.assertEqual(result["status"], "edit_order_price_success")
        updates = self.mock_db.update_order.call_args[0][1]
        self.assertEqual(str(updates["total_price"]), "5.00")  # 2.50 * 2

    @patch.object(OrderEditing, "_send_message")
    def test_apply_status_sends_confirmation(self, mock_send):
        self.mock_db.update_order.return_value = True
        result = self.handler.apply_status(123, self.order.order_id, "completed")
        self.assertEqual(result["status"], "edit_order_status_success")

    @patch.object(OrderEditing, "_send_message")
    def test_aspect_menu_includes_order_details(self, mock_send):
        offer = Mock()
        offer.name = "Fermentaria Local Reserva Local (WILD) 75cl"
        self.mock_db.get_offer.return_value = offer
        customer = Mock()
        customer.first_name = "Siebrand"
        customer.last_name = "Mazeland"
        self.mock_db.get_customer.return_value = customer

        self.handler._show_aspect_menu(123, self.order)
        text = mock_send.call_args[0][1]
        # details present above the buttons
        self.assertIn(self.order.order_id[:8], text)
        self.assertIn("Siebrand Mazeland", text)
        self.assertIn(str(self.order.offer_id), text)
        self.assertIn("Fermentaria", text)
        # buttons still present
        self.assertIn("inline_keyboard", mock_send.call_args[1]["reply_markup"])


if __name__ == "__main__":
    unittest.main()
