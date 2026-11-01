from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from handlers.base_handler import BaseHandler
from models.entities import DiscountPeriod, DiscountStatus


class DiscountCommands(BaseHandler):
    def handle_create_discount(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /create_discount command"""
        error = self._validate_args(args, 1, "usage_create_discount", chat_id)
        if error:
            return error

        try:
            percentage = float(args[0])
            hours = int(args[1]) if len(args) > 1 else 24  # Default 24 hours

            if percentage <= 0 or percentage >= 100:
                return self._send_error(chat_id, "discount_percentage_invalid", "invalid_percentage", user_id=chat_id)

            if hours <= 0:
                return self._send_error(chat_id, "discount_duration_invalid", "invalid_duration", user_id=chat_id)

            # Check for existing active discount
            existing = self.db.get_active_discount()
            if existing:
                return self._send_error(
                    chat_id,
                    "discount_already_exists",
                    "discount_exists",
                    user_id=chat_id,
                    percentage=existing.discount_percentage,
                )

            # Create discount
            end_time = datetime.now(UTC) + timedelta(hours=hours)
            discount = DiscountPeriod(discount_percentage=Decimal(str(percentage)), end_time=end_time)

            if self.db.create_discount(discount):
                from utils.timezone import to_cet_string

                self._send_message(
                    chat_id,
                    self._t("discount_created", chat_id, percentage=percentage, end_time=to_cet_string(end_time)),
                )
                return {"status": "success"}
            else:
                return self._send_error(chat_id, "failed_create_discount", "error", user_id=chat_id)

        except ValueError:
            return self._send_error(chat_id, "invalid_percentage_format", "invalid_format", user_id=chat_id)

    def handle_cancel_discount(self, chat_id: int) -> dict[str, Any]:
        """Handle /cancel_discount command"""
        discount = self.db.get_active_discount()
        if not discount:
            return self._send_error(chat_id, "no_active_discount", "no_discount", user_id=chat_id)

        if self.db.update_discount(discount.discount_id, {"status": DiscountStatus.CANCELLED.value}):
            return self._send_success(
                chat_id, "discount_cancelled", user_id=chat_id, percentage=discount.discount_percentage
            )
        else:
            return self._send_error(chat_id, "failed_cancel_discount", "error", user_id=chat_id)

    def handle_view_discount(self, chat_id: int) -> dict[str, Any]:
        """Handle /view_discount command"""
        discount = self.db.get_active_discount()
        if not discount:
            return self._send_error(chat_id, "no_active_discount_info", "no_discount", user_id=chat_id)

        from utils.timezone import to_cet_string

        if discount.end_time:
            self._send_message(
                chat_id,
                self._t(
                    "active_discount_status",
                    chat_id,
                    percentage=discount.discount_percentage,
                    start_time=to_cet_string(discount.start_time),
                    end_time=to_cet_string(discount.end_time),
                ),
            )
        else:
            self._send_message(
                chat_id,
                self._t(
                    "active_discount_unlimited",
                    chat_id,
                    percentage=discount.discount_percentage,
                    start_time=to_cet_string(discount.start_time),
                ),
            )
        return {"status": "success"}
