import json
import logging
import os
from typing import Any
from urllib.parse import urlsplit

from services.box_status_manager import BoxStatusManager
from services.database import DynamoDBService
from services.export_expiry import ExportExpiryService
from services.telegram_client import TelegramClient
from utils.pagination import PaginationUtils
from utils.validation import ValidationUtils

logger = logging.getLogger()


class BaseHandler:
    def __init__(self, db: DynamoDBService, admin_user_id: int, environment: str, telegram_token: str):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.telegram_token = telegram_token
        self._bot_username: str | None = None
        self._translations: dict[str, dict[str, str]] = {}
        self.validator = ValidationUtils(db, self._t)
        self.box_status_manager = BoxStatusManager(db)
        self.export_expiry = ExportExpiryService(db, self._delete_message_result)

    def _load_translations(self, lang: str) -> dict[str, str]:
        """Load translations for given language"""
        if lang in self._translations:
            return self._translations[lang]

        # Default to Dutch for most users, fallback to English
        lang_file = lang if lang in ["en", "nl"] else "nl"

        try:
            file_path = os.path.join(os.path.dirname(__file__), "..", "translations", f"{lang_file}.json")
            with open(file_path, encoding="utf-8") as f:
                self._translations[lang] = json.load(f)
                return self._translations[lang]
        except Exception as e:
            logger.error(f"Error loading translations for {lang}: {e}")
            # Fallback to English if Dutch fails
            if lang_file != "en":
                return self._load_translations("en")
            return {}

    def _t(self, key: str, user_id: int | None = None, force_group_lang: bool = False, **params) -> str:
        """Translate message key to user language"""
        # Force Dutch for group messages
        if force_group_lang:
            lang = "nl"
        else:
            # Get user language preference, default to Dutch
            lang = "nl"
            if user_id:
                customer = self.db.get_customer_by_telegram_id(user_id)
                if customer and hasattr(customer, "language") and customer.language:
                    lang = customer.language

        translations = self._load_translations(lang)
        message = translations.get(key, key)
        if not params:
            return message
        try:
            return message.format(**params)
        except (KeyError, IndexError, ValueError) as e:
            # A translation with a placeholder the caller does not pass (or a stray brace) must not break the
            # command: send the text unfilled. Only the key and the error are logged, never the parameters.
            logger.error(f"Translation {key!r} ({lang}) could not be filled in: {type(e).__name__}: {e}")
            return message

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
        """Escape HTML special characters to prevent injection"""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )

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

    def _send_error(self, chat_id: int, error_key: str, status: str, **kwargs):
        """Send error message and return status"""
        user_id = kwargs.pop("user_id", None)
        self._send_message(chat_id, self._t(error_key, user_id, **kwargs))
        return {"status": status}

    def _send_success(self, chat_id: int, success_key: str, status: str = "success", **kwargs):
        """Send success message and return status"""
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
            logger.info(f"Sending photo to chat {chat_id}: {urlsplit(photo_url).hostname}")
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

    def sync_offer_messages(self, offer_id: int, cancelled: bool = False):
        """Re-render all tracked announcement messages for an offer.

        Rebuilds the text + keyboard from the *current* offer (name/price/
        description) and its *current* status (icon/buttons), then edits the group
        announcement first (one cheap, high-priority call) and the subscriber DMs
        afterwards. Subscriber edits trickle inline for small counts and are handed
        off to the NotificationSender Lambda for large counts, mirroring the
        announce path. Pass ``cancelled=True`` from the cancel path, where the
        offer's stored status is INACTIVE but the message must show the cancelled
        marker.
        """
        offer = self.db.get_offer(offer_id)
        if not offer:
            logger.warning(f"sync_offer_messages: offer {offer_id} not found")
            return

        # Event-based export expiry: piggyback on this message update
        self.expire_exports()

        rows = self.db.get_notification_messages_by_offer(offer_id)
        group_rows = [r for r in rows if getattr(r, "kind", "group") == "group"]
        subscriber_rows = [r for r in rows if getattr(r, "kind", "group") == "subscriber"]

        # Group and subscriber messages render the same: order buttons when active,
        # none when sold out or cancelled.
        text, reply_markup = self._build_offer_message(offer, cancelled)

        # Group first: single, most-important surface, always inline.
        for row in group_rows:
            self._edit_tracked_message(row, text, reply_markup)

        if not subscriber_rows:
            return

        # Small batches inline; large batches off to the async Lambda.
        if len(subscriber_rows) <= 10:
            for row in subscriber_rows:
                self._edit_tracked_message(row, text, reply_markup)
        else:
            self._sync_subscriber_messages_async(offer_id, cancelled)

    def _build_offer_message(self, offer, cancelled: bool):
        """Build the text and reply_markup with the shared builder.

        Group messages use Dutch. The group message shows order buttons.
        """
        from services.offer_message_builder import OfferMessageBuilder

        bot_username = self._get_bot_username()
        builder = OfferMessageBuilder(bot_username, lambda key: self._t(key, force_group_lang=True))
        return builder.build(offer, cancelled=cancelled)

    def _edit_tracked_message(self, row, text, reply_markup, prune: bool = True) -> bool:
        """Edit one tracked message; prune its row if Telegram says it's gone.

        A ``None`` reply_markup means "no buttons" (sold_out/cancelled). Telegram
        leaves the existing keyboard untouched when reply_markup is omitted, so an
        explicit empty keyboard is sent to actually remove the order buttons.

        ``prune`` controls whether a "message not found" result deletes the tracking
        row. Callers without ``dynamodb:DeleteItem`` on the notifications table
        (e.g. the NotificationSender Lambda) pass ``prune=False`` and leave cleanup
        to the row's 168h TTL.
        """
        markup = reply_markup if reply_markup is not None else {"inline_keyboard": []}
        result = self._edit_message_text(row.chat_id, row.message_id, text, parse_mode="HTML", reply_markup=markup)
        if prune and result.get("not_found"):
            try:
                self.db.delete_notification_message(row.notification_id)
            except Exception as e:
                logger.error(f"Failed to prune notification row {row.notification_id}: {e}")
        return result.get("success", False)

    def _sync_subscriber_messages_async(self, offer_id: int, cancelled: bool = False):
        """Hand off large subscriber-edit batches to the NotificationSender Lambda."""
        import json
        from decimal import Decimal

        import boto3

        try:
            lambda_client = boto3.client("lambda")
            function_name = os.environ.get(
                "NOTIFICATION_LAMBDA_NAME", f"ubbc-bot-{os.environ.get('ENVIRONMENT', 'test')}-notification-sender"
            )

            class DecimalEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    return super().default(obj)

            payload = {
                "action": "sync_offer_messages",
                "offer_id": offer_id,
                "cancelled": cancelled,
                "environment": os.environ.get("ENVIRONMENT", "test"),
            }
            lambda_client.invoke(
                FunctionName=function_name,
                InvocationType="Event",
                Payload=json.dumps(payload, cls=DecimalEncoder),
            )
            logger.info(f"Async subscriber-message sync invoked for offer {offer_id}")
        except Exception as e:
            logger.error(f"Failed to invoke async subscriber-message sync for offer {offer_id}: {e}")
