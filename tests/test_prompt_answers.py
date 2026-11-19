"""The handlers check what the admin typed after a prompt (moved there from BotService._handle_edit_reply)"""

from unittest.mock import Mock

import pytest

from handlers.admin.offer_commands import OfferCommands
from handlers.admin.order.order_placement import OrderPlacement
from utils.telegram_entities import entities_to_html

ADMIN_ID = 1


@pytest.fixture
def offers():
    handler = OfferCommands(Mock(), ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler.handle_confirm_process_wholesale = Mock(return_value={"status": "success"})
    return handler


@pytest.fixture
def placement():
    handler = OrderPlacement(Mock(), ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    handler.handle_create_order_for_quantity_select = Mock(return_value={"status": "success"})
    return handler


class TestCustomWholesaleQuantity:
    def test_a_number_of_boxes_processes_the_wholesale_order(self, offers):
        assert offers.handle_custom_wholesale_quantity_answer(ADMIN_ID, "12", " 3 ") == {"status": "success"}

        offers.handle_confirm_process_wholesale.assert_called_once_with(ADMIN_ID, ["12", "3"])

    @pytest.mark.parametrize(
        "text,status", [("drie", "invalid_format"), ("0", "invalid_quantity"), ("-2", "invalid_quantity")]
    )
    def test_anything_else_is_refused(self, offers, text, status):
        assert offers.handle_custom_wholesale_quantity_answer(ADMIN_ID, "12", text) == {"status": status}

        offers.handle_confirm_process_wholesale.assert_not_called()
        offers._send_message.assert_called_once()


class TestOrderForQuantity:
    def test_a_quantity_places_the_order(self, placement):
        result = placement.handle_create_order_for_quantity_answer(ADMIN_ID, "cust-1_12", "4")

        assert result == {"status": "success"}
        placement.handle_create_order_for_quantity_select.assert_called_once_with(ADMIN_ID, "cust-1", "12", "4")

    @pytest.mark.parametrize(
        "text,status", [("vier", "invalid_format"), ("0", "invalid_quantity"), ("11", "invalid_quantity")]
    )
    def test_anything_else_is_refused(self, placement, text, status):
        assert placement.handle_create_order_for_quantity_answer(ADMIN_ID, "cust-1_12", text) == {"status": status}

        placement.handle_create_order_for_quantity_select.assert_not_called()
        placement._send_message.assert_called_once()

    def test_a_broken_prompt_does_nothing(self, placement):
        assert placement.handle_create_order_for_quantity_answer(ADMIN_ID, "no-offer", "4") == {
            "status": "invalid_context"
        }
        placement._send_message.assert_not_called()


class TestDescriptionFormatting:
    def test_without_formatting_the_text_is_kept(self):
        assert entities_to_html("Pils", []) == "Pils"

    def test_bold_italic_and_spoiler_become_html(self):
        entities = [
            {"type": "bold", "offset": 0, "length": 4},
            {"type": "italic", "offset": 5, "length": 3},
            {"type": "spoiler", "offset": 9, "length": 4},
        ]

        assert entities_to_html("Pils met kaas", entities) == "<b>Pils</b> <i>met</i> <tg-spoiler>kaas</tg-spoiler>"

    def test_other_entities_are_left_alone(self):
        assert entities_to_html("zie ubbc.nl", [{"type": "url", "offset": 4, "length": 7}]) == "zie ubbc.nl"

    def test_offsets_are_counted_in_utf16_units(self):
        # 🍺 is two UTF-16 code units, so "Pils" starts at 3, not 2
        entities = [{"type": "bold", "offset": 3, "length": 4}, {"type": "italic", "offset": 8, "length": 3}]

        assert entities_to_html("🍺 Pils met 🍻", entities) == "🍺 <b>Pils</b> <i>met</i> 🍻"

    def test_the_text_around_the_tags_is_escaped(self):
        entities = [{"type": "bold", "offset": 7, "length": 4}]

        assert entities_to_html("Bier & kaas <3", entities) == "Bier &amp; <b>kaas</b> &lt;3"

    def test_nested_entities_stay_nested(self):
        entities = [{"type": "bold", "offset": 0, "length": 8}, {"type": "italic", "offset": 5, "length": 3}]

        assert entities_to_html("Pils met", entities) == "<b>Pils <i>met</i></b>"
