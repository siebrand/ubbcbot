import logging
import os
from typing import Any

from handlers.base_handler import BaseHandler
from models.entities import OfferStatus, OrderStatus
from services import offer_listing
from utils.pagination import PaginationUtils
from utils.s3_url import is_s3_url

logger = logging.getLogger(__name__)

# /help <section>: the text of a section is the translation help_<section>. In this order for /help all.
CUSTOMER_HELP_SECTIONS = ("general", "orders")
ADMIN_HELP_SECTIONS = ("suppliers", "offers", "users", "delivery", "import", "system", "reports")


class InfoCommands(BaseHandler):
    def handle_privacy(self, chat_id: int, user_id: int, args: list | None = None) -> dict[str, Any]:
        """Handle /privacy command: reply with a link to the rendered privacy statement."""
        privacy_url = os.environ.get("PRIVACY_URL", "")
        message = self._t("privacy_info", user_id, url=privacy_url)
        self._send_message(chat_id, message, parse_mode="HTML")
        return {"status": "success"}

    def handle_start(self, chat_id: int, user_id: int, args: list | None = None) -> dict[str, Any]:
        """Handle /start command with optional help section parameter"""
        if self.environment == "test":
            logger.info(f"Processing /start command for user {user_id}, chat {chat_id}")

        # Check if specific help section requested
        section = args[0].lower() if args and len(args) > 0 else None

        if section:
            return self._show_help_section(chat_id, user_id, section)

        # Show general help
        message = self._t("welcome_ubbc", user_id)

        if self._is_admin(user_id):
            message += self._t("admin_sections_available", user_id)

        result = self._send_message(chat_id, message)
        success = result.get("success", False)
        if self.environment == "test":
            logger.info(f"Message send result: {success}")

        return {"status": "success"}

    def handle_help(self, chat_id: int, user_id: int, args: list | None = None) -> dict[str, Any]:
        """Handle /help command with optional section parameter"""
        section = args[0].lower() if args and len(args) > 0 else None

        if section:
            return self._show_help_section(chat_id, user_id, section)

        # Get bot username first
        bot_username = self._get_bot_username()

        # Show available sections
        message = self._t("help_sections", user_id, bot_username=bot_username)

        if self._is_admin(user_id):
            message += self._t("admin_help_sections", user_id, bot_username=bot_username)

        self._send_message(chat_id, message, parse_mode="Markdown")
        return {"status": "success"}

    def _show_help_section(self, chat_id: int, user_id: int, section: str) -> dict[str, Any]:
        """Show help for specific section"""
        is_admin = self._is_admin(user_id)
        visible = CUSTOMER_HELP_SECTIONS + (ADMIN_HELP_SECTIONS if is_admin else ())

        if section == "all":
            # Show all available sections in separate messages
            for name in visible:
                self._send_message(chat_id, self._t(f"help_{name}", user_id))
            return {"status": "success"}

        if section in visible:
            message = self._t(f"help_{section}", user_id)
        elif section in ADMIN_HELP_SECTIONS:
            message = self._t("admin_only_section", user_id)
        else:
            sections = CUSTOMER_HELP_SECTIONS + ("all",) + (ADMIN_HELP_SECTIONS if is_admin else ())
            message = self._t("unknown_section", user_id, section=section, sections=", ".join(sections))

        self._send_message(chat_id, message)
        return {"status": "success"}

    def _format_offer_line(self, offer, status_emoji, user_id, total_ordered=None, total_capacity=None, is_draft=False):
        """Format a single offer line with consistent markup. The name is plain text, like in the announcement."""
        bot_username = self._get_bot_username()

        line = (
            f"{status_emoji} <a href='https://t.me/{bot_username}?start=view_offer_{offer.offer_id}'>"
            f"<b>{offer.offer_id}</b></a> <b>{self._escape_html(offer.name)}</b> €{offer.price_per_unit:.2f}"
        )
        if not is_draft and total_ordered is not None and total_capacity is not None:
            line += f" ({total_ordered}/{total_capacity} {self._t('ordered_text', user_id)})"
        return line + "\n"

    def _get_offer_capacity_info(
        self, offer_id: int, boxes_by_offer: dict | None = None, orders_by_offer: dict | None = None
    ) -> tuple[int, int]:
        """(ordered, capacity) of an offer. The lists pass the boxes and open orders they loaded; the detail view
        reads those of the one offer."""
        if boxes_by_offer is not None and orders_by_offer is not None:
            return offer_listing.ordered_and_capacity(
                boxes_by_offer.get(offer_id, []), orders_by_offer.get(offer_id, [])
            )
        boxes = self.db.get_boxes_by_offer(offer_id)
        orders = [o for o in self.db.get_orders_by_offer(offer_id) if o.status in offer_listing.OPEN_ORDER_STATUSES]
        return offer_listing.ordered_and_capacity(boxes, orders)

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
            return self.show_fomo(chat_id, user_id, customer)

        customer, error = self._validate_customer(chat_id, user_id)
        if error:
            return error
        return self.show_fomo(chat_id, user_id, customer)

    def show_fomo(self, chat_id: int, caller_user_id: int, customer) -> dict[str, Any]:
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

        # This message is sent as HTML, so the name is escaped (the "nothing to order" one above is plain text)
        header_key = "fomo_header" if is_self else "fomo_header_for_user"
        message = self._t(header_key, caller_user_id, name=self._html_customer_name(customer)) + "\n\n"
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

    def handle_list_offers(self, chat_id: int, user_id: int, args: list | None = None, page: int = 1) -> dict[str, Any]:
        """Handle /list_offers command with optional status filtering (see services/offer_listing.py)"""
        offers = self.db.list_offers()
        if not offers:
            return self._no_offers(chat_id, user_id)

        is_admin = self._is_admin(user_id)
        # Filter words without underscores, so sold_out and soldout are the same
        word = args[0].lower().replace("_", "") if args else None

        if word == "help":
            help_message = self._t("list_offers_help", user_id)
            if is_admin:
                help_message += "\n\n" + self._t("list_offers_help_admin", user_id)
            self._send_message(chat_id, help_message)
            return {"status": "success"}

        if word and page == 1 and not offer_listing.is_known_filter(word, is_admin):
            # Shown before the list, on the first page only (the page buttons keep the word)
            self._send_message(chat_id, self._t("list_offers_unknown_filter", user_id, word=args[0][:30]))

        # Loaded once for all lines: how much is ordered of each offer
        boxes = offer_listing.by_offer(self.db.get_all_boxes())
        orders = offer_listing.by_offer(self.db.get_all_orders(statuses=list(offer_listing.OPEN_ORDER_STATUSES)))

        if word == "soldout":
            sold_out = offer_listing.sold_out_offers(offers)
            if not sold_out:
                return self._no_offers(chat_id, user_id)
            page_offers, total_pages = PaginationUtils.paginate_list(sold_out, page, offer_listing.PAGE_SIZE)
            body = "".join(
                self._listed_line(offer, offer_listing.SOLD_OUT, user_id, boxes, orders) for offer in page_offers
            )
            title = self._t("sold_out_offers_title", user_id)
            return self._send_offer_page(chat_id, user_id, title, body, page, total_pages, "list_offers_soldout")

        if is_admin and word != "user":
            return self._send_admin_overview(chat_id, user_id, offers, word, page, boxes, orders)

        # Customers, and the admin's "user" view: what customers can order
        active = offer_listing.customer_offers(offers)
        if not active:
            return self._no_offers(chat_id, user_id)
        page_offers, total_pages = PaginationUtils.paginate_list(active, page, offer_listing.PAGE_SIZE)
        body = "".join(self._listed_line(offer, offer_listing.ACTIVE, user_id, boxes, orders) for offer in page_offers)
        title = self._t("active_offers_customer", user_id)
        buttons = "list_offers_user" if is_admin else "list_offers"
        return self._send_offer_page(chat_id, user_id, title, body, page, total_pages, buttons)

    def _send_admin_overview(
        self, chat_id: int, user_id: int, offers: list, word: str | None, page: int, boxes: dict, orders: dict
    ) -> dict[str, Any]:
        """The admin's list: the statuses of the filter, with a header per status in the overview views"""
        view = offer_listing.admin_view(word)
        listed = offer_listing.offers_in_view(offers, view)
        page_items, total_pages = PaginationUtils.paginate_list(listed, page, offer_listing.PAGE_SIZE)

        body = ""
        current = None
        for status, offer in page_items:
            if view.sections and status != current:
                body += ("\n" if current else "") + self._section_title(status, user_id) + "\n"
            current = status
            body += self._listed_line(offer, status, user_id, boxes, orders, admin=True)

        title = self._t(view.title_key, user_id) if view.title_key else self._section_title(view.statuses[0], user_id)
        # The page buttons keep the word as typed (also an unknown one, which shows the default view)
        buttons = f"list_offers_{word}" if word else "list_offers"
        return self._send_offer_page(chat_id, user_id, title, body, page, total_pages, buttons)

    def _section_title(self, status: str, user_id: int) -> str:
        key = offer_listing.SECTION_TITLE_KEYS.get(status)
        if key:
            return self._t(key, user_id)
        label = self._t(offer_listing.STATUS_LABEL_KEYS[status], user_id).upper()
        return f"{offer_listing.STATUS_ICONS[status]} {label}:"

    def _listed_line(self, offer, status: str, user_id: int, boxes: dict, orders: dict, admin: bool = False) -> str:
        """One offer in a list: its icon, and for the statuses that show it, how much is ordered"""
        icon = offer_listing.STATUS_ICONS[status]
        if admin and status == offer_listing.ACTIVE and offer_listing.has_ordered_box(boxes.get(offer.offer_id, [])):
            icon = offer_listing.ORDERED_BOX_ICON
        if status not in offer_listing.SHOWS_ORDERED:
            return self._format_offer_line(offer, icon, user_id)
        ordered, capacity = self._get_offer_capacity_info(offer.offer_id, boxes, orders)
        return self._format_offer_line(offer, icon, user_id, ordered, capacity)

    def _send_offer_page(
        self, chat_id: int, user_id: int, title: str, body: str, page: int, total_pages: int, buttons: str
    ) -> dict[str, Any]:
        """A page of an offer list: the title (with the page number when there are more), the lines, page buttons"""
        reply_markup = None
        if total_pages > 1:
            title += " - " + self._t("page_indicator", user_id, page=page, total_pages=total_pages)
            reply_markup = PaginationUtils.build_pagination_keyboard(page, total_pages, buttons, enhanced=True)
        self._send_message(chat_id, f"{title}\n\n{body}", parse_mode="HTML", reply_markup=reply_markup)
        return {"status": "success"}

    def _no_offers(self, chat_id: int, user_id: int) -> dict[str, Any]:
        self._send_message(chat_id, self._t("no_offers", user_id))
        return {"status": "no_offers"}

    def handle_list_my_orders(
        self, chat_id: int, user_id: int, args: list | None = None, page: int = 1
    ) -> dict[str, Any]:
        """Handle /list_my_orders command"""
        show_ids = args and len(args) > 0 and args[0].lower() == "id"

        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, self._t("customer_not_found", user_id))
            return {"status": "customer_not_found"}

        # Import BaseOrderHandler to use shared method
        from handlers.admin.order.base_order_handler import BaseOrderHandler

        base_handler = BaseOrderHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        return base_handler.show_customer_orders(chat_id, customer, page, show_order_ids=show_ids, user_id=user_id)

    def handle_view_offer(self, chat_id: int, user_id: int, args: list | None = None) -> dict[str, Any]:
        """The details of an offer, from a deep link, a button or /view_offer"""
        if not args:
            # Return same as list_offers without parameters
            return self.handle_list_offers(chat_id, user_id, [])

        try:
            offer_id = int(args[0])
            # "user": the admin sees the offer as customers do. Editing is the admin's edit screen (OfferCommands).
            show_as_user = len(args) > 1 and args[1].lower() == "user" and self._is_admin(user_id)

            offer = self.db.get_offer(offer_id)

            if not offer:
                self._send_message(chat_id, self._t("offer_not_found", user_id))
                return {"status": "offer_not_found"}

            # Only show draft offers to admins
            if offer.status == OfferStatus.DRAFT.value and not self._is_admin(user_id):
                self._send_message(chat_id, self._t("offer_not_available", user_id))
                return {"status": "offer_not_available"}

            # Block DRAFT, IMPORT, INACTIVE for non-admins unless they have orders
            RESTRICTED_STATUSES = [OfferStatus.DRAFT.value, OfferStatus.IMPORT.value, OfferStatus.INACTIVE.value]

            if not self._is_admin(user_id) and offer.status in RESTRICTED_STATUSES:
                customer = self.db.get_customer_by_telegram_id(user_id)
                if not customer or not self.db.get_orders_by_customer_and_offer(customer.customer_id, offer_id):
                    self._send_message(chat_id, self._t("offer_not_available", user_id))
                    return {"status": "offer_not_available"}

            self._send_offer_view(chat_id, offer, user_id, as_customer=show_as_user)
            return {"status": "success"}

        except ValueError:
            self._send_message(chat_id, self._t("invalid_offer_id", user_id))
            return {"status": "invalid_format"}

    def _send_offer_view(self, chat_id: int, offer, user_id: int, as_customer: bool = False):
        """Send rich offer details with images and description. ``as_customer``: the admin sees what customers see."""
        is_admin = self._is_admin(user_id) and not as_customer
        self._send_offer_images(chat_id, offer.images)
        message = self._offer_view_text(offer, user_id, is_admin)
        reply_markup = self._offer_view_keyboard(offer, user_id, is_admin)
        self._send_message(chat_id, message, reply_markup=reply_markup, parse_mode="HTML")

    def _send_offer_images(self, chat_id: int, images: list) -> None:
        """One image as a photo, more as an album (Telegram takes at most 10). S3 images are sent presigned."""
        urls = []
        for image_url in images[:10]:
            try:
                urls.append(self._viewable_url(image_url))
            except Exception as e:
                logger.error(f"Failed to prepare an offer image: {type(e).__name__}")
        if not urls:
            return
        if len(images) == 1:
            self._send_photo(chat_id, urls[0])
        else:
            self._send_media_group(chat_id, [{"type": "photo", "media": url} for url in urls])

    def _viewable_url(self, image_url: str) -> str:
        if is_s3_url(image_url):
            return self.db.get_presigned_url(image_url) or image_url
        return image_url

    def _offer_view_text(self, offer, user_id: int, is_admin: bool) -> str:
        message = ""
        if offer.status == OfferStatus.DRAFT.value and is_admin:
            message = self._t("preview_offer_look", user_id) + "\n"

        # The name is plain text; the description is HTML (validated when the admin enters it)
        name = self._escape_html(offer.name)
        if offer.status == OfferStatus.ACTIVE.value:
            # Get availability for active offers
            total_ordered, total_capacity = self._get_offer_capacity_info(offer.offer_id)
            available = total_capacity - total_ordered

            message += (
                f"<b>{offer.offer_id}. {name} €{offer.price_per_unit:.2f} "
                f"({available}/{total_capacity} {self._t('available_text', user_id)})</b>\n\n"
            )
        else:
            message += f"<b>{offer.offer_id}. {name} €{offer.price_per_unit:.2f}</b>\n\n"

        # Show admin-only info
        if is_admin:
            message += self._t("box_size_units", user_id, size=offer.wholesale_box_size) + "\n"
            message += self._t("supplier_name", user_id, name=self._escape_html(offer.supplier_name)) + "\n"
            message += self._t("status_label", user_id, status=offer.status) + "\n"

        if offer.status != OfferStatus.ACTIVE.value and not is_admin:
            message += f"{self._t('product_cannot_be_ordered', user_id)}\n"

        return message + f"\n{offer.description}\n"

    def _offer_view_keyboard(self, offer, user_id: int, is_admin: bool) -> dict | None:
        """Order buttons when the offer is active; for the admin also edit (and publish for a draft)"""
        offer_id = offer.offer_id
        edit_button = [{"text": self._t("edit_offer_button", user_id), "callback_data": f"view_offer_{offer_id}_edit"}]
        reply_markup = None
        if offer.status == OfferStatus.ACTIVE.value:
            order_buttons = [
                {"text": self._t("order_1", user_id), "callback_data": f"order_{offer_id}_1"},
                {"text": self._t("order_2", user_id), "callback_data": f"order_{offer_id}_2"},
            ]
            rows = [order_buttons, edit_button] if is_admin else [order_buttons]
            reply_markup = {"inline_keyboard": rows}
        elif is_admin and offer.status == OfferStatus.DRAFT.value:
            # Draft preview: single message with the distinct draft actions
            reply_markup = {
                "inline_keyboard": [
                    [{"text": self._t("edit_details", user_id), "callback_data": f"view_offer_{offer_id}_edit"}],
                    [{"text": self._t("publish_offer_btn", user_id), "callback_data": f"publish_offer_{offer_id}"}],
                ]
            }
        elif is_admin:
            # Add edit button for admins on non-active offers
            reply_markup = {"inline_keyboard": [edit_button]}
        return reply_markup
