"""Async Lambda that builds and sends a customer's personal data export.

The webhook handler claims the monthly slot and invokes this function asynchronously, so the zip
build (which reads several tables) cannot hold up Telegram's webhook call. The finished zip is
sent to the customer's private chat and tracked for deletion, like the admin order exports.
If anything fails after the claim, the claim is released so a failure does not use up the month.
"""

import logging
from datetime import UTC, datetime

from config import ADMIN_USER_ID
from handlers.base_handler import BaseHandler
from models.entities import Customer
from services.data_export import DataExportService
from services.database import DynamoDBService
from services.export_expiry import EXPORT_LIFETIME_SECONDS
from utils.log_redaction import configure_logging

logger = logging.getLogger()
configure_logging()


def lambda_handler(event, context):
    """Event: customer_id, chat_id, claimed_at, previous (last export before the claim), environment"""
    environment = event.get("environment", "test")
    customer_id = event["customer_id"]
    chat_id = event["chat_id"]
    claimed_at = event["claimed_at"]
    previous = event.get("previous")

    db = None
    handler = None
    try:
        import boto3

        token_param = f"/ubbc-bot/{environment}/telegram-bot-token"
        telegram_token = boto3.client("ssm").get_parameter(Name=token_param, WithDecryption=True)["Parameter"]["Value"]

        db = DynamoDBService()
        handler = DataExporter(db, ADMIN_USER_ID, environment, telegram_token)

        status = handler.export(customer_id, chat_id)
        if status != "sent":
            _release(db, customer_id, claimed_at, previous)
        return {"statusCode": 200 if status == "sent" else 500, "body": status}
    except Exception as e:
        logger.error(f"Error in data exporter for customer {customer_id}: {e}")
        if db is not None:
            _release(db, customer_id, claimed_at, previous)
            if handler is not None:
                handler.notify_failure(chat_id)
        return {"statusCode": 500, "body": "error"}


def _release(db, customer_id: str, claimed_at: int, previous: int | None) -> None:
    released = db.release_data_export_claim(customer_id, claimed_at, previous)
    logger.info(f"Released data export claim for customer {customer_id}: {released}")


class DataExporter(BaseHandler):
    """Builds the zip and sends it to the customer"""

    def export(self, customer_id: str, chat_id: int) -> str:
        """Returns "sent", "customer_not_found" or "send_failed" """
        # Clear earlier exports that have expired before adding a new one
        self.expire_exports(force=True)

        customer = self.db.get_customer(customer_id)
        if not customer:
            logger.warning(f"Customer {customer_id} no longer exists, nothing to export")
            return "customer_not_found"

        now = datetime.now(UTC)
        content = self._build(customer, now)
        filename = f"ubbc_my_data_{self.environment}_{now:%Y%m%d}.zip"
        caption = self._t("data_export_caption", chat_id, minutes=EXPORT_LIFETIME_SECONDS // 60)

        result = self._send_document_message(chat_id, content, filename, caption, mime_type="application/zip")
        if not result.get("success"):
            self.notify_failure(chat_id)
            return "send_failed"

        self.export_expiry.track(chat_id, result["message_id"])
        return "sent"

    def _build(self, customer: Customer, now: datetime) -> bytes:
        def translate(key: str, **params):
            return self._t(key, customer.telegram_user_id, **params)

        return DataExportService(self.db, translate).build_zip(customer, now)

    def notify_failure(self, chat_id: int) -> None:
        try:
            self._send_message(chat_id, self._t("data_export_failed", chat_id))
        except Exception as e:
            logger.error(f"Could not tell the customer the data export failed: {e}")
