import hmac
import json
import logging
import os
from typing import Any

from services.bot_service import BotService
from utils.response import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SECRET_TOKEN_HEADER = "x-telegram-bot-api-secret-token"

_cached_webhook_secret = None


def _get_webhook_secret() -> str | None:
    """Get webhook secret token from Parameter Store with caching"""
    global _cached_webhook_secret
    if _cached_webhook_secret:
        return _cached_webhook_secret

    import boto3

    environment = os.environ.get("ENVIRONMENT", "test")
    parameter_name = f"/ubbc-bot/{environment}/telegram-webhook-secret"
    try:
        response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
        _cached_webhook_secret = response["Parameter"]["Value"] or None
    except Exception as e:
        logger.error(f"Error getting webhook secret from {parameter_name}: {e}")
        return None
    return _cached_webhook_secret


def _is_authentic_request(event: dict[str, Any]) -> bool:
    """Verify the request comes from Telegram via the secret token header (fails closed)"""
    expected = _get_webhook_secret()
    if not expected:
        return False

    # API Gateway preserves header casing as sent, so match case-insensitively
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    received = headers.get(SECRET_TOKEN_HEADER) or ""
    return hmac.compare_digest(received.encode(), expected.encode())


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for Telegram webhook"""
    if not _is_authentic_request(event):
        logger.warning("Rejected webhook request with missing or invalid secret token")
        return create_response(403, {"error": "Forbidden"})

    try:
        # Parse webhook data
        body = json.loads(event.get("body", "{}"))

        # Initialize bot service (reused across warm Lambda invocations)
        bot_service = BotService.get_instance()

        # Process update
        bot_service.process_update(body)

        return create_response(200, {"status": "ok"})

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return create_response(500, {"error": "Internal server error"})
