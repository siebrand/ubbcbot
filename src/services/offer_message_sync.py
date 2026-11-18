"""Handing a large re-edit of offer announcements to the NotificationSender Lambda.

The group announcement and a few subscriber messages are edited inline (BaseHandler.sync_offer_messages); with many
subscribers that would take too long for the webhook, so the edits run asynchronously in notification_sender.py.
"""

import json
import logging
import os

import boto3

logger = logging.getLogger()


def notification_lambda_name(environment: str) -> str:
    return os.environ.get("NOTIFICATION_LAMBDA_NAME", f"ubbc-bot-{environment}-notification-sender")


def start_subscriber_sync(offer_id: int, cancelled: bool, environment: str) -> bool:
    """Ask the NotificationSender Lambda to re-edit the subscriber messages of an offer. Never raises."""
    payload = {
        "action": "sync_offer_messages",
        # From DynamoDB the id can be a Decimal, which json cannot write
        "offer_id": int(offer_id),
        "cancelled": cancelled,
        "environment": environment,
    }
    try:
        boto3.client("lambda").invoke(
            FunctionName=notification_lambda_name(environment),
            InvocationType="Event",
            Payload=json.dumps(payload),
        )
        logger.info(f"Async subscriber-message sync invoked for offer {offer_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to invoke async subscriber-message sync for offer {offer_id}: {e}")
        return False
