"""Customer names must be escaped wherever they end up in an HTML (parse_mode=HTML) message.

A first name comes from Telegram and is chosen by the customer. With a "<" in it Telegram rejects the
whole message, and markup in it could inject formatting or a link into the group message.
"""

import re
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.order.order_cancellation import OrderCancellation
from handlers.admin.order.order_status import OrderStatusManagement
from handlers.base_handler import BaseHandler
from handlers.customer.info_commands import InfoCommands
from handlers.customer.order_commands import CustomerOrderCommands
from models.entities import Customer, Offer, OfferStatus

ADMIN_ID = 15005473
EVIL = '<b>Bob</b> <a href="https://evil.example">click</a> & "co"'
ESCAPED_FRAGMENTS = ("&lt;b&gt;Bob&lt;/b&gt;", "&lt;a href=&quot;https://evil.example&quot;&gt;", "&amp;")


def _customer(first_name=EVIL, last_name="<Zed>", username="user", is_guest=False):
    return Customer(
        customer_id="11111111-2222-3333-4444-555555555555",
        telegram_user_id=-5 if is_guest else 4242,
        username=username,
        first_name=first_name,
        last_name=last_name,
        is_guest=is_guest,
    )


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def _tags(text: str) -> list[str]:
    parser = _Tags()
    parser.feed(text)
    return parser.tags


def _assert_name_is_inert(text: str):
    """The evil name appears only as escaped text: none of its markup or its link survives.

    The message may contain markup the bot builds itself (bold labels, the offer link), so this checks
    for the injected markup, not for markup in general.
    """
    assert "<b>Bob</b>" not in text
    assert '<a href="https://evil.example">' not in text
    assert "https://evil.example" not in re.sub(r"&quot;https://evil\.example&quot;", "", text)
    for fragment in ESCAPED_FRAGMENTS:
        assert fragment in text


class TestHtmlCustomerName:
    @pytest.fixture
    def handler(self):
        return BaseHandler(Mock(), ADMIN_ID, "test", "token")

    def test_escapes_markup_and_special_characters(self, handler):
        name = handler._html_customer_name(_customer(last_name="O'Neil"))

        assert name.startswith("&lt;b&gt;Bob&lt;/b&gt;")
        assert "&quot;co&quot;" in name and "&amp;" in name and "O&#x27;Neil" in name
        assert "<" not in name and ">" not in name

    def test_joins_first_and_last_name(self, handler):
        assert handler._html_customer_name(_customer(first_name="Jan", last_name="de Vries")) == "Jan de Vries"

    def test_missing_name_parts_are_skipped_not_printed_as_none(self, handler):
        assert handler._html_customer_name(_customer(first_name="Jan", last_name=None)) == "Jan"
        assert handler._html_customer_name(_customer(first_name=None, last_name="Vries")) == "Vries"

    def test_no_name_or_no_customer_falls_back_to_unknown(self, handler):
        handler._t = Mock(return_value="Unknown")

        assert handler._html_customer_name(_customer(first_name=None, last_name=None)) == "Unknown"
        assert handler._html_customer_name(None) == "Unknown"


class TestGroupOrderNotification:
    @pytest.fixture
    def handler(self):
        handler = CustomerOrderCommands(Mock(), ADMIN_ID, "test", "token")
        handler._get_bot_username = Mock(return_value="ubbc_bot")
        handler.db.get_offer.return_value = Offer(offer_id=7, name="Pils & Co", status=OfferStatus.ACTIVE.value)
        handler.db.get_boxes_by_offer.return_value = []
        handler.box_status_manager = Mock(get_available_capacity_for_orders=Mock(return_value=3))
        return handler

    def test_public_name_is_escaped(self, handler):
        name = handler._get_public_name(_customer())

        assert name.startswith("&lt;b&gt;Bob&lt;/b&gt;")
        assert name.endswith("&lt;")  # the last name initial "<"
        assert "<" not in name

    def test_username_fallback_is_escaped_too(self, handler):
        name = handler._get_public_name(_customer(first_name=None, last_name=None, username="<u>x"))

        assert name == "&lt;u&gt;x"

    def test_the_group_message_contains_no_markup_from_the_name(self, handler):
        message = handler._build_order_notification_message(_customer(), Offer(offer_id=7, name="Pils & Co"), 2)

        assert message is not None
        _assert_name_is_inert(message)
        assert _tags(message) == ["a"]  # only the offer link the bot itself builds

    def test_the_offer_name_is_still_escaped(self, handler):
        message = handler._build_order_notification_message(_customer(), Offer(offer_id=7, name="Pils & Co"), 2)

        assert "Pils &amp; Co" in message

    def test_group_and_admin_both_receive_the_escaped_message(self, handler):
        handler._send_message = Mock(return_value={"success": True})
        handler._send_order_notification_to_group = Mock()
        order = SimpleNamespace(order_id="abcdefgh-1", total_price=5, status="pending")
        offer = Offer(offer_id=7, name="Pils & Co")

        handler._send_order_confirmation(1, 4242, order, offer, 2, False, _customer())

        group_message = handler._send_order_notification_to_group.call_args.args[0]
        admin_calls = [c for c in handler._send_message.call_args_list if c.args[0] == ADMIN_ID]
        assert len(admin_calls) == 1 and admin_calls[0].kwargs["parse_mode"] == "HTML"
        for message in (group_message, admin_calls[0].args[1]):
            _assert_name_is_inert(message)


