import logging
from typing import Any

from handlers.base_handler import BaseHandler
from handlers.payment_message import PaymentMessageMixin
from models.entities import AuthorizationStatus, Box, BoxStatus, OfferStatus, Order, OrderStatus
from services.box_status_manager import BoxStatusManager
from services.order_allocation import allocate, may_create_boxes

logger = logging.getLogger()

# How often a request is allocated and written: once more when another request took the room in between
ORDER_ATTEMPTS = 2


class CustomerOrderCommands(PaymentMessageMixin, BaseHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)

    def handle_create_order(
        self, chat_id: int, user_id: int, args: list, skip_duplicate_check: bool = False
    ) -> dict[str, Any]:
        """Handle /create_order command"""
        error = self._validate_args(args, 1, "usage_order", chat_id)
        if error:
            return error

        offer_id, error = self._parse_int_arg(args[0], "invalid_format", chat_id)
        if error:
            return error

        quantity = 1
        if len(args) > 1:
            quantity, error = self._parse_int_arg(args[1], "invalid_format", chat_id)
            if error:
                return error

        if quantity <= 0:
            return self._send_error(chat_id, "quantity_must_positive", "invalid_quantity", user_id=user_id)

        # Get and validate offer and customer
        offer, customer = self._get_offer_and_customer(chat_id, user_id, offer_id)
        if not offer or not customer:
            return {"status": "validation_failed"}

        # Check order limits
        if not self._check_order_limits(chat_id, customer.customer_id, offer_id, quantity):
            return {"status": "limit_exceeded"}

        # Check for duplicates
        if not skip_duplicate_check and self._has_duplicate_orders(
            chat_id, user_id, customer.customer_id, offer_id, quantity, offer.name
        ):
            return {"status": "confirmation_required"}

        return self.execute_order(chat_id, user_id, quantity, offer, customer)

    def handle_confirm_order(self, chat_id: int, user_id: int, args: list) -> dict[str, Any]:
        """Handle /confirm_order command"""
        error = self._validate_args(args, 1, "usage_confirm_order", chat_id)
        if error:
            return error

        return self.handle_create_order(chat_id, user_id, args, skip_duplicate_check=True)

    def execute_order(
        self, chat_id: int, user_id: int, quantity: int, offer, customer, placed_by_admin: bool = False
    ) -> dict[str, Any]:
        """Place a request: spread over the boxes of the offer that have room and, while the offer may get them, new
        boxes (services/order_allocation.py), one order per box, all in one transaction. What does not fit is not
        ordered, and the customer is told; with no room at all the offer is sold out. One confirmation and one group
        announcement per request. The order limit and the duplicate check are the caller's, on the whole request."""
        # The messages below go to chat_id: the admin's own chat for an order the admin places
        reader = chat_id if placed_by_admin else user_id
        try:
            placed = self._place_request(customer, offer, quantity, placed_by_admin)
            if placed is None:
                self._send_message(chat_id, self._t("order_failed", reader))
                return {"status": "error"}
            orders, allocation = placed
            if not orders:
                self._send_message(chat_id, self._t("offer_sold_out_named", reader, offer_name=offer.name))
                return {"status": "sold_out"}

            # An existing box the request filled is full now (written on condition: an ordered or delivered box stays)
            for box, units in allocation.existing:
                if box.current_quantity + units >= box.max_capacity:
                    self.db.mark_box_full_if_at_capacity(box.box_id)
            # Update offer status and send notifications (syncs channel messages)
            self._check_offer_status_after_change(offer.offer_id)
            if placed_by_admin:
                # The admin gets one confirmation, from the caller, which also says whether the customer was told
                return {"status": "success", "orders": orders, "shortfall": allocation.shortfall}
            self._send_order_confirmation(chat_id, user_id, orders, offer, quantity, customer)

            return {"status": "success"}

        except Exception as e:
            logger.error(f"Error in execute_order: {type(e).__name__}")
            self._send_message(chat_id, self._t("order_processing_failed", reader))
            return {"status": "error"}

    def _place_request(self, customer, offer, quantity: int, placed_by_admin: bool):
        """Allocate and write the request: (orders, allocation), no orders when there is no room. When another
        request took the room between the read and the write, the boxes are read again (ORDER_ATTEMPTS times); None
        when the write kept failing."""
        for _ in range(ORDER_ATTEMPTS):
            boxes = self.db.get_boxes_by_offer(offer.offer_id)
            allocation = allocate(boxes, quantity, offer.wholesale_box_size, may_create_boxes(offer, boxes))
            if allocation.placed == 0:
                return [], allocation

            new_boxes = [
                Box(
                    offer_id=offer.offer_id,
                    max_capacity=offer.wholesale_box_size,
                    current_quantity=units,
                    status=BoxStatus.FULL.value if units >= offer.wholesale_box_size else BoxStatus.OPEN.value,
                )
                for units in allocation.new_boxes
            ]
            orders = [
                self._new_order(customer, offer, box, units, placed_by_admin) for box, units in allocation.existing
            ]
            orders += [
                self._new_order(customer, offer, box, box.current_quantity, placed_by_admin) for box in new_boxes
            ]
            increments = [(box.box_id, units, box.max_capacity) for box, units in allocation.existing]
            if self.db.create_orders_in_boxes(orders, new_boxes, increments):
                return orders, allocation
        return None

    @staticmethod
    def _new_order(customer, offer, box, quantity: int, placed_by_admin: bool) -> Order:
        """An order of ``quantity`` in ``box``, its status from the box: delivered units are ready for labeling, units
        in an ordered box are ordered, others pending"""
        if box.status == BoxStatus.DELIVERED.value:
            status, received = OrderStatus.READY_FOR_LABELING.value, quantity
        elif box.status == BoxStatus.ORDERED.value:
            status, received = OrderStatus.ORDERED.value, 0
        else:
            status, received = OrderStatus.PENDING.value, 0
        return Order(
            customer_id=customer.customer_id,
            box_id=box.box_id,
            offer_id=offer.offer_id,
            quantity=quantity,
            received_quantity=received,
            unit_price=offer.price_per_unit,
            total_price=offer.price_per_unit * quantity,
            status=status,
            placed_by_admin=placed_by_admin,
        )

    def request_summary(self, orders: list, reader: int) -> dict[str, Any]:
        """The confirmation params of the orders of one request: their short ids, the units, the amount and their
        statuses (in the reader's language, each once)"""
        statuses = list(dict.fromkeys(self._t(f"status_{order.status}", reader) for order in orders))
        return {
            "order_id": ", ".join(order.order_id[:8] for order in orders),
            "quantity": sum(order.quantity for order in orders),
            "total": float(sum(order.total_price for order in orders)),
            "status": ", ".join(statuses),
        }

    def _get_offer_and_customer(self, chat_id: int, user_id: int, offer_id: int) -> tuple:
        """Get and validate offer and customer"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t("offer_not_found", user_id))
            return None, None

        if offer.status == OfferStatus.SOLD_OUT.value:
            self._send_message(chat_id, self._t("offer_sold_out_named", user_id, offer_name=offer.name))
            return None, None

        if offer.status not in (OfferStatus.ACTIVE.value, OfferStatus.IMPORT.value):
            self._send_message(chat_id, self._t("offer_not_found", user_id))
            return None, None

        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, self._t("customer_not_found", user_id))
            return None, None

        # Every entry point (command, deep link, button) must respect authorization
        if not self._is_admin(user_id) and customer.authorization_status != AuthorizationStatus.APPROVED.value:
            self._send_message(user_id, self._t("unauthorized", user_id))
            return None, None

        return offer, customer

    def _check_order_limits(self, chat_id: int, customer_id: str, offer_id: int, quantity: int) -> bool:
        """Check if order is within limits"""
        valid, limit_message = self.validator.validate_order_limit(customer_id, offer_id, quantity)
        if not valid:
            self._send_message(chat_id, limit_message)
        return valid

    def _has_duplicate_orders(
        self, chat_id: int, user_id: int, customer_id: str, offer_id: int, quantity: int, offer_name: str
    ) -> bool:
        """Check for duplicate orders and prompt confirmation"""
        existing_orders = self.db.get_orders_by_customer_and_offer(customer_id, offer_id)
        if not existing_orders:
            return False

        from utils.timezone import to_cet_string

        message = self._t("duplicate_order_warning", user_id, offer_name=offer_name)
        message += "\n\n"
        for order in existing_orders:
            order_date = to_cet_string(order.created_at, "%Y-%m-%d")
            status = self._t(f"status_{order.status}", user_id)
            message += f"• [{order_date}] {order.quantity}x €{order.total_price:.2f} ({status})\n"

        message += self._t("confirm_additional_order", user_id, quantity=quantity)

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": self._t("confirm", user_id), "callback_data": f"confirm_order_{offer_id}_{quantity}"},
                    {"text": self._t("cancel", user_id), "callback_data": "cancel_confirmation"},
                ]
            ]
        }

        self._send_message(chat_id, message, reply_markup=keyboard)
        return True

    def _send_order_confirmation(self, chat_id: int, user_id: int, orders: list, offer, requested: int, customer):
        """One confirmation of the orders of a request, with what could not be ordered; one group announcement"""
        display_name = f"{customer.first_name} {customer.last_name}".strip() if customer else ""
        summary = self.request_summary(orders, user_id)
        message = self._t("order_placed_single", user_id, name=display_name, product=offer.name, **summary)
        if summary["quantity"] < requested:
            message += "\n\n" + self._t("order_shortfall", user_id, requested=requested, placed=summary["quantity"])
        self._send_message(chat_id, message)

        announcement = self._build_order_notification_message(customer, offer, summary["quantity"])
        if announcement:
            self._send_order_notification_to_group(announcement)
            self._send_message(self.admin_user_id, announcement, parse_mode="HTML")

    def _build_order_notification_message(self, customer, offer, quantity):
        """Build order notification message"""
        try:
            bot_username = self._get_bot_username()

            # Check if offer is now sold out and calculate remaining availability
            updated_offer = self.db.get_offer(offer.offer_id)
            availability_text = ""

            if updated_offer and updated_offer.status == OfferStatus.SOLD_OUT.value:
                availability_text = f" - {self._t('status_sold_out', force_group_lang=True)}"
            else:
                # Calculate remaining availability from all boxes under capacity
                boxes = self.db.get_boxes_by_offer(offer.offer_id)
                total_available = self.box_status_manager.get_available_capacity_for_orders(boxes)

                if total_available > 6:
                    availability_text = f" ({self._t('sufficient_available', force_group_lang=True)})"
                elif total_available > 0:
                    availability_text = f" ({self._t('units_available', force_group_lang=True, count=total_available)})"

            # Format offer name as link
            offer_link = f"<a href='https://t.me/{bot_username}?start=view_offer_{offer.offer_id}'>{self._escape_html(offer.name)}</a>"

            customer_name = self._get_public_name(customer)
            message = self._t(
                "order_notification",
                force_group_lang=True,
                customer_name=customer_name,
                quantity=quantity,
                offer_name=offer_link,
                availability=availability_text,
            )
            return message
        except Exception as e:
            logger.error(f"Error building order notification message: {e}")
            return None

    def announce_order_for(self, customer, offer, quantity: int) -> None:
        """Announce in the group an order that the admin placed for a customer (guests' orders are not announced)"""
        if customer.is_guest:
            return
        message = self._build_order_notification_message(customer, offer, quantity)
        if message:
            self._send_order_notification_to_group(message)

    def _send_order_notification_to_group(self, message):
        """Send order notification message to default group"""
        import os

        try:
            group_id = os.environ.get("DEFAULT_GROUP_ID")
            if not group_id:
                return False

            # Only send notifications for non-guest orders
            result = self._send_message(int(group_id), message, parse_mode="HTML", force_group=True)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Error sending group notification: {e}")
            return False

    def handle_delete_cancelled_orders(self, chat_id: int, user_id: int) -> dict[str, Any]:
        """Handle /delete_cancelled_orders command - delete all cancelled orders for user"""
        return self._delete_orders_with_status(chat_id, user_id, OrderStatus.CANCELLED.value)

    def handle_delete_completed_orders(self, chat_id: int, user_id: int) -> dict[str, Any]:
        """Handle /delete_completed_orders command - delete all completed orders for user"""
        return self._delete_orders_with_status(chat_id, user_id, OrderStatus.COMPLETED.value)

    def _delete_orders_with_status(self, chat_id: int, user_id: int, status: str) -> dict[str, Any]:
        """Delete the customer's own cancelled or completed orders (the translation keys follow the status)"""
        failed_key = f"failed_delete_{status}_orders"
        try:
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, self._t("customer_not_found", user_id))
                return {"status": "customer_not_found"}

            orders = self.db.get_orders_by_customer_and_status(customer.customer_id, status)
            if not orders:
                self._send_message(chat_id, self._t(f"no_{status}_orders", user_id))
                return {"status": f"no_{status}_orders"}

            deleted_count = sum(1 for order in orders if self.db.delete_order(order.order_id))
            if deleted_count == 0:
                self._send_message(chat_id, self._t(failed_key, user_id))
                return {"status": "error"}

            self._send_message(chat_id, self._t(f"{status}_orders_deleted", user_id, count=deleted_count))
            return {"status": "success", "deleted_count": deleted_count}

        except Exception as e:
            logger.error(f"Error deleting {status} orders: {type(e).__name__}")
            self._send_message(chat_id, self._t(failed_key, user_id))
            return {"status": "error"}

    def handle_payment_info(self, chat_id: int, user_id: int) -> dict[str, Any]:
        """Handle /payment_info command - show customer their payment details"""
        try:
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, self._t("customer_not_found", user_id))
                return {"status": "customer_not_found"}

            orders = self.db.get_orders_by_customer(customer.customer_id)
            awaiting_payment_orders = [o for o in orders if o.status == OrderStatus.AWAITING_PAYMENT.value]

            if not awaiting_payment_orders:
                self._send_message(
                    chat_id, self._t("no_orders_awaiting_payment", user_id, customer_name=customer.first_name)
                )
                return {"status": "no_orders"}

            payment_link = self._payment_link_for(awaiting_payment_orders)
            if not payment_link:
                self._send_message(chat_id, self._t("no_payment_link_stored", user_id))
                return {"status": "no_payment_link"}

            message = self._build_delivery_message(
                customer, awaiting_payment_orders, [], payment_link, is_reminder=False
            )

            self._send_message(chat_id, message, parse_mode="HTML")
            return {"status": "success"}

        except Exception as e:
            logger.error(f"Error in handle_payment_info: {e}")
            self._send_message(chat_id, self._t("order_processing_failed", user_id))
            return {"status": "error"}
