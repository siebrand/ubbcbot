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

    def handle_export_user_data(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /export_user_data (admin): build the same zip for a customer who asked by email.

        The file goes to the admin's private chat, not to the customer, and is not limited to once a month.
        """
        if not args:
            self._send_message(chat_id, self._t("usage_export_user_data", chat_id))
            return {"status": "invalid_args"}

        customer, error = self._find_customer_with_disambiguation(" ".join(args), chat_id, "export_user_data_select")
        if error:
            return error

        return self._start_admin_export(chat_id, customer)

    def handle_export_user_data_select(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Handle user selection from disambiguation for /export_user_data"""
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t("user_not_found", chat_id, identifier=customer_id))
            return {"status": "user_not_found"}

        return self._start_admin_export(chat_id, customer)

    def _start_admin_export(self, chat_id: int, customer) -> dict[str, Any]:
        if not self._invoke_exporter(customer.customer_id, self.admin_user_id, None, None):
            self._send_message(chat_id, self._t("data_export_failed", chat_id))
            return {"status": "error"}

        self._send_message(chat_id, self._t("export_user_data_started", chat_id, label=self._customer_label(customer)))
        return {"status": "success"}

    def _customer_label(self, customer) -> str:
        """Plain-text label for admin messages: the name plus the short customer ID to tell namesakes apart"""
        name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t("unknown", user_id=None)
        return f"{name} ({customer.customer_id[:8]})"

    def handle_clear_data_export(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /clear_data_export (admin): let a customer use /my_data again before the 30 days are over"""
        if not args:
            self._send_message(chat_id, self._t("usage_clear_data_export", chat_id))
            return {"status": "invalid_args"}

        customer, error = self._find_customer_with_disambiguation(" ".join(args), chat_id, "clear_data_export_select")
        if error:
            return error

        return self._clear_data_export(chat_id, customer)

    def handle_clear_data_export_select(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Handle user selection from disambiguation for /clear_data_export"""
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t("user_not_found", chat_id, identifier=customer_id))
            return {"status": "user_not_found"}

        return self._clear_data_export(chat_id, customer)

    def _clear_data_export(self, chat_id: int, customer) -> dict[str, Any]:
        # The customer found by name comes from a cached list; read the record itself for the export time
        current = self.db.get_customer(customer.customer_id)
        label = self._customer_label(customer)

        if current is None or current.last_data_export_at is None:
            self._send_message(chat_id, self._t("clear_data_export_nothing", chat_id, label=label))
            return {"status": "nothing_to_clear"}

        if not self.db.clear_data_export(customer.customer_id):
            self._send_message(chat_id, self._t("clear_data_export_failed", chat_id, label=label))
            return {"status": "error"}

        logger.info(f"Cleared the last data export time of customer {customer.customer_id}")
        self._send_message(chat_id, self._t("clear_data_export_done", chat_id, label=label))
        return {"status": "success"}

    def _invoke_exporter(self, customer_id: str, chat_id: int, claimed_at: int | None, previous: int | None) -> bool:
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
