import json
import os
from decimal import Decimal
from typing import Any

import boto3

from handlers.payment_message import PaymentMessageMixin
from models.entities import EditContext, OrderStatus
from services.payment_matching import age_key, cents, find_payment_match, parse_amount, selection_token
from utils.pagination import PaginationUtils

from .base_order_handler import BaseOrderHandler


class OrderStatusManagement(PaymentMessageMixin, BaseOrderHandler):
    """Handles order status management functionality"""

    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.lambda_client = boto3.client("lambda")
        self.message_sender_lambda = os.environ.get("MESSAGE_SENDER_LAMBDA_NAME")

    def handle_send_delivery_overviews(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /send_delivery_overviews command"""
        customers_with_ready_orders = self.db.get_approved_customers_with_orders(OrderStatus.LABELING_COMPLETED.value)

        if not customers_with_ready_orders:
            self._send_message(chat_id, self._t("no_customers_ready_overview", user_id=self.admin_user_id))
            return {"status": "no_customers"}

        total_customers = len(customers_with_ready_orders)
        batches_needed = (total_customers + 49) // 50  # Round up

        message = self._t(
            "delivery_overview_summary", chat_id, total_customers=total_customers, batches_needed=batches_needed
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": self._t("start_sending_overviews", user_id=self.admin_user_id),
                        "callback_data": "start_send_overviews",
                    },
                    {"text": self._t("cancel", user_id=self.admin_user_id), "callback_data": "cancel_action"},
                ]
            ]
        }

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "confirmation_shown"}

    def handle_process_payment(self, chat_id: int, args: list, page: int = 1) -> dict[str, Any]:
        """Handle /process_payment command with pagination"""
        customers_awaiting_payment = self.db.get_approved_customers_with_orders(OrderStatus.AWAITING_PAYMENT.value)

        if not customers_awaiting_payment:
            self._send_message(
                chat_id,
                self._t("no_customers_awaiting_payment", user_id=self.admin_user_id),
                reply_markup=self._build_admin_menu_keyboard(),
            )
            return {"status": "no_customers"}

        # Sort alphabetically by last name, then first name
        customers_awaiting_payment.sort(key=lambda x: (x[0].last_name or "", x[0].first_name or ""))

        # Paginate results
        page_customers, total_pages = PaginationUtils.paginate_list(customers_awaiting_payment, page, 10)

        # Show customers as buttons only (name + amount + order count on the button itself)
        message = self._t(
            "customers_awaiting_payment_title", user_id=self.admin_user_id, page=page, total_pages=total_pages
        )
        keyboard_rows = []

        for customer, orders in page_customers:
            total_amount = sum(order.amount_due for order in orders)

            # Button text: ✓ Last, First €amount (N)
            last_name = customer.last_name or ""
            first_name = customer.first_name or self._t("unknown", user_id=self.admin_user_id)
            button_text = f"✓ {last_name}, {first_name} €{total_amount:.2f} ({len(orders)})".strip()
            keyboard_rows.append(
                [
                    # Pays everything, as before
                    {"text": button_text, "callback_data": f"process_payment_{customer.customer_id}_{page}"},
                    # Asks for the amount received and pays the oldest open orders that add up to it
                    {
                        "text": self._t("payment_amount_btn", chat_id),
                        "callback_data": f"payment_amount_{customer.customer_id}_{page}",
                    },
                ]
            )

        # Add pagination keyboard if needed
        if total_pages > 1:
            pagination_keyboard = PaginationUtils.build_pagination_keyboard(
                page, total_pages, "process_payment", enhanced=True
            )
            keyboard_rows.extend(pagination_keyboard["inline_keyboard"])

        # Add Done button
        keyboard_rows.append(
            [{"text": self._t("done_general", user_id=self.admin_user_id), "callback_data": "cancel_action"}]
        )

        keyboard = {"inline_keyboard": keyboard_rows}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "customers_shown"}

    # ------------------------------------------------------------ partial payments (partial-payments-design.md)
    def _open_orders_of(self, customer_id: str) -> list:
        return [
            o for o in self.db.get_orders_by_customer(customer_id) if o.status == OrderStatus.AWAITING_PAYMENT.value
        ]

    def _customer_name(self, customer, chat_id: int) -> str:
        return " ".join(part for part in (customer.first_name, customer.last_name) if part) or self._t(
            "unknown", chat_id
        )

    def handle_payment_amount_answer(self, chat_id: int, entity_id: str, text: str) -> dict[str, Any]:
        """The amount the admin received from a customer (entity "<customer_id>_<page>"): propose the oldest open
        orders whose amounts due add up to it. An invalid amount is asked again."""
        customer_id, _, page_text = entity_id.rpartition("_")
        page = int(page_text) if page_text.isdigit() else 1
        amount = parse_amount(text)
        if amount is None:
            self.db.create_edit_context(
                EditContext(chat_id=chat_id, edit_type="payment_amount_input", entity_id=entity_id)
            )
            self._send_message(chat_id, self._t("payment_amount_invalid", chat_id))
            return {"status": "invalid_amount"}

        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t("customer_not_found", chat_id))
            return {"status": "customer_not_found"}
        open_orders = self._open_orders_of(customer_id)
        if not open_orders:
            self._send_message(
                chat_id, self._t("no_orders_awaiting_payment", chat_id, customer_name=customer.first_name)
            )
            return {"status": "no_orders"}

        name = self._customer_name(customer, chat_id)
        result = find_payment_match(open_orders, amount)
        if result.too_many:
            self._send_message(chat_id, self._t("payment_match_too_many", chat_id, customer_name=name))
            self.handle_process_payment(chat_id, [], page)
            return {"status": "too_many"}
        if result.match is None:
            closest = result.closest_total if result.closest_total is not None else Decimal("0")
            self._send_message(
                chat_id, self._t("payment_match_none", chat_id, customer_name=name, amount=amount, closest=closest)
            )
            self.handle_process_payment(chat_id, [], page)
            return {"status": "no_match"}

        self._send_payment_proposal(chat_id, customer, name, amount, result.match, open_orders, page)
        return {"status": "proposal_shown"}

    def _send_payment_proposal(self, chat_id: int, customer, name, amount, match, open_orders, page: int) -> None:
        """What would be paid, what is settled along (nothing due) and what stays open; confirm or cancel"""
        settled = {o.order_id for o in match.selected + match.settle_with}
        staying = [o for o in open_orders if o.order_id not in settled]
        message = self._t(
            "payment_match_proposal",
            chat_id,
            customer_name=name,
            amount=amount,
            orders="\n".join(self._payment_line(o, chat_id) for o in match.selected + match.settle_with),
            open_total=sum((o.amount_due for o in staying), Decimal("0")),
            open_count=len(staying),
        )
        confirm = f"payok_{customer.customer_id}_{cents(amount)}_{selection_token(match.selected)}_{page}"
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": self._t("payment_match_confirm_btn", chat_id), "callback_data": confirm},
                    {"text": self._t("cancel", chat_id), "callback_data": "cancel_action"},
                ]
            ]
        }
        self._send_message(chat_id, message, reply_markup=keyboard)

    def _payment_line(self, order, chat_id: int) -> str:
        from utils.timezone import to_cet_string

        offer = self.db.get_offer(order.offer_id)
        offer_name = offer.name if offer else self._t("unknown", chat_id)
        date = to_cet_string(order.update_date or order.created_at, "%Y-%m-%d")
        return f"• {offer_name} ({date}) €{max(order.amount_due, Decimal('0')):.2f}"

    def handle_payment_confirm(self, chat_id: int, customer_id: str, amount_cents: int, token: str, page: int):
        """The admin confirmed the proposal. Nothing of it is stored: search again, and pay only when the same
        orders come out (an order that changed in between, or a second tap, gives another or no selection)."""
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t("customer_not_found", chat_id))
            return {"status": "customer_not_found"}
        result = find_payment_match(self._open_orders_of(customer_id), Decimal(amount_cents) / 100)
        if result.match is None or selection_token(result.match.selected) != token:
            self._send_message(chat_id, self._t("payment_match_changed", chat_id))
            self.handle_process_payment(chat_id, [], page)
            return {"status": "match_changed"}

        to_pay = result.match.selected + result.match.settle_with
        # Each order only while it still awaits payment; the payment events are written for those that changed
        paid_ids = set(
            self.db.batch_update_order_status(
                [o.order_id for o in to_pay],
                OrderStatus.COMPLETED.value,
                self.admin_user_id,
                from_status=OrderStatus.AWAITING_PAYMENT.value,
            )
        )
        paid = [o for o in to_pay if o.order_id in paid_ids]
        name = self._customer_name(customer, chat_id)
        if len(paid) < len(to_pay):
            self._send_message(
                chat_id,
                self._t(
                    "payment_partly_marked",
                    chat_id,
                    customer_name=name,
                    failed=len(to_pay) - len(paid),
                    count=len(to_pay),
                ),
            )
        if paid:
            self._send_message(
                chat_id,
                self._t(
                    "payment_confirmed",
                    chat_id,
                    customer_name=name,
                    updated_count=len(paid),
                    total_amount=sum((o.amount_due for o in paid), Decimal("0")),
                ),
            )
            self._tell_customer_of_payment(chat_id, customer, name, paid)
        self.handle_process_payment(chat_id, [], page)
        return {"status": "paid" if paid else "nothing_paid", "paid": len(paid)}

    def _tell_customer_of_payment(self, chat_id: int, customer, name: str, paid: list) -> None:
        """From the admin account, in the customer's language: what was received and, when orders remain open, what
        is still to pay. Not for guests. A failed send does not undo the payment; the admin is told."""
        if customer.is_guest:
            return
        language_of = customer.telegram_user_id
        amount = sum((o.amount_due for o in paid), Decimal("0"))
        still_open = self._open_orders_of(customer.customer_id)
        if still_open:
            message = self._t(
                "payment_partial_received_notification",
                language_of,
                amount=amount,
                count=len(paid),
                open_total=sum((o.amount_due for o in still_open), Decimal("0")),
                open_count=len(still_open),
            )
        else:
            message = self._t(
                "payment_received_notification",
                language_of,
                total_amount=amount,
                location=self._escape_html(customer.location),
            )
        if not self._send_user_message(customer.telegram_user_id, message).get("success"):
            self._send_message(chat_id, self._t("payment_customer_not_reached", chat_id, customer_name=name))

    def handle_list_open_payments(self, chat_id: int, args: list, page: int = 1) -> dict[str, Any]:
        """/list_open_payments: read only. Per customer with open orders: the open total (amount due), the number of
        orders and the age in days of the oldest open order; oldest first, 10 per page."""
        from datetime import UTC, datetime

        customers = self.db.get_approved_customers_with_orders(OrderStatus.AWAITING_PAYMENT.value)
        back = [{"text": self._t("back_to_admin", chat_id), "callback_data": "admin:main"}]
        if not customers:
            self._send_message(chat_id, self._t("no_open_payments", chat_id), reply_markup={"inline_keyboard": [back]})
            return {"status": "no_open_payments"}

        customers.sort(key=lambda entry: min(age_key(order) for order in entry[1]))
        page_customers, total_pages = PaginationUtils.paginate_list(customers, page, 10)
        now = datetime.now(UTC)
        lines = []
        for customer, orders in page_customers:
            oldest = min(orders, key=age_key)
            lines.append(
                self._t(
                    "list_open_payments_line",
                    chat_id,
                    name=self._customer_name(customer, chat_id),
                    amount=sum((o.amount_due for o in orders), Decimal("0")),
                    count=len(orders),
                    days=max((now - age_key(oldest)[0]).days, 0),
                )
            )
        page_label = self._t("page_indicator", chat_id, page=page, total_pages=total_pages)
        message = self._t("list_open_payments_title", chat_id, page=page_label) + "\n\n" + "\n".join(lines)

        rows = []
        if total_pages > 1:
            rows.extend(
                PaginationUtils.build_pagination_keyboard(page, total_pages, "list_open_payments", enhanced=True)[
                    "inline_keyboard"
                ]
            )
        rows.append([{"text": self._t("open_payments_process_btn", chat_id), "callback_data": "cmd:process_payment"}])
        rows.append(back)
        self._send_message(chat_id, message, reply_markup={"inline_keyboard": rows})
        return {"status": "open_payments_shown"}

    def handle_failed_notifications(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /failed_notifications: the labeled orders that have no delivery overview yet.

        An overview moves its orders to AWAITING_PAYMENT before it is sent (asynchronously), so a send that failed
        is not listed here: the message sender reports those to the admin. What stays LABELING_COMPLETED is what was
        never sent, e.g. a batch whose payment link was never given."""
        unsent = self.db.get_approved_customers_with_orders(OrderStatus.LABELING_COMPLETED.value)
        keyboard = {"inline_keyboard": [[{"text": self._t("back_to_admin", chat_id), "callback_data": "admin:main"}]]}

        if not unsent:
            self._send_message(chat_id, self._t("no_failed_notifications", chat_id), reply_markup=keyboard)
            return {"status": "no_failed"}

        message = self._t("failed_delivery_notifications_title", chat_id) + "\n\n"

        for customer, orders in unsent:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t(
                "unknown", chat_id
            )
            username = f" (@{customer.username})" if customer.username else ""
            total_amount = sum(order.amount_due for order in orders)
            message += f"👤 {customer_name}{username}\n"
            message += self._t("unsent_overview_total", chat_id, amount=total_amount, count=len(orders)) + "\n"
            for order in orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t("unknown", chat_id)
                message += f"   • {order.quantity}x {offer_name} - €{order.total_price:.2f}\n"
            message += "\n"

        message += self._t("unsent_overviews_hint", chat_id)

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "failed_shown"}

    def handle_send_payment_reminder(self, chat_id: int, args: list, page: int = 1) -> dict[str, Any]:
        """Handle /send_payment_reminder command with pagination"""
        customers_awaiting_payment = self.db.get_approved_customers_with_orders(OrderStatus.AWAITING_PAYMENT.value)

        if not customers_awaiting_payment:
            self._send_message(
                chat_id,
                self._t("no_customers_awaiting_payment", user_id=self.admin_user_id),
                reply_markup=self._build_admin_menu_keyboard(),
            )
            return {"status": "no_customers"}

        # Sort alphabetically by last name, then first name
        customers_awaiting_payment.sort(key=lambda x: (x[0].last_name or "", x[0].first_name or ""))

        # Paginate results
        page_customers, total_pages = PaginationUtils.paginate_list(customers_awaiting_payment, page, 10)

        # Show customers with reminder buttons
        page_label = self._t("page_indicator", chat_id, page=page, total_pages=total_pages)
        message = self._t("payment_reminders_title", chat_id, page=page_label) + "\n\n"
        keyboard_rows = []

        for customer, orders in page_customers:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t(
                "unknown", chat_id
            )
            total_amount = sum(order.amount_due for order in orders)
            message += (
                self._t(
                    "payment_reminder_customer_line",
                    chat_id,
                    name=customer_name,
                    amount=f"{total_amount:.2f}",
                    count=len(orders),
                )
                + "\n"
            )

            # Button text: 🔔 Last, First €amount
            last_name = customer.last_name or ""
            first_name = customer.first_name or self._t("unknown", chat_id)
            button_text = f"🔔 {last_name}, {first_name} €{total_amount:.2f}".strip()
            keyboard_rows.append(
                [{"text": button_text, "callback_data": f"remind_payment_{customer.customer_id}_{page}"}]
            )

        # Add pagination keyboard if needed
        if total_pages > 1:
            pagination_keyboard = PaginationUtils.build_pagination_keyboard(
                page, total_pages, "remind_payment", enhanced=True
            )
            keyboard_rows.extend(pagination_keyboard["inline_keyboard"])

        # Add Done button
        keyboard_rows.append(
            [{"text": self._t("done_general", user_id=self.admin_user_id), "callback_data": "cancel_action"}]
        )

        keyboard = {"inline_keyboard": keyboard_rows}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "customers_shown"}

    def handle_send_payment_reminder_to_customer(
        self, chat_id: int, customer_id: str, current_page: int = 1
    ) -> dict[str, Any]:
        """Send payment reminder to a specific customer"""
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t("customer_not_found", user_id=self.admin_user_id))
            return {"status": "customer_not_found"}

        # Get awaiting payment orders
        orders = self.db.get_orders_by_customer(customer_id)
        awaiting_payment_orders = [o for o in orders if o.status == OrderStatus.AWAITING_PAYMENT.value]

        if not awaiting_payment_orders:
            self._send_message(
                chat_id,
                self._t("no_orders_awaiting_payment", user_id=self.admin_user_id, customer_name=customer.first_name),
            )
            return {"status": "no_orders"}

        payment_link = self._payment_link_for(awaiting_payment_orders)
        if not payment_link:
            self._send_message(chat_id, self._t("no_payment_link_stored", user_id=self.admin_user_id))
            return {"status": "no_payment_link"}

        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t(
            "unknown", user_id=self.admin_user_id
        )
        message = self._build_delivery_message(customer, awaiting_payment_orders, [], payment_link, is_reminder=True)

        # Ensure message is a plain string (convert any Decimal formatting)
        message = str(message)

        # Send from admin account (not bot) for regular customers
        if customer.is_guest:
            # For guests, send to admin with customer context (sent as HTML, so the name is escaped)
            guest_name = self._html_customer_name(customer)
            title = self._t("payment_reminder_for", self.admin_user_id, customer_name=guest_name)
            admin_message = f"🔔 {title}\n\n{message}"
            result = self._send_message(self.admin_user_id, admin_message, parse_mode="HTML")
        else:
            # For regular customers, send directly from admin account
            result = self._send_user_message(customer.telegram_user_id, message)

        if result.get("success"):
            self._send_message(
                chat_id, self._t("payment_reminder_sent", user_id=self.admin_user_id, customer_name=customer_name)
            )
            return self.handle_send_payment_reminder(chat_id, [], current_page)
        else:
            error = result.get("error", "Unknown error")
            self._send_message(
                chat_id,
                self._t("payment_reminder_failed", user_id=self.admin_user_id, customer_name=customer_name)
                + f" ({error})",
            )
            return {"status": "error"}

    def _send_user_message(
        self, user_id: int, message: str, parse_mode: str = "HTML", disable_web_page_preview: bool = True
    ) -> dict[str, Any]:
        """Send message from admin account via MessageSender Lambda"""
        try:
            payload = self._message_sender_event(
                [
                    {
                        "user_id": int(user_id),
                        "message": str(message),
                        "from_admin": True,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": disable_web_page_preview,
                    }
                ]
            )

            response = self.lambda_client.invoke(
                FunctionName=self.message_sender_lambda, InvocationType="RequestResponse", Payload=json.dumps(payload)
            )

            result = json.loads(response["Payload"].read())
            body = json.loads(result.get("body", "{}"))

            if body.get("success_count", 0) > 0:
                return {"success": True}
            else:
                error = body.get("results", [{}])[0].get("error", "Unknown error")
                return {"success": False, "error": error}
        except Exception as e:
            # Shown to the admin: the type only, the text of a Lambda or boto error can name resources
            return {"success": False, "error": type(e).__name__}
