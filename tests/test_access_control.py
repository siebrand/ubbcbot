#!/usr/bin/env python3
"""
Access control tests: webhook authenticity, admin-only edit replies and
order authorization outside the command router.
"""

import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from unittest.mock import Mock, patch

import pytest

import handlers.webhook as webhook
from handlers.customer.order_commands import CustomerOrderCommands
from models.entities import OfferStatus
from services.bot_service import BotService

ADMIN_ID = 15005473
SECRET = "a" * 64


class TestWebhookSecretToken:
    """The webhook must only process requests carrying Telegram's secret token"""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        webhook._cached_webhook_secret = None
        yield
        webhook._cached_webhook_secret = None

    def _event(self, headers=None):
        return {"headers": headers, "body": json.dumps({"update_id": 1})}

    @pytest.mark.parametrize(
        "headers",
        [
            None,
            {},
            {"X-Telegram-Bot-Api-Secret-Token": "wrong"},
            {"X-Telegram-Bot-Api-Secret-Token": ""},
        ],
    )
    def test_rejects_missing_or_invalid_token(self, headers):
        with (
            patch.object(webhook, "_get_webhook_secret", return_value=SECRET),
            patch.object(webhook, "BotService") as bot_service,
        ):
            response = webhook.handler(self._event(headers), None)

        assert response["statusCode"] == 403
        bot_service.assert_not_called()

    @pytest.mark.parametrize(
        "header_name",
        [
            "X-Telegram-Bot-Api-Secret-Token",
            "x-telegram-bot-api-secret-token",
        ],
    )
    def test_accepts_valid_token_case_insensitive(self, header_name):
        with (
            patch.object(webhook, "_get_webhook_secret", return_value=SECRET),
            patch.object(webhook, "BotService") as bot_service,
        ):
            response = webhook.handler(self._event({header_name: SECRET}), None)

        assert response["statusCode"] == 200
        bot_service.get_instance.return_value.process_update.assert_called_once_with({"update_id": 1})

    def test_fails_closed_when_secret_unavailable(self):
        """If the secret cannot be loaded, nothing is processed (even an empty header)"""
        with (
            patch.object(webhook, "_get_webhook_secret", return_value=None),
            patch.object(webhook, "BotService") as bot_service,
        ):
            response = webhook.handler(self._event({"X-Telegram-Bot-Api-Secret-Token": ""}), None)

        assert response["statusCode"] == 403
        bot_service.assert_not_called()


class TestEditReplyAccess:
    """Edit contexts belong to admin flows; other users' replies must not consume them"""

    @pytest.fixture
    def bot_service(self):
        service = BotService.__new__(BotService)
        service.db = Mock()
        service.db.get_edit_context_by_chat_id.return_value = Mock(edit_type="cancel_order_reason", entity_id="order1")
        service.admin_user_id = ADMIN_ID
        service.environment = "test"
        service.command_router = Mock()
        service.media_handler = Mock()
        service._register_customer_if_needed = Mock()
        service._handle_edit_reply = Mock(return_value={"status": "handled"})
        return service

    def _message(self, user_id, chat_id=-100123, text="reply text"):
        return {
            "message": {
                "message_id": 1,
                "chat": {"id": chat_id},
                "from": {"id": user_id, "first_name": "Test"},
                "text": text,
            }
        }

    def test_non_admin_reply_ignored(self, bot_service):
        result = bot_service.process_update(self._message(user_id=12345))

        assert result == {"status": "processed"}
        bot_service._handle_edit_reply.assert_not_called()
        bot_service.db.get_edit_context_by_chat_id.assert_not_called()

    def test_admin_reply_handled(self, bot_service):
        result = bot_service.process_update(self._message(user_id=ADMIN_ID))

        assert result == {"status": "handled"}
        bot_service._handle_edit_reply.assert_called_once()


class TestUpdateDeduplication:
    """A re-delivered update_id must be processed at most once (idempotency)"""

    def _service(self):
        service = BotService.__new__(BotService)
        service.db = Mock()
        service.admin_user_id = ADMIN_ID
        service.environment = "test"
        service.command_router = Mock()
        service.callback_handler = Mock()
        service._register_customer_if_needed = Mock()
        return service

    def test_first_delivery_processed(self):
        service = self._service()
        service.db.mark_update_processed.return_value = True  # first time

        result = service.process_update({"update_id": 42, "callback_query": {"x": 1}})

        service.db.mark_update_processed.assert_called_once_with(42)
        service.callback_handler.handle_callback_query.assert_called_once()
        assert result != {"status": "duplicate"}

    def test_redelivered_update_skipped(self):
        service = self._service()
        service.db.mark_update_processed.return_value = False  # already seen

        result = service.process_update({"update_id": 42, "callback_query": {"x": 1}})

        assert result == {"status": "duplicate"}
        service.callback_handler.handle_callback_query.assert_not_called()

    def test_missing_update_id_not_deduplicated(self):
        service = self._service()

        service.process_update({"callback_query": {"x": 1}})

        # No update_id -> dedup store is not touched, update still handled
        service.db.mark_update_processed.assert_not_called()
        service.callback_handler.handle_callback_query.assert_called_once()


class TestOrderAuthorization:
    """handle_create_order must enforce approval regardless of entry point"""

    @pytest.fixture
    def handler(self):
        db = Mock()
        db.get_offer.return_value = Mock(offer_id=1, name="Beer", status=OfferStatus.ACTIVE.value)
        h = CustomerOrderCommands(db, ADMIN_ID, "test", "test_token")
        h._send_message = Mock(return_value={"success": True})
        h.execute_order = Mock(return_value={"status": "success"})
        h._check_order_limits = Mock(return_value=True)
        h._has_duplicate_orders = Mock(return_value=False)
        return h

    @pytest.mark.parametrize("status", ["unauthorized", "rejected"])
    def test_unapproved_customer_cannot_order(self, handler, status):
        handler.db.get_customer_by_telegram_id.return_value = Mock(
            customer_id="c1", authorization_status=status, language="nl"
        )

        result = handler.handle_create_order(-100123, 12345, ["1", "2"])

        assert result == {"status": "validation_failed"}
        handler.execute_order.assert_not_called()

    def test_approved_customer_can_order(self, handler):
        handler.db.get_customer_by_telegram_id.return_value = Mock(
            customer_id="c1", authorization_status="approved", language="nl"
        )

        result = handler.handle_create_order(-100123, 12345, ["1", "2"])

        assert result == {"status": "success"}
        handler.execute_order.assert_called_once()

    def test_admin_can_order_without_approved_record(self, handler):
        handler.db.get_customer_by_telegram_id.return_value = Mock(
            customer_id="c1", authorization_status="unauthorized", language="nl"
        )

        result = handler.handle_create_order(ADMIN_ID, ADMIN_ID, ["1", "2"])

        assert result == {"status": "success"}
