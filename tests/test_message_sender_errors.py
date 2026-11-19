"""The message Lambda says what kind of error it hit, never its text (an SSM or Telethon error names things)"""

import json
import logging
from unittest.mock import patch

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
