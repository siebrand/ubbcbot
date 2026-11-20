"""The payment message a customer gets: when the order is ready, as a reminder, and on /payment_info."""

from decimal import Decimal

from handlers.base_handler import BaseHandler


class PaymentMessageMixin(BaseHandler):
    """For handlers (it uses `self.db`, `self._t` and `self._escape_html`). The text is sent as HTML."""

    def _payment_link_for(self, orders: list) -> str | None:
        """The link the customer was asked to pay with: that of the batch of their newest order awaiting payment.
        Orders moved before the link was kept with them fall back to the last link that was stored."""
        with_link = [o for o in orders if o.payment_link]
        if with_link:
            return max(with_link, key=lambda o: str(o.update_date or "")).payment_link
        return self.db.get_payment_link()

    def _aggregate_order_lines(self, orders: list, reader: int | None = None) -> list[tuple]:
        """Aggregate orders by offer and sort alphabetically by offer name.

        Returns a list of (offer_name, offer_id, total_quantity, total_price)
        tuples, one per distinct offer, sorted by offer name (case-insensitive).
        Multiple orders of the same offer are combined into a single line.
        """
        grouped: dict = {}
        for order in orders:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else self._t("unknown", reader)
            key = order.offer_id
            if key not in grouped:
                grouped[key] = {"name": offer_name, "offer_id": order.offer_id, "quantity": 0, "total": 0}
            grouped[key]["quantity"] += order.quantity
            grouped[key]["total"] += order.total_price
        rows = [(g["name"], g["offer_id"], g["quantity"], g["total"]) for g in grouped.values()]
        rows.sort(key=lambda r: (r[0] or "").lower())
        return rows

    def _build_delivery_message(
        self, customer, delivered_orders: list, delayed_orders: list, payment_link: str, is_reminder: bool = False
    ) -> str:
        """Build delivery/reminder message for customer"""
        delivered_total = sum(order.total_price for order in delivered_orders)

        # Add title based on message type
        if is_reminder:
            message = self._t("payment_reminder_title", user_id=customer.telegram_user_id) + "\n\n"
            message += self._t("payment_reminder_intro", user_id=customer.telegram_user_id) + "\n\n"
        else:
            message = self._t("delivery_ready_title", user_id=customer.telegram_user_id) + "\n\n"
            message += self._t("delivery_ready_intro", user_id=customer.telegram_user_id) + "\n\n"

        if delivered_orders:
            message += self._t("order_summary_title", user_id=customer.telegram_user_id) + "\n\n"
            for offer_name, offer_id, quantity, line_total in self._aggregate_order_lines(
                delivered_orders, customer.telegram_user_id
            ):
                message += f"- {quantity}x [{offer_id}] {offer_name} — €{line_total:.2f}\n"

            message += (
                "\n" + self._t("total_amount_bold", user_id=customer.telegram_user_id, total=delivered_total) + "\n"
            )
            # Credit used when the overview asked for the payment (audit 5, A2): the same amounts in every reminder
            credit = sum((order.credit_applied or 0 for order in delivered_orders), Decimal("0"))
            to_pay = delivered_total - credit
            if credit > 0:
                message += self._t("credit_used_line", user_id=customer.telegram_user_id, amount=credit) + "\n"
            elif credit < 0:
                message += self._t("debt_added_line", user_id=customer.telegram_user_id, amount=-credit) + "\n"
            if credit:
                message += self._t("amount_to_pay_bold", user_id=customer.telegram_user_id, total=to_pay) + "\n"
            message += "\n"
            if to_pay > 0:
                message += (
                    self._t(
                        "pay_via_payment_request",
                        user_id=customer.telegram_user_id,
                        link=self._escape_html(payment_link),
                        total=to_pay,
                    )
                    + "\n"
                )
            else:
                message += self._t("nothing_to_pay", user_id=customer.telegram_user_id) + "\n"
            message += "━━━━━━━━━━━━━━━━━━━━\n"
            message += (
                self._t(
                    "pickup_location_bold",
                    user_id=customer.telegram_user_id,
                    location=self._escape_html(customer.location or ""),
                )
                + "\n"
            )
            message += "━━━━━━━━━━━━━━━━━━━━\n"
            message += self._t("questions_contact", user_id=customer.telegram_user_id) + "\n\n"

        if delayed_orders:
            message += self._t("delayed_items_info", user_id=customer.telegram_user_id) + "\n"
            delayed_grouped: dict = {}
            for order in delayed_orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t("unknown", customer.telegram_user_id)
                delayed_qty = order.quantity - (order.received_quantity or 0)
                if order.offer_id not in delayed_grouped:
                    delayed_grouped[order.offer_id] = {"name": offer_name, "offer_id": order.offer_id, "quantity": 0}
                delayed_grouped[order.offer_id]["quantity"] += delayed_qty
            for g in sorted(delayed_grouped.values(), key=lambda r: (r["name"] or "").lower()):
                message += (
                    f"• {g['quantity']}x [{g['offer_id']}] {g['name']} - "
                    + self._t("will_arrive_later", user_id=customer.telegram_user_id)
                    + "\n"
                )

        return message
