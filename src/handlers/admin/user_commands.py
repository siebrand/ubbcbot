import logging
from collections.abc import Callable
from typing import Any

from handlers.base_handler import BaseHandler
from models.entities import AuthorizationStatus, Customer
from services.customer_deletion import SETTLED_ORDER_STATUSES, CustomerDeletionService
from services.user_cache import UserCache
from utils.pagination import PaginationUtils
from utils.update_utils import UpdateUtils

logger = logging.getLogger()


class UserCommands(BaseHandler):
    # Status emoji mapping - single source of truth
    STATUS_EMOJIS = {
        AuthorizationStatus.UNAUTHORIZED.value: "⚠️",
        AuthorizationStatus.APPROVED.value: "✅",
        AuthorizationStatus.REJECTED.value: "❌",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.deletion_service = CustomerDeletionService(self.db)
        self.update_utils = UpdateUtils(self.db, self._t, self._send_message)
        self.update_utils._show_customer_edit_interface = lambda chat_id, customer: self._show_user_edit_interface(
            customer, chat_id
        )

    def _approve_user_by_customer(self, chat_id: int, customer) -> dict[str, Any]:
        """Shared approval logic for customer object"""
        if customer.authorization_status == AuthorizationStatus.APPROVED.value:
            name = self._first_name(customer, chat_id)
            self._send_message(chat_id, self._t("user_already_approved", chat_id, name=name))
            return {"status": "already_approved"}

        # Update user status
        if self.db.update_customer(customer.customer_id, {"authorization_status": AuthorizationStatus.APPROVED.value}):
            self._tell_user(chat_id, customer, "user_authorized")
            self._send_message(chat_id, self._t("user_approved", chat_id, name=self._first_name(customer, chat_id)))

            # Enter update user dialog
            return self._show_user_edit_interface(customer, chat_id)
        else:
            self._send_message(chat_id, self._t("failed_approve_user", chat_id))
            return {"status": "error"}

    def _first_name(self, customer, chat_id: int) -> str:
        return customer.first_name or self._t("unknown", chat_id)

    def _full_name(self, customer, chat_id: int) -> str:
        """First and last name, as plain text"""
        return " ".join(filter(None, [self._first_name(customer, chat_id), customer.last_name]))

    def _tell_user(self, chat_id: int, customer, key: str) -> None:
        """Tell a user the decision on their access, and tell the admin when the message did not arrive"""
        result = self._notify_customer(customer, key)
        if not result.get("success") and not result.get("skipped_guest"):
            self._send_message(chat_id, self._t("user_not_notified", chat_id, name=self._full_name(customer, chat_id)))

    # The statuses the edit screen can set, in this order
    EDITABLE_STATUSES = (
        AuthorizationStatus.APPROVED.value,
        AuthorizationStatus.UNAUTHORIZED.value,
        AuthorizationStatus.REJECTED.value,
    )

    def _statuses_for(self, customer) -> tuple[str, ...]:
        """The statuses a customer can be given: a guest cannot sign up, so never pending"""
        if customer.is_guest:
            return tuple(s for s in self.EDITABLE_STATUSES if s != AuthorizationStatus.UNAUTHORIZED.value)
        return self.EDITABLE_STATUSES

    def _confirm_if_open_orders(self, chat_id: int, customer, status: str, confirmed: bool) -> dict[str, Any] | None:
        """Taking the approval from a customer with orders that are not paid or cancelled needs a confirmation: the
        delivery overview, /process_payment and the payment reminders only handle approved customers, so those
        orders get stuck. Without open orders, or once confirmed, None: the status may change."""
        if confirmed or customer.authorization_status != AuthorizationStatus.APPROVED.value:
            return None
        open_orders = [
            o for o in self.db.get_orders_by_customer(customer.customer_id) if o.status not in SETTLED_ORDER_STATUSES
        ]
        if not open_orders:
            return None
        warning = self._t(
            "customer_status_open_orders", chat_id, name=self._full_name(customer, chat_id), count=len(open_orders)
        )
        buttons = [
            [
                {
                    "text": self._t("confirm_status_change_btn", chat_id),
                    "callback_data": f"edit_customer_forcestatus_{customer.customer_id}_{status}",
                },
                {"text": self._t("cancel", chat_id), "callback_data": "cancel_action"},
            ]
        ]
        self._send_message(chat_id, warning, reply_markup={"inline_keyboard": buttons})
        return {"status": "confirmation_required"}

    def handle_customer_status_options(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """The status button of the edit screen: the other statuses this customer can be given"""
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t("user_not_found", chat_id, identifier=customer_id))
            return {"status": "user_not_found"}
        buttons = [
            [
                {
                    "text": f"{self.STATUS_EMOJIS[status]} {self._t(f'customer_status_{status}', chat_id)}",
                    "callback_data": f"edit_customer_setstatus_{customer.customer_id}_{status}",
                }
            ]
            for status in self._statuses_for(customer)
            if status != customer.authorization_status
        ]
        buttons.append([{"text": self._t("cancel", chat_id), "callback_data": f"edit_user_select_{customer_id}"}])
        current = self._t(f"customer_status_{customer.authorization_status}", chat_id)
        self._send_message(
            chat_id,
            self._t("choose_customer_status", chat_id, name=self._full_name(customer, chat_id), status=current),
            reply_markup={"inline_keyboard": buttons},
        )
        return {"status": "status_options_shown"}

    def handle_set_customer_status(
        self, chat_id: int, customer_id: str, status: str, confirmed: bool = False
    ) -> dict[str, Any]:
        """Give the customer another authorization status: approved (they are told, as with /approve_user), rejected
        (they are told, as with /reject_user) or unauthorized (back to the pending list, not told). ``confirmed``:
        the admin confirmed the warning about open orders."""
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t("user_not_found", chat_id, identifier=customer_id))
            return {"status": "user_not_found"}
        if status not in self._statuses_for(customer):
            self._send_message(chat_id, self._t("failed_customer_status", chat_id))
            return {"status": "invalid_status"}
        if status == AuthorizationStatus.APPROVED.value:
            return self._approve_user_by_customer(chat_id, customer)
        if status == AuthorizationStatus.REJECTED.value:
            result = self._reject_customer(chat_id, customer, confirmed)
        else:
            asked = self._confirm_if_open_orders(chat_id, customer, status, confirmed)
            if asked:
                return asked
            if not self.db.update_customer(customer.customer_id, {"authorization_status": status}):
                self._send_message(chat_id, self._t("failed_customer_status", chat_id))
                return {"status": "error"}
            name = self._full_name(customer, chat_id)
            self._send_message(chat_id, self._t("customer_status_set_pending", chat_id, name=name))
            result = {"status": "success"}
        if result["status"] == "success":
            UserCache.invalidate_cache()
            updated = self.db.get_customer(customer_id)
            if updated:
                self._show_user_edit_interface(updated, chat_id)
        return result

    def _reject_customer(self, chat_id: int, customer, confirmed: bool = False) -> dict[str, Any]:
        asked = self._confirm_if_open_orders(chat_id, customer, AuthorizationStatus.REJECTED.value, confirmed)
        if asked:
            return asked
        if not self.db.update_customer(
            customer.customer_id, {"authorization_status": AuthorizationStatus.REJECTED.value}
        ):
            self._send_message(chat_id, self._t("failed_reject_user", chat_id))
            return {"status": "error"}

        self._tell_user(chat_id, customer, "access_rejected")
        self._send_message(chat_id, self._t("user_rejected", chat_id, name=self._first_name(customer, chat_id)))
        return {"status": "success"}

    def _send_user_status(self, chat_id: int, customer) -> dict[str, Any]:
        username_part = f" (@{customer.username})" if customer.username else ""
        status_emoji = self.STATUS_EMOJIS.get(customer.authorization_status, "❓")
        message = f"{status_emoji} {self._full_name(customer, chat_id)}{username_part}\n"
        message += self._t("user_status_label", chat_id, status=customer.authorization_status)
        self._send_message(chat_id, message)
        return {"status": "success"}

    def handle_list_pending(self, chat_id: int, page: int = 1) -> dict[str, Any]:
        """Handle /list_pending command with pagination"""
        customers = self.db.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value)

        if not customers:
            self._send_message(chat_id, self._t("no_pending_users", chat_id))
            return {"status": "no_pending"}

        # Paginate results
        page_customers, total_pages = self._paginate_list(customers, page, 5)  # Smaller page size for buttons

        message = self._t("pending_users_title", chat_id, page=page, total_pages=total_pages) + "\n\n"
        keyboard_buttons = []

        for customer in page_customers:
            username_part = f"(@{customer.username})" if customer.username else self._t("no_username", chat_id)
            message += f"{self._full_name(customer, chat_id)} {username_part}\n"

            # Add approve/reject buttons for each user
            keyboard_buttons.append(
                [
                    {
                        "text": self._t("approve_user", chat_id, name=self._first_name(customer, chat_id)),
                        "callback_data": f"approve_user_{customer.customer_id}",
                    },
                    {
                        "text": self._t("reject_user", chat_id, name=self._first_name(customer, chat_id)),
                        "callback_data": f"reject_user_{customer.customer_id}",
                    },
                ]
            )

        # Add pagination buttons if needed
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": self._t("previous", chat_id), "callback_data": f"page_pending_{page - 1}_"})
            nav_buttons.append(
                {
                    "text": self._t("page_indicator", chat_id, page=page, total_pages=total_pages),
                    "callback_data": "page_info",
                }
            )
            if page < total_pages:
                nav_buttons.append({"text": self._t("next", chat_id), "callback_data": f"page_pending_{page + 1}_"})
            keyboard_buttons.append(nav_buttons)

        if keyboard_buttons:
            keyboard = {"inline_keyboard": keyboard_buttons}
            self._send_message(chat_id, message, reply_markup=keyboard)
        else:
            self._send_message(chat_id, message)

        return {"status": "success"}

    def handle_approve_user(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /approve_user command"""
        if not args:
            self._send_message(chat_id, self._t("usage_approve_user", chat_id))
            return {"status": "invalid_args"}

        identifier = " ".join(args)
        customer, error = self._find_customer_with_disambiguation(
            identifier, chat_id, "approve_user_select", AuthorizationStatus.UNAUTHORIZED.value
        )

        if error:
            return error

        return self._approve_user_by_customer(chat_id, customer)

    def handle_reject_user(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /reject_user command"""
        if not args:
            self._send_message(chat_id, self._t("usage_reject_user", chat_id))
            return {"status": "invalid_args"}

        identifier = " ".join(args)
        # With several matches the list's buttons reject the customer picked (reject_user_<id>)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "reject_user")

        if error:
            return error

        return self._reject_customer(chat_id, customer)

    def handle_user_status(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /user_status command"""
        if not args:
            self._send_message(chat_id, self._t("usage_user_status", chat_id))
            return {"status": "invalid_args"}

        identifier = " ".join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "user_status_select")

        if error:
            return error

        return self._send_user_status(chat_id, customer)

    def _show_user_edit_interface(self, customer, chat_id: int) -> dict[str, Any]:
        """Show edit interface for a customer"""
        display_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t(
            "unknown", user_id=None
        )
        username_part = (
            f" (@{customer.username})"
            if customer.username and not customer.is_guest
            else (f" ({customer.username})" if customer.is_guest else "")
        )

        message = self._t("edit_user", chat_id, name=display_name, username=username_part) + "\n\n"
        message += self._t("first_name", chat_id, value=customer.first_name or self._t("not_set", chat_id)) + "\n"
        message += self._t("last_name", chat_id, value=customer.last_name or self._t("not_set", chat_id)) + "\n"

        if customer.is_guest:
            message += self._t("contact", chat_id, value=customer.contact_info or self._t("not_set", chat_id)) + "\n"

        message += self._t("location", chat_id, value=customer.location or self._t("not_set", chat_id)) + "\n"
        message += self._t("select_edit", chat_id)

        keyboard_buttons = [
            [
                {
                    "text": self._t("edit_first_name", chat_id),
                    "callback_data": f"edit_customer_first_name_{customer.customer_id}",
                }
            ],
            [
                {
                    "text": self._t("edit_last_name", chat_id),
                    "callback_data": f"edit_customer_last_name_{customer.customer_id}",
                }
            ],
        ]

        if customer.is_guest:
            keyboard_buttons.append(
                [
                    {
                        "text": self._t("edit_contact", chat_id),
                        "callback_data": f"edit_customer_contact_{customer.customer_id}",
                    }
                ]
            )

        keyboard_buttons.append(
            [
                {
                    "text": self._t("edit_location", chat_id),
                    "callback_data": f"edit_customer_location_{customer.customer_id}",
                }
            ]
        )
        keyboard_buttons.append(
            [
                {
                    "text": self._t("edit_customer_status_btn", chat_id),
                    "callback_data": f"edit_customer_status_{customer.customer_id}",
                }
            ]
        )
        keyboard_buttons.append([{"text": self._t("done", chat_id), "callback_data": "done_action"}])

        keyboard = {"inline_keyboard": keyboard_buttons}

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "success"}

    def handle_update_user(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /update_user command"""
        if not args:
            self._send_message(chat_id, self._t("usage_update_user", chat_id))
            return {"status": "invalid_args"}

        identifier = " ".join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "edit_user_select")

        if error:
            return error

        return self._show_user_edit_interface(customer, chat_id)

    def _deletion_label(self, customer) -> str:
        """HTML-safe label for deletion messages: name plus short customer ID to tell namesakes apart"""
        name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t("unknown", user_id=None)
        return f"{self._escape_html(name)} ({customer.customer_id[:8]})"

    def _send_deletion_blocked(self, chat_id: int, customer, blockers) -> dict[str, Any]:
        """Explain why a customer cannot be deleted yet"""
        message = self._t("delete_user_blocked", chat_id, label=self._deletion_label(customer)) + "\n\n"

        if blockers.open_orders:
            lines = []
            for order in blockers.open_orders:
                offer = self.db.get_offer(order.offer_id)
                offer_name = self._escape_html(offer.name) if offer else self._t("unknown", user_id=None)
                lines.append(f"  – {order.order_id[:8]}: {order.quantity}x {offer_name} ({order.status})")
            message += (
                self._t("delete_user_blocked_orders", chat_id, count=len(blockers.open_orders), orders="\n".join(lines))
                + "\n"
            )

        if blockers.credit_balance != 0:
            message += self._t("delete_user_blocked_credit", chat_id, balance=f"{blockers.credit_balance:.2f}") + "\n"

        self._send_message(chat_id, message.rstrip(), parse_mode="HTML")
        return {"status": "delete_blocked"}

    def _show_delete_user_confirmation(self, chat_id: int, customer) -> dict[str, Any]:
        """Ask for confirmation, or explain what blocks the deletion"""
        blockers = self.deletion_service.get_blockers(customer)
        if blockers.blocked:
            return self._send_deletion_blocked(chat_id, customer, blockers)

        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": self._t("delete_user_confirm_btn", chat_id),
                        "callback_data": f"delete_user_confirm_{customer.customer_id}",
                    },
                    {"text": self._t("cancel", chat_id), "callback_data": "cancel_confirmation"},
                ]
            ]
        }
        message = self._t("delete_user_confirm", chat_id, label=self._deletion_label(customer))
        self._send_message(chat_id, message, parse_mode="HTML", reply_markup=keyboard)
        return {"status": "confirmation_required"}

    def handle_delete_user(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /delete_user command: remove a customer record (right to be forgotten)"""
        if not args:
            self._send_message(chat_id, self._t("usage_delete_user", chat_id))
            return {"status": "invalid_args"}

        identifier = " ".join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "delete_user_select")

        if error:
            return error

        return self._show_delete_user_confirmation(chat_id, customer)

    def handle_delete_user_select(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Handle user selection from disambiguation for delete user"""
        customer = self.db.get_customer(customer_id)

        if not customer:
            self._send_message(chat_id, self._t("user_not_found", chat_id, identifier=customer_id))
            return {"status": "user_not_found"}

        return self._show_delete_user_confirmation(chat_id, customer)

    def handle_delete_user_confirm(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Delete the customer after confirmation. Blockers are checked again: state may have changed."""
        customer = self.db.get_customer(customer_id)

        if not customer:
            self._send_message(chat_id, self._t("user_not_found", chat_id, identifier=customer_id))
            return {"status": "user_not_found"}

        label = self._deletion_label(customer)
        deleted, blockers = self.deletion_service.delete(customer)

        if blockers.blocked:
            return self._send_deletion_blocked(chat_id, customer, blockers)

        if not deleted:
            self._send_message(chat_id, self._t("delete_user_failed", chat_id, label=label), parse_mode="HTML")
            return {"status": "error"}

        logger.info(f"Customer {customer_id} deleted")
        self._send_message(chat_id, self._t("delete_user_done", chat_id, label=label), parse_mode="HTML")
        return {"status": "success"}

    def handle_update_user_first_name(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /update_user_first_name command"""
        return self.update_utils.handle_customer_update(chat_id, args, "first_name")

    def handle_update_user_last_name(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /update_user_last_name command"""
        return self.update_utils.handle_customer_update(chat_id, args, "last_name")

    def handle_update_user_contact(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /update_user_contact command"""
        return self.update_utils.handle_customer_update(chat_id, args, "contact_info")

    def handle_update_user_location(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /update_user_location command"""
        return self.update_utils.handle_customer_update(chat_id, args, "location")

    def handle_list_users(
        self, chat_id: int, page: int = 1, status_filter: str = "all", search_string: str | None = None
    ) -> dict[str, Any]:
        """Handle /list_users command with pagination, filtering, and optional search"""
        # Get customers based on filter using cache
        if status_filter == "subscribers":
            customers = self.db.get_subscribers()
        elif status_filter == "all":
            customers = self.db.get_all_customers()
        else:
            customers = self.db.get_customers_by_status(status_filter)

        # Apply search filter if provided
        if search_string:
            customers = self.validator.match_customers(search_string, customers)

        if not customers:
            search_text = f" {self._t('matching_search', chat_id, search=search_string)}" if search_string else ""
            self._send_message(
                chat_id, self._t("no_customers_found", chat_id, status=status_filter, search=search_text)
            )
            return {"status": "no_customers"}

        # Sort by first name
        customers.sort(key=lambda x: (x.first_name or "zzz").lower())

        # Paginate results
        page_customers, total_pages = self._paginate_list(customers, page, 20)

        search_text = f" {self._t('matching_search', chat_id, search=search_string)}" if search_string else ""
        header = self._t(
            "customers_page_header",
            chat_id,
            status=status_filter,
            search=search_text,
            page=page,
            total_pages=total_pages,
        )
        message = header + "\n\n"

        for customer in page_customers:
            display_name = self._full_name(customer, chat_id)

            # Add subscriber indicator
            subscriber_indicator = "🔔" if customer.subscribed_to_offers else ""
            # Add guest indicator
            guest_indicator = "🎫" if customer.is_guest else ""
            username_part = (
                f" (@{customer.username})"
                if customer.username and not customer.is_guest
                else (f" ({customer.username})" if customer.is_guest else "")
            )
            status_emoji = self.STATUS_EMOJIS.get(customer.authorization_status, "❓")

            # Build line and clean up multiple spaces
            line = f"{status_emoji} {display_name}{username_part} {subscriber_indicator}{guest_indicator}"
            line = " ".join(line.split())  # Remove multiple spaces
            message += f"{line}\n"

        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_user_pagination_keyboard(page, total_pages, f"customers_{status_filter}")

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "success"}

    def _build_user_pagination_keyboard(self, current_page: int, total_pages: int, entity_type: str) -> dict[str, Any]:
        """Build enhanced pagination keyboard for user lists"""
        return PaginationUtils.build_pagination_keyboard(current_page, total_pages, entity_type, enhanced=True)

    def _with_button_customer(
        self, chat_id: int, customer_id: str, action: Callable[[Any], dict[str, Any]]
    ) -> dict[str, Any]:
        """Hand the customer of a button to ``action``, or tell the admin the customer is gone"""
        customer = self.db.get_customer(customer_id)
        if not customer:
            self._send_message(chat_id, self._t("user_not_found", chat_id, identifier=customer_id))
            return {"status": "user_not_found"}
        return action(customer)

    def handle_edit_user_select(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Handle user selection from ambiguity resolution buttons"""
        return self._with_button_customer(chat_id, customer_id, lambda c: self._show_user_edit_interface(c, chat_id))

    def handle_user_status_select(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Handle user selection from disambiguation for user status"""
        return self._with_button_customer(chat_id, customer_id, lambda c: self._send_user_status(chat_id, c))

    def handle_approve_user_select(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Handle user selection from disambiguation for approve user"""
        return self._with_button_customer(chat_id, customer_id, lambda c: self._approve_user_by_customer(chat_id, c))

    def handle_approve_user_by_id(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Handle user approval by customer ID (called from button callback)"""
        return self.handle_approve_user_select(chat_id, customer_id)

    def handle_reject_user_by_id(self, chat_id: int, customer_id: str) -> dict[str, Any]:
        """Handle user rejection by customer ID (called from button callback)"""
        return self._with_button_customer(chat_id, customer_id, lambda c: self._reject_customer(chat_id, c))

    def handle_create_guest(self, chat_id: int, args: list) -> dict[str, Any]:
        """Handle /create_guest command"""
        if not args:
            self._send_message(chat_id, self._t("usage_create_guest", chat_id))
            return {"status": "invalid_args"}

        first_name = args[0]
        last_name = args[1] if len(args) > 1 and not args[1].startswith("@") and "@" not in args[1] else None
        contact_info = (
            " ".join(args[2:]) if len(args) > 2 else (args[1] if len(args) > 1 and last_name is None else None)
        )

        # Validate name length
        if len(first_name) > 100:
            self._send_message(chat_id, self._t("name_too_long", chat_id, field=self._t("field_first_name", chat_id)))
            return {"status": "name_too_long"}
        if last_name and len(last_name) > 100:
            self._send_message(chat_id, self._t("name_too_long", chat_id, field=self._t("field_last_name", chat_id)))
            return {"status": "name_too_long"}

        # Get next guest number from counter
        next_number = self.db.get_next_guest_id()
        guest_id = f"GUEST_{next_number:03d}"

        # Create guest customer with dummy telegram_user_id
        guest = Customer(
            telegram_user_id=-1,  # Dummy ID for all guests
            first_name=first_name,
            last_name=last_name,
            username=guest_id,  # Store GUEST_xxx as username for identification
            authorization_status=AuthorizationStatus.APPROVED.value,
            language="nl",
            is_guest=True,
            contact_info=contact_info,
        )

        if self.db.create_customer(guest):
            display_name = f"{first_name} {last_name}" if last_name else first_name
            contact_display = f"\n{self._t('contact_label', chat_id)}: {contact_info}" if contact_info else ""
            self._send_message(
                chat_id, self._t("guest_added", chat_id, name=display_name, guest_id=guest_id, contact=contact_display)
            )
            return {"status": "success", "guest_id": guest_id}
        else:
            self._send_message(chat_id, self._t("failed_add_guest", chat_id))
            return {"status": "error"}

    def handle_list_guests(self, chat_id: int, page: int = 1) -> dict[str, Any]:
        """Handle /list_guests command with pagination"""
        all_customers = self.db.get_all_customers()
        guests = [c for c in all_customers if c.is_guest]

        if not guests:
            self._send_message(chat_id, self._t("no_guests", chat_id))
            return {"status": "no_guests"}

        # Sort by username (GUEST_xxx)
        guests.sort(key=lambda x: x.username or "")

        # Paginate results
        page_guests, total_pages = self._paginate_list(guests, page, 20)

        message = self._t("guests_page_header", chat_id, page=page, total_pages=total_pages) + "\n\n"

        for guest in page_guests:
            contact_part = f" - {guest.contact_info}" if guest.contact_info else ""
            message += f"🎫 {self._full_name(guest, chat_id)} ({guest.username}){contact_part}\n"

        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_user_pagination_keyboard(page, total_pages, "guests")

        self._send_message(chat_id, message, reply_markup=keyboard)
        return {"status": "success"}
