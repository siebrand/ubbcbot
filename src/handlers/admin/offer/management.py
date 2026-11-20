import logging
from typing import Any

from models.entities import Box, BoxStatus, OfferStatus, OrderStatus
from services.box_deletion_service import BoxDeletionService
from services.box_status_manager import BoxStatusManager
from services.wholesale_plan import WholesalePlan, boxes_needed, plan_wholesale
from utils.pagination import PaginationUtils
from utils.timezone import to_cet_string

from .base import OfferBaseHandler

logger = logging.getLogger()


class OfferManagementHandler(OfferBaseHandler):
    """Handler for offer management operations"""

    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)
        self.box_deletion_service = BoxDeletionService(db)

    def handle_process_wholesale(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /order_wholesale command"""
        if not args:
            # Show available offers with pending orders
            return self._show_wholesale_offers_selection(chat_id, page=1)

        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error

        if offer.status not in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value]:
            self._send_message(chat_id, self._t("offer_not_active", chat_id))
            return {"status": "offer_not_active"}

        # Get all pending orders for this offer, sorted by date ascending
        pending_orders = sorted(
            (o for o in self.db.get_orders_by_offer(offer.offer_id) if o.status == OrderStatus.PENDING.value),
            key=lambda o: o.created_at,
        )
        if not pending_orders:
            self._send_message(chat_id, self._t("no_pending_orders", chat_id))
            return {"status": "no_pending_orders"}

        total_units = sum(order.quantity for order in pending_orders)
        boxes = boxes_needed(total_units, offer.wholesale_box_size)

        # Show order summary
        message = self._t(
            "wholesale_order_summary",
            chat_id,
            offer_id=offer.offer_id,
            name=offer.name,
            price=offer.price_per_unit,
            box_size=offer.wholesale_box_size,
            total_units=total_units,
            boxes_needed=boxes,
            order_count=len(pending_orders),
        )
        for i, order in enumerate(pending_orders, 1):
            order_date = to_cet_string(order.created_at, "%m-%d %H:%M")
            message += (
                f"{i}. {self._first_name(order.customer_id, chat_id)}: "
                f"{order.quantity} {self._units(order.quantity, chat_id)} [{order_date}]\n"
            )

        # Add inline keyboard for confirmation
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": self._t("order_wholesale_boxes", chat_id, boxes=boxes),
                        "callback_data": f"confirm_process_wholesale_{offer.offer_id}_{boxes}",
                    },
                    {
                        "text": self._t("custom_quantity", chat_id),
                        "callback_data": f"custom_wholesale_quantity_{offer.offer_id}",
                    },
                    {"text": self._t("cancel", chat_id), "callback_data": "cancel_action"},
                ]
            ]
        }

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "success"}

    def handle_custom_wholesale_quantity(self, chat_id: int, offer_id: str) -> dict[str, Any]:
        """Handle custom wholesale quantity input"""
        try:
            offer_id_int = int(offer_id)
            offer = self.db.get_offer(offer_id_int)

            if not offer:
                self._send_message(chat_id, self._t("offer_not_found"))
                return {"status": "offer_not_found"}

            # Store context for text input processing
            from utils.edit_context import EditContextManager

            edit_context_manager = EditContextManager(self.db, self._t, self._send_message)
            edit_context_manager.store_edit_context(chat_id, "custom_wholesale_quantity", offer_id)

            # Prompt for custom quantity
            message = self._t("enter_custom_wholesale_quantity", offer_id=offer_id)
            self._send_message(chat_id, message)
            return {"status": "awaiting_input"}

        except ValueError:
            self._send_message(chat_id, self._t("invalid_offer_id"))
            return {"status": "invalid_format"}

    def handle_custom_wholesale_quantity_answer(self, chat_id: int, offer_id: str, text: str) -> dict[str, Any]:
        """The number of boxes the admin typed after "custom quantity": process the wholesale order with it"""
        try:
            boxes = int(text.strip())
        except ValueError:
            self._send_message(chat_id, self._t("invalid_format", chat_id))
            return {"status": "invalid_format"}
        if boxes <= 0:
            self._send_message(chat_id, self._t("boxes_must_positive", chat_id))
            return {"status": "invalid_quantity"}
        return self.handle_confirm_process_wholesale(chat_id, [offer_id, str(boxes)])

    def handle_confirm_process_wholesale(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /confirm_process_wholesale: order boxes at the wholesaler and serve the pending orders from them"""
        offer, boxes_ordered, error = self._wholesale_arguments(chat_id, args)
        if error:
            return error

        pending = [o for o in self.db.get_orders_by_offer(offer.offer_id) if o.status == OrderStatus.PENDING.value]
        plan = plan_wholesale(pending, boxes_ordered, offer.wholesale_box_size)

        boxes_with_orders = self._apply_wholesale_plan(offer, plan)
        offer_status_msg = self._offer_status_after_wholesale(chat_id, offer, plan)
        self._complete_ordered_boxes(offer, boxes_ordered, boxes_with_orders)
        deleted_boxes = self.box_deletion_service.delete_empty_boxes(offer.offer_id)

        summary = self._wholesale_summary(chat_id, offer, boxes_ordered, plan, offer_status_msg, deleted_boxes)
        buttons = [[{"text": self._t("back_to_admin", chat_id), "callback_data": "admin:main"}]]
        if self._pending_orders_by_offer():
            buttons.insert(0, [{"text": self._t("process_next_offer", chat_id), "callback_data": "process_wholesale"}])
        self._send_message(chat_id, summary, reply_markup={"inline_keyboard": buttons})
        return {"status": "success"}

    def _wholesale_arguments(self, chat_id: int, args: list) -> tuple:
        """(offer, number of boxes, None), or (None, None, error result) after telling the admin what is wrong"""
        if len(args) < 2:
            self._send_message(chat_id, self._t("usage_confirm_process_wholesale", chat_id))
            return None, None, {"status": "invalid_args"}

        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return None, None, error

        try:
            boxes_ordered = int(args[1])
        except ValueError:
            self._send_message(chat_id, self._t("invalid_format", chat_id))
            return None, None, {"status": "invalid_format"}

        if boxes_ordered <= 0:
            self._send_message(chat_id, self._t("boxes_must_positive", chat_id))
            return None, None, {"status": "invalid_quantity"}
        return offer, boxes_ordered, None

    def _apply_wholesale_plan(self, offer, plan: WholesalePlan) -> set:
        """Write the plan: orders ordered, reduced or cancelled, customers told. Returns the boxes with orders left.

        Each write is on condition that the order is still as the plan read it (audit 6, A5): an order that was
        cancelled, moved or changed in between keeps what it has, and moves from its list to ``plan.changed``.
        """
        boxes_with_orders = set()
        ordered = {"status": OrderStatus.ORDERED.value}
        for order in list(plan.fulfilled):
            if not self.db.update_order_as_read(order, ordered):
                plan.fulfilled.remove(order)
                plan.changed.append(order)
                continue
            boxes_with_orders.add(order.box_id)

        for reduction in list(plan.reduced):
            order, old_qty, new_qty = reduction
            new_total_price = new_qty * order.unit_price
            # The box keeps only what is still ordered, in the same write
            updates = {"quantity": new_qty, "total_price": new_total_price, **ordered}
            if not self.db.update_order_as_read(order, updates, box_delta=new_qty - old_qty):
                plan.reduced.remove(reduction)
                plan.changed.append(order)
                continue
            boxes_with_orders.add(order.box_id)
            self._notify_customer(
                self.db.get_customer(order.customer_id),
                "order_updated_limited",
                name=offer.name,
                old_qty=old_qty,
                new_qty=new_qty,
                total=float(new_total_price),
            )

        boxes_to_mark = [
            box.box_id
            for box in self.db.get_boxes_by_offer(offer.offer_id)
            if box.box_id in boxes_with_orders and box.status != BoxStatus.ORDERED.value
        ]
        if boxes_to_mark:
            self.box_status_manager.mark_boxes_as_ordered(boxes_to_mark)

        # Cancelled orders give their units back to the box (as a normal cancellation does), so a box that only held
        # cancelled orders is empty and cleaned up afterwards
        for order in list(plan.cancelled):
            if not self.db.cancel_order_with_box(order):
                plan.cancelled.remove(order)
                plan.changed.append(order)
                continue
            self.box_status_manager.update_box_status_after_change(order.box_id)
            self._notify_customer(
                self.db.get_customer(order.customer_id),
                "order_cancelled_insufficient",
                name=offer.name,
                quantity=order.quantity,
                total=order.total_price,
            )
        return boxes_with_orders

    def _offer_status_after_wholesale(self, chat_id: int, offer, plan: WholesalePlan) -> str:
        """Sold out when nothing is pending and the ordered boxes are full; the line for the summary"""
        # Read again: an order can have come in while this ran
        pending = [o for o in self.db.get_orders_by_offer(offer.offer_id) if o.status == OrderStatus.PENDING.value]
        if pending:
            return self._t("offer_remains_active_pending", chat_id, pending_count=len(pending))
        if plan.units_left == 0:
            self.db.update_offer(offer.offer_id, {"status": OfferStatus.SOLD_OUT.value})
            self.sync_offer_messages(offer.offer_id)
            return self._t("offer_is_sold_out", chat_id)
        return self._t(
            "offer_remains_active_capacity",
            chat_id,
            capacity=plan.units_left,
            units=self._units(plan.units_left, chat_id),
        )

    def _complete_ordered_boxes(self, offer, boxes_ordered: int, boxes_with_orders: set) -> None:
        """Add empty ORDERED boxes until there are as many as ordered at the wholesaler"""
        ordered = [
            box
            for box in self.db.get_boxes_by_offer(offer.offer_id)
            if box.status == BoxStatus.ORDERED.value or box.box_id in boxes_with_orders
        ]
        for _ in range(boxes_ordered - len(ordered)):
            self.db.create_box(
                Box(offer_id=offer.offer_id, max_capacity=offer.wholesale_box_size, status=BoxStatus.ORDERED.value)
            )

    def _wholesale_summary(
        self, chat_id: int, offer, boxes_ordered: int, plan: WholesalePlan, offer_status_msg: str, deleted_boxes: int
    ) -> str:
        summary = self._t(
            "offer_fulfilled_summary",
            chat_id,
            offer_id=offer.offer_id,
            boxes=boxes_ordered,
            fulfilled_orders=len(plan.fulfilled),
            fulfilled_units=sum(order.quantity for order in plan.fulfilled),
        )
        if plan.reduced:
            order, old_qty, new_qty = plan.reduced[0]
            summary += "\n" + self._t(
                "order_reduced",
                chat_id,
                customer=self._first_name(order.customer_id, chat_id),
                old_qty=old_qty,
                new_qty=new_qty,
            )
        if plan.cancelled:
            details = ", ".join(
                f"{self._first_name(o.customer_id, chat_id)} ({o.quantity} {self._units(o.quantity, chat_id)})"
                for o in plan.cancelled
            )
            summary += "\n" + self._t(
                "orders_cancelled",
                chat_id,
                cancelled_orders=len(plan.cancelled),
                cancelled_units=sum(order.quantity for order in plan.cancelled),
                details=details,
            )
        if plan.changed:
            details = ", ".join(
                f"{self._first_name(o.customer_id, chat_id)} ({o.quantity} {self._units(o.quantity, chat_id)})"
                for o in plan.changed
            )
            summary += "\n" + self._t("orders_changed_meanwhile", chat_id, details=details)
        summary += "\n\n" + self._t(
            "total_allocated", chat_id, allocated=plan.units_allocated, available=plan.units_available
        )
        summary += f"\n📊 {offer_status_msg}"
        if deleted_boxes > 0:
            summary += "\n" + self._t("cleaned_empty_boxes", chat_id, count=deleted_boxes)
        return summary

    def _first_name(self, customer_id: str, chat_id: int) -> str:
        customer = self.db.get_customer(customer_id)
        return customer.first_name if customer and customer.first_name else self._t("unknown", chat_id)

    def _pending_orders_by_offer(self) -> dict[int, list]:
        """The pending orders of the active and sold-out offers, read at once through the status index"""
        offer_ids = {
            offer.offer_id
            for offer in self.db.list_offers()
            if offer.status in (OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value)
        }
        pending: dict[int, list] = {}
        for order in self.db.get_all_orders(statuses=[OrderStatus.PENDING.value]):
            if order.offer_id in offer_ids:
                pending.setdefault(order.offer_id, []).append(order)
        return pending

    def handle_process_wholesale_page(self, chat_id: int, page: int) -> dict[str, Any]:
        """Handle pagination for process_wholesale offer selection"""
        return self._show_wholesale_offers_selection(chat_id, page=page)

    def _show_wholesale_offers_selection(self, chat_id: int, page: int = 1) -> dict[str, Any]:
        """Show offers with pending orders for wholesale ordering"""
        offers = {offer.offer_id: offer for offer in self.db.list_offers()}
        offers_with_orders = [
            (offers[offer_id], len(orders), sum(order.quantity for order in orders))
            for offer_id, orders in self._pending_orders_by_offer().items()
        ]

        if not offers_with_orders:
            self._send_message(chat_id, self._t("no_pending_orders", chat_id))
            return {"status": "no_offers"}

        # Sort alphabetically by offer name
        offers_with_orders.sort(key=lambda x: x[0].name.lower())
        page_offers, total_pages = PaginationUtils.paginate_list(offers_with_orders, page, page_size=10)

        message = self._t("select_offer_wholesale", chat_id)
        if total_pages > 1:
            message += " (" + self._t("page_indicator", chat_id, page=page, total_pages=total_pages) + ")"
        message += "\n\n"
        keyboard_buttons = []

        supplier_names = {supplier.name for supplier in self.db.list_suppliers()}
        for offer, order_count, total_units in page_offers:
            known = offer.supplier_name in supplier_names
            supplier_name = offer.supplier_name if known else self._t("unknown", chat_id)
            needed = boxes_needed(total_units, offer.wholesale_box_size)
            boxes_text = self._t("box", chat_id) if needed == 1 else self._t("boxes", chat_id)

            message += (
                f"🍺 {offer.name} ({offer.offer_id}) • {order_count} {self._t('orders_abbrev', chat_id)} • "
                f"{total_units} {self._t('units', chat_id)} • {needed} {boxes_text} • {supplier_name}\n"
            )
            keyboard_buttons.append(
                [
                    {
                        "text": self._t("select_wholesale_offer", chat_id, name=offer.name, boxes=needed),
                        "callback_data": f"wholesale_select_{offer.offer_id}",
                    }
                ]
            )

        # Add pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(
                    {"text": self._t("previous", chat_id), "callback_data": f"page_process_wholesale_{page - 1}"}
                )
            if page < total_pages:
                nav_buttons.append(
                    {"text": self._t("next", chat_id), "callback_data": f"page_process_wholesale_{page + 1}"}
                )
            keyboard_buttons.append(nav_buttons)

        keyboard_buttons.append([{"text": self._t("cancel", chat_id), "callback_data": "cancel_action"}])
        keyboard = {"inline_keyboard": keyboard_buttons}

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "success"}

    def handle_cancel_offer(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /cancel_offer command"""
        if not args:
            self._send_message(chat_id, self._t("usage_cancel_offer"))
            return {"status": "invalid_args"}

        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error

        if offer.status != OfferStatus.ACTIVE.value:
            self._send_message(chat_id, self._t("offer_not_active"))
            return {"status": "offer_not_active"}

        # Get all orders for this offer
        active_orders = self._active_orders(offer.offer_id)

        if not active_orders:
            # No active orders, just cancel the offer
            self.db.update_offer(offer.offer_id, {"status": OfferStatus.INACTIVE.value})
            self._delete_offer_boxes(offer.offer_id)
            self.sync_offer_messages(offer.offer_id, cancelled=True)
            self._send_message(chat_id, self._t("offer_cancelled_no_orders", offer_id=offer.offer_id))
            return {"status": "success"}

        # Show confirmation with order details
        message = self._t(
            "cancel_offer_warning", offer_id=offer.offer_id, name=offer.name, order_count=len(active_orders)
        )

        # Add inline keyboard for confirmation
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": self._t("confirm_cancel"), "callback_data": f"confirm_cancel_offer_{offer.offer_id}"},
                    {"text": self._t("keep_offer"), "callback_data": "cancel_action"},
                ]
            ]
        }

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "confirmation_required"}

    def handle_confirm_cancel_offer(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /confirm_cancel_offer command"""
        if not args:
            self._send_message(chat_id, self._t("usage_confirm_cancel_offer"))
            return {"status": "invalid_args"}

        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error

        # Get all pending orders
        active_orders = self._active_orders(offer.offer_id)

        # Cancel all active orders and notify customers
        cancelled_count = 0
        notified_customers = []
        for order in active_orders:
            if self.db.cancel_order(order.order_id, self.admin_user_id, "Offer cancelled by admin"):
                cancelled_count += 1
                customer = self.db.get_customer(order.customer_id)
                if customer:
                    notified_customers.append(customer.first_name)
                self._notify_customer_cancellation(order, offer)

        # Delete all boxes
        deleted_boxes = self._delete_offer_boxes(offer.offer_id)

        # Cancel the offer
        self.db.update_offer(offer.offer_id, {"status": OfferStatus.INACTIVE.value})
        self.sync_offer_messages(offer.offer_id, cancelled=True)

        # Send summary
        summary = self._t(
            "offer_cancelled_summary",
            offer_id=offer.offer_id,
            cancelled_count=cancelled_count,
            deleted_boxes=deleted_boxes,
            notified_count=cancelled_count,
        )

        if notified_customers:
            summary += "\n" + self._t("notified_customers", customers=", ".join(notified_customers))

        self._send_message(chat_id, summary)
        return {"status": "success"}

    def _delete_offer_boxes(self, offer_id: int) -> int:
        """Delete all boxes for an offer and return count"""
        return self.box_deletion_service.delete_offer_boxes(offer_id)

    def _notify_customer_cancellation(self, order, offer):
        """Notify customer about order cancellation"""
        self._notify_customer(
            self.db.get_customer(order.customer_id),
            "order_cancelled_offer_cancelled",
            name=offer.name,
            quantity=order.quantity,
            total=float(order.total_price),
        )

    def handle_delete_offer(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /delete_offer command - accepts one or more offer IDs"""
        if not args:
            self._send_message(chat_id, self._t("usage_delete_offer"))
            return {"status": "invalid_args"}

        for arg in args[:100]:
            offer, error = self._validate_and_get_offer([arg], chat_id)
            if error:
                continue

            if offer.status not in [OfferStatus.COMPLETED.value, OfferStatus.INACTIVE.value]:
                self._send_message(chat_id, self._t("offer_cannot_delete", status=self._t(f"status_{offer.status}")))
                continue

            self._delete_offer_boxes(offer.offer_id)

            if self.db.delete_offer(offer.offer_id):
                self._send_message(chat_id, self._t("offer_deleted", offer_id=offer.offer_id, name=offer.name))
            else:
                self._send_message(chat_id, self._t("failed_delete_offer"))

        return {"status": "success"}
