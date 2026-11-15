"""/my_data: a customer downloads all data the bot stores about them, at most once per 30 days.

This (webhook) side only does the cheap part: claim the monthly slot atomically and hand the work
to the DataExporter Lambda. See data_exporter.py for the export itself.
"""

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from handlers.base_handler import BaseHandler
from services.data_export import DATA_EXPORT_MIN_INTERVAL_SECONDS
from utils.timezone import to_cet_string

logger = logging.getLogger()


class DataExportCommands(BaseHandler):
    def handle_my_data(self, user_id: int) -> dict[str, Any]:
        """Handle /my_data. Everything goes to the user's private chat, whatever chat the command came from."""
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            return {"status": "not_found"}

        now = int(time.time())
        claim = self.db.claim_data_export(customer.customer_id, now, DATA_EXPORT_MIN_INTERVAL_SECONDS)

        if claim is None:
            self._send_message(user_id, self._t("data_export_failed", user_id))
            return {"status": "error"}

        if not claim.claimed:
            if claim.last_export_at is None:  # No earlier export, so the claim failed for another reason
                self._send_message(user_id, self._t("data_export_failed", user_id))
                return {"status": "error"}
            next_at = datetime.fromtimestamp(claim.last_export_at + DATA_EXPORT_MIN_INTERVAL_SECONDS, UTC)
            self._send_message(
                user_id, self._t("data_export_too_soon", user_id, date=to_cet_string(next_at, "%Y-%m-%d %H:%M"))
            )
            return {"status": "rate_limited"}

        if not self._invoke_exporter(customer.customer_id, user_id, now, claim.previous):
            self.db.release_data_export_claim(customer.customer_id, now, claim.previous)
            self._send_message(user_id, self._t("data_export_failed", user_id))
            return {"status": "error"}

        self._send_message(user_id, self._t("data_export_started", user_id))
        return {"status": "success"}

    def _invoke_exporter(self, customer_id: str, chat_id: int, claimed_at: int, previous: int | None) -> bool:
        """Start the DataExporter Lambda asynchronously. Returns False when it could not be started."""
        try:
            import boto3

            function_name = os.environ.get(
                "DATA_EXPORT_LAMBDA_NAME", f"ubbc-bot-{os.environ.get('ENVIRONMENT', 'test')}-data-exporter"
            )
            payload = {
                "customer_id": customer_id,
                "chat_id": chat_id,
                "claimed_at": claimed_at,
                "previous": previous,
                "environment": os.environ.get("ENVIRONMENT", "test"),
            }
            boto3.client("lambda").invoke(
                FunctionName=function_name, InvocationType="Event", Payload=json.dumps(payload)
            )
            logger.info(f"Data export started for customer {customer_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to start the data export for customer {customer_id}: {e}")
            return False
