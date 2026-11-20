import logging
from decimal import Decimal
from typing import Any

from models.entities import ACTIVE_ORDER_STATUSES, BoxStatus, OrderStatus
from services.box_refill import REFILLABLE_BOX_STATUSES
from services.box_status_manager import BoxStatusManager

from .base_order_handler import BaseOrderHandler

logger = logging.getLogger(__name__)

# The statuses of an order whose units are in its box and that no money is involved in yet (see _status_options)
CORRECTABLE_STATUSES = (
    OrderStatus.PENDING.value,
    OrderStatus.ORDERED.value,
    OrderStatus.RECEIVED_PARTIAL_DELAYED.value,
    OrderStatus.READY_FOR_LABELING.value,
    OrderStatus.LABELING_COMPLETED.value,
)

# The boxes an order may be moved between: a pending order between boxes not yet ordered at the wholesaler, an
# ordered one between boxes that were (which box it is in is corrected). A delivered order stays in its box.
MOVABLE_BETWEEN = {
    OrderStatus.PENDING.value: REFILLABLE_BOX_STATUSES,
    OrderStatus.ORDERED.value: (BoxStatus.ORDERED.value,),
}


class OrderEditing(BaseOrderHandler):
    """Admin editing of a single order: box, unit price, or status.

    Short-id resolution is shared with cancellation via
    BaseOrderHandler.find_orders_by_partial_id. Box moves reuse the atomic
    box-occupancy mechanisms in BoxStatusManager.
    """

    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)

    # ------------------------------------------------------------------ boxes
    def _boxes_with_space(self, order) -> list:
        """Boxes of the order's offer it may move to (see MOVABLE_BETWEEN) that have room for the order's quantity,
        excluding the order's current box, sorted by creation order."""
        statuses = MOVABLE_BETWEEN.get(order.status, ())
        boxes = self.db.get_boxes_by_offer(order.offer_id) or []
        candidates = [
            b
            for b in boxes
            if b.box_id != order.box_id
            and b.status in statuses
            and (b.max_capacity - b.current_quantity) >= order.quantity
        ]
        candidates.sort(key=lambda b: getattr(b, "created_at", None) or 0)
        return candidates

    def _apply_box_change(self, order, new_box_id: str) -> tuple[bool, str]:
        """Move the order to new_box_id: the order and both box counts in one transaction (audit 6, A4), on
        condition that the order still has the status, box and quantity it was read with, the new box has room and
        both boxes are still in a status the order may move between (MOVABLE_BETWEEN). Returns (success,
        message_key)."""
        if new_box_id == order.box_id:
            return False, "edit_order_same_box"

        new_box = self.db.get_box(new_box_id)
        if not new_box:
            return False, "edit_order_box_not_found"
        if new_box.offer_id != order.offer_id:
            return False, "edit_order_box_wrong_offer"
        statuses = MOVABLE_BETWEEN.get(order.status, ())
        if new_box.status not in statuses:
            return False, "edit_order_box_not_allowed"
        if new_box.max_capacity - new_box.current_quantity < order.quantity:
            return False, "edit_order_box_full"

        if not self.db.move_order_to_box(
            order.order_id, order.quantity, order.box_id, new_box_id, new_box.max_capacity, order.status, statuses
        ):
            return False, "edit_order_move_failed"

        for box_id in (order.box_id, new_box_id):
            self.box_status_manager.update_box_status_after_change(box_id)
        self._check_offer_status_after_change(order.offer_id)
        return True, "edit_order_box_success"

    # -------------------------------------------------------------- unit price
    def _apply_unit_price_change(self, order, new_unit_price) -> tuple[bool, str]:
        """Set the order's unit_price and recompute total_price = unit * quantity."""
        try:
            unit = Decimal(str(new_unit_price))
        except ArithmeticError, ValueError:
            return False, "edit_order_bad_price"
        # A unit price of 0 is allowed (free / comped item); only negatives are rejected.
        if unit < 0:
            return False, "edit_order_bad_price"

        total = unit * order.quantity
        if not self.db.update_order(
            order.order_id,
            {"unit_price": unit, "total_price": total},
            self.admin_user_id,
            "Order unit price edited",
        ):
            return False, "edit_order_update_failed"
        return True, "edit_order_price_success"

    # ------------------------------------------------------------------ status
    def _status_options(self, order) -> list[str]:
        """The statuses this order may be given here, in workflow order (audit 6, A3).

        Between pending and labeling completed the units are in the box and no money is involved: one of those
        statuses may be corrected into another, and a pending or ordered order may be cancelled (as /cancel_order
        does: the box gets the units back). A cancelled order is not brought back (its room may have gone to other
        orders: place a new one), only the delivery overview asks for a payment (it applies the credit and the
        payment link), an order awaiting payment may only be marked paid, and a paid order keeps its status.
        """
        if order.status in CORRECTABLE_STATUSES:
            options = [status for status in CORRECTABLE_STATUSES if status != order.status]
            if order.status in ACTIVE_ORDER_STATUSES:
                options.append(OrderStatus.CANCELLED.value)
            return options
        if order.status == OrderStatus.AWAITING_PAYMENT.value:
            return [OrderStatus.COMPLETED.value]
        return []

    def _apply_status_change(self, order, new_status: str) -> tuple[bool, str]:
        """Give the order one of the statuses of _status_options, on condition that it still has the status it was
        read with. Cancelling takes the units off the box in the same write."""
        if new_status not in {status.value for status in OrderStatus}:
            return False, "edit_order_bad_status"
        if new_status not in self._status_options(order):
            return False, "edit_order_status_not_allowed"
        if new_status == OrderStatus.CANCELLED.value:
            if not self.db.cancel_order_with_box(order):
                return False, "edit_order_update_failed"
            self.box_status_manager.update_box_status_after_change(order.box_id)
            self._check_offer_status_after_change(order.offer_id)
            return True, "edit_order_status_success"
        if not self.db.batch_update_order_status([order.order_id], new_status, self.admin_user_id, order.status):
            return False, "edit_order_update_failed"
        return True, "edit_order_status_success"

    # ------------------------------------------------------------------ entry
    def handle_edit_order(self, chat_id: int, args: list) -> dict[str, Any]:
        """Entry point for /edit_order <short_id>: resolve the order and show the
        aspect menu (box / unit price / status)."""
        if not args:
            self._send_message(chat_id, self._t("edit_order_usage", chat_id))
            return {"status": "awaiting_input"}

        partial = args[0]
        matches = self.find_orders_by_partial_id(partial, include_cancelled=True)
        if not matches:
            self._send_message(chat_id, self._t("no_orders_found_partial", chat_id, partial_id=partial))
            return {"status": "order_not_found"}
        if len(matches) > 1:
            return self._show_order_disambiguation(chat_id, matches)

        order, _customer = matches[0]
        return self.show_aspect_menu(chat_id, order)

    def _show_order_disambiguation(self, chat_id: int, matches: list) -> dict[str, Any]:
        message = self._t("multiple_orders_found_partial", chat_id, partial_id=matches[0][0].order_id[:8]) + "\n\n"
        buttons = []
        for order, customer in matches:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else self._t("unknown", user_id=None)
            name = f"{customer.first_name} {customer.last_name}" if customer else self._t("unknown", user_id=None)
            label = f"{order.order_id[:8]}: {name} - {order.quantity}x {offer_name}"
            buttons.append([{"text": label, "callback_data": f"edit_order_pick_{order.order_id[:8]}"}])
        buttons.append([{"text": self._t("cancel", user_id=None), "callback_data": "cancel_action"}])
        self._send_message(chat_id, message, reply_markup={"inline_keyboard": buttons})
        return {"status": "disambiguation_shown"}

    def _order_details_block(self, order) -> str:
        """Human-readable summary of the order shown above the edit buttons."""
        offer = self.db.get_offer(order.offer_id)
        offer_name = offer.name if offer else self._t("unknown", user_id=None)
        customer = self.db.get_customer(order.customer_id)
        customer_name = (
            f"{customer.first_name} {customer.last_name}".strip() if customer else self._t("unknown", user_id=None)
        )
        return self._t(
            "edit_order_details",
            None,
            order_id=order.order_id[:8],
            customer=self._escape_html(customer_name),
            offer_id=order.offer_id,
            offer_name=self._escape_html(offer_name),
            quantity=order.quantity,
            unit_price=order.unit_price,
            total_price=order.total_price,
            box_id=order.box_id,
            status=order.status,
        )

    def show_aspect_menu(self, chat_id: int, order) -> dict[str, Any]:
        oid = order.order_id[:8]  # short id keeps callback_data within Telegram's 64-byte limit
        buttons = [
            [{"text": self._t("edit_order_aspect_box", chat_id), "callback_data": f"edit_order_box_{oid}"}],
            [{"text": self._t("edit_order_aspect_price", chat_id), "callback_data": f"edit_order_price_{oid}"}],
            [{"text": self._t("edit_order_aspect_status", chat_id), "callback_data": f"edit_order_status_{oid}"}],
            [{"text": self._t("cancel", user_id=None), "callback_data": "cancel_action"}],
        ]
        message = (
            self._order_details_block(order) + "\n\n" + self._t("edit_order_choose_aspect", chat_id, order_id=oid[:8])
        )
        self._send_message(chat_id, message, parse_mode="HTML", reply_markup={"inline_keyboard": buttons})
        return {"status": "aspect_menu_shown"}

    # ----------------------------------------------------------- callback flow
    def _get_order_or_warn(self, chat_id: int, order_id: str):
        # callback_data carries the short (8-char) order id to stay within
        # Telegram's 64-byte limit; resolve it to the full order here.
        order = self.db.get_order(order_id)
        if not order:
            matches = self.find_orders_by_partial_id(order_id, include_cancelled=True)
            order = matches[0][0] if len(matches) == 1 else None
        if not order:
            self._send_message(chat_id, self._t("order_not_found_full_id", chat_id, order_id=order_id))
        return order

    def _resolve_box(self, order, box_short_id: str):
        """Resolve a short box id (first 8 chars) to a full box of the order's offer."""
        for b in self.db.get_boxes_by_offer(order.offer_id) or []:
            if b.box_id.startswith(box_short_id):
                return b
        return None

    def show_box_options(self, chat_id: int, order_id: str) -> dict[str, Any]:
        """Show buttons listing boxes (of the order's offer) that have space."""
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        boxes = self._boxes_with_space(order)
        if not boxes:
            self._send_message(chat_id, self._t("edit_order_no_boxes", chat_id))
            return {"status": "no_boxes_available"}
        buttons = [
            [
                {
                    "text": f"{b.box_id[:8]} ({b.current_quantity}/{b.max_capacity})",
                    "callback_data": f"edit_order_setbox_{order.order_id[:8]}_{b.box_id[:8]}",
                }
            ]
            for b in boxes
        ]
        buttons.append(
            [{"text": self._t("cancel", user_id=None), "callback_data": f"edit_order_pick_{order.order_id[:8]}"}]
        )
        self._send_message(chat_id, self._t("edit_order_pick_box", chat_id), reply_markup={"inline_keyboard": buttons})
        return {"status": "box_options_shown"}

    def confirm_box(self, chat_id: int, order_id: str, box_short_id: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        box = self._resolve_box(order, box_short_id)
        if not box:
            self._send_message(chat_id, self._t("edit_order_box_not_found", chat_id))
            return {"status": "box_not_found"}
        buttons = [
            [
                {
                    "text": self._t("confirm", user_id=None),
                    "callback_data": f"edit_order_applybox_{order.order_id[:8]}_{box.box_id[:8]}",
                }
            ],
            [{"text": self._t("cancel", user_id=None), "callback_data": f"edit_order_pick_{order.order_id[:8]}"}],
        ]
        self._send_message(
            chat_id,
            self._t("edit_order_confirm_box", chat_id, order_id=order.order_id[:8], box_id=box.box_id[:8]),
            reply_markup={"inline_keyboard": buttons},
        )
        return {"status": "confirm_shown"}

    def apply_box(self, chat_id: int, order_id: str, box_short_id: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        box = self._resolve_box(order, box_short_id)
        if not box:
            self._send_message(chat_id, self._t("edit_order_box_not_found", chat_id))
            return {"status": "box_not_found"}
        ok, key = self._apply_box_change(order, box.box_id)
        self._send_message(chat_id, self._t(key, chat_id, order_id=order.order_id[:8], box_id=box.box_id[:8]))
        self._return_to_menu(chat_id, order.order_id)
        return {"status": key if ok else "edit_failed"}

    def show_status_options(self, chat_id: int, order_id: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        options = self._status_options(order)
        if not options:
            self._send_message(chat_id, self._t("edit_order_status_not_allowed", chat_id))
            self._return_to_menu(chat_id, order.order_id)
            return {"status": "no_status_options"}
        buttons = [
            [
                {
                    "text": self._t(f"status_{s}", chat_id),
                    "callback_data": f"edit_order_setstatus_{order.order_id[:8]}_{s}",
                }
            ]
            for s in options
        ]
        buttons.append(
            [{"text": self._t("cancel", user_id=None), "callback_data": f"edit_order_pick_{order.order_id[:8]}"}]
        )
        self._send_message(
            chat_id, self._t("edit_order_pick_status", chat_id), reply_markup={"inline_keyboard": buttons}
        )
        return {"status": "status_options_shown"}

    def confirm_status(self, chat_id: int, order_id: str, new_status: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        buttons = [
            [
                {
                    "text": self._t("confirm", user_id=None),
                    "callback_data": f"edit_order_applystatus_{order.order_id[:8]}_{new_status}",
                }
            ],
            [{"text": self._t("cancel", user_id=None), "callback_data": f"edit_order_pick_{order.order_id[:8]}"}],
        ]
        self._send_message(
            chat_id,
            self._t("edit_order_confirm_status", chat_id, order_id=order.order_id[:8], status=new_status),
            reply_markup={"inline_keyboard": buttons},
        )
        return {"status": "confirm_shown"}

    def apply_status(self, chat_id: int, order_id: str, new_status: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        ok, key = self._apply_status_change(order, new_status)
        self._send_message(chat_id, self._t(key, chat_id, order_id=order_id[:8], status=new_status))
        self._return_to_menu(chat_id, order.order_id)
        return {"status": key if ok else "edit_failed"}

    def prompt_price(self, chat_id: int, order_id: str) -> dict[str, Any]:
        """Store an EditContext and ask the admin to type the new unit price."""
        from models.entities import EditContext

        self.db.create_edit_context(
            EditContext(chat_id=chat_id, edit_type="edit_order_price_input", entity_id=order_id)
        )
        self._send_message(chat_id, self._t("edit_order_enter_price", chat_id))
        return {"status": "awaiting_price"}

    def apply_price_input(self, chat_id: int, order_id: str, text: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        ok, key = self._apply_unit_price_change(order, (text or "").strip())
        self._send_message(chat_id, self._t(key, chat_id, order_id=order_id[:8]))
        self._return_to_menu(chat_id, order.order_id)
        return {"status": key if ok else "edit_failed"}

    def _return_to_menu(self, chat_id: int, order_id: str):
        """After a property edit completes, re-show the aspect menu with the
        refreshed order so the admin can make another change or exit."""
        order = self.db.get_order(order_id)
        if order:
            self.show_aspect_menu(chat_id, order)