class TestDeliveryOverviewAdminMessages:
    @pytest.fixture
    def handler(self):
        handler = DeliveryOverviewHandler(Mock(), ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        handler._aggregate_order_lines = Mock(return_value=[("Pils", 7, 2, 5)])
        return handler

    def test_a_successful_overview_is_sent_as_html_with_an_escaped_name(self, handler):
        handler._send_admin_notification(_customer(), [], [], "MSG", True, "plain name", 5)

        call = handler._send_message.call_args
        assert call.kwargs["parse_mode"] == "HTML"
        _assert_name_is_inert(call.args[1])

    def test_a_guest_overview_is_escaped_too(self, handler):
        handler._send_admin_notification(_customer(is_guest=True), [], [], "MSG", True, "plain name", 5)

        call = handler._send_message.call_args
        assert call.kwargs["parse_mode"] == "HTML"
        _assert_name_is_inert(call.args[1])

    def test_a_failed_overview_is_plain_text_and_keeps_the_real_name(self, handler):
        handler._send_admin_notification(_customer(), [], [], "MSG", False, "Bob <Zed>", 5)

        call = handler._send_message.call_args
        assert "parse_mode" not in call.kwargs  # plain text: escaping here would show "&lt;" literally
        assert "Bob <Zed>" in call.args[1] and "&lt;" not in call.args[1]

    def test_the_guest_payload_sent_via_the_message_sender_is_escaped(self, handler):
        guest = _customer(is_guest=True)
        handler.db.get_customer.return_value = guest
        handler.db.get_order.return_value = None
        handler._build_delivery_message = Mock(return_value="MSG")
        data = {"customer_id": guest.customer_id, "delivered_order_ids": [], "delayed_order_ids": []}

        payload = handler._build_delivery_message_payload(data, "https://pay.example")

        assert payload["parse_mode"] == "HTML"
        _assert_name_is_inert(payload["message"])
        # The plain name travels separately for the (plain text) failure report
        assert payload["customer_name"] == f"{guest.first_name} {guest.last_name}"


class TestPaymentReminderToGuest:
    def test_the_admin_copy_for_a_guest_is_escaped(self):
        guest = _customer(is_guest=True)
        db = Mock()
        db.get_customer.return_value = guest
        db.get_orders_by_customer.return_value = [SimpleNamespace(status="awaiting_payment")]
        db.get_payment_link.return_value = "https://pay.example"
        handler = OrderStatusManagement(db, ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        handler.handle_send_payment_reminder = Mock(return_value={"status": "customers_shown"})

        with patch.object(OrderStatusManagement, "_build_delivery_message", return_value="MSG"):
            handler.handle_send_payment_reminder_to_customer(1, guest.customer_id)

        admin_call = next(c for c in handler._send_message.call_args_list if c.args[0] == ADMIN_ID)
        assert admin_call.kwargs["parse_mode"] == "HTML"
        _assert_name_is_inert(admin_call.args[1])


class TestCancelConfirmation:
    def test_the_customer_name_in_the_html_confirmation_is_escaped(self):
        db = Mock()
        db.get_box.return_value = SimpleNamespace(current_quantity=1, max_capacity=12, status="open")
        db.get_offer.return_value = Offer(offer_id=7, name="Pils")
        handler = OrderCancellation(db, ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        order = SimpleNamespace(
            order_id="abc-1",
            box_id="box-1",
            offer_id=7,
            quantity=2,
            total_price=5,
            status="pending",
            created_at="2026-01-01T10:00:00+00:00",
        )

        handler._show_enhanced_cancel_confirmation(1, order, _customer(), "partial ID 'abc'")

        call = handler._send_message.call_args
        assert call.kwargs["parse_mode"] == "HTML"
        _assert_name_is_inert(call.args[1])

    def test_a_customer_without_a_name_shows_unknown_not_none(self):
        db = Mock()
        db.get_box.return_value = SimpleNamespace(current_quantity=1, max_capacity=12, status="open")
        db.get_offer.return_value = Offer(offer_id=7, name="Pils")
        handler = OrderCancellation(db, ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        order = SimpleNamespace(
            order_id="abc-1",
            box_id="box-1",
            offer_id=7,
            quantity=2,
            total_price=5,
            status="pending",
            created_at="2026-01-01T10:00:00+00:00",
        )

        handler._show_enhanced_cancel_confirmation(1, order, _customer(first_name=None, last_name=None), "x")

        assert "None" not in handler._send_message.call_args.args[1]


class TestFomoForAnotherCustomer:
    @pytest.fixture
    def handler(self):
        db = Mock()
        db.list_offers.return_value = [Offer(offer_id=7, name="Pils", status=OfferStatus.ACTIVE.value)]
        db.get_orders_by_customer.return_value = []
        handler = InfoCommands(db, ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        handler._format_offer_line = Mock(return_value="• Pils\n")
        return handler

    def test_the_html_header_escapes_the_name(self, handler):
        handler.show_fomo(1, ADMIN_ID, _customer())

        call = handler._send_message.call_args
        assert call.kwargs["parse_mode"] == "HTML"
        _assert_name_is_inert(call.args[1])

    def test_the_plain_nothing_to_order_message_keeps_the_real_name(self, handler):
        handler.db.list_offers.return_value = []

        handler.show_fomo(1, ADMIN_ID, _customer(first_name="Bob", last_name="<Zed>"))

        call = handler._send_message.call_args
        assert "parse_mode" not in call.kwargs
        assert "Bob <Zed>" in call.args[1]
