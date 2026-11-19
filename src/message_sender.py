"""
Unified message sender for bot and admin user messages
Handles async sending to avoid Lambda timeouts
"""

import asyncio
import json
import logging

import boto3

from config import ADMIN_USER_ID
from services.telegram_client import TelegramClient
from services.translator import DEFAULT_LANGUAGE, text
from services.user_client import UserClient
from utils.log_redaction import configure_logging

logger = logging.getLogger()
configure_logging()

# Module-level event loop for Lambda container reuse
_loop = None
_user_client = None

# Telegram allows a bot about 30 messages a second: batches of 25 with a second between them stay under it
BOT_BATCH_SIZE = 25
BOT_BATCH_PAUSE_SECONDS = 1
# A message refused with 429 is tried again after Telegram's retry_after, at most this often in all
BOT_SEND_ATTEMPTS = 3
MAX_RETRY_AFTER_SECONDS = 30
ADMIN_BATCH_SIZE = 5
ADMIN_BATCH_PAUSE_SECONDS = 0.5


async def _pause(seconds: float) -> None:
    await asyncio.sleep(seconds)


def get_event_loop():
    """Get or create event loop for Lambda container"""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def lambda_handler(event, context):
    """
    Send messages from bot or admin account

    Event format:
    {
        "messages": [
            {
                "user_id": 123456789,
                "message": "Text",
                "from_admin": true/false,
                "parse_mode": "HTML" (optional),
                "disable_web_page_preview": true (optional)
            }
        ],
        "environment": "test",
        "admin_language": "nl" (optional: the language of the failure report to the admin)
    }
    """
    try:
        messages = event.get("messages", [])
        environment = event.get("environment", "test")
        admin_language = event.get("admin_language") or DEFAULT_LANGUAGE

        if not messages:
            return {"statusCode": 400, "body": json.dumps({"error": "No messages provided"})}

        # Get credentials
        ssm = boto3.client("ssm")
        bot_token = ssm.get_parameter(Name=f"/ubbc-bot/{environment}/telegram-bot-token", WithDecryption=True)[
            "Parameter"
        ]["Value"]

        # Send messages
        loop = get_event_loop()
        results = loop.run_until_complete(send_messages(messages, environment, bot_token, admin_language))

        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        error_count = len(results) - success_count

        logger.info(f"Sent {success_count} messages, {error_count} errors out of {len(messages)} total")

        return {
            "statusCode": 200,
            "body": json.dumps({"success_count": success_count, "error_count": error_count, "results": results}),
        }

    except Exception as e:
        # The type only, as on the webhook: the message of an SSM or Telethon error can name a parameter or a user
        logger.error(f"Error in message sender: {type(e).__name__}")
        return {"statusCode": 500, "body": json.dumps({"error": type(e).__name__})}


async def send_messages(messages, environment, bot_token, admin_language=DEFAULT_LANGUAGE):
    """Send all messages with controlled concurrency"""
    # Separate admin and bot messages
    admin_messages = [msg for msg in messages if msg.get("from_admin")]
    bot_messages = [msg for msg in messages if not msg.get("from_admin")]

    results = []

    if admin_messages:
        logger.info(f"Sending {len(admin_messages)} admin messages")
        results.extend(
            await _send_in_batches(
                admin_messages,
                lambda msg: send_from_admin(msg, environment),
                ADMIN_BATCH_SIZE,
                ADMIN_BATCH_PAUSE_SECONDS,
            )
        )

    if bot_messages:
        logger.info(f"Sending {len(bot_messages)} bot messages")
        results.extend(
            await _send_in_batches(
                bot_messages,
                lambda msg: send_from_bot(msg, environment, bot_token),
                BOT_BATCH_SIZE,
                BOT_BATCH_PAUSE_SECONDS,
            )
        )

    # Notify admin of failures
    failures = [r for r in results if isinstance(r, dict) and not r.get("success")]
    if failures:
        await notify_admin_of_failures(failures, environment, bot_token, admin_language)

    return results


async def _send_in_batches(messages, send, batch_size, pause_seconds):
    """Send a batch at a time, concurrently within the batch, with a pause between batches"""
    results = []
    for i in range(0, len(messages), batch_size):
        if i:
            await _pause(pause_seconds)
        batch_results = await asyncio.gather(
            *(send(msg) for msg in messages[i : i + batch_size]), return_exceptions=True
        )
        results.extend(batch_results)
        sent = sum(1 for r in batch_results if isinstance(r, dict) and r.get("success"))
        logger.info(f"Completed batch {i // batch_size + 1}, sent {sent} messages")
    return results


