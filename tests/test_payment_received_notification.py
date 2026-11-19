"""The message a customer gets when the admin marks the payment as received"""

import json
from decimal import Decimal
from unittest.mock import Mock, patch

from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from models.entities import AuthorizationStatus, Customer, Order, OrderStatus

ADMIN_ID = 15005473


def test_the_pickup_location_is_escaped_in_the_html_message():
    customer = Customer(
        customer_id="c1",
        telegram_user_id=101,
        first_name="Jan",
        location="Kerkstraat 1 <achterom> & schuur",
        authorization_status=AuthorizationStatus.APPROVED.value,
    )
    db = Mock()
    db.get_customer.return_value = customer
    db.get_customer_by_telegram_id.return_value = None  # no language chosen: Dutch
    db.get_orders_by_customer.return_value = [
        Order(customer_id="c1", total_price=Decimal("5"), status=OrderStatus.AWAITING_PAYMENT.value)
    ]
    db.mark_order_paid.return_value = True
    handler = DeliveryOverviewHandler(db, ADMIN_ID, "prod", "token")
    handler._send_message = Mock(return_value={"status": "sent"})
    handler.lambda_client = Mock()

    with patch("handlers.admin.order_commands.AdminOrderCommands"):
        handler.handle_process_customer_paid(ADMIN_ID, "c1")

    (message,) = json.loads(handler.lambda_client.invoke.call_args.kwargs["Payload"])["messages"]
    assert message["parse_mode"] == "HTML"
    assert "Kerkstraat 1 &lt;achterom&gt; &amp; schuur" in message["message"]
    assert "<achterom>" not in message["message"]
