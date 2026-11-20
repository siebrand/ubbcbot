import html
import logging
from typing import Any

from services.box_status_manager import BoxStatusManager
from services.database import DynamoDBService
from services.export_expiry import ExportExpiryService
from services.offer_message_sync import OfferAnnouncements
from services.telegram_client import TelegramClient
from services.translator import Translator, load_translations
from utils.pagination import PaginationUtils
from utils.s3_url import _s3_host
from utils.validation import ValidationUtils

logger = logging.getLogger()


class BaseHandler:
    def __init__(self, db: DynamoDBService, admin_user_id: int, environment: str, telegram_token: str):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.telegram_token = telegram_token
        self._bot_username: str | None = None
        self.validator = ValidationUtils(db, self._t)
        self.box_status_manager = BoxStatusManager(db)
        self.export_expiry = ExportExpiryService(db, self._delete_message_result)

    @property
    def translator(self) -> Translator:
        """Texts in the user's language. Built on use; the translation files are cached per container."""
        return Translator(self.db)

    @staticmethod
    def _load_translations(lang: str) -> dict[str, str]:
        """All texts of a language (see services/translator.py)"""
        return load_translations(lang)

    def _t(self, key: str, user_id: int | None = None, force_group_lang: bool = False, **params) -> str:
        """Translate message key to user language"""
        return self.translator.translate(key, user_id, force_group_lang, **params)

    def _message_sender_event(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """The event for the MessageSender Lambda, which has no database: it gets the admin's language with it"""
        return {
            "messages": messages,
            "environment": self.environment,
            "admin_language": self.translator.language(self.admin_user_id),
        }

    def _get_bot_username(self) -> str:
        """Get bot username from Telegram API"""
        if self._bot_username:
            return self._bot_username

        response = self.telegram.call("getMe", get=True)
        if response.ok and isinstance(response.result, dict) and response.result.get("username"):
            self._bot_username = response.result["username"]
            return self._bot_username

        # Fallback based on environment
        return "ubbc_test_bot" if self.environment == "test" else "ubbc_bot"

    @property
    def telegram(self) -> TelegramClient:
        """The Bot API transport. Built on use, so it always has the current token."""
        return TelegramClient(self.telegram_token)

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters to prevent injection (also quotes, for attribute values)"""
        return html.escape(text) if text else ""

    def _html_customer_name(self, customer) -> str:
        """Full name of a customer, escaped for use in an HTML message (parse_mode HTML).

        Names come from Telegram or from the admin, so they must never reach an HTML message raw: a
        "<" makes Telegram reject the whole message and markup in a name could inject formatting or
        links. Falls back to the localized "Unknown" when the customer has no name.
        """
        name = " ".join(part for part in (customer.first_name, customer.last_name) if part) if customer else ""
        return self._escape_html(name) if name else self._t("unknown", user_id=None)

    def _get_public_name(self, customer):
        """Customer's public display name (Firstname L), escaped for HTML.

        The format of the group order notification, also used in reports: never the full last name.
        """
        name_parts = []
        if customer.first_name:
            name_parts.append(customer.first_name)
        if customer.last_name:
            name_parts.append(f"{customer.last_name[0]}")

        name = " ".join(name_parts) if name_parts else customer.username or self._t("unknown", user_id=None)
        return self._escape_html(name)

    def _send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict | None = None,
        force_group: bool = False,
    ) -> dict:
        """Send message to Telegram chat and return response with message_id"""

        # Skip sending to guest users (they don't have Telegram)
        if chat_id == -1:
            logger.info("Skipping message to guest user")
            return {"success": False, "skipped_guest": True}

        if self.environment == "test":
            text = f"TEST - {text}"

        # In production, redirect to PM unless explicitly for group
        if self.environment == "prod" and chat_id < 0 and not force_group:
            # This is a group chat in production - we need user_id to send PM
            # For now, just log and don't send (caller should handle PM sending)
            logger.info(f"Production group message blocked: chat_id={chat_id}, text_length={len(text)}")
            return {"success": False}

        data: dict[str, Any] = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = reply_markup

        logger.info(f"Sending message: chat_id={chat_id}, force_group={force_group}, text_length={len(text)}")
        response = self.telegram.call("sendMessage", data)
        if self.environment == "test":
            logger.info(f"Telegram API response: {response.status_code}")

        if response.ok:
            return {"success": True, "message_id": response.message_id}
        if response.status_code is not None:
            logger.error(f"Sending message failed: status {response.status_code}, response {response.body}")
        return {"success": False}

    def _notify_customer(self, customer, key: str, parse_mode: str | None = None, **params) -> dict:
        """A personal message to a customer, in their own language. Guests have no Telegram and get nothing."""
        if not customer or customer.is_guest or not customer.telegram_user_id or customer.telegram_user_id < 0:
            return {"success": False, "skipped_guest": True}
        text = self._t(key, customer.telegram_user_id, **params)
        return self._send_message(customer.telegram_user_id, text, parse_mode=parse_mode)

    def _delete_message(self, chat_id: int, message_id: int) -> bool:
        """Delete message from Telegram chat"""
        return self.telegram.call("deleteMessage", {"chat_id": chat_id, "message_id": message_id}).ok

    def _delete_message_result(self, chat_id: int, message_id: int) -> dict:
        """Delete a message and report why it failed.

        Returns ``success`` when Telegram deleted it. ``gone`` is True when retrying cannot help:
        the message no longer exists, the chat is unknown, or it is too old to delete (48 hours).
        Anything else (network error, 5xx, rate limit) is neither, so the caller may retry later.
        """
        response = self.telegram.call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        if response.ok:
            return {"success": True, "gone": False}

        gone = response.status_code == 400 and response.says(
            "message to delete not found", "message can't be deleted", "chat not found"
        )
        if not gone and response.status_code is not None:
            logger.error(f"Failed to delete message: status {response.status_code}")
        return {"success": False, "gone": gone}

    def expire_exports(self, force: bool = False) -> None:
        """Delete exported files that have passed their expiry. Never raises.

        Called from events that already happen (offer publish, message sync, admin updates, a new
        export) instead of from a schedule. See services/export_expiry.py.
        """
        try:
            self.export_expiry.sweep(force=force)
        except Exception as e:
            logger.error(f"Error expiring exports: {e}")

    def _set_message_reaction(self, chat_id: int, message_id: int, emoji: str = "👍") -> bool:
        """Set an emoji reaction on a Telegram message (e.g. 👍). Returns success."""
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [{"type": "emoji", "emoji": emoji}],
        }
        response = self.telegram.call("setMessageReaction", data)
        if not response.ok and response.status_code is not None:
            logger.error(f"Failed to set reaction: status {response.status_code}, response {response.body}")
        return response.ok

    def _edit_message_text(
        self, chat_id: int, message_id: int, text: str, parse_mode: str | None = None, reply_markup: dict | None = None
    ) -> dict:
        """Edit the text (and optionally inline keyboard) of an existing message.

        Returns a dict with:
          - ``success``: True when Telegram accepted the edit.
          - ``not_found``: True when Telegram reports the message no longer exists
            (so the caller can prune its tracking row).

        ``reply_markup`` is only sent when provided; omitting it removes the inline
        keyboard (used to drop the order buttons on sold_out/cancelled).
        """
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup is not None:
            data["reply_markup"] = reply_markup

        response = self.telegram.call("editMessageText", data)
        # Telegram returns 400 with these descriptions when the message is gone
        # or unchanged. "message is not modified" is harmless (idempotent edit).
        if response.ok or response.says("message is not modified"):
            return {"success": True, "not_found": False}
        not_found = response.says("message to edit not found", "message can't be edited", "chat not found")
        if not not_found and response.status_code is not None:
            logger.error(f"Failed to edit message: status {response.status_code}, response {response.body}")
        return {"success": False, "not_found": not_found}

    def _send_message_simple(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict | None = None,
        force_group: bool = False,
    ) -> bool:
        """Send message and return simple boolean for backward compatibility"""
        result = self._send_message(chat_id, text, parse_mode, reply_markup, force_group)
        return result.get("success", False)

    def _send_document(self, chat_id: int, content: str, filename: str, caption: str | None = None) -> bool:
        """Send document to Telegram chat"""
        return self._send_document_message(chat_id, content, filename, caption)["success"]

    def _send_document_message(
        self,
        chat_id: int,
        content: str | bytes,
        filename: str,
        caption: str | None = None,
        mime_type: str = "text/csv",
    ) -> dict:
        """Send a document and return ``success`` plus the ``message_id`` Telegram assigned to it"""
        from io import BytesIO

        if self.environment == "test" and caption:
            caption = f"TEST - {caption}"

        # Text is sent as UTF-8, binary content (a zip) as is
        file_data = BytesIO(content.encode("utf-8") if isinstance(content, str) else content)
        files = {"document": (filename, file_data, mime_type)}

        data: dict[str, Any] = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption

        if self.environment == "test":
            logger.info(f"Sending document to chat {chat_id}: {filename}")
        response = self.telegram.call("sendDocument", data, files=files)
        if self.environment == "test":
            logger.info(f"Telegram API response: {response.status_code}")
        if not response.ok or response.message_id is None:
            return {"success": False}
        return {"success": True, "message_id": response.message_id}

    def _build_pagination_keyboard(
        self, current_page: int, total_pages: int, entity_type: str, filters: str = "", enhanced: bool = False
    ) -> dict[str, Any]:
        """Build pagination keyboard for list commands"""
        return PaginationUtils.build_pagination_keyboard(current_page, total_pages, entity_type, filters, enhanced)

    def _build_admin_menu_keyboard(self) -> dict[str, Any]:
        """Build keyboard with button to return to admin menu"""
        return {"inline_keyboard": [[{"text": self._t("admin_menu", user_id=None), "callback_data": "admin:main"}]]}

    def _paginate_list(self, items: list, page: int, page_size: int = 10) -> tuple:
        """Paginate a list of items"""
        return PaginationUtils.paginate_list(items, page, page_size)

    def _validate_and_get_offer(self, args: list, chat_id: int):
        """Validate offer ID and return offer or send error"""
        offer, error = self.validator.validate_and_get_offer(args)
        if error and "message" in error:
            self._send_message(chat_id, error["message"])
        return offer, error

    def _validate_and_get_customer(self, args: list, chat_id: int):
        """Validate customer ID and return customer or send error"""
        customer, error = self.validator.validate_and_get_customer(args)
        if error and "message" in error:
            self._send_message(chat_id, error["message"])
        return customer, error

    def _parse_int_arg(self, arg: str, error_key: str, chat_id: int):
        """Parse integer argument or send error"""
        try:
            return int(arg), None
        except ValueError:
            self._send_message(chat_id, self._t(error_key))
            return None, {"status": "invalid_format"}

    def _validate_args(self, args: list, min_count: int, usage_key: str, chat_id: int):
        """Validate minimum argument count or send usage message"""
        if len(args) < min_count:
            self._send_message(chat_id, self._t(usage_key))
            return {"status": "invalid_args"}
        return None

    def _send_error(self, chat_id: int, error_key: str, status: str, /, **kwargs):
        """Send error message and return status. Positional-only, so a text can have a {status} of its own."""
        user_id = kwargs.pop("user_id", None)
        self._send_message(chat_id, self._t(error_key, user_id, **kwargs))
        return {"status": status}

    def _send_success(self, chat_id: int, success_key: str, status: str = "success", /, **kwargs):
        """Send success message and return status. Positional-only, so a text can have a {status} of its own."""
        user_id = kwargs.pop("user_id", None)
        self._send_message(chat_id, self._t(success_key, user_id, **kwargs))
        return {"status": status}

    def _send_photo(self, chat_id: int, photo_url: str, caption: str | None = None, force_group: bool = False) -> dict:
        """Send photo to Telegram chat"""
        # Skip sending to guest users (they don't have Telegram)
        if chat_id == -1:
            logger.info("Skipping photo to guest user")
            return {"success": False, "skipped_guest": True}

        if self.environment == "test" and caption:
            caption = f"TEST - {caption}"

        # In production, redirect to PM unless explicitly for group
        if self.environment == "prod" and chat_id < 0 and not force_group:
            logger.info("Production group photo blocked")
            return {"success": False}

        data: dict[str, Any] = {"chat_id": chat_id, "photo": photo_url}
        if caption:
            data["caption"] = caption

        if self.environment == "test":
            # Not the URL itself: a presigned S3 URL carries a signature that grants access to the image
            logger.info(f"Sending photo to chat {chat_id}: {_s3_host(photo_url)}")
        response = self.telegram.call("sendPhoto", data)
        if self.environment == "test":
            logger.info(f"Telegram API response: {response.status_code}")

        if response.ok:
            return {"success": True, "message_id": response.message_id}
        return {"success": False}

    def _send_media_group(self, chat_id: int, media_group: list, force_group: bool = False) -> dict:
        """Send media group to Telegram chat"""
        # Skip sending to guest users (they don't have Telegram)
        if chat_id == -1:
            logger.info("Skipping media group to guest user")
            return {"success": False, "skipped_guest": True}

        # In production, redirect to PM unless explicitly for group
        if self.environment == "prod" and chat_id < 0 and not force_group:
            logger.info("Production group media group blocked")
            return {"success": False}

        if self.environment == "test":
            logger.info(f"Sending media group to chat {chat_id}: {len(media_group)} items")
        response = self.telegram.call("sendMediaGroup", {"chat_id": chat_id, "media": media_group})
        if self.environment == "test":
            logger.info(f"Telegram API response: {response.status_code}")

        if response.ok and isinstance(response.result, list):
            return {"success": True, "message_ids": [message["message_id"] for message in response.result]}
        return {"success": False}

    def _format_customer_candidates(self, matches: list, limit: int = 5) -> str:
        """'Name (@username, 1a2b3c4d), ...': enough to tell similar customers apart and to type the ID prefix"""
        described = []
        for customer in matches[:limit]:
            name = " ".join(part for part in (customer.first_name, customer.last_name) if part)
            described.append(f"{name} (@{customer.username}, {str(customer.customer_id)[:8]})")
        candidates = ", ".join(described)
        return candidates + ", …" if len(matches) > limit else candidates

    def _find_customer_with_disambiguation(
        self, identifier: str, chat_id: int, callback_prefix: str, status_filter: str | None = None
    ):
        """Find customer with disambiguation UI if multiple matches"""
        customer, error = self.validator.find_customer_with_disambiguation(
            identifier, chat_id, callback_prefix, status_filter
        )

        if error:
            if error["status"] == "user_not_found":
                keyboard = error.get("keyboard")
                self._send_message(chat_id, error["message"], reply_markup=keyboard)
                return None, error
            elif error["status"] == "disambiguation_shown":
                self._send_message(chat_id, error["message"], reply_markup=error["keyboard"])
                return None, error

        return customer, None

    def _check_offer_status_after_change(self, offer_id: int):
        """Recompute the offer's status from box states and, if it changed, sync
        the channel/subscriber announcement messages so they reflect the new
        sold_out/active state (icon + order buttons)."""
        new_status = self.box_status_manager.update_offer_status_after_change(offer_id)
        if new_status is not None:
            self.sync_offer_messages(offer_id)

    def _execute_cancel(self, order, box, chat_id: int, reason: str = "Manual cancellation") -> dict[str, Any]:
        """Cancel an order as the admin: the box gets the units back, the customer is told, the admin sees the box"""
        if not self.db.cancel_order(order.order_id, self.admin_user_id, reason):
            self._send_message(chat_id, self._t("failed_cancel_order", chat_id))
            return {"status": "error"}

        if not self.box_status_manager.update_box_after_order_cancellation(box.box_id, order.quantity):
            logger.error(f"Failed to update box {box.box_id} after cancellation")
        self._check_offer_status_after_change(order.offer_id)

        offer = self.db.get_offer(order.offer_id)
        self._notify_customer(
            self.db.get_customer(order.customer_id),
            "order_cancelled_by_admin",
            name=offer.name if offer else self._t("unknown", chat_id),
            quantity=order.quantity,
            total=float(order.total_price),
            reason=reason,
        )

        box = self.db.get_box(order.box_id)
        admin_message = self._t(
            "order_cancelled_success",
            chat_id,
            order_id=order.order_id,
            new_quantity=box.current_quantity if box else 0,
            max_capacity=box.max_capacity if box else 0,
        )
        self._send_message(chat_id, admin_message)
        return {"status": "success"}

    @property
    def announcements(self) -> OfferAnnouncements:
        """The tracked announcement messages of offers. Built on use, with this handler's Telegram and translations."""
        return OfferAnnouncements(
            self.db,
            self._edit_message_text,
            lambda key: self._t(key, force_group_lang=True),
            self._get_bot_username,
            self.environment,
        )

    def sync_offer_messages(self, offer_id: int, cancelled: bool = False):
        """Re-render all tracked announcement messages of an offer (see services/offer_message_sync.py).

        Pass ``cancelled=True`` from the cancel path, where the offer's stored status is INACTIVE but the message must
        show the cancelled marker.
        """
        offer = self.db.get_offer(offer_id)
        if not offer:
            logger.warning(f"sync_offer_messages: offer {offer_id} not found")
            return

        # Event-based export expiry: piggyback on this message update
        self.expire_exports()
        self.announcements.sync(offer, cancelled)
