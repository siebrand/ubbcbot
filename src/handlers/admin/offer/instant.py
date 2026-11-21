"""/instant_order: create an offer, a delivered box and the first order in one step (instant-orders-design.md).

After the write the offer is an ordinary offer: an active one whose delivered box has free units takes more orders
straight to ready_for_labeling, as after a partial wholesale delivery.
"""

import json
import logging
import os
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from models.entities import Box, BoxStatus, EditContext, Offer, OfferStatus, Order, OrderStatus
from services.instant_order_input import InstantOrderInput, InstantOrderInputError, parse_instant_order

from .notifications import NotificationHandler

logger = logging.getLogger(__name__)

CUSTOMER_SELECT = "instant_order_customer_select"


class InstantOrderHandler(NotificationHandler):  # an OfferBaseHandler that can announce offers
    def handle_instant_order(self, chat_id: int, args: list) -> dict[str, Any]:
        """/instant_order <supplier> <offer name> <price> <customer> [box_size]"""
        if not args:
            self._send_message(chat_id, self._t("usage_instant_order", chat_id))
            return {"status": "invalid_args"}
        try:
            parsed = parse_instant_order(args)
        except InstantOrderInputError as error:
            self._send_message(chat_id, self._t(error.key, chat_id))
            return {"status": "invalid_args"}
        return self._instant_order_for_input(chat_id, parsed)

    def _instant_order_for_input(self, chat_id: int, parsed: InstantOrderInput) -> dict[str, Any]:
        """Check the offer and find the customer; with more than one match, keep the input and show the list"""
        error = self._instant_offer_error(chat_id, parsed)
        if error:
            return error

        customer, found = self._find_customer_with_disambiguation(
            parsed.customer, chat_id, "instant_order_customer", status_filter="approved"
        )
        if found:
            if found.get("status") == "disambiguation_shown":
                self.db.create_edit_context(
                    EditContext(chat_id=chat_id, edit_type=CUSTOMER_SELECT, entity_id=self._input_json(parsed))
                )
            return found
        return self._create_instant_order(chat_id, parsed, customer)

    def _instant_offer_error(self, chat_id: int, parsed: InstantOrderInput) -> dict[str, Any] | None:
        """The supplier must exist and be active, and the name must be valid; None when they are"""
        valid, key = self._validate_offer_name(parsed.offer_name)
        if valid:
            valid, key = self._validate_supplier(parsed.supplier)
        if valid:
            return None
        self._send_message(chat_id, self._t(key, chat_id, name=parsed.supplier))
        return {"status": "invalid_input"}

    @staticmethod
    def _input_json(parsed: InstantOrderInput) -> str:
        return json.dumps({**asdict(parsed), "price": str(parsed.price)})

    @staticmethod
    def _input_from_json(text: str) -> InstantOrderInput | None:
        try:
            values = json.loads(text)
            return InstantOrderInput(**{**values, "price": Decimal(values["price"])})
        except ValueError, TypeError, KeyError, ArithmeticError:
            return None

    def handle_instant_order_customer_select(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """The admin picked the customer from the list: create the order with the input that was kept"""
        context = self.db.get_edit_context_by_chat_id(chat_id)
        parsed = None
        if context and context.edit_type == CUSTOMER_SELECT:
            self.db.delete_edit_context(context.context_id)
            parsed = self._input_from_json(context.entity_id)
        if parsed is None:
            self._send_message(chat_id, self._t("instant_order_context_expired", chat_id))
            return {"status": "context_expired"}

        customer = self.db.get_customer(customer_id)
        if not customer or customer.authorization_status != "approved":
            self._send_message(chat_id, self._t("user_not_found", chat_id, identifier=customer_id))
            return {"status": "user_not_found"}
        error = self._instant_offer_error(chat_id, parsed)
        if error:
            return error
        return self._create_instant_order(chat_id, parsed, customer)

    def _create_instant_order(self, chat_id: int, parsed: InstantOrderInput, customer) -> dict[str, Any]:
        """The offer, its delivered box with one unit and the first order, in one write; then tell everyone"""
        supplier = self.db.get_supplier_by_name(parsed.supplier)
        has_room = parsed.box_size > 1
        offer = Offer(
            supplier_name=supplier.name if supplier else parsed.supplier,
            name=parsed.offer_name,
            price_per_unit=parsed.price,
            wholesale_box_size=parsed.box_size,
            status=OfferStatus.ACTIVE.value if has_room else OfferStatus.SOLD_OUT.value,
        )
        box = Box(max_capacity=parsed.box_size, current_quantity=1, status=BoxStatus.DELIVERED.value)
        order = Order(
            customer_id=customer.customer_id,
            quantity=1,
            received_quantity=1,
            unit_price=parsed.price,
            total_price=parsed.price,
            status=OrderStatus.READY_FOR_LABELING.value,
            placed_by_admin=True,
        )
        if not self.db.create_instant_offer(offer, box, order):
            self._send_message(chat_id, self._t("failed_instant_order", chat_id))
            return {"status": "error"}

        pm_result = self._notify_customer(
            customer,
            "admin_order_placed",
            product=offer.name,
            quantity=order.quantity,
            total=order.total_price,
            order_id=order.order_id[:8],
            status=self._t(f"status_{order.status}", customer.telegram_user_id),
        )
        self._send_message(chat_id, self._instant_order_confirmation(chat_id, offer, order, customer, pm_result))
        if offer.wholesale_box_size > 1:
            self._announce_instant_offer(offer)
        return {"status": "success", "offer_id": offer.offer_id}

    def _announce_instant_offer(self, offer) -> None:
        """An offer with free units gets one tracked group announcement with the order buttons (synced later, as any
        announcement). It names no customer, and subscribers get no message."""
        self.expire_exports()
        group_id = os.environ.get("DEFAULT_GROUP_ID")
        if group_id:
            self._send_rich_offer_message(int(group_id), offer, force_group=True, include_buttons=True)

    def _instant_order_confirmation(self, chat_id: int, offer, order, customer, pm_result: dict) -> str:
        name = " ".join(part for part in (customer.first_name, customer.last_name) if part) or self._t(
            "unknown", chat_id
        )
        # A plain-text message: no HTML escaping
        params = {
            "offer_id": offer.offer_id,
            "name": offer.name,
            "price": float(offer.price_per_unit),
            "box_size": offer.wholesale_box_size,
            "customer": name,
            "customer_ref": customer.username or str(customer.customer_id)[:8],
            "status": self._t(f"status_{order.status}", chat_id),
        }
        key = "instant_order_created_with_room" if offer.wholesale_box_size > 1 else "instant_order_created"
        message = self._t(key, chat_id, **params)
        if not customer.is_guest and not pm_result.get("success"):
            message += "\n" + self._t("pm_notification_failed", chat_id, name=name)
        return message
