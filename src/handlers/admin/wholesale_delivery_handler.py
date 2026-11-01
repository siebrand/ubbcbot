import logging
from typing import Any

from handlers.admin.base_box_workflow_handler import BaseBoxWorkflowHandler
from models.entities import DeliveryAction, Order
from services.box_status_manager import BoxStatusManager
from services.wholesaler_delivery import WholesalerDeliveryService

logger = logging.getLogger()


class WholesaleDeliveryHandler(BaseBoxWorkflowHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        box_status_manager = BoxStatusManager(db)
        self.delivery_service = WholesalerDeliveryService(db, box_status_manager)

    def handle_process_delivery(self, chat_id: int, user_id: int, args: list[str]) -> dict[str, Any]:
        """Start wholesale delivery drill-down interface"""
        if not self._is_admin(user_id):
            return self._send_message(chat_id, self._t("admin_only", user_id))

        suppliers = self.db.get_suppliers_with_ordered_offers()
        if not suppliers:
            return self._send_message(
                chat_id, self._t("no_ordered_offers", user_id), reply_markup=self._build_admin_menu_keyboard()
            )

        keyboard = self._build_supplier_keyboard(suppliers, "wd")
        return self._send_message(chat_id, self._t("select_supplier_for_delivery", user_id), reply_markup=keyboard)

    def handle_supplier_selection(self, chat_id: int, supplier_id_short: str) -> dict[str, Any]:
        """Handle supplier selection and show offers"""
        return super().handle_supplier_selection(
            chat_id,
            supplier_id_short,
            "wd",
            self.db.get_suppliers_with_ordered_offers,
            self.db.get_ordered_offers_by_supplier,
            "select_offer_for_delivery",
        )

    def handle_offer_selection(self, chat_id: int, offer_id: int, supplier_id_short: str) -> dict[str, Any]:
        """Handle offer selection and show boxes"""
        # Get boxes with ORDERED status (not delivered)
        all_boxes = self.db.get_boxes_by_offer(offer_id)
        boxes = [box for box in all_boxes if box.status == "ordered"]

        return super().handle_offer_selection(
            chat_id,
            offer_id,
            supplier_id_short,
            "wd",
            lambda oid: boxes,  # Use ordered boxes
            "select_box_for_delivery",
            add_complete_button=True,  # Enable complete delivery button
        )

    def handle_box_selection(
        self, chat_id: int, box_id_short: str, offer_id: int, supplier_id_short: str
    ) -> dict[str, Any]:
        """Handle box selection and show triage options"""
        return super().handle_box_selection(
            chat_id,
            box_id_short,
            offer_id,
            supplier_id_short,
            self.db.get_boxes_by_offer_with_orders,
            self._build_triage_keyboard,
            "box_delivery_triage",
        )

    def handle_back_navigation(self, chat_id: int, target: str, *args) -> dict[str, Any]:
        """Handle back button navigation"""
        return super().handle_back_navigation(
            chat_id,
            target,
            "wd",
            self.db.get_suppliers_with_ordered_offers,
            self.db.get_ordered_offers_by_supplier,
            self.db.get_boxes_by_offer_with_orders,
            "select_supplier_for_delivery",
            "select_offer_for_delivery",
            "select_box_for_delivery",
            "no_ordered_offers_for_supplier",
            *args,
        )

    def _build_triage_keyboard(self, box_id: str, offer_id: int, supplier_id_short: str) -> dict[str, Any]:
        """Build triage interface keyboard"""
        box_id_short = box_id[:8]
        keyboard = [
            [
                {
                    "text": self._t("full_delivery_btn", user_id=None),
                    "callback_data": (
                        f"wd_action:{DeliveryAction.FULL.value}:{box_id_short}:{offer_id}:{supplier_id_short}"
                    ),
                }
            ],
            [
                {
                    "text": "⏳ Delayed",
                    "callback_data": (
                        f"wd_action:{DeliveryAction.DELAYED.value}:{box_id_short}:{offer_id}:{supplier_id_short}"
                    ),
                }
            ],
            [
                {
                    "text": self._t("cancel", user_id=None),
                    "callback_data": (
                        f"wd_action:{DeliveryAction.CANCEL.value}:{box_id_short}:{offer_id}:{supplier_id_short}"
                    ),
                }
            ],
            [
                {
                    "text": self._t("incomplete_delivery_btn", user_id=None),
                    "callback_data": (
                        f"wd_action:{DeliveryAction.INCOMPLETE.value}:{box_id_short}:{offer_id}:{supplier_id_short}"
                    ),
                }
            ],
            [
                {
                    "text": self._t("back_to_boxes", user_id=None),
                    "callback_data": f"wd_back:boxes:{offer_id}:{supplier_id_short}",
                }
            ],
        ]

        return {"inline_keyboard": keyboard}

    def handle_delivery_action(
        self, chat_id: int, action: str, box_id_short: str, offer_id: int, supplier_id_short: str
    ) -> dict[str, Any]:
        """Handle delivery action selection"""
        # Find the full box_id from the shortened version
        boxes = self.db.get_boxes_by_offer_with_orders(offer_id)
        box = None
        for b in boxes:
            if b.box_id.startswith(box_id_short):
                box = b
                break

        if not box:
            return self._send_message(chat_id, self._t("box_not_found"))

        orders = self.db.get_orders_by_box(box.box_id)
        total_units = sum(order.quantity for order in orders)

        if action == DeliveryAction.FULL.value:
            return self._handle_full_delivery(chat_id, box.box_id, orders)
        elif action == DeliveryAction.DELAYED.value:
            return self._handle_delayed_delivery(chat_id, box.box_id, orders)
        elif action == DeliveryAction.CANCEL.value:
            return self._handle_cancelled_delivery(chat_id, box.box_id, orders)
        elif action == DeliveryAction.INCOMPLETE.value:
            return self._handle_incomplete_delivery(chat_id, box.box_id, total_units, offer_id, supplier_id_short)

    def _handle_full_delivery(self, chat_id: int, box_id: str, orders: list[Order]) -> dict[str, Any]:
        """Handle full delivery - all units received"""
        success = self.delivery_service.process_wholesaler_delivery(
            box_id, sum(order.quantity for order in orders), False
        )

        if success:
            self._send_message(chat_id, self._t("full_delivery_processed", box_id=box_id[:8]))
            # Continue workflow by showing remaining boxes
            return self._continue_workflow_after_action(chat_id, box_id)
        else:
            return self._send_message(chat_id, self._t("delivery_processing_failed"))

    def _handle_delayed_delivery(self, chat_id: int, box_id: str, orders: list[Order]) -> dict[str, Any]:
        """Handle delayed delivery - no units received but coming later"""
        success = self.delivery_service.process_wholesaler_delivery(box_id, 0, True)

        if success:
            self._send_message(chat_id, self._t("delayed_delivery_processed", box_id=box_id[:8]))
            # Continue workflow by showing remaining boxes
            return self._continue_workflow_after_action(chat_id, box_id)
        else:
            return self._send_message(chat_id, self._t("delivery_processing_failed"))

    def _handle_cancelled_delivery(self, chat_id: int, box_id: str, orders: list[Order]) -> dict[str, Any]:
        """Handle cancelled delivery - no units received and won't come"""
        success = self.delivery_service.process_wholesaler_delivery(box_id, 0, False)

        if success:
            self._send_message(chat_id, self._t("cancelled_delivery_processed", box_id=box_id[:8]))
            # Continue workflow by showing remaining boxes
            return self._continue_workflow_after_action(chat_id, box_id)
        else:
            return self._send_message(chat_id, self._t("delivery_processing_failed"))

    def _handle_incomplete_delivery(
        self, chat_id: int, box_id: str, total_units: int, offer_id: int, supplier_id: str
    ) -> dict[str, Any]:
        """Handle incomplete delivery - prompt for received quantity"""
        # Store context for processing the reply
        self._store_delivery_context(chat_id, box_id, total_units, offer_id, supplier_id)

        return self._send_message(
            chat_id,
            self._t("enter_received_quantity", total_units=total_units),
            reply_markup={
                "force_reply": True,
                "input_field_placeholder": self._t("placeholder_enter_number_range", max=total_units),
            },
        )

    def _store_delivery_context(self, chat_id: int, box_id: str, total_units: int, offer_id: int, supplier_id: str):
        """Store delivery context for processing incomplete delivery reply"""
        from models.entities import EditContext

        # Delete existing context
        existing = self.db.get_edit_context_by_chat_id(chat_id)
        if existing:
            self.db.delete_edit_context(existing.context_id)

        # Create new context with delivery data
        context = EditContext(
            chat_id=chat_id,
            edit_type="incomplete_delivery",
            entity_id=f"{box_id}:{total_units}:{offer_id}:{supplier_id}",
        )
        self.db.create_edit_context(context)

    def handle_incomplete_delivery_reply(self, chat_id: int, received_text: str, context_data: str) -> dict[str, Any]:
        """Handle reply for incomplete delivery quantity"""
        try:
            parts = context_data.split(":")
            box_id, total_units, offer_id, supplier_id = parts[0], int(parts[1]), int(parts[2]), parts[3]

            received_units = int(received_text.strip())

            if received_units < 0 or received_units > total_units:
                return self._send_message(chat_id, self._t("invalid_quantity_range", max_units=total_units))

            if received_units == total_units:
                # Full delivery
                return self._handle_full_delivery(chat_id, box_id, self.db.get_orders_by_box(box_id))
            elif received_units == 0:
                # Show delayed/cancel options
                return self._show_incomplete_options(chat_id, box_id, offer_id, supplier_id, received_units)
            else:
                # Partial delivery - show delayed/cancel options
                return self._show_incomplete_options(chat_id, box_id, offer_id, supplier_id, received_units)

        except ValueError, IndexError:
            return self._send_message(chat_id, self._t("invalid_number_format"))

    def _show_incomplete_options(
        self, chat_id: int, box_id: str, offer_id: int, supplier_id: str, received_units: int
    ) -> dict[str, Any]:
        """Show options for handling remaining units after partial delivery"""
        box_id_short = box_id[:8]
        keyboard = [
            [{"text": "⏳ Remaining Delayed", "callback_data": f"wd_partial:delayed:{box_id_short}:{received_units}"}],
            [
                {
                    "text": self._t("remaining_cancelled_btn", user_id=None),
                    "callback_data": f"wd_partial:cancel:{box_id_short}:{received_units}",
                }
            ],
        ]

        return self._send_message(
            chat_id,
            self._t("choose_remaining_action", received_units=received_units),
            reply_markup={"inline_keyboard": keyboard},
        )

    def handle_partial_action(
        self, chat_id: int, action: str, box_id_short: str, received_units: int
    ) -> dict[str, Any]:
        """Handle action for remaining units in partial delivery"""
        # Find the full box_id from the shortened version by searching all boxes
        # Since we don't have offer_id here, we need to search across all boxes
        all_boxes = []
        try:
            # Get all offers and their boxes to find the matching box
            offers = self.db.list_offers()
            for offer in offers:
                boxes = self.db.get_boxes_by_offer_with_orders(offer.offer_id)
                all_boxes.extend(boxes)
        except Exception as e:
            logger.error(f"Error getting boxes for partial action: {e}")
            return self._send_message(chat_id, self._t("box_not_found"))

        box = None
        for b in all_boxes:
            if b.box_id.startswith(box_id_short):
                box = b
                break

        if not box:
            return self._send_message(chat_id, self._t("box_not_found"))

        is_delayed = action == "delayed"
        success = self.delivery_service.process_wholesaler_delivery(box.box_id, received_units, is_delayed)

        if success:
            action_text = "delayed" if is_delayed else "cancelled"
            self._send_message(
                chat_id,
                self._t(
                    "partial_delivery_processed",
                    box_id=box.box_id[:8],
                    received_units=received_units,
                    action=action_text,
                ),
            )
            # Continue workflow by showing remaining boxes
            return self._continue_workflow_after_action(chat_id, box.box_id)

    def handle_complete_delivery(self, chat_id: int, offer_id: int, supplier_id_short: str) -> dict[str, Any]:
        """Handle complete delivery for all boxes in an offer"""
        # Get all ordered boxes for this offer
        all_boxes = self.db.get_boxes_by_offer(offer_id)
        ordered_boxes = [box for box in all_boxes if box.status == "ordered"]

        if not ordered_boxes:
            return self._send_message(chat_id, self._t("no_ordered_offers"))

        # Show confirmation
        keyboard = [
            [
                {
                    "text": self._t("confirm", user_id=None),
                    "callback_data": f"wd_confirm_complete:{offer_id}:{supplier_id_short}",
                }
            ],
            [
                {
                    "text": self._t("cancel", user_id=None),
                    "callback_data": f"wd_back:boxes:{offer_id}:{supplier_id_short}",
                }
            ],
        ]

        return self._send_message(
            chat_id,
            self._t("complete_delivery_confirmation", box_count=len(ordered_boxes)),
            reply_markup={"inline_keyboard": keyboard},
        )

    def handle_confirm_complete_delivery(self, chat_id: int, offer_id: int, supplier_id_short: str) -> dict[str, Any]:
        """Confirm and execute complete delivery for all boxes"""
        # Get all ordered boxes for this offer
        all_boxes = self.db.get_boxes_by_offer(offer_id)
        ordered_boxes = [box for box in all_boxes if box.status == "ordered"]

        if not ordered_boxes:
            return self._send_message(chat_id, self._t("no_ordered_offers"))

        # Process complete delivery for all boxes
        processed_count = 0
        for box in ordered_boxes:
            orders = self.db.get_orders_by_box(box.box_id)
            total_units = sum(order.quantity for order in orders)

            success = self.delivery_service.process_wholesaler_delivery(
                box.box_id,
                total_units,  # Full delivery
                False,
            )

            if success:
                processed_count += 1

        if processed_count > 0:
            self._send_message(chat_id, self._t("complete_delivery_success", box_count=processed_count))
            # Continue workflow by showing remaining boxes or go back to supplier selection
            return self._continue_workflow_after_complete_delivery(chat_id, offer_id, supplier_id_short)
        else:
            return self._send_message(chat_id, self._t("delivery_processing_failed"))

    def _continue_workflow_after_complete_delivery(
        self, chat_id: int, offer_id: int, supplier_id_short: str
    ) -> dict[str, Any]:
        """Continue workflow after complete delivery - check if any boxes remain"""
        # Check if there are any remaining ordered boxes for this offer
        all_boxes = self.db.get_boxes_by_offer(offer_id)
        remaining_boxes = [box for box in all_boxes if box.status == "ordered"]

        if remaining_boxes:
            # Still have boxes, show them
            return self.handle_offer_selection(chat_id, offer_id, supplier_id_short)
        else:
            # No more boxes for this offer, go back to main wholesale delivery menu
            return self.handle_process_delivery(chat_id, self.admin_user_id, [])

    def _continue_workflow_after_action(self, chat_id: int, processed_box_id: str) -> dict[str, Any]:
        """Continue workflow by showing remaining boxes for the same offer"""
        # Find the offer for this box
        offer = None
        try:
            offers = self.db.list_offers()
            for o in offers:
                boxes = self.db.get_boxes_by_offer_with_orders(o.offer_id)
                if any(b.box_id == processed_box_id for b in boxes):
                    offer = o
                    break
        except Exception as e:
            logger.error(f"Error finding offer for box {processed_box_id}: {e}")
            return {"status": "error"}

        if not offer:
            return {"status": "offer_not_found"}

        # Get remaining boxes with ORDERED status for this offer
        all_boxes = self.db.get_boxes_by_offer(offer.offer_id)
        remaining_boxes = [box for box in all_boxes if box.status == "ordered"]

        if not remaining_boxes:
            # No more boxes, go back to offer selection
            supplier = self.db.get_supplier_by_name(offer.supplier_name)
            if supplier:
                supplier_id_short = supplier.supplier_id[:8]
                return self.handle_supplier_selection(chat_id, supplier_id_short)
            else:
                return self.handle_process_delivery(chat_id, self.admin_user_id, [])

        # Show remaining boxes
        supplier = self.db.get_supplier_by_name(offer.supplier_name)
        supplier_id_short = supplier.supplier_id[:8] if supplier else "unknown"

        return self.handle_offer_selection(chat_id, offer.offer_id, supplier_id_short)