def _retry_after(response) -> int | None:
    """The seconds Telegram asks to wait before trying again, for a 429; None for any other answer"""
    if response.status_code != 429:
        return None
    try:
        seconds = int(json.loads(response.body)["parameters"]["retry_after"])
    except ValueError, KeyError, TypeError:
        seconds = 1
    return min(max(seconds, 1), MAX_RETRY_AFTER_SECONDS)


async def send_from_admin(msg, environment):
    """Send message from admin account via Telethon, fallback to bot on error"""
    global _user_client

    try:
        user_id = msg["user_id"]

        # A Telegram user id is positive: guests have negative ids of their own (-1, -2, ...)
        if user_id <= 0:
            return {
                "success": False,
                "user_id": user_id,
                "error": "Invalid user ID (guest user)",
                "customer_name": msg.get("customer_name"),
            }

        message = msg["message"]
        parse_mode = msg.get("parse_mode")
        disable_web_page_preview = msg.get("disable_web_page_preview", False)

        # Add TEST prefix in test environment
        if environment == "test":
            message = f"TEST - {message}"

        if _user_client is None:
            _user_client = UserClient()

        await _user_client.send_message(user_id, message, parse_mode, disable_web_page_preview)

        return {"success": True, "user_id": user_id}
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error sending from admin to {msg.get('user_id')}: {error_msg}")

        # If entity not found, return error (don't fallback - admin needs to interact with user first)
        if "Could not find the input entity" in error_msg:
            return {
                "success": False,
                "user_id": msg.get("user_id"),
                "error": "User not in admin contacts",
                "customer_name": msg.get("customer_name"),
            }

        return {
            "success": False,
            "user_id": msg.get("user_id"),
            "error": error_msg,
            "customer_name": msg.get("customer_name"),
        }


async def send_from_bot(msg, environment, bot_token):
    """Send message from bot account"""
    try:
        user_id = msg["user_id"]
        message = msg["message"]
        parse_mode = msg.get("parse_mode")
        disable_web_page_preview = msg.get("disable_web_page_preview", False)

        # Add TEST prefix in test environment
        if environment == "test":
            message = f"TEST - {message}"

        payload = {"chat_id": user_id, "text": message}

        if parse_mode:
            payload["parse_mode"] = parse_mode
        if disable_web_page_preview:
            payload["disable_web_page_preview"] = True

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        for attempt in range(1, BOT_SEND_ATTEMPTS + 1):
            response = await loop.run_in_executor(None, lambda: TelegramClient(bot_token).call("sendMessage", payload))
            retry_after = _retry_after(response)
            if retry_after is None or attempt == BOT_SEND_ATTEMPTS:
                break
            logger.warning(f"Telegram rate limit, retrying after {retry_after}s (attempt {attempt})")
            await _pause(retry_after)

        if response.ok:
            return {"success": True, "user_id": user_id}
        return {
            "success": False,
            "user_id": user_id,
            # The failure report goes to the admin's chat: Telegram's answer, never an exception (it holds the token)
            "error": response.body or "No answer from Telegram",
            "customer_name": msg.get("customer_name"),
        }

    except Exception as e:
        logger.error(f"Error sending from bot to {msg.get('user_id')}: {type(e).__name__}")
        return {
            "success": False,
            "user_id": msg.get("user_id"),
            "error": type(e).__name__,
            "customer_name": msg.get("customer_name"),
        }


async def notify_admin_of_failures(failures, environment, bot_token, language=DEFAULT_LANGUAGE):
    """Tell the admin, in their language, which messages were not delivered"""
    try:
        unknown = text(language, "unknown")
        lines = [
            text(
                language,
                "message_sender_failure_line",
                # The result holds the key with None when the message had no name or id
                name=failure.get("customer_name") or unknown,
                user_id=failure.get("user_id") or unknown,
                error=(failure.get("error") or text(language, "unknown_error"))[:100],
            )
            for failure in failures
        ]
        message = text(language, "message_sender_failures", lines="\n\n".join(lines))

        if environment == "test":
            message = f"TEST - {message}"

        payload = {"chat_id": ADMIN_USER_ID, "text": message}

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: TelegramClient(bot_token).call("sendMessage", payload))

    except Exception as e:
        logger.error(f"Failed to notify admin of failures: {type(e).__name__}")
