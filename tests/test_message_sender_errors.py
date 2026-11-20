"""The message Lambda says what kind of error it hit, never its text (an SSM or Telethon error names things)"""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, patch

from telethon.errors import FloodWaitError

import message_sender

SECRET = "/ubbc-bot/test/telegram-session of user Jan Jansen"


def test_the_body_and_the_log_hold_the_type_of_the_error_only(caplog):
    caplog.set_level(logging.ERROR)
    with patch.object(message_sender.boto3, "client") as client:
        client.return_value.get_parameter.side_effect = PermissionError(SECRET)

        result = message_sender.lambda_handler({"messages": [{"user_id": 1, "message": "Hoi"}]}, None)

    assert result["statusCode"] == 500
    assert json.loads(result["body"]) == {"error": "PermissionError"}
    assert "PermissionError" in caplog.text
    assert SECRET not in caplog.text


class TestSendFromAdmin:
    """What the admin's failure report and the log get when Telethon refuses a message (audit 5, B5)"""

    @staticmethod
    def send(error: Exception, caplog) -> dict:
        caplog.set_level(logging.ERROR)
        client = AsyncMock()
        client.send_message.side_effect = error
        with patch.object(message_sender, "_user_client", client):
            return asyncio.run(message_sender.send_from_admin({"user_id": 42, "message": "Hoi"}, "prod"))

    def test_an_error_is_reported_and_logged_by_its_type_only(self, caplog):
        result = self.send(RuntimeError(SECRET), caplog)

        assert result["success"] is False and result["error"] == "RuntimeError"
        assert SECRET not in caplog.text and "RuntimeError" in caplog.text

    def test_a_user_not_in_the_contacts_is_named_as_such(self, caplog):
        result = self.send(ValueError("Could not find the input entity for PeerUser(user_id=42)"), caplog)

        assert result["error"] == "User not in admin contacts"
        assert "PeerUser" not in caplog.text

    def test_a_flood_wait_says_how_long_to_wait(self, caplog):
        result = self.send(FloodWaitError(request=None, capture=120), caplog)

        assert result["error"] == "Flood wait: try again in 120 s"
