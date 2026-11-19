"""Keeping the announcement messages of an offer in step with the offer.

An announcement is tracked per message (the group post, one DM per subscriber). When the offer changes (name, price,
description, status), every tracked message is re-rendered from the offer as it is now. The group post and a few
subscriber messages are edited inline; with many subscribers that would take too long for the webhook, so the edits
run asynchronously in notification_sender.py.
"""

import json
import logging
import os
import time
from collections.abc import Callable

import boto3

from services.offer_message_builder import OfferMessageBuilder

logger = logging.getLogger()

INLINE_SUBSCRIBER_LIMIT = 10  # more subscriber messages than this are edited by the NotificationSender Lambda
BATCH_SIZE = 20  # the Lambda edits in batches, with a pause between them for Telegram's rate limit


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


def _kind(row) -> str:
    return getattr(row, "kind", "group")


class OfferAnnouncements:
    """The tracked announcement messages of an offer, re-rendered from the offer as it is now"""

    def __init__(
        self,
        db,
        edit_message: Callable[..., dict],
        translate_group: Callable[[str], str],
        bot_username: Callable[[], str],
        environment: str,
    ):
        self.db = db
        self.edit_message = edit_message  # BaseHandler._edit_message_text
        self.translate_group = translate_group  # announcements are always in the group language
        self.bot_username = bot_username
        self.environment = environment

    def render(self, offer, cancelled: bool = False) -> tuple:
        """The text and keyboard of an announcement: order buttons when active, none when sold out or cancelled"""
        return OfferMessageBuilder(self.bot_username(), self.translate_group).build(offer, cancelled=cancelled)

    def sync(self, offer, cancelled: bool = False) -> None:
        """Edit the group post first (one call, the most important), then the subscriber messages: inline when there
        are a few, by the NotificationSender Lambda when there are many. ``cancelled``: the stored status is INACTIVE
        but the message must show the cancelled marker."""
        rows = self.db.get_notification_messages_by_offer(offer.offer_id)
        text, reply_markup = self.render(offer, cancelled)

        for row in (r for r in rows if _kind(r) == "group"):
            self.edit(row, text, reply_markup)

        subscriber_rows = [r for r in rows if _kind(r) == "subscriber"]
        if len(subscriber_rows) > INLINE_SUBSCRIBER_LIMIT:
            start_subscriber_sync(offer.offer_id, cancelled, self.environment)
            return
        for row in subscriber_rows:
            self.edit(row, text, reply_markup)

    def sync_subscribers(self, offer, cancelled: bool = False) -> tuple[int, int]:
        """The NotificationSender Lambda's part: edit the subscriber messages in rate-limited batches.

        Returns (edited, failed). The Lambda has no DeleteItem on the notifications table, so a message that is gone
        keeps its row until the 168h TTL removes it.
        """
        text, reply_markup = self.render(offer, cancelled)
        rows = [r for r in self.db.get_notification_messages_by_offer(offer.offer_id) if _kind(r) == "subscriber"]

        edited = failed = 0
        for i in range(0, len(rows), BATCH_SIZE):
            for row in rows[i : i + BATCH_SIZE]:
                if self.edit(row, text, reply_markup, prune=False):
                    edited += 1
                else:
                    failed += 1
            if i + BATCH_SIZE < len(rows):
                time.sleep(0.5)
        return edited, failed

    def edit(self, row, text: str, reply_markup, prune: bool = True) -> bool:
        """Edit one tracked message; delete its row (``prune``) when Telegram says the message is gone.

        A ``None`` reply_markup means "no buttons". Telegram leaves the keyboard as it is when reply_markup is
        omitted, so an explicit empty keyboard is sent to remove the order buttons.
        """
        markup = reply_markup if reply_markup is not None else {"inline_keyboard": []}
        result = self.edit_message(row.chat_id, row.message_id, text, parse_mode="HTML", reply_markup=markup)
        if prune and result.get("not_found"):
            try:
                self.db.delete_notification_message(row.notification_id)
            except Exception as e:
                logger.error(f"Failed to prune notification row {row.notification_id}: {e}")
        return result.get("success", False)
