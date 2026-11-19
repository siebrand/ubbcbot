import contextlib
from datetime import datetime
from typing import Any

from models.entities import Box, BoxStatus, OfferStatus, OrderStatus
from services import box_refill
from services.box_status_manager import BoxStatusManager
from services.wholesale_plan import boxes_needed

from .base import OfferBaseHandler


class BoxManagementHandler(OfferBaseHandler):
    """Handler for box management operations"""

    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)

    def handle_create_box(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /create_box command"""
        error = self._validate_args(args, 1, "usage_create_box", chat_id)
        if error:
            return error

        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)

            if not offer:
                self._send_message(chat_id, self._t("offer_not_found", chat_id))
                return {"status": "offer_not_found"}

            # Create new box
            box = Box(offer_id=offer_id, max_capacity=offer.wholesale_box_size)

            if self.db.create_box(box):
                # Update offer status from sold_out to active if needed
                if offer.status == OfferStatus.SOLD_OUT.value:
                    self.db.update_offer(offer_id, {"status": OfferStatus.ACTIVE.value})
                    self.sync_offer_messages(offer_id)
                    self._send_message(chat_id, self._t("box_added_offer_active", chat_id, offer_id=offer_id))
                else:
                    self._send_message(chat_id, self._t("box_added", chat_id, offer_id=offer_id))
                return {"status": "success"}
            else:
                self._send_message(chat_id, self._t("failed_create_box", chat_id))
                return {"status": "error"}

        except ValueError:
            self._send_message(chat_id, self._t("invalid_offer_id", chat_id))
            return {"status": "invalid_format"}

    # The box statuses each /list_boxes filter shows (None: every status)
    BOX_FILTERS = {
        "active": {BoxStatus.OPEN.value, BoxStatus.FULL.value, BoxStatus.ORDERED.value},
        "ordered": {BoxStatus.ORDERED.value},
        "full": {BoxStatus.FULL.value},
        "delivered": {BoxStatus.DELIVERED.value},
        "all": None,
    }
    # Per offer: ordered boxes first, then full, open and delivered
    STATUS_PRIORITY = {
        BoxStatus.ORDERED.value: 0,
        BoxStatus.FULL.value: 1,
        BoxStatus.OPEN.value: 2,
        BoxStatus.DELIVERED.value: 3,
    }
    STATUS_EMOJIS = {
        BoxStatus.OPEN.value: "🟢",
        BoxStatus.FULL.value: "🔴",
        BoxStatus.ORDERED.value: "📦",
        BoxStatus.DELIVERED.value: "✅",
    }

    @classmethod
    def _parse_list_boxes_args(cls, args: list) -> tuple[str, int | None, int]:
        """(status filter, offer id or None, page) from `/list_boxes [status|offer_id] [page]`"""
        status_filter, offer_filter, page_args = "active", None, []
        if args:
            if args[0].lower() in cls.BOX_FILTERS:
                status_filter, page_args = args[0].lower(), args[1:2]
            else:
                with contextlib.suppress(ValueError):
                    offer_filter = int(args[0])
                    page_args = args[1:2]
        page = 1
        if page_args:
            with contextlib.suppress(ValueError):
                page = int(page_args[0])
        return status_filter, offer_filter, page

    @staticmethod
    def _created_at_key(box) -> str:
        """created_at is an ISO 8601 string (sortable as text), but may be a datetime"""
        created_at = box.created_at
        if isinstance(created_at, datetime):
            return created_at.isoformat()
        return str(created_at) if created_at is not None else ""

    def handle_list_boxes(self, chat_id: int, args: list | None = None) -> dict[str, Any]:
        """Handle /list_boxes command with pagination and optional status/offer filter"""
        args = args or []
        if args and args[0].lower() == "help":
            self._send_message(chat_id, self._t("box_status_help", chat_id))
            return {"status": "success"}
        status_filter, offer_filter, page = self._parse_list_boxes_args(args)

        offers = {offer.offer_id: offer for offer in self.db.list_offers()}
        if offer_filter:
            if offer_filter not in offers:
                self._send_message(chat_id, self._t("offer_not_found", chat_id))
                return {"status": "offer_not_found"}
            boxes = self.db.get_boxes_by_offer(offer_filter)
        else:
            boxes = self.db.get_all_boxes()

        wanted = self.BOX_FILTERS[status_filter]
        offer_boxes = [
            (offers[box.offer_id], box)
            for box in boxes
            if box.offer_id in offers and (wanted is None or box.status in wanted)
        ]
        if not offer_boxes:
            self._send_message(chat_id, self._t("no_boxes_found", chat_id, status=status_filter))
            return {"status": "no_boxes"}

        offer_boxes.sort(
            key=lambda x: (x[0].offer_id, self.STATUS_PRIORITY.get(x[1].status, 99), self._created_at_key(x[1]))
        )
        page_items, total_pages = self._paginate_list(offer_boxes, page, 10)

        message = (
            self._t("box_status_header", chat_id, status=status_filter.title(), page=page, total_pages=total_pages)
            + "\n\n"
        )
        message += "```\n"
        message += self._t("box_status_table_header", chat_id) + "\n"
        message += self._t("box_status_table_separator", chat_id) + "\n"
        for offer, box in page_items:
            status_emoji = self.STATUS_EMOJIS.get(box.status, "❓")
            price_str = f"€{offer.price_per_unit:.2f}"
            units_str = f"{box.current_quantity}/{box.max_capacity}"
            message += (
                f"{status_emoji}     {str(offer.offer_id):<4}  {box.box_id[:8]:<8}  "
                f"{offer.name[:20]:<20}  {price_str:>6}  {units_str:>5}\n"
            )
        message += "```"

        rows = []
        if total_pages > 1:
            filter_key = f"offer_{offer_filter}" if offer_filter else status_filter
            keyboard = self._build_pagination_keyboard(page, total_pages, f"boxes_{filter_key}", enhanced=True)
            rows = keyboard["inline_keyboard"]

        # A button to finish labeling, for the listed boxes with orders that are ready for it
        ready = {o.box_id for o in self.db.get_all_orders(statuses=[OrderStatus.READY_FOR_LABELING.value])}
        rows += [
            [
                {
                    "text": self._t("finish_labeling_box", chat_id, box_id=box.box_id[:8]),
                    "callback_data": f"finish_labeling_{box.box_id}",
                }
            ]
            for _offer, box in page_items
            if box.box_id in ready
        ]
        rows.append([{"text": self._t("back_to_admin", chat_id), "callback_data": "admin:main"}])

        self._send_message(chat_id, message, reply_markup={"inline_keyboard": rows}, parse_mode="Markdown")
        return {"status": "success"}

    def handle_audit_offer(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /audit_offer command - check and fix order/box discrepancies"""
        if not args:
            # Show button interface to select offer
            return self.show_audit_offer_selection(chat_id)

        try:
            offer_id = int(args[0])
            return self.execute_audit_offer(chat_id, offer_id)
        except ValueError:
            self._send_message(chat_id, self._t("invalid_offer_id", chat_id))
            return {"status": "invalid_format"}

    def show_audit_offer_selection(self, chat_id: int, page: int = 1) -> dict[str, Any]:
        """Show paginated list of offers for audit selection"""
        offers = [
            o for o in self.db.list_offers() if o.status in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value]
        ]

        if not offers:
            self._send_message(chat_id, self._t("no_offers_for_audit", chat_id))
            return {"status": "no_offers"}

        # Sort by offer_id for consistent ordering
        offers.sort(key=lambda x: x.offer_id)

        # Paginate results
        page_offers, total_pages = self._paginate_list(offers, page, 10)

        message = self._t("select_offer_for_audit", chat_id, page=page, total_pages=total_pages) + "\n\n"
        keyboard_buttons = []

        supplier_names = {supplier.name for supplier in self.db.list_suppliers()}
        for offer in page_offers:
            known = offer.supplier_name in supplier_names
            supplier_name = offer.supplier_name if known else self._t("unknown", chat_id)
            button_text = f"🍺 {offer.name} - €{offer.price_per_unit:.2f} ({supplier_name})"
            keyboard_buttons.append([{"text": button_text, "callback_data": f"audit_offer_{offer.offer_id}"}])

        # Add pagination if needed
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(
                    {"text": self._t("previous", chat_id), "callback_data": f"audit_offers_page_{page - 1}"}
                )
            nav_buttons.append(
                {
                    "text": self._t("page_indicator", chat_id, page=page, total_pages=total_pages),
                    "callback_data": "page_info",
                }
            )
            if page < total_pages:
                nav_buttons.append({"text": self._t("next", chat_id), "callback_data": f"audit_offers_page_{page + 1}"})
            keyboard_buttons.append(nav_buttons)

        # Add cancel button
        keyboard_buttons.append([{"text": self._t("cancel", chat_id), "callback_data": "cancel_action"}])

        keyboard = {"inline_keyboard": keyboard_buttons}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "success"}

    def execute_audit_offer(self, chat_id: int, offer_id: int) -> dict[str, Any]:
        """Execute audit for specific offer"""
        offer = self.db.get_offer(offer_id)

        if not offer:
            self._send_message(chat_id, self._t("offer_not_found", chat_id))
            return {"status": "offer_not_found"}

        active_orders = self._active_orders(offer_id)
        total_ordered_units = sum(order.quantity for order in active_orders)

        # Get boxes and calculate total capacity
        boxes = self.db.get_boxes_by_offer(offer_id)
        total_box_capacity = sum(box.current_quantity for box in boxes)

        # Check if numbers match
        if total_ordered_units == total_box_capacity:
            self._send_message(
                chat_id,
                self._t("audit_offer_match", chat_id, offer_id=offer_id, units=total_ordered_units, boxes=len(boxes)),
            )
            return {"status": "match"}

        # Numbers don't match - determine remediation
        discrepancy = total_ordered_units - total_box_capacity

        if discrepancy > 0:
            # More orders than box capacity
            self._send_message(
                chat_id,
                self._t(
                    "audit_excess_orders",
                    chat_id,
                    offer_id=offer_id,
                    ordered=total_ordered_units,
                    capacity=total_box_capacity,
                    excess=discrepancy,
                ),
            )
            return self._propose_excess_orders_action(chat_id, offer, boxes, active_orders, discrepancy)
        else:
            # More box capacity than orders
            self._send_message(
                chat_id,
                self._t(
                    "audit_excess_capacity",
                    chat_id,
                    offer_id=offer_id,
                    ordered=total_ordered_units,
                    capacity=total_box_capacity,
                    excess=abs(discrepancy),
                ),
            )
            return {"status": "excess_capacity"}

    def _propose_excess_orders_action(
        self, chat_id: int, offer, boxes, active_orders, excess_units: int
    ) -> dict[str, Any]:
        """Propose action for excess orders - fill existing boxes first, then create new boxes if needed"""
        # Get unordered and ordered boxes separately
        unordered_boxes = [b for b in boxes if b.status not in [BoxStatus.ORDERED.value, BoxStatus.DELIVERED.value]]
        ordered_boxes = [b for b in boxes if b.status == BoxStatus.ORDERED.value]

        # Calculate available capacity in unordered boxes
        unordered_capacity = sum(max(0, b.max_capacity - b.current_quantity) for b in unordered_boxes)

        # Calculate available capacity in ordered boxes
        ordered_capacity = sum(max(0, b.max_capacity - b.current_quantity) for b in ordered_boxes)

        total_capacity = unordered_capacity + ordered_capacity

        if total_capacity >= excess_units:
            # Can fill existing boxes (prioritize unordered, then ordered)
            message = self._t(
                "audit_propose_fill_boxes",
                chat_id,
                offer_id=offer.offer_id,
                excess=excess_units,
                available=total_capacity,
            )

            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": self._t("confirm_fill_boxes", chat_id),
                            "callback_data": f"audit_fill_boxes_{offer.offer_id}_{excess_units}",
                        }
                    ],
                    [{"text": self._t("cancel", chat_id), "callback_data": "cancel_action"}],
                ]
            }
        elif unordered_boxes and total_capacity > 0:
            # Fill existing boxes and create new ones (only if unordered boxes exist)
            box_size = offer.wholesale_box_size
            new_boxes = boxes_needed(excess_units - total_capacity, box_size)

            message = self._t(
                "audit_propose_fill_and_create",
                chat_id,
                offer_id=offer.offer_id,
                excess=excess_units,
                available=total_capacity,
                boxes=new_boxes,
                box_size=box_size,
            )

            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": self._t("confirm_fill_and_create", chat_id),
                            "callback_data": f"audit_fill_create_{offer.offer_id}_{excess_units}",
                        }
                    ],
                    [{"text": self._t("cancel", chat_id), "callback_data": "cancel_action"}],
                ]
            }
        elif not ordered_boxes:
            # No ordered boxes exist - create new boxes instead of canceling orders
            box_size = offer.wholesale_box_size
            new_boxes = boxes_needed(excess_units, box_size)

            message = self._t(
                "audit_propose_create_boxes",
                chat_id,
                offer_id=offer.offer_id,
                excess=excess_units,
                boxes=new_boxes,
                box_size=box_size,
            )

            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": self._t("confirm_create_boxes", chat_id),
                            "callback_data": f"audit_create_boxes_{offer.offer_id}_{excess_units}",
                        }
                    ],
                    [{"text": self._t("cancel", chat_id), "callback_data": "cancel_action"}],
                ]
            }
        else:
            # No capacity available - need to cancel orders
            orders_to_cancel = self._orders_to_cancel(active_orders, excess_units)
            order_details = []
            for order in orders_to_cancel:
                customer = self.db.get_customer(order.customer_id)
                customer_name = customer.first_name if customer else self._t("unknown", chat_id)
                order_details.append(f"{customer_name} ({order.quantity} {self._units(order.quantity, chat_id)})")

            message = self._t(
                "audit_propose_cancel_orders",
                chat_id,
                offer_id=offer.offer_id,
                count=len(orders_to_cancel),
                excess=excess_units,
                orders="\n".join(order_details),
            )

            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": self._t("confirm_cancel_orders", chat_id),
                            "callback_data": f"audit_cancel_orders_{offer.offer_id}_{excess_units}",
                        }
                    ],
                    [{"text": self._t("cancel", chat_id), "callback_data": "cancel_action"}],
                ]
            }

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "awaiting_confirmation"}

    def execute_fill_boxes(self, chat_id: int, offer_id: int, excess_units: int) -> dict[str, Any]:
        """Execute filling existing boxes after confirmation"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t("offer_not_found", chat_id))
            return {"status": "offer_not_found"}

        # Unordered boxes first, then ordered ones; delivered boxes are done
        boxes = self.db.get_boxes_by_offer(offer_id)
        unordered_boxes = [b for b in boxes if b.status not in [BoxStatus.ORDERED.value, BoxStatus.DELIVERED.value]]
        ordered_boxes = [b for b in boxes if b.status == BoxStatus.ORDERED.value]

        filled_units = 0
        for box in unordered_boxes + ordered_boxes:
            if filled_units >= excess_units:
                break
            available = box.max_capacity - box.current_quantity
            if available > 0:
                fill_amount = min(available, excess_units - filled_units)
                self.box_status_manager.update_box_after_order_placement(box.box_id, fill_amount)
                filled_units += fill_amount

        if filled_units > 0:
            self._check_offer_status_after_change(offer_id)

        self._send_message(chat_id, self._t("audit_boxes_filled", chat_id, offer_id=offer_id, filled=filled_units))
        return {"status": "boxes_filled", "filled": filled_units}

    def execute_fill_and_create(self, chat_id: int, offer_id: int, excess_units: int) -> dict[str, Any]:
        """Execute filling existing boxes and creating new ones after confirmation"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t("offer_not_found", chat_id))
            return {"status": "offer_not_found"}

        # First fill existing capacity
        fill_result = self.execute_fill_boxes(chat_id, offer_id, excess_units)
        filled_units = fill_result.get("filled", 0)

        # Create new boxes for remaining units
        remaining_units = excess_units - filled_units
        if remaining_units > 0:
            create_result = self._add_box_capacity(chat_id, offer, remaining_units)
            boxes_created = create_result.get("boxes", 0)

            self._send_message(
                chat_id,
                self._t(
                    "audit_filled_and_created",
                    chat_id,
                    offer_id=offer_id,
                    filled=filled_units,
                    boxes=boxes_created,
                    remaining=remaining_units,
                ),
            )

        return {"status": "filled_and_created", "filled": filled_units, "remaining": remaining_units}

    def execute_create_boxes(self, chat_id: int, offer_id: int, excess_units: int) -> dict[str, Any]:
        """Execute box creation after confirmation"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t("offer_not_found", chat_id))
            return {"status": "offer_not_found"}

        return self._add_box_capacity(chat_id, offer, excess_units)

    def execute_cancel_orders(self, chat_id: int, offer_id: int, excess_units: int) -> dict[str, Any]:
        """Execute order cancellation after confirmation"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t("offer_not_found", chat_id))
            return {"status": "offer_not_found"}

        return self._cancel_excess_orders(chat_id, offer, self._active_orders(offer_id), excess_units)

    def _add_box_capacity(self, chat_id: int, offer, needed_units: int) -> dict[str, Any]:
        """Add box capacity by creating new boxes and filling them with needed units"""
        box_size = offer.wholesale_box_size
        created_boxes = 0
        remaining_units = needed_units

        for _ in range(boxes_needed(needed_units, box_size)):
            box = Box(offer_id=offer.offer_id, max_capacity=box_size)
            created_box = self.db.create_box(box)
            if created_box:
                fill_amount = min(remaining_units, box_size)
                self.box_status_manager.update_box_after_order_placement(created_box.box_id, fill_amount)
                remaining_units -= fill_amount
                created_boxes += 1

        if created_boxes > 0:
            self._check_offer_status_after_change(offer.offer_id)
            self._send_message(
                chat_id,
                self._t(
                    "audit_boxes_created", chat_id, offer_id=offer.offer_id, boxes=created_boxes, units=needed_units
                ),
            )
            return {"status": "boxes_created", "boxes": created_boxes}
        else:
            self._send_message(chat_id, self._t("audit_failed_create_boxes", chat_id))
            return {"status": "error"}

    @staticmethod
    def _orders_to_cancel(active_orders, excess_units: int) -> list:
        """The newest orders, until together they hold the excess units"""
        chosen, units = [], 0
        for order in sorted(active_orders, key=lambda o: o.created_at, reverse=True):
            if units >= excess_units:
                break
            chosen.append(order)
            units += order.quantity
        return chosen

    def _cancel_excess_orders(self, chat_id: int, offer, active_orders, excess_units: int) -> dict[str, Any]:
        """Cancel the newest orders until the excess is gone; each customer is told"""
        cancelled_count = 0
        for order in self._orders_to_cancel(active_orders, excess_units):
            box = self.db.get_box(order.box_id)
            if box and self._execute_cancel(order, box, chat_id)["status"] == "success":
                cancelled_count += 1

        capacity = sum(box.current_quantity for box in self.db.get_boxes_by_offer(offer.offer_id))
        self._send_message(
            chat_id,
            self._t(
                "audit_orders_cancelled",
                chat_id,
                offer_id=offer.offer_id,
                cancelled=cancelled_count,
                ordered=excess_units + capacity,
                capacity=capacity,
            ),
        )
        return {"status": "orders_cancelled", "cancelled": cancelled_count}

    # ------------------------------------------------------------------ /refill_boxes
    def _refill_plan(self, chat_id: int, offer_id: int) -> tuple[Any, list, list[box_refill.Move]] | dict[str, Any]:
        """(offer, boxes, moves), or the answer when the offer cannot be refilled"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t("offer_not_found", chat_id))
            return {"status": "offer_not_found"}
        if offer.status in box_refill.CLOSED_OFFER_STATUSES:
            status = self._t(f"status_{offer.status}", chat_id)
            self._send_message(chat_id, self._t("refill_boxes_offer_closed", chat_id, offer_id=offer_id, status=status))
            return {"status": "offer_closed"}
        boxes = self.db.get_boxes_by_offer(offer_id)
        moves = box_refill.plan_refill(boxes, self.db.get_orders_by_offer(offer_id))
        if not moves:
            self._send_message(chat_id, self._t("refill_boxes_nothing", chat_id, offer_id=offer_id))
            return {"status": "nothing_to_move"}
        return offer, boxes, moves

    def handle_refill_boxes(self, chat_id: int, args: list) -> dict[str, Any]:
        """/refill_boxes <offer_id>: propose moving orders from later boxes into the room of earlier ones"""
        error = self._validate_args(args, 1, "usage_refill_boxes", chat_id)
        if error:
            return error
        try:
            offer_id = int(args[0])
        except ValueError:
            self._send_message(chat_id, self._t("invalid_offer_id", chat_id))
            return {"status": "invalid_format"}

        planned = self._refill_plan(chat_id, offer_id)
        if isinstance(planned, dict):
            return planned
        offer, boxes, moves = planned

        lines = []
        for move in moves:
            customer = self.db.get_customer(move.customer_id)
            lines.append(
                self._t(
                    "refill_boxes_move",
                    chat_id,
                    quantity=move.quantity,
                    customer=self._get_public_name(customer) if customer else self._t("unknown", chat_id),
                    from_box=move.from_box_id[:8],
                    to_box=move.to_box_id[:8],
                )
            )
        emptied = box_refill.boxes_emptied(boxes, moves)
        in_use = len([b for b in boxes if b.current_quantity > 0])
        message = self._t(
            "refill_boxes_proposal",
            chat_id,
            offer_id=offer_id,
            name=self._escape_html(offer.name),
            moves="\n".join(lines),
            emptied=len(emptied),
            before=in_use,
            after=in_use - len(emptied),
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": self._t("refill_boxes_confirm", chat_id, count=len(moves)),
                        "callback_data": f"refill_boxes_confirm_{offer_id}",
                    }
                ],
                [{"text": self._t("cancel", chat_id), "callback_data": "cancel_action"}],
            ]
        }
        self._send_message(chat_id, message, reply_markup=keyboard, parse_mode="HTML")
        return {"status": "confirmation_required", "moves": len(moves)}

    def handle_confirm_refill_boxes(self, chat_id: int, offer_id: int) -> dict[str, Any]:
        """Carry out the refill. The plan is made again: the boxes may have changed since the proposal."""
        planned = self._refill_plan(chat_id, offer_id)
        if isinstance(planned, dict):
            return planned
        _offer, boxes, moves = planned

        capacity = {box.box_id: box.max_capacity for box in boxes}
        moved = [
            move
            for move in moves
            if self.db.move_order_to_box(
                move.order_id, move.quantity, move.from_box_id, move.to_box_id, capacity[move.to_box_id]
            )
        ]

        deleted = 0
        for box_id in {move.from_box_id for move in moved} | {move.to_box_id for move in moved}:
            box = self.db.get_box(box_id)
            if not box:
                continue
            if box.current_quantity <= 0:
                # Only while still empty: an order may have joined the box since it was read
                deleted += 1 if self.db.delete_box_if_empty(box_id) else 0
                continue
            status = BoxStatus.FULL.value if box.current_quantity >= box.max_capacity else BoxStatus.OPEN.value
            if box.status != status:
                self.db.update_box(box_id, {"status": status})

        if moved:
            # Fewer boxes: the announcement shows the room that is left
            self.box_status_manager.update_offer_status_after_change(offer_id)
            self.sync_offer_messages(offer_id)

        key = "refill_boxes_done" if len(moved) == len(moves) else "refill_boxes_partly"
        self._send_message(
            chat_id,
            self._t(key, chat_id, offer_id=offer_id, moved=len(moved), planned=len(moves), deleted=deleted),
        )
        return {"status": "refilled", "moved": len(moved), "planned": len(moves), "deleted": deleted}
