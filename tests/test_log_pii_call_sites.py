"""Call sites must log identifiers and lengths, never names, handles or free-text input."""

import logging
from unittest.mock import Mock, patch

import pytest

from handlers.admin.offer_commands import OfferCommands
from handlers.base_handler import BaseHandler
from services.bot_service import BotService

ADMIN_ID = 1
FIRST_NAME = "Jantje"
USERNAME = "jantje_beton"
FREE_TEXT = "Kerkstraat 5, jan@example.com, 0612345678"


@pytest.fixture
def bot():
    service = BotService.__new__(BotService)
    service.admin_user_id = ADMIN_ID
    service.environment = "test"
    service.db = Mock()
    service.db.mark_update_processed.return_value = True
    service.db.get_customer_by_telegram_id.return_value = Mock()
    service.command_router = Mock()
    service.command_router.route_command.return_value = {"status": "ok"}
    service.supplier_commands = Mock()
    service.offer_commands = Mock()
    service.user_commands = Mock()
    service.media_handler = Mock()
    service.handlers = {"supplier": Mock(), "offer": Mock(), "user": Mock()}
    return service


def _joined(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


def test_incoming_command_log_has_user_id_only(bot, caplog):
    caplog.set_level(logging.DEBUG)
    update = {
        "update_id": 1,
        "message": {
            "message_id": 7,
            "chat": {"id": 42},
            "from": {"id": 42, "first_name": FIRST_NAME, "username": USERNAME},
            "text": "/start",
        },
    }

    bot.process_update(update)

    logs = _joined(caplog)
    assert "Command: /start | User ID: 42" in logs
    assert FIRST_NAME not in logs
    assert USERNAME not in logs


def test_new_user_admin_notification_logs_have_no_name(bot, caplog):
    caplog.set_level(logging.DEBUG)
    bot.base_handler = Mock()
    bot.base_handler._t.return_value = "msg"
    bot.base_handler._send_message.return_value = {"success": True}
    user_data = {"id": 42, "first_name": FIRST_NAME, "last_name": "Beton", "username": USERNAME}

    bot._notify_admin_new_user_pending(user_data, Mock(customer_id="c-1"))

    logs = _joined(caplog)
    assert "user ID: 42" in logs
    assert FIRST_NAME not in logs
    assert USERNAME not in logs


def test_new_user_admin_notification_failure_log_has_no_name(bot, caplog):
    caplog.set_level(logging.DEBUG)
    bot.base_handler = Mock()
    bot.base_handler._t.return_value = "msg"
    bot.base_handler._send_message.return_value = {"success": False}
    user_data = {"id": 42, "first_name": FIRST_NAME, "username": USERNAME}

    bot._notify_admin_new_user_pending(user_data, Mock(customer_id="c-1"))

    logs = _joined(caplog)
    assert "Failed to send new user notification to admin for user ID: 42" in logs
    assert FIRST_NAME not in logs
    assert USERNAME not in logs


@pytest.mark.parametrize("edit_type", ["customer_contact", "customer_first_name", "offer_description"])
def test_edit_reply_logs_never_contain_the_typed_text(bot, caplog, edit_type):
    caplog.set_level(logging.DEBUG)
    context = Mock(edit_type=edit_type, entity_id="e-1", context_id="ctx")

    bot._handle_edit_reply(context, 42, ADMIN_ID, FREE_TEXT, {})

    logs = _joined(caplog)
    assert f"text_length={len(FREE_TEXT)}" in logs
    for fragment in ("Kerkstraat", "jan@example.com", "0612345678"):
        assert fragment not in logs


def test_description_with_entities_logs_no_text_or_html(caplog):
    caplog.set_level(logging.DEBUG)
    handler = OfferCommands(Mock(), ADMIN_ID, "test", "token")
    handler.handle_update_offer_description = Mock(return_value={"status": "success"})

    handler.handle_offer_description_answer(42, "7", "Kerkstraat 5", [{"type": "bold", "offset": 0, "length": 10}])

    logs = _joined(caplog)
    assert "entity_count=1" in logs
    assert "Kerkstraat" not in logs
    handler.handle_update_offer_description.assert_called_once_with(42, ["7", "<b>Kerkstraat</b> 5"])


class TestSendMessageLogging:
    TEXT = "Jantje B. bestelde 2x Pils"

    def _handler(self, environment):
        return BaseHandler(Mock(), ADMIN_ID, environment, "token")

    def test_sent_message_text_is_not_logged(self, caplog):
        caplog.set_level(logging.DEBUG)
        handler = self._handler("test")
        response = Mock(status_code=200)
        response.json.return_value = {"result": {"message_id": 5}}

        with patch("services.telegram_client.requests.post", return_value=response):
            result = handler._send_message(42, self.TEXT)

        assert result == {"success": True, "message_id": 5}
        logs = _joined(caplog)
        assert "Jantje" not in logs
        assert "text_length=" in logs

    def test_blocked_prod_group_message_text_is_not_logged(self, caplog):
        caplog.set_level(logging.DEBUG)
        handler = self._handler("prod")

        result = handler._send_message(-100123, self.TEXT)

        assert result == {"success": False}
        logs = _joined(caplog)
        assert "Jantje" not in logs
        assert "Production group message blocked: chat_id=-100123" in logs
