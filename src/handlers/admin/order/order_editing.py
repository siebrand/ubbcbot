import logging
from decimal import Decimal
from typing import Any

from models.entities import BoxStatus
from services.box_status_manager import BoxStatusManager

from .base_order_handler import BaseOrderHandler

logger = logging.getLogger(__name__)


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
        """Boxes of the order's offer that have room for the order's quantity,
        excluding the order's current box, sorted by creation order."""
        boxes = self.db.get_boxes_by_offer(order.offer_id) or []
        candidates = [
            b
            for b in boxes
            if b.box_id != order.box_id
            and b.status != BoxStatus.DELIVERED.value
            and (b.max_capacity - b.current_quantity) >= order.quantity
        ]
        candidates.sort(key=lambda b: getattr(b, "created_at", None) or 0)
        return candidates

    def _apply_box_change(self, order, new_box_id: str) -> tuple[bool, str]:
        """Move the order to new_box_id, correcting occupancy atomically.

        Increments the new box first (capacity-guarded); only if that succeeds
        does it decrement the old box. Rolls back the new-box increment if the
        old-box decrement fails. Returns (success, message_key)."""
        if new_box_id == order.box_id:
            return False, "edit_order_same_box"

        new_box = self.db.get_box(new_box_id)
        if not new_box:
            return False, "edit_order_box_not_found"
        if new_box.offer_id != order.offer_id:
            return False, "edit_order_box_wrong_offer"

        # Increment the destination first; the capacity guard rejects overfill.
        if not self.box_status_manager.update_box_after_order_placement(new_box_id, order.quantity):
            return False, "edit_order_box_full"

        # Then free the old box; roll back the increment if this fails.
        if not self.box_status_manager.update_box_after_order_cancellation(order.box_id, order.quantity):
            self.box_status_manager.update_box_after_order_cancellation(new_box_id, order.quantity)
            return False, "edit_order_move_failed"

        if not self.db.update_order(order.order_id, {"box_id": new_box_id}, self.admin_user_id, "Order box edited"):
            return False, "edit_order_update_failed"

        self.box_status_manager.update_offer_status_after_change(order.offer_id)
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
    def _status_options(self) -> list[str]:
        """Order statuses offered for editing, in workflow order."""
        return [
            "pending",
            "ordered",
            "received_partial_delayed",
            "ready_for_labeling",
            "labeling_completed",
            "awaiting_payment",
            "completed",
            "cancelled",
        ]

    def _apply_status_change(self, order, new_status: str) -> tuple[bool, str]:
        """Set the order's status (no guards; any workflow status allowed)."""
        if new_status not in self._status_options():
            return False, "edit_order_bad_status"
        if not self.db.update_order(order.order_id, {"status": new_status}, self.admin_user_id, "Order status edited"):
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
        return self._show_aspect_menu(chat_id, order)

    def _show_order_disambiguation(self, chat_id: int, matches: list) -> dict[str, Any]:
        message = self._t("multiple_orders_found_partial", chat_id, partial_id=matches[0][0].order_id[:8]) + "\n\n"
        buttons = []
        for order, customer in matches:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else self._t("unknown", user_id=None)
            name = f"{customer.first_name} {customer.last_name}" if customer else self._t("unknown", user_id=None)
            label = f"{order.order_id[:8]}: {name} - {order.quantity}x {offer_name}"
            buttons.append([{"text": label, "callback_data": f"edit_order_pick_{order.order_id}"}])
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

    def _show_aspect_menu(self, chat_id: int, order) -> dict[str, Any]:
        oid = order.order_id
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
        order = self.db.get_order(order_id)
        if not order:
            self._send_message(chat_id, self._t("order_not_found_full_id", chat_id, order_id=order_id))
        return order

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
                    "text": f"{b.box_id} ({b.current_quantity}/{b.max_capacity})",
                    "callback_data": f"edit_order_setbox_{order_id}_{b.box_id}",
                }
            ]
            for b in boxes
        ]
        buttons.append([{"text": self._t("cancel", user_id=None), "callback_data": "cancel_action"}])
        self._send_message(chat_id, self._t("edit_order_pick_box", chat_id), reply_markup={"inline_keyboard": buttons})
        return {"status": "box_options_shown"}

    def confirm_box(self, chat_id: int, order_id: str, new_box_id: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        buttons = [
            [
                {
                    "text": self._t("confirm", user_id=None),
                    "callback_data": f"edit_order_applybox_{order_id}_{new_box_id}",
                }
            ],
            [{"text": self._t("cancel", user_id=None), "callback_data": "cancel_action"}],
        ]
        self._send_message(
            chat_id,
            self._t("edit_order_confirm_box", chat_id, order_id=order_id[:8], box_id=new_box_id),
            reply_markup={"inline_keyboard": buttons},
        )
        return {"status": "confirm_shown"}

    def apply_box(self, chat_id: int, order_id: str, new_box_id: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        ok, key = self._apply_box_change(order, new_box_id)
        self._send_message(chat_id, self._t(key, chat_id, order_id=order_id[:8], box_id=new_box_id))
        return {"status": key if ok else "edit_failed"}

    def show_status_options(self, chat_id: int, order_id: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        buttons = [
            [{"text": s, "callback_data": f"edit_order_setstatus_{order_id}_{s}"}] for s in self._status_options()
        ]
        buttons.append([{"text": self._t("cancel", user_id=None), "callback_data": "cancel_action"}])
        self._send_message(
            chat_id, self._t("edit_order_pick_status", chat_id), reply_markup={"inline_keyboard": buttons}
        )
        return {"status": "status_options_shown"}

    def confirm_status(self, chat_id: int, order_id: str, new_status: str) -> dict[str, Any]:
        buttons = [
            [
                {
                    "text": self._t("confirm", user_id=None),
                    "callback_data": f"edit_order_applystatus_{order_id}_{new_status}",
                }
            ],
            [{"text": self._t("cancel", user_id=None), "callback_data": "cancel_action"}],
        ]
        self._send_message(
            chat_id,
            self._t("edit_order_confirm_status", chat_id, order_id=order_id[:8], status=new_status),
            reply_markup={"inline_keyboard": buttons},
        )
        return {"status": "confirm_shown"}

    def apply_status(self, chat_id: int, order_id: str, new_status: str) -> dict[str, Any]:
        order = self._get_order_or_warn(chat_id, order_id)
        if not order:
            return {"status": "order_not_found"}
        ok, key = self._apply_status_change(order, new_status)
        self._send_message(chat_id, self._t(key, chat_id, order_id=order_id[:8], status=new_status))
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
        return {"status": key if ok else "edit_failed"}
