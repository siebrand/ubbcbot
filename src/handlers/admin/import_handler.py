import logging
from typing import Any

from handlers.admin.offer.notifications import NotificationHandler
from models.entities import AuthorizationStatus, Box, BoxStatus, OfferStatus, Order, OrderStatus
from services.box_status_manager import BoxStatusManager
from utils.csv_parser import CSVParser

logger = logging.getLogger()


class ImportHandler(NotificationHandler):
    """Handler for order import operations"""

    MAX_AMBIGUOUS_LINES_SHOWN = 10
    MAX_CANDIDATES_SHOWN = 5
    # How often an import order tries a box again after the box it chose filled up in the meantime
    MAX_BOX_ATTEMPTS = 3

    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)

    def handle_import_orders(self, chat_id: int, user_id: int) -> dict[str, Any]:
        """Handle /import_orders command - prompt for CSV file"""
        # Check if already waiting for file
        existing = self.db.get_edit_context_by_chat_id(chat_id)
        if existing and existing.edit_type == "import_csv":
            return self._send_error(chat_id, "import_already_pending", "already_pending")

        # Store context in DynamoDB
        from utils.edit_context import EditContextManager

        edit_context_manager = EditContextManager(self.db, self._t, self._send_message)
        edit_context_manager.store_edit_context(chat_id, "import_csv", "pending")

        # Send prompt with force reply
        self._send_message(
            chat_id,
            self._t("import_orders_prompt", self.admin_user_id),
            reply_markup={
                "force_reply": True,
                "input_field_placeholder": self._t("placeholder_csv_file", self.admin_user_id),
            },
        )
        return {"status": "awaiting_file"}

    def handle_document_upload(self, chat_id: int, user_id: int, file_id: str, file_name: str) -> dict[str, Any]:
        """Handle document upload for import"""
        # Check if user is waiting for import file
        context = self.db.get_edit_context_by_chat_id(chat_id)
        if not context or context.edit_type != "import_csv":
            return {"status": "not_waiting"}

        # Clear context
        self.db.delete_edit_context(context.context_id)

        # Download file
        file_content = self._download_file(file_id)
        if not file_content:
            return self._send_error(chat_id, "import_download_failed", "download_failed")

        # Parse CSV
        parse_result = CSVParser.parse_import_csv(file_content)

        if not parse_result["success"]:
            error_key = f"import_error_{parse_result['error']}"
            if parse_result["error"] == "too_many_lines":
                return self._send_error(
                    chat_id,
                    error_key,
                    parse_result["error"],
                    line_count=parse_result["line_count"],
                    max_lines=CSVParser.MAX_LINES,
                )
            elif parse_result["error"] == "empty_cell":
                return self._send_error(
                    chat_id, error_key, parse_result["error"], line=parse_result["line"], field=parse_result["field"]
                )
            elif parse_result["error"] == "invalid_headers":
                return self._send_error(
                    chat_id,
                    error_key,
                    parse_result["error"],
                    expected=", ".join(parse_result["expected"]),
                    found=", ".join(parse_result.get("found", [])),
                )
            else:
                return self._send_error(chat_id, error_key, parse_result["error"])

        # Process rows
        rows = parse_result["rows"]

        # Only approved customers may order (CLAUDE.md); the others only explain why a line is not imported.
        # A name that fits more than one approved customer cannot be imported: refuse the whole file, import nothing
        all_customers = self.validator.load_customers()
        customers = [c for c in all_customers if c.authorization_status == AuthorizationStatus.APPROVED.value]
        not_approved = [c for c in all_customers if c.authorization_status != AuthorizationStatus.APPROVED.value]
        collisions = self._find_ambiguous_lines(rows, customers)
        if collisions:
            return self._refuse_ambiguous(chat_id, collisions)

        self._send_message(chat_id, self._t("import_processing", self.admin_user_id, row_count=len(rows)))

        success_count = 0
        errors: list[str] = []
        max_errors = 5

        for idx, row in enumerate(rows, start=2):  # Line numbers start at 2 (header is 1)
            # Stop processing if we hit max errors
            if len(errors) >= max_errors:
                break
            offer_id_str = row["offer_id"].strip()
            username = row["username"].strip()

            # Validate offer_id
            try:
                offer_id = int(offer_id_str)
            except ValueError:
                errors.append(
                    self._t("import_line_error_invalid_offer_id", self.admin_user_id, line=idx, offer_id=offer_id_str)
                )
                continue

            # Get offer
            offer = self.db.get_offer(offer_id)
            if not offer:
                errors.append(
                    self._t("import_line_error_offer_not_found", self.admin_user_id, line=idx, offer_id=offer_id)
                )
                continue

            # Check offer status
            if offer.status != OfferStatus.IMPORT.value:
                errors.append(
                    self._t(
                        "import_line_error_wrong_status",
                        self.admin_user_id,
                        line=idx,
                        offer_id=offer_id,
                        status=offer.status,
                    )
                )
                continue

            # Find customer (no interactive disambiguation: ambiguous names were refused above)
            customer, error = self._find_customer_for_import(username, customers, not_approved)
            if error:
                errors.append(
                    self._t("import_line_error_customer", self.admin_user_id, line=idx, username=username, reason=error)
                )
                continue

            # Create order
            order_result = self._create_import_order(offer, customer)
            if order_result["success"]:
                success_count += 1
            else:
                errors.append(
                    self._t(
                        "import_line_error_order_failed",
                        self.admin_user_id,
                        line=idx,
                        username=username,
                        offer_id=offer_id,
                    )
                )

        # Send summary
        summary = self._t("import_completed", self.admin_user_id, success_count=success_count)

        if errors:
            summary += "\n\n" + self._t("import_errors_header", self.admin_user_id, error_count=len(errors))
            for error in errors[:5]:  # Show max 5 errors
                summary += f"\n{error}"

            if len(errors) > 5:
                summary += "\n" + self._t("import_more_errors", self.admin_user_id, remaining=len(errors) - 5)

        self._send_message(chat_id, summary)
        return {"status": "success", "imported": success_count, "errors": len(errors)}

    def _find_customer_for_import(self, username: str, customers: list, not_approved: list | None = None) -> tuple:
        """Find the approved customer for a CSV line - returns (customer, None) or (None, reason text).

        No messages and no buttons: the CSV import has nobody to ask which customer was meant.
        """
        matches = self.validator.match_customers(username, customers)
        if not matches:
            if self.validator.match_customers(username, not_approved or []):
                return None, self._t("not_approved", self.admin_user_id)
            return None, self._t("not_found", self.admin_user_id)
        if len(matches) > 1:
            return None, self._t("multiple_matches", self.admin_user_id)
        return matches[0], None

    def _find_ambiguous_lines(self, rows: list, customers: list) -> list[tuple[int, str, list]]:
        """The lines of the file whose name matches more than one customer: (line number, name, customers)"""
        collisions = []
        for idx, row in enumerate(rows, start=2):  # Line numbers start at 2 (header is 1)
            username = row["username"].strip()
            matches = self.validator.match_customers(username, customers)
            if len(matches) > 1:
                collisions.append((idx, username, matches))
        return collisions

    def _refuse_ambiguous(self, chat_id: int, collisions: list[tuple[int, str, list]]) -> dict[str, Any]:
        """Tell the admin which lines are ambiguous and who they could be. Nothing has been imported."""
        shown = collisions[: self.MAX_AMBIGUOUS_LINES_SHOWN]
        reader = self.admin_user_id
        message = self._t("import_refused_ambiguous", reader, count=len(collisions))
        for line, username, matches in shown:
            candidates = self._format_customer_candidates(matches, self.MAX_CANDIDATES_SHOWN)
            message += "\n" + self._t(
                "import_line_error_ambiguous",
                reader,
                line=line,
                username=username,
                count=len(matches),
                matches=candidates,
            )
        if len(collisions) > len(shown):
            message += "\n" + self._t("import_ambiguous_more", reader, remaining=len(collisions) - len(shown))

        self._send_message(chat_id, message)
        return {"status": "ambiguous_customers", "lines": [line for line, _, _ in collisions]}

    def _create_import_order(self, offer, customer) -> dict[str, Any]:
        """Create order for import (quantity=1, no announcement).

        The order and its unit in the box are one transaction (as for customers' orders). When the box filled up
        between reading it and writing (customers may order while the import runs), the boxes are read again and
        the next one with room is tried.
        """
        try:
            for _ in range(self.MAX_BOX_ATTEMPTS):
                box = self._import_box(offer)
                if not box:
                    return {"success": False}

                order = Order(
                    customer_id=customer.customer_id,
                    box_id=box.box_id,
                    offer_id=offer.offer_id,
                    quantity=1,
                    unit_price=offer.price_per_unit,
                    total_price=offer.price_per_unit,
                    placed_by_admin=True,
                )
                if not self.db.create_order_with_box_increment(order, box.box_id, 1, box.max_capacity):
                    continue

                # Best-effort status follow-up, as for customers' orders: the box is FULL at capacity
                if box.current_quantity + 1 >= box.max_capacity:
                    self.db.update_box(box.box_id, {"status": BoxStatus.FULL.value})
                return {"success": True}

            logger.error(f"Import order for offer {offer.offer_id} found no box with room")
            return {"success": False}

        except Exception as e:
            logger.error(f"Error creating import order: {e}")
            return {"success": False}

    def _import_box(self, offer) -> Box | None:
        """The first open box of the offer with room, or a new one"""
        boxes = self.db.get_boxes_by_offer(offer.offer_id)
        open_boxes = [b for b in boxes if b.status == BoxStatus.OPEN.value and b.current_quantity < b.max_capacity]
        if open_boxes:
            return open_boxes[0]
        return self.db.create_box(
            Box(offer_id=offer.offer_id, max_capacity=offer.wholesale_box_size, status=BoxStatus.OPEN.value)
        )

    def _download_file(self, file_id: str) -> bytes | None:
        """Download file from Telegram"""
        return self.telegram.download_file(file_id)

    def handle_finalize_import(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /finalize_import command"""
        # If no args, show list of IMPORT offers
        if not args:
            return self._show_import_offers_selection(chat_id)

        error = self._validate_args(args, 1, "usage_finalize_import", chat_id)
        if error:
            return error

        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error

        # Check offer status
        if offer.status != OfferStatus.IMPORT.value:
            return self._send_error(chat_id, "finalize_import_wrong_status", "wrong_status", status=offer.status)

        # Mark all boxes as ORDERED and update order statuses
        boxes = self.db.get_boxes_by_offer(offer.offer_id)
        if boxes:
            box_ids = [b.box_id for b in boxes]
            self.box_status_manager.mark_boxes_as_ordered(box_ids)

            # Update all orders in these boxes to ORDERED status
            for box_id in box_ids:
                orders = self.db.get_orders_by_box(box_id)
                for order in orders:
                    if order.status == OrderStatus.PENDING.value:
                        self.db.update_order(order.order_id, {"status": OrderStatus.ORDERED.value})

        # Update offer status based on box states
        new_status = self.box_status_manager.update_offer_status_after_change(offer.offer_id)

        if new_status == OfferStatus.SOLD_OUT.value:
            self._send_success(chat_id, "finalize_import_sold_out", "success", offer_id=offer.offer_id, name=offer.name)
        else:
            # Offer is ACTIVE, announce it. Without boxes (nothing imported) the status was not changed: write it,
            # or the announced offer stays in import
            if new_status is None:
                self.db.update_offer(offer.offer_id, {"status": OfferStatus.ACTIVE.value})
            offer.status = OfferStatus.ACTIVE.value
            self._announce_offer(offer)
            self._send_success(chat_id, "finalize_import_active", "success", offer_id=offer.offer_id, name=offer.name)

        # Show import offers selection again if more exist
        return self._show_import_offers_selection(chat_id)

    def _announce_offer(self, offer):
        """Announce offer to default group and subscribers"""
        import os

        # Event-based export expiry: piggyback on the announcement
        self.expire_exports()

        default_group_id = os.environ.get("DEFAULT_GROUP_ID")

        # Send to default group
        if default_group_id:
            self._send_rich_offer_message(int(default_group_id), offer, force_group=True, include_buttons=True)

        # Send to subscribers
        self._notify_subscribers_rich(offer)

    def _show_import_offers_selection(self, chat_id: int) -> dict[str, Any]:
        """Show offers with IMPORT status for finalization"""
        offers = self.db.list_offers()
        import_offers = [o for o in offers if o.status == OfferStatus.IMPORT.value]

        if not import_offers:
            self._send_message(chat_id, self._t("no_import_offers", chat_id))
            return {"status": "no_offers"}

        # Sort by offer_id
        import_offers.sort(key=lambda x: x.offer_id)

        message = self._t("select_offer_finalize_import", chat_id) + "\n\n"
        keyboard_buttons = []

        for offer in import_offers:
            # Get order count
            orders = self.db.get_orders_by_offer(offer.offer_id)
            order_count = len([o for o in orders if o.status == OrderStatus.PENDING.value])

            message += (
                self._t("import_offer_line", chat_id, offer_id=offer.offer_id, name=offer.name, count=order_count)
                + "\n"
            )
            keyboard_buttons.append(
                [{"text": f"{offer.offer_id}. {offer.name}", "callback_data": f"finalize_import_{offer.offer_id}"}]
            )

        keyboard_buttons.append([{"text": self._t("cancel", chat_id), "callback_data": "cancel_action"}])
        keyboard = {"inline_keyboard": keyboard_buttons}

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "success"}
