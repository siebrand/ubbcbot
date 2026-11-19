"""Admin screens are in the admin's language, customer messages in the customer's (audit 4, B7)"""

import json
from decimal import Decimal
from unittest.mock import Mock

import pytest

from handlers.admin.credit_commands import CreditCommands
from handlers.admin.import_handler import ImportHandler
from handlers.admin.labeling_completion_handler import LabelingCompletionHandler
from handlers.admin.test_commands import TestCommands as AdminTestCommands  # not a test class
from models.entities import Box, Customer, Offer, OfferStatus, Order, OrderStatus

ADMIN_ID = 15005473
CUSTOMER = Customer(customer_id="c1", telegram_user_id=101, first_name="Jan", language="nl")
GUEST = Customer(customer_id="g1", telegram_user_id=-2, first_name="Gast", is_guest=True)
BOX_ID = "abcdef12-0000-4000-8000-000000000000"


@pytest.fixture
def db():
    """The admin reads English; the customer Dutch"""
    db = Mock()
    admin = Customer(customer_id="a1", telegram_user_id=ADMIN_ID, language="en")
    db.get_customer_by_telegram_id.side_effect = lambda tid: {ADMIN_ID: admin, 101: CUSTOMER}.get(tid)
    return db


def sent(handler) -> list[tuple[int, str]]:
    return [(c.args[0], c.args[1]) for c in handler._send_message.call_args_list]


def build(cls, db):
    handler = cls(db, ADMIN_ID, "test", "token")
    handler._send_message = Mock(return_value={"success": True})
    return handler


class TestLabeling:
    def test_the_labeling_screens_are_in_the_admin_language(self, db):
        db.get_boxes_by_offer_with_ready_orders.side_effect = [[Box(box_id=BOX_ID, offer_id=7)], []]
        db.get_orders_by_box.return_value = [Order(box_id=BOX_ID, status=OrderStatus.READY_FOR_LABELING.value)]
        db.update_order.return_value = True
        db.get_offer.return_value = Offer(offer_id=7, status=OfferStatus.ACTIVE.value)
        handler = build(LabelingCompletionHandler, db)

        handler.handle_labeling_action(ADMIN_ID, "complete", BOX_ID[:8], 7, "sup12345")

        (_, text), keyboard = sent(handler)[0], handler._send_message.call_args.kwargs["reply_markup"]
        assert text == handler._t("labeling_completed_success", ADMIN_ID, box_id=BOX_ID[:8], updated_count=1)
        assert text.startswith("✅ Labeling completed")
        assert keyboard["inline_keyboard"][0][0]["text"] == handler._t("back_to_offers", ADMIN_ID)

    def test_the_labeling_buttons_are_in_the_admin_language(self, db):
        handler = build(LabelingCompletionHandler, db)

        keyboard = handler._build_labeling_keyboard(BOX_ID, 7, "sup12345")

        assert keyboard["inline_keyboard"][0][0]["text"] == handler._t("complete_labeling_btn", ADMIN_ID)
        assert handler._t("complete_labeling_btn", ADMIN_ID) != handler._t("complete_labeling_btn", 101)


class TestCredit:
    def _issue(self, db, customer, reason):
        handler = build(CreditCommands, db)
        handler.credit_service = Mock()
        handler.credit_service.issue_credit.return_value = True
        handler.credit_service.get_customer_credit_balance.return_value = Decimal("5")
        handler._issue_credit_to_customer(ADMIN_ID, customer, Decimal("5"), reason)
        return handler

    def test_a_credit_without_reason_tells_the_customer_so_in_their_language(self, db):
        handler = self._issue(db, CUSTOMER, "")

        (chat, text), _ = sent(handler)
        assert chat == 101
        assert handler._t("credit_no_reason", 101) in text
        assert handler._t("credit_no_reason", 101) != handler._t("credit_no_reason", ADMIN_ID)

    def test_a_guest_gets_no_message(self, db):
        handler = self._issue(db, GUEST, "")

        assert [chat for chat, _ in sent(handler)] == [ADMIN_ID]


class TestTestCommands:
    @pytest.mark.parametrize(
        ("body", "key", "params"),
        [
            ({"success_count": 1}, "test_user_message_sent", {"telegram_id": 555}),
            ({"success_count": 0, "results": [{"error": "Blocked"}]}, "test_user_message_failed", {"error": "Blocked"}),
        ],
    )
    def test_the_outcome_is_in_the_admin_language(self, db, body, key, params):
        db.get_customers_by_status.return_value = []
        handler = build(AdminTestCommands, db)
        handler.lambda_client = Mock()
        handler.lambda_client.invoke.return_value = {
            "Payload": Mock(read=Mock(return_value=json.dumps({"body": json.dumps(body)})))
        }

        handler.handle_test_user_message(ADMIN_ID, ["555", "Hoi"])

        assert sent(handler)[-1] == (ADMIN_ID, handler._t(key, ADMIN_ID, **params))


class TestImport:
    def test_the_finalize_list_is_in_the_admin_language(self, db):
        db.list_offers.return_value = [Offer(offer_id=7, name="Pils", status=OfferStatus.IMPORT.value)]
        db.get_orders_by_offer.return_value = [Order(status=OrderStatus.PENDING.value)]
        handler = build(ImportHandler, db)

        handler._show_import_offers_selection(ADMIN_ID)

        assert handler._t("import_offer_line", ADMIN_ID, offer_id=7, name="Pils", count=1) in sent(handler)[0][1]
        assert "(1 orders)" in sent(handler)[0][1]
