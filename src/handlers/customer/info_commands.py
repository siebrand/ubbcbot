import logging
from typing import Any

from handlers.base_handler import BaseHandler
from models.entities import OfferStatus, OrderStatus
from services.box_status_manager import BoxStatusManager
from utils.pagination import PaginationUtils

logger = logging.getLogger(__name__)


class InfoCommands(BaseHandler):
    def handle_start(self, chat_id: int, user_id: int, args: list = None) -> dict[str, Any]:
        """Handle /start command with optional help section parameter"""
        import logging

        logger = logging.getLogger()

        if self.environment == "test":
            logger.info(f"Processing /start command for user {user_id}, chat {chat_id}")

        # Check if specific help section requested
        section = args[0].lower() if args and len(args) > 0 else None

        if section:
            return self._show_help_section(chat_id, user_id, section)

        # Show general help
        message = self._t("welcome_ubbc")

        if self._is_admin(user_id):
            message += self._t("admin_sections_available")

        result = self._send_message(chat_id, message)
        success = result.get("success", False)
        if self.environment == "test":
            logger.info(f"Message send result: {success}")

        return {"status": "success"}

    def handle_help(self, chat_id: int, user_id: int, args: list = None) -> dict[str, Any]:
        """Handle /help command with optional section parameter"""
        section = args[0].lower() if args and len(args) > 0 else None

        if section:
            return self._show_help_section(chat_id, user_id, section)

        # Get bot username first
        bot_username = self._get_bot_username()

        # Show available sections
        message = self._t("help_sections", bot_username=bot_username)

        if self._is_admin(user_id):
            message += self._t("admin_help_sections", bot_username=bot_username)

        # Replace bot_username placeholder
        message = message.format(bot_username=bot_username)

        self._send_message(chat_id, message, parse_mode="Markdown")
        return {"status": "success"}

    def _show_help_section(self, chat_id: int, user_id: int, section: str) -> dict[str, Any]:
        """Show help for specific section"""
        if section == "all":
            # Show all available sections in separate messages
            sections = ["general", "orders"]
            if self._is_admin(user_id):
                sections.extend(["suppliers", "offers", "users", "delivery", "import", "system"])

            for sect in sections:
                message = self._get_section_help(sect)
                self._send_message(chat_id, message)

            return {"status": "success"}

        elif section in [
            "general",
            "orders",
            "suppliers",
            "offers",
            "users",
            "delivery",
            "import",
            "system",
        ]:
            if section in [
                "suppliers",
                "offers",
                "users",
                "delivery",
                "import",
                "system",
            ] and not self._is_admin(user_id):
                message = self._t("admin_only_section")
            else:
                message = self._get_section_help(section)

        else:
            available_sections = ["general", "orders", "all"]
            if self._is_admin(user_id):
                available_sections.extend(["suppliers", "offers", "users", "delivery", "import", "system"])

            sections_text = ", ".join(available_sections)
            message = self._t("unknown_section", user_id, section=section, sections=sections_text)

        self._send_message(chat_id, message)
        return {"status": "success"}

    def _get_section_help(self, section: str) -> str:
        """Get help text for a specific section"""
        if section == "general":
            return self._t("help_general")
        elif section == "orders":
            return self._t("help_orders")
        elif section == "suppliers":
            return self._t("help_suppliers")
        elif section == "offers":
            return self._t("help_offers")
        elif section == "users":
            return self._t("help_users")
        elif section == "delivery":
            return self._t("help_delivery")
        elif section == "import":
            return self._t("help_import")
        elif section == "system":
            return self._t("help_system")
        return ""

    def _format_offer_line(self, offer, status_emoji, user_id, total_ordered=None, total_capacity=None, is_draft=False):
        """Format a single offer line with consistent markup"""
        bot_username = self._get_bot_username()

        if is_draft:
            return (
                f"{status_emoji} <a href='https://t.me/{bot_username}?start=view_offer_{offer.offer_id}'>"
                f"<b>{offer.offer_id}</b></a> <b>{offer.name}</b> €{offer.price_per_unit:.2f}\n"
            )
        elif total_ordered is not None and total_capacity is not None:
            return (
                f"{status_emoji} <a href='https://t.me/{bot_username}?start=view_offer_{offer.offer_id}'>"
                f"<b>{offer.offer_id}</b></a> <b>{offer.name}</b> €{offer.price_per_unit:.2f} "
                f"({total_ordered}/{total_capacity} {self._t('ordered_text', user_id)})\n"
            )
        else:
            return (
                f"{status_emoji} <a href='https://t.me/{bot_username}?start=view_offer_{offer.offer_id}'>"
                f"<b>{offer.offer_id}</b></a> <b>{offer.name}</b> €{offer.price_per_unit:.2f}\n"
            )

    def _get_offer_capacity_info(
        self, offer_id: int, user_id: int = None, boxes_by_offer: dict = None, orders_by_offer: dict = None
    ):
        """Get order and capacity information for an offer using BoxStatusManager

        Args:
            offer_id: The offer ID
            user_id: Optional user ID (unused, kept for compatibility)
            boxes_by_offer: Optional pre-loaded boxes dictionary
            orders_by_offer: Optional pre-loaded orders dictionary (unused when boxes provided)

        Returns:
            tuple: (total_ordered, total_capacity)
        """
        boxes = boxes_by_offer.get(offer_id, []) if boxes_by_offer is not None else self.db.get_boxes_by_offer(offer_id)

        box_manager = BoxStatusManager(self.db)

        # Check if any boxes are delivered
        delivered_boxes = box_manager.get_delivered_boxes(boxes)

        if delivered_boxes:
            # For delivered boxes: calculate from box capacity
            total_capacity = sum(box.max_capacity for box in delivered_boxes)
            total_ordered = sum(box.current_quantity for box in delivered_boxes)
        else:
            # For non-delivered boxes: calculate from orders
            if orders_by_offer is not None:
                orders = orders_by_offer.get(offer_id, [])
            else:
                orders = self.db.get_orders_by_offer(offer_id)
                orders = [o for o in orders if o.status in ["pending", "ordered"]]

            total_capacity = sum(box.max_capacity for box in boxes)
            total_ordered = sum(order.quantity for order in orders)

        return total_ordered, total_capacity

    def _validate_customer(self, chat_id: int, user_id: int):
        """Validate customer exists and return customer object or error status"""
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, self._t("must_register", user_id))
            return None, {"status": "not_registered"}
        return customer, None

    def handle_fomo(self, chat_id: int, user_id: int, args=None) -> dict[str, Any]:
        """Handle /fomo command"""
        if args and self._is_admin(user_id):
            identifier = " ".join(args)
            customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "fomo_user_select")
            if error:
                return {"status": "disambiguation_or_not_found"}
            return self._show_fomo(chat_id, user_id, customer)

        customer, error = self._validate_customer(chat_id, user_id)
        if error:
            return error
        return self._show_fomo(chat_id, user_id, customer)

    def _show_fomo(self, chat_id: int, caller_user_id: int, customer) -> dict[str, Any]:
        """Show active offers the customer hasn't ordered yet"""
        active_offers = [o for o in self.db.list_offers() if o.status == OfferStatus.ACTIVE.value]
        orders = self.db.get_orders_by_customer(customer.customer_id)
        ordered_offer_ids = {o.offer_id for o in orders if o.status != OrderStatus.CANCELLED.value}
        unordered = sorted(
            [o for o in active_offers if o.offer_id not in ordered_offer_ids], key=lambda o: o.name.lower()
        )

        is_self = customer.telegram_user_id == caller_user_id
        customer_name = f"{customer.first_name} {customer.last_name or ''}".strip()

        if not unordered:
            key = "fomo_none" if is_self else "fomo_none_for_user"
            self._send_message(chat_id, self._t(key, caller_user_id, name=customer_name))
            return {"status": "success"}

        header_key = "fomo_header" if is_self else "fomo_header_for_user"
        message = self._t(header_key, caller_user_id, name=customer_name) + "\n\n"
        for offer in unordered:
            message += self._format_offer_line(offer, "🍺", caller_user_id)

        self._send_message(chat_id, message, parse_mode="HTML")
        return {"status": "success"}

    def handle_subscribe(self, chat_id: int, user_id: int) -> dict[str, Any]:
        """Handle /subscribe command"""
        customer, error = self._validate_customer(chat_id, user_id)
        if error:
            return error

        # Update subscription status
        if self.db.update_customer(customer.customer_id, {"subscribed_to_offers": True}):
            self._send_message(chat_id, self._t("subscribed", user_id))
            return {"status": "success"}
        else:
            self._send_message(chat_id, self._t("failed_subscribe", user_id))
            return {"status": "error"}

    def handle_unsubscribe(self, chat_id: int, user_id: int) -> dict[str, Any]:
        """Handle /unsubscribe command"""
        customer, error = self._validate_customer(chat_id, user_id)
        if error:
            return error

        # Update subscription status
        if self.db.update_customer(customer.customer_id, {"subscribed_to_offers": False}):
            self._send_message(chat_id, self._t("unsubscribed", user_id))
            return {"status": "success"}
        else:
            self._send_message(chat_id, self._t("failed_unsubscribe", user_id))
            return {"status": "error"}

    def handle_list_offers(self, chat_id: int, user_id: int, args: list = None, page: int = 1) -> dict[str, Any]:
        """Handle /list_offers command with optional status filtering"""
        offers = self.db.list_offers()

        if not offers:
            self._send_message(chat_id, self._t("no_offers", user_id))
            return {"status": "no_offers"}

        # Batch load all boxes and orders once
        all_boxes = self.db.get_all_boxes()
        all_orders = self.db.get_all_orders(statuses=["pending", "ordered"])

        # Build lookup dictionaries
        boxes_by_offer = {}
        for box in all_boxes:
            boxes_by_offer.setdefault(box.offer_id, []).append(box)

        orders_by_offer = {}
        for order in all_orders:
            orders_by_offer.setdefault(order.offer_id, []).append(order)

        # Sort offers by offer_id ascending
        offers.sort(key=lambda x: x.offer_id)

        message = ""

        is_admin = self._is_admin(user_id)

        # Parse filter argument and normalize underscores
        filter_arg = args[0].lower().replace("_", "") if args and len(args) > 0 else None
        show_user_view = filter_arg == "user" and is_admin

        # Handle help request
        if filter_arg == "help":
            help_message = self._t("list_offers_help", user_id)
            if is_admin:
                help_message += "\n\n" + self._t("list_offers_help_admin", user_id)
            self._send_message(chat_id, help_message)
            return {"status": "success"}

        # Handle special filters
        if filter_arg == "soldout":
            # Filter sold_out offers from the already-loaded list
            sold_out_offers = [o for o in offers if o.status == OfferStatus.SOLD_OUT.value]
            if not sold_out_offers:
                self._send_message(chat_id, self._t("no_offers", user_id))
                return {"status": "no_offers"}

            # Paginate sold out offers
            page_offers, total_pages = PaginationUtils.paginate_list(sold_out_offers, page, 20)

            message += self._t("sold_out_offers_title", user_id)
            if total_pages > 1:
                message += f" - Page {page}/{total_pages}"
            message += "\n\n"

            for offer in page_offers:
                total_ordered, total_capacity = self._get_offer_capacity_info(
                    offer.offer_id, user_id, boxes_by_offer, orders_by_offer
                )
                message += self._format_offer_line(offer, "🚫", user_id, total_ordered, total_capacity)

            reply_markup = None
            if total_pages > 1:
                reply_markup = PaginationUtils.build_pagination_keyboard(
                    page, total_pages, "list_offers_soldout", enhanced=True
                )

            self._send_message(chat_id, message, parse_mode="HTML", reply_markup=reply_markup)
            return {"status": "success"}

        if is_admin and not show_user_view:
            # Determine which statuses to show based on filter
            show_all = filter_arg == "all"
            show_draft = filter_arg == "draft"
            show_active = filter_arg == "active"
            show_completed = filter_arg == "completed"
            show_inactive = filter_arg == "inactive"
            show_archived = filter_arg == "archived"
            show_import = filter_arg == "import"

            # Default: show draft + import + active only
            if not filter_arg or filter_arg not in [
                "all",
                "draft",
                "active",
                "completed",
                "inactive",
                "archived",
                "import",
            ]:
                show_draft = show_import = show_active = True

            # Group by status
            offers_by_status = {}
            for offer in offers:
                offers_by_status.setdefault(offer.status, []).append(offer)

            draft_offers = offers_by_status.get(OfferStatus.DRAFT.value, [])
            active_offers = offers_by_status.get(OfferStatus.ACTIVE.value, [])
            import_offers = offers_by_status.get(OfferStatus.IMPORT.value, [])

            # Build list of offers to display
            display_offers = []

            # Add draft offers
            if draft_offers and (show_all or show_draft or (not filter_arg)):
                for offer in draft_offers:
                    display_offers.append(("draft", offer))

            # Add import offers
            if import_offers and (show_all or show_import or (not filter_arg)):
                for offer in import_offers:
                    display_offers.append(("import", offer))

            # Add active offers
            if active_offers and (show_all or show_active or (not filter_arg)):
                for offer in active_offers:
                    display_offers.append(("active", offer))

            # Add other status offers
            if show_all or show_completed or show_inactive or show_archived:
                status_order = [OfferStatus.SOLD_OUT.value, OfferStatus.COMPLETED.value, OfferStatus.INACTIVE.value]
                for status in status_order:
                    status_offers = offers_by_status.get(status, [])
                    if not status_offers:
                        continue
                    if show_completed and status != OfferStatus.COMPLETED.value:
                        continue
                    if show_inactive and status != OfferStatus.INACTIVE.value:
                        continue
                    if show_archived and status not in [
                        OfferStatus.SOLD_OUT.value,
                        OfferStatus.COMPLETED.value,
                        OfferStatus.INACTIVE.value,
                    ]:
                        continue
                    for offer in status_offers:
                        display_offers.append((status, offer))

            # Paginate offers
            page_offers, total_pages = PaginationUtils.paginate_list(display_offers, page, 20)

            # Determine if we need section headers
            show_section_headers = (
                show_all
                or (not filter_arg)
                or len(
                    [
                        s
                        for s in [show_draft, show_import, show_active, show_completed, show_inactive, show_archived]
                        if s
                    ]
                )
                > 1
            )

            # Build title based on filter (only if not showing section headers)
            if not show_section_headers:
                if show_draft:
                    message += self._t("draft_offers", user_id)
                elif show_active:
                    message += self._t("active_offers", user_id)
                elif show_import:
                    message += self._t("import_offers", user_id)
                elif show_archived:
                    message += self._t("archived_offers", user_id)

                if total_pages > 1:
                    message += f" - Page {page}/{total_pages}"
                message += "\n\n"
            else:
                # Show general title for multi-section views
                if show_all:
                    message += self._t("all_offers_admin")
                else:
                    message += self._t("current_offers_admin", user_id)

                if total_pages > 1:
                    message += f" - Page {page}/{total_pages}"
                message += "\n\n"

            # Group paginated offers by status for display
            current_status = None
            first_section = True

            for status_type, offer in page_offers:
                if status_type != current_status:
                    current_status = status_type
                    if show_section_headers:
                        if not first_section:
                            message += "\n"
                        first_section = False
                        if status_type == "draft":
                            message += self._t("draft_offers") + "\n"
                        elif status_type == "import":
                            message += self._t("import_offers") + "\n"
                        elif status_type == "active":
                            message += self._t("active_offers") + "\n"
                        else:
                            status_emoji = {
                                OfferStatus.SOLD_OUT.value: "🚫",
                                OfferStatus.COMPLETED.value: "✅",
                                OfferStatus.INACTIVE.value: "❌",
                            }.get(status_type, "❓")
                            status_label = {
                                OfferStatus.SOLD_OUT.value: self._t("status_sold_out", user_id=None).upper(),
                                OfferStatus.COMPLETED.value: self._t("status_completed", user_id=None).upper(),
                                OfferStatus.INACTIVE.value: self._t("status_inactive", user_id=None).upper(),
                            }.get(status_type, status_type.upper())
                            message += f"{status_emoji} {status_label}:\n"

                # Format offer line
                if status_type == "draft":
                    message += self._format_offer_line(offer, "📝", user_id, is_draft=True)
                elif status_type == "import":
                    total_ordered, total_capacity = self._get_offer_capacity_info(
                        offer.offer_id, user_id, boxes_by_offer, orders_by_offer
                    )
                    message += self._format_offer_line(offer, "📥", user_id, total_ordered, total_capacity)
                elif status_type == "active":
                    total_ordered, total_capacity = self._get_offer_capacity_info(
                        offer.offer_id, user_id, boxes_by_offer, orders_by_offer
                    )
                    boxes = boxes_by_offer.get(offer.offer_id, [])
                    has_ordered_boxes = any(box.status == "ordered" for box in boxes)
                    emoji = "📦🍺" if has_ordered_boxes else "🍺"
                    message += self._format_offer_line(offer, emoji, user_id, total_ordered, total_capacity)
                else:
                    status_emoji = {
                        OfferStatus.SOLD_OUT.value: "🚫",
                        OfferStatus.COMPLETED.value: "✅",
                        OfferStatus.INACTIVE.value: "❌",
                    }.get(status_type, "❓")

                    # Only show availability for sold_out offers
                    if status_type == OfferStatus.SOLD_OUT.value:
                        total_ordered, total_capacity = self._get_offer_capacity_info(
                            offer.offer_id, user_id, boxes_by_offer, orders_by_offer
                        )
                        message += self._format_offer_line(offer, status_emoji, user_id, total_ordered, total_capacity)
                    else:
                        message += self._format_offer_line(offer, status_emoji, user_id)

            reply_markup = None
            if total_pages > 1:
                filter_suffix = f"_{filter_arg}" if filter_arg else ""
                reply_markup = PaginationUtils.build_pagination_keyboard(
                    page, total_pages, f"list_offers{filter_suffix}", enhanced=True
                )

            self._send_message(chat_id, message, parse_mode="HTML", reply_markup=reply_markup)
            return {"status": "success"}
        else:
            # Show only active offers for customers
            active_offers = [o for o in offers if o.status == OfferStatus.ACTIVE.value]

            if not active_offers:
                self._send_message(chat_id, self._t("no_offers", user_id))
                return {"status": "no_offers"}

            # Sort active offers by offer_id descending (highest first)
            active_offers.sort(key=lambda x: x.offer_id, reverse=True)

            # Paginate active offers
            page_offers, total_pages = PaginationUtils.paginate_list(active_offers, page, 20)

            message += self._t("active_offers_customer")
            if total_pages > 1:
                message += f" - Page {page}/{total_pages}"
            message += "\n\n"

            for offer in page_offers:
                total_ordered, total_capacity = self._get_offer_capacity_info(
                    offer.offer_id, user_id, boxes_by_offer, orders_by_offer
                )
                message += self._format_offer_line(offer, "🍺", user_id, total_ordered, total_capacity)

            reply_markup = None
            if total_pages > 1:
                filter_suffix = "_user" if show_user_view else ""
                reply_markup = PaginationUtils.build_pagination_keyboard(
                    page, total_pages, f"list_offers{filter_suffix}", enhanced=True
                )

            self._send_message(chat_id, message, parse_mode="HTML", reply_markup=reply_markup)
            return {"status": "success"}

        self._send_message(chat_id, message, parse_mode="HTML")
        return {"status": "success"}

    def handle_list_my_orders(self, chat_id: int, user_id: int, args: list = None, page: int = 1) -> dict[str, Any]:
        """Handle /list_my_orders command"""
        show_ids = args and len(args) > 0 and args[0].lower() == "id"

        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, self._t("customer_not_found", user_id))
            return {"status": "customer_not_found"}

        # Import BaseOrderHandler to use shared method
        from handlers.admin.order.base_order_handler import BaseOrderHandler

        base_handler = BaseOrderHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        return base_handler._show_customer_orders(chat_id, customer, page, show_order_ids=show_ids, user_id=user_id)

    def handle_view_offer(self, chat_id: int, user_id: int, args: list = None) -> dict[str, Any]:
        """Handle offer details display and editing from deep link or command"""
        if not args:
            # Return same as list_offers without parameters
            return self.handle_list_offers(chat_id, user_id, [])

        try:
            offer_id = int(args[0])
            # Check for "edit" parameter for admin edit mode
            edit_mode = len(args) > 1 and args[1].lower() == "edit" and self._is_admin(user_id)
            # Check for "user" parameter for admin user view
            show_as_user = len(args) > 1 and args[1].lower() == "user" and self._is_admin(user_id)

            offer = self.db.get_offer(offer_id)

            if not offer:
                self._send_message(chat_id, self._t("offer_not_found"))
                return {"status": "offer_not_found"}

            # Only show draft offers to admins
            if offer.status == OfferStatus.DRAFT.value and not self._is_admin(user_id):
                self._send_message(chat_id, self._t("offer_not_available"))
                return {"status": "offer_not_available"}

            # Block DRAFT, IMPORT, INACTIVE for non-admins unless they have orders
            RESTRICTED_STATUSES = [OfferStatus.DRAFT.value, OfferStatus.IMPORT.value, OfferStatus.INACTIVE.value]

            if not self._is_admin(user_id) and offer.status in RESTRICTED_STATUSES:
                customer = self.db.get_customer_by_telegram_id(user_id)
                if not customer or not self.db.get_orders_by_customer_and_offer(customer.customer_id, offer_id):
                    self._send_message(chat_id, self._t("offer_not_available"))
                    return {"status": "offer_not_available"}

            # Handle edit mode for admins
            if edit_mode:
                return self._show_edit_interface(chat_id, offer)

            # Send rich offer details
            if show_as_user:
                # Show as regular user would see it
                self._send_offer_view(chat_id, offer, user_id=999999)  # Fake non-admin user ID
            else:
                self._send_offer_view(chat_id, offer, user_id)

            return {"status": "success"}

        except ValueError:
            self._send_message(chat_id, self._t("invalid_offer_id"))
            return {"status": "invalid_format"}

    def _show_edit_interface(self, chat_id: int, offer) -> dict[str, Any]:
        """Show editing interface for offer"""
        message = self._t(
            "edit_offer_details",
            offer_id=offer.offer_id,
            name=offer.name,
            price=offer.price_per_unit,
            box_size=offer.wholesale_box_size,
            status=offer.status,
            supplier=offer.supplier_name,
            description=offer.description or self._t("not_set"),
            image_count=len(offer.images),
        )

        keyboard = {
            "inline_keyboard": [
                [{"text": self._t("edit_name"), "callback_data": f"edit_offer_name_{offer.offer_id}"}],
                [{"text": self._t("edit_price"), "callback_data": f"edit_offer_price_{offer.offer_id}"}],
                [{"text": self._t("edit_description"), "callback_data": f"edit_offer_description_{offer.offer_id}"}],
                [{"text": self._t("upload_image"), "callback_data": f"upload_offer_image_{offer.offer_id}"}],
                [{"text": self._t("clear_images"), "callback_data": f"clear_offer_images_{offer.offer_id}"}]
                if offer.images
                else [],
                [{"text": self._t("exit_edit_mode"), "callback_data": f"view_offer_{offer.offer_id}"}],
            ]
        }

        # Remove empty rows
        keyboard["inline_keyboard"] = [row for row in keyboard["inline_keyboard"] if row]

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "success"}

    def _send_offer_view(self, chat_id: int, offer, user_id: int):
        """Send rich offer details with images and description"""
        # Send images as media group if available
        if offer.images:
            if len(offer.images) == 1:
                # Single image
                try:
                    image_url = offer.images[0]
                    if "s3.amazonaws.com" in image_url:
                        presigned_url = self.db.get_presigned_url(image_url)
                        if presigned_url:
                            image_url = presigned_url
                    self._send_photo(chat_id, image_url)
                except Exception as e:
                    logger.error(f"Failed to send image {image_url}: {e}")
            else:
                # Multiple images as media group
                media_group = []
                for image_url in offer.images[:10]:  # Telegram limit is 10 images per group
                    try:
                        if "s3.amazonaws.com" in image_url:
                            presigned_url = self.db.get_presigned_url(image_url)
                            if presigned_url:
                                image_url = presigned_url
                        media_group.append({"type": "photo", "media": image_url})
                    except Exception as e:
                        logger.error(f"Failed to prepare image {image_url}: {e}")

                if media_group:
                    self._send_media_group(chat_id, media_group)

        # Build detailed message
        is_draft = offer.status == OfferStatus.DRAFT.value
        is_admin = self._is_admin(user_id)

        message = ""
        if is_draft and is_admin:
            message = self._t("preview_offer_look") + "\n"

        if offer.status == OfferStatus.ACTIVE.value:
            # Get availability for active offers
            total_ordered, total_capacity = self._get_offer_capacity_info(offer.offer_id, user_id)
            available = total_capacity - total_ordered

            message += (
                f"<b>{offer.offer_id}. {offer.name} €{offer.price_per_unit:.2f} "
                f"({available}/{total_capacity} {self._t('available_text', user_id)})</b>\n\n"
            )
        else:
            message += f"<b>{offer.offer_id}. {offer.name} €{offer.price_per_unit:.2f}</b>\n\n"

        # Show admin-only info
        if is_admin:
            message += self._t("box_size_units", size=offer.wholesale_box_size) + "\n"
            message += self._t("supplier_name", name=offer.supplier_name) + "\n"
            message += self._t("status_label", status=offer.status) + "\n"

        if offer.status != OfferStatus.ACTIVE.value and not is_admin:
            message += f"{self._t('product_cannot_be_ordered')}\n"

        message += f"\n{offer.description}\n"

        # Add order buttons for active offers
        reply_markup = None
        if offer.status == OfferStatus.ACTIVE.value:
            # message += "\n" + self._t('order_with_command', offer_id=offer.offer_id)
            if is_admin:
                reply_markup = {
                    "inline_keyboard": [
                        [
                            {"text": self._t("order_1"), "callback_data": f"order_{offer.offer_id}_1"},
                            {"text": self._t("order_2"), "callback_data": f"order_{offer.offer_id}_2"},
                        ],
                        [{"text": self._t("edit_offer_button"), "callback_data": f"view_offer_{offer.offer_id}_edit"}],
                    ]
                }
            else:
                reply_markup = {
                    "inline_keyboard": [
                        [
                            {"text": self._t("order_1"), "callback_data": f"order_{offer.offer_id}_1"},
                            {"text": self._t("order_2"), "callback_data": f"order_{offer.offer_id}_2"},
                        ]
                    ]
                }
        elif is_admin and offer.status == OfferStatus.DRAFT.value:
            # Draft preview: single message with the distinct draft actions
            reply_markup = {
                "inline_keyboard": [
                    [{"text": self._t("edit_details"), "callback_data": f"view_offer_{offer.offer_id}_edit"}],
                    [{"text": self._t("publish_offer_btn"), "callback_data": f"publish_offer_{offer.offer_id}"}],
                ]
            }
        elif is_admin:
            # Add edit button for admins on non-active offers
            reply_markup = {
                "inline_keyboard": [
                    [{"text": self._t("edit_offer_button"), "callback_data": f"view_offer_{offer.offer_id}_edit"}]
                ]
            }

        self._send_message(chat_id, message, reply_markup=reply_markup, parse_mode="HTML")
