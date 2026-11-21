import logging
from dataclasses import dataclass
from typing import Any

from handlers.base_handler import BaseHandler
from models.entities import Box, Offer, Supplier

logger = logging.getLogger()


@dataclass
class OfferCompletion:
    """What completing an offer did: the boxes and units that moved on, and the boxes that could not"""

    boxes: int = 0
    units: int = 0
    failed_boxes: int = 0


CHECKED, UNCHECKED = "✅", "⏹️"


class BaseBoxWorkflowHandler(BaseHandler):
    """Base class for box-based workflow handlers (wholesale delivery, labeling completion)

    After the supplier the offers are a checklist: tick offers (all unticked at first), then complete them all with
    one confirmation; › opens an offer box by box, as before. The ticks are kept in the message's own keyboard
    (Telegram sends it with every tap), so nothing is stored, and the message is edited in place.
    """

    # The workflow: its button prefix, translation keys, and what is open and how it is completed (subclasses)
    callback_prefix = ""
    checklist_title_key = ""
    checklist_confirm_key = ""
    no_offers_key = "no_ordered_offers_for_supplier"

    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)

    def _workflow_suppliers(self) -> list[Supplier]:
        raise NotImplementedError

    def _workflow_offers(self, supplier_name: str) -> list[Offer]:
        raise NotImplementedError

    def _open_work(self, offer_id: int) -> tuple[int, int]:
        """(boxes, units) still to do for the offer in this workflow"""
        raise NotImplementedError

    def complete_offer(self, offer_id: int) -> OfferCompletion:
        raise NotImplementedError

    # ---------------------------------------------------------------------------------------------- checklist
    def _supplier(self, supplier_id_short: str) -> Supplier | None:
        return next((s for s in self._workflow_suppliers() if s.supplier_id.startswith(supplier_id_short)), None)

    def _show(self, chat_id: int, message_id: int | None, text: str, keyboard: dict[str, Any]) -> dict[str, Any]:
        """Edit the tapped message in place; send a new one when there is none or it cannot be edited"""
        if message_id and self._edit_message_text(chat_id, message_id, text, reply_markup=keyboard).get("success"):
            return {"success": True, "message_id": message_id}
        return self._send_message(chat_id, text, reply_markup=keyboard)

    def _selected(self, markup: dict | None) -> set[int]:
        """The offers ticked in a checklist (or confirmation) keyboard"""
        prefix = f"{self.callback_prefix}_tg:"
        selected = set()
        for row in (markup or {}).get("inline_keyboard", []):
            for button in row:
                data = button.get("callback_data", "")
                if data.startswith(prefix) and button.get("text", "").startswith(CHECKED):
                    offer_id = data[len(prefix) :].split(":", 1)[0]
                    if offer_id.isdigit():
                        selected.add(int(offer_id))
        return selected

    def show_offer_checklist(
        self, chat_id: int, supplier_id_short: str, selected: set[int], message_id: int | None = None
    ) -> dict[str, Any]:
        """The supplier's offers with work left, each to tick (or to open with ›), and the bulk button"""
        callback_prefix = self.callback_prefix
        supplier = self._supplier(supplier_id_short)
        if not supplier:
            return self._send_message(chat_id, self._t("supplier_not_found", chat_id))
        offers = sorted(self._workflow_offers(supplier.name), key=lambda o: o.name.lower())
        if not offers:
            return self._send_message(chat_id, self._t(self.no_offers_key, chat_id, supplier_name=supplier.name))

        selected = selected & {offer.offer_id for offer in offers}
        keyboard = []
        for offer in offers:
            boxes, units = self._open_work(offer.offer_id)
            mark = CHECKED if offer.offer_id in selected else UNCHECKED
            row_text = self._t("checklist_row", chat_id, mark=mark, name=offer.name, boxes=boxes, units=units)
            keyboard.append(
                [
                    {"text": row_text, "callback_data": f"{callback_prefix}_tg:{offer.offer_id}:{supplier_id_short}"},
                    {"text": "›", "callback_data": f"{callback_prefix}_off:{offer.offer_id}:{supplier_id_short}"},
                ]
            )
        keyboard.append(
            [
                {
                    "text": self._t("checklist_select_all", chat_id),
                    "callback_data": f"{callback_prefix}_all:{supplier_id_short}",
                },
                {
                    "text": self._t("checklist_select_none", chat_id),
                    "callback_data": f"{callback_prefix}_none:{supplier_id_short}",
                },
            ]
        )
        keyboard.append(
            [
                {
                    "text": self._t("checklist_bulk_btn", chat_id, count=len(selected)),
                    "callback_data": f"{callback_prefix}_bulk:{supplier_id_short}",
                }
            ]
        )
        keyboard.append(
            [{"text": self._t("back_to_suppliers", chat_id), "callback_data": f"{callback_prefix}_back:suppliers"}]
        )
        text = self._t(self.checklist_title_key, chat_id, supplier_name=supplier.name, count=len(selected))
        return self._show(chat_id, message_id, text, {"inline_keyboard": keyboard})

    def handle_checklist_toggle(
        self, chat_id: int, message_id: int, markup: dict | None, offer_id: int, supplier_id_short: str
    ) -> dict[str, Any]:
        """Tick or untick one offer (from the checklist or from the confirmation)"""
        return self.show_offer_checklist(chat_id, supplier_id_short, self._selected(markup) ^ {offer_id}, message_id)

    def handle_checklist_select(
        self, chat_id: int, message_id: int, supplier_id_short: str, everything: bool
    ) -> dict[str, Any]:
        """Tick every offer, or none"""
        supplier = self._supplier(supplier_id_short)
        offers = self._workflow_offers(supplier.name) if supplier and everything else []
        return self.show_offer_checklist(chat_id, supplier_id_short, {o.offer_id for o in offers}, message_id)

    def handle_checklist_back(
        self, chat_id: int, message_id: int, markup: dict | None, supplier_id_short: str
    ) -> dict[str, Any]:
        """From the confirmation back to the checklist, with the same offers ticked"""
        return self.show_offer_checklist(chat_id, supplier_id_short, self._selected(markup), message_id)

    def handle_checklist_bulk(
        self, chat_id: int, message_id: int, markup: dict | None, supplier_id_short: str
    ) -> dict[str, Any]:
        """One confirmation for every ticked offer: per offer and in total, what will be completed"""
        callback_prefix = self.callback_prefix
        supplier = self._supplier(supplier_id_short)
        offers = {o.offer_id: o for o in self._workflow_offers(supplier.name)} if supplier else {}
        selected = [offers[i] for i in sorted(self._selected(markup)) if i in offers]
        if not selected:
            self._send_message(chat_id, self._t("checklist_nothing_selected", chat_id))
            return {"status": "nothing_selected"}

        lines, total_boxes, total_units = [], 0, 0
        keyboard = []
        for offer in sorted(selected, key=lambda o: o.name.lower()):
            boxes, units = self._open_work(offer.offer_id)
            total_boxes, total_units = total_boxes + boxes, total_units + units
            lines.append(self._t("checklist_line", chat_id, name=offer.name, boxes=boxes, units=units))
            # The ticked offers stay in the keyboard: they are the selection the confirmation carries
            keyboard.append(
                [
                    {
                        "text": f"{CHECKED} {offer.name}",
                        "callback_data": f"{callback_prefix}_tg:{offer.offer_id}:{supplier_id_short}",
                    }
                ]
            )
        keyboard.append(
            [{"text": self._t("confirm", chat_id), "callback_data": f"{callback_prefix}_bulkok:{supplier_id_short}"}]
        )
        keyboard.append(
            [
                {
                    "text": self._t("checklist_back_btn", chat_id),
                    "callback_data": f"{callback_prefix}_bulkback:{supplier_id_short}",
                }
            ]
        )
        text = self._t(
            self.checklist_confirm_key,
            chat_id,
            lines="\n".join(lines),
            offers=len(selected),
            boxes=total_boxes,
            units=total_units,
        )
        self._show(chat_id, message_id, text, {"inline_keyboard": keyboard})
        return {"status": "confirmation_shown"}

    def handle_checklist_confirm(
        self, chat_id: int, message_id: int, markup: dict | None, supplier_id_short: str
    ) -> dict[str, Any]:
        """Complete every ticked offer that still has work left; report what was done, skipped or failed"""
        callback_prefix = self.callback_prefix
        supplier = self._supplier(supplier_id_short)
        offers = {o.offer_id: o for o in self._workflow_offers(supplier.name)} if supplier else {}
        done: list[str] = []
        failed: list[str] = []
        skipped: list[int] = []
        boxes = units = 0
        for offer_id in sorted(self._selected(markup)):
            offer = offers.get(offer_id)
            if offer is None:  # done or changed since the confirmation was shown
                skipped.append(offer_id)
                continue
            result = self.complete_offer(offer_id)
            boxes, units = boxes + result.boxes, units + result.units
            (failed if result.failed_boxes else done).append(offer.name)

        text = self._t("checklist_done", chat_id, offers=len(done), boxes=boxes, units=units)
        if skipped:
            names = ", ".join(self._offer_name(offer_id) for offer_id in skipped)
            text += "\n" + self._t("checklist_skipped", chat_id, names=names)
        if failed:
            text += "\n" + self._t("checklist_failed", chat_id, names=", ".join(failed))
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": self._t("back_to_offers", chat_id),
                        "callback_data": f"{callback_prefix}_back:offers:{supplier_id_short}",
                    }
                ],
                [{"text": self._t("back_to_admin_menu", chat_id), "callback_data": "admin:main"}],
            ]
        }
        self._show(chat_id, message_id, text, keyboard)
        return {"status": "completed", "offers": len(done), "skipped": len(skipped), "failed": len(failed)}

    def _offer_name(self, offer_id: int) -> str:
        offer = self.db.get_offer(offer_id)
        return offer.name if offer else str(offer_id)

    def _build_supplier_keyboard(self, suppliers: list[Supplier], callback_prefix: str) -> dict[str, Any]:
        """Build inline keyboard for supplier selection"""
        # Sort suppliers alphabetically by name
        sorted_suppliers = sorted(suppliers, key=lambda s: s.name.lower())

        keyboard = []
        for supplier in sorted_suppliers:
            keyboard.append(
                [{"text": supplier.name, "callback_data": f"{callback_prefix}_sup:{supplier.supplier_id[:8]}"}]
            )

        # Add back to admin menu button
        keyboard.append([{"text": self._t("back_to_admin_menu", user_id=None), "callback_data": "admin:main"}])

        return {"inline_keyboard": keyboard}

    def _build_box_keyboard(
        self,
        boxes: list[Box],
        offer_id: int,
        supplier_id_short: str,
        callback_prefix: str,
        add_complete_button: bool = False,
    ) -> dict[str, Any]:
        """Build inline keyboard for box selection"""
        keyboard = []

        # Add "Complete delivery" button if requested
        if add_complete_button and boxes:
            keyboard.append(
                [
                    {
                        "text": self._t("complete_delivery_btn", user_id=None),
                        "callback_data": f"{callback_prefix}_complete:{offer_id}:{supplier_id_short}",
                    }
                ]
            )

        for box in boxes:
            orders = self.db.get_orders_by_box(box.box_id)
            total_units = sum(order.quantity for order in orders)

            keyboard.append(
                [
                    {
                        "text": f"Box {box.box_id[:8]}... ({total_units} units)",
                        "callback_data": f"{callback_prefix}_box:{box.box_id[:8]}:{offer_id}:{supplier_id_short}",
                    }
                ]
            )

        # Add back button
        keyboard.append(
            [
                {
                    "text": self._t("back_to_offers", user_id=None),
                    "callback_data": f"{callback_prefix}_back:offers:{supplier_id_short}",
                }
            ]
        )

        return {"inline_keyboard": keyboard}

    def handle_offer_selection(
        self,
        chat_id: int,
        offer_id: int,
        supplier_id_short: str,
        callback_prefix: str,
        get_boxes_func,
        select_box_msg_key: str,
        add_complete_button: bool = False,
    ) -> dict[str, Any]:
        """Handle offer selection and show boxes"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            return self._send_message(chat_id, self._t("offer_not_found"))

        boxes = get_boxes_func(offer_id)
        if not boxes:
            return self._send_message(chat_id, self._t("no_boxes_with_orders", offer_name=offer.name))

        keyboard = self._build_box_keyboard(boxes, offer_id, supplier_id_short, callback_prefix, add_complete_button)
        return self._edit_message(chat_id, self._t(select_box_msg_key, offer_name=offer.name), reply_markup=keyboard)

    def handle_box_selection(
        self,
        chat_id: int,
        box_id_short: str,
        offer_id: int,
        supplier_id_short: str,
        get_boxes_func,
        build_action_keyboard_func,
        box_action_msg_key: str,
    ) -> dict[str, Any]:
        """Handle box selection and show action options"""
        # Find the full box_id from the shortened version
        boxes = get_boxes_func(offer_id)
        box = None
        for b in boxes:
            if b.box_id.startswith(box_id_short):
                box = b
                break

        if not box:
            return self._send_message(chat_id, self._t("box_not_found"))

        orders = self.db.get_orders_by_box(box.box_id)
        total_units = sum(order.quantity for order in orders)

        keyboard = build_action_keyboard_func(box.box_id, offer_id, supplier_id_short)

        message = self._t(box_action_msg_key, box_id=box.box_id[:8], total_units=total_units, order_count=len(orders))

        return self._edit_message(chat_id, message, reply_markup=keyboard)

    def handle_back_navigation(
        self,
        chat_id: int,
        target: str,
        callback_prefix: str,
        get_suppliers_func,
        get_offers_func,
        get_boxes_func,
        select_supplier_msg_key: str,
        select_offer_msg_key: str,
        select_box_msg_key: str,
        no_offers_msg_key: str = "no_ordered_offers_for_supplier",
        *args,
    ) -> dict[str, Any]:
        """Handle back button navigation"""
        if target == "suppliers":
            suppliers = get_suppliers_func()
            keyboard = self._build_supplier_keyboard(suppliers, callback_prefix)
            return self._edit_message(chat_id, self._t(select_supplier_msg_key), reply_markup=keyboard)
        elif target == "offers" and args:
            # The offers of the supplier are the checklist, nothing ticked
            return self.show_offer_checklist(chat_id, args[0], set())
        elif target == "boxes" and len(args) >= 2:
            offer_id, supplier_id_short = int(args[0]), args[1]
            offer = self.db.get_offer(offer_id)
            boxes = get_boxes_func(offer_id)
            keyboard = self._build_box_keyboard(
                boxes, offer_id, supplier_id_short, callback_prefix, add_complete_button=callback_prefix == "wd"
            )  # Only for wholesale delivery
            return self._edit_message(
                chat_id, self._t(select_box_msg_key, offer_name=offer.name), reply_markup=keyboard
            )

        logger.warning(f"Unknown back navigation target: {target} (args: {args})")
        return {"status": "unknown_target"}

    def _edit_message(self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
        """Edit message with new content and keyboard - placeholder that sends new message

        Note: This is a simplified implementation. For proper message editing,
        the message_id needs to be passed through the callback context.
        """
        return self._send_message(chat_id, text, reply_markup=reply_markup)
