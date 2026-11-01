from decimal import Decimal
from typing import Any

from handlers.base_handler import BaseHandler
from models.entities import EditContext
from services.credit_service import CreditService
from utils.validation import ValidationUtils


class CreditCommands(BaseHandler):
    """Admin commands for credit management"""

    def __init__(self, db, admin_user_id, environment, telegram_token):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.credit_service = CreditService(db)
        self.validation = ValidationUtils(db, self._t)

    def handle_credit(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /credit <username> <amount> [reason] command"""
        if len(args) < 2:
            return self._send_error(chat_id, "usage_credit", "invalid_format", user_id=chat_id)

        username = args[0].lstrip("@")

        try:
            amount = Decimal(args[1])
        except ValueError, TypeError:
            return self._send_error(chat_id, "invalid_amount", "invalid_format", user_id=chat_id)

        reason = " ".join(args[2:]) if len(args) > 2 else ""

        # Require reason for negative amounts
        if amount < 0 and not reason:
            return self._send_error(chat_id, "reason_required_negative", "invalid_format", user_id=chat_id)

        # Find customer using validation utility
        customer, error = self.validation.find_customer_with_disambiguation(
            username, chat_id, "credit_customer", status_filter="approved"
        )

        if error:
            if error.get("status") == "disambiguation_shown":
                context = EditContext(
                    chat_id=chat_id, edit_type="credit_customer_select", entity_id=f"{amount}|{reason}"
                )
                self.db.create_edit_context(context)

            if error.get("keyboard"):
                self._send_message(chat_id, error["message"], reply_markup=error["keyboard"])
            else:
                self._send_message(chat_id, error["message"])
            return error

        # Issue credit
        return self._issue_credit_to_customer(chat_id, customer, amount, reason)

    def handle_credit_customer_select(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Handle customer selection from disambiguation for credit command"""
        context = self.db.get_edit_context_by_chat_id(chat_id)
        if not context or context.edit_type != "credit_customer_select":
            return self._send_error(chat_id, "invalid_format", "error", user_id=chat_id)

        try:
            parts = context.entity_id.split("|", 1)
            amount = Decimal(parts[0])
            reason = parts[1] if len(parts) > 1 else ""
        except ValueError, IndexError:
            self.db.delete_edit_context(context.context_id)
            return self._send_error(chat_id, "invalid_format", "error", user_id=chat_id)

        customer = self.db.get_customer(customer_id)
        if not customer:
            self.db.delete_edit_context(context.context_id)
            return self._send_error(chat_id, "user_not_found", "error", user_id=chat_id, identifier=customer_id)

        self.db.delete_edit_context(context.context_id)
        return self._issue_credit_to_customer(chat_id, customer, amount, reason)

    def _issue_credit_to_customer(self, chat_id: int, customer, amount: Decimal, reason: str) -> dict[str, Any]:
        """Issue credit to a customer and send notifications"""
        success = self.credit_service.issue_credit(customer.customer_id, amount, reason, chat_id)

        if success:
            # Get new balance
            new_balance = self.credit_service.get_customer_credit_balance(customer.customer_id)

            # Notify customer
            if customer.telegram_user_id > 0:
                customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                self._send_message(
                    customer.telegram_user_id,
                    self._t(
                        "credit_notification",
                        customer.telegram_user_id,
                        amount=amount,
                        reason=reason or "No reason provided",
                        balance=new_balance,
                    ),
                )

            # Confirm to admin
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            return self._send_success(
                chat_id, "credit_issued_success", user_id=chat_id, amount=amount, customer_name=customer_name
            )
        else:
            return self._send_error(chat_id, "failed_issue_credit", "error", user_id=chat_id)
