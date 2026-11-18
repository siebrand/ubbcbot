"""Personal data export: /my_data (webhook side), the DataExporter Lambda and the zip contents."""

import io
import json
import time
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

import data_exporter
from handlers.customer.data_export_commands import DataExportCommands
from models.entities import (
    AuthorizationStatus,
    CreditTransaction,
    Customer,
    CustomerCredit,
    Offer,
    Order,
    OrderHistory,
    OrderStatus,
)
from repositories.credit_repository import CreditRepository
from repositories.order_history_repository import OrderHistoryRepository
from repositories.order_repository import OrderRepository
from services.command_router import CommandRouter
from services.data_export import DATA_EXPORT_MIN_INTERVAL_SECONDS, DataExportService
from services.database import DynamoDBService
from services.export_expiry import EXPORT_KIND, EXPORT_LIFETIME_SECONDS, EXPORT_OFFER_ID, ExportExpiryService
from services.user_cache import UserCache

ADMIN_ID = 15005473
USER_ID = 4242
GROUP_ID = -1003399818858
MONTH = DATA_EXPORT_MIN_INTERVAL_SECONDS
FILES = {"README.txt", "profile.json", "orders.json", "credit.json", "purchase_history.json"}


@pytest.fixture(autouse=True)
def reset_throttle():
    ExportExpiryService._last_sweep = 0.0
    yield
    ExportExpiryService._last_sweep = 0.0


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


def _customer(db, telegram_id=USER_ID, first_name="Jantje", language="nl", **extra):
    return db.create_customer(
        Customer(
            telegram_user_id=telegram_id,
            username=f"user{telegram_id}",
            first_name=first_name,
            last_name="Beton",
            language=language,
            authorization_status=AuthorizationStatus.APPROVED.value,
            **extra,
        )
    )


@pytest.fixture
def customer(db):
    return _customer(db)


@pytest.fixture
def populated(db, customer):
    """The customer has orders, credit, a transaction and history. Another customer has data too."""
    db.create_offer(Offer(offer_id=7, name="Pils", price_per_unit=Decimal("2.50")))
    for status in (OrderStatus.COMPLETED, OrderStatus.PENDING):
        db.order_repo.create_order(
            Order(
                customer_id=customer.customer_id,
                offer_id=7,
                quantity=2,
                unit_price=Decimal("2.50"),
                total_price=Decimal("5.00"),
                status=status.value,
            )
        )
    db.create_customer_credit(CustomerCredit(customer_id=customer.customer_id, current_balance=Decimal("12.50")))
    db.create_credit_transaction(
        CreditTransaction(
            customer_id=customer.customer_id,
            transaction_type="MANUAL_ADD",
            amount=Decimal("12.50"),
            balance_before=Decimal("0"),
            balance_after=Decimal("12.50"),
            reason="Refund",
            created_by=ADMIN_ID,
        )
    )
    db.create_order_history(
        OrderHistory(
            customer_id=customer.customer_id, offer_name="Pils", event_type="ORDER_CREATED", amount=Decimal("5")
        )
    )

    other = _customer(db, telegram_id=999, first_name="Other")
    other_order = Order(customer_id=other.customer_id, offer_id=7, quantity=9, status=OrderStatus.PENDING.value)
    db.order_repo.create_order(other_order)
    db.create_customer_credit(CustomerCredit(customer_id=other.customer_id, current_balance=Decimal("99")))
    db.create_order_history(OrderHistory(customer_id=other.customer_id, offer_name="Pils", event_type="ORDER_CREATED"))
    return {"customer": customer, "other": other, "other_order": other_order}


def _unzip(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def _json(files: dict[str, bytes], name: str):
    return json.loads(files[name].decode("utf-8"))


def _build(db, customer) -> dict[str, bytes]:
    service = DataExportService(db, lambda key, **p: f"{key} {p}")
    return _unzip(service.build_zip(customer, datetime(2026, 11, 15, 12, 0, tzinfo=UTC)))


class TestZipContents:
    def test_contains_the_expected_files(self, db, populated):
        assert set(_build(db, populated["customer"])) == FILES

    def test_profile_holds_the_customer_record(self, db, populated):
        customer = populated["customer"]

        profile = _json(_build(db, customer), "profile.json")

        assert profile["customer_id"] == customer.customer_id
        assert profile["telegram_user_id"] == USER_ID
        assert profile["first_name"] == "Jantje"
        assert profile["username"] == f"user{USER_ID}"
        assert profile["last_data_export_at"] is None

    def test_orders_include_offer_name_and_exact_amounts(self, db, populated):
        orders = _json(_build(db, populated["customer"]), "orders.json")

        assert len(orders) == 2
        assert {o["status"] for o in orders} == {"completed", "pending"}
        for order in orders:
            assert order["offer_name"] == "Pils"
            assert order["unit_price"] == "2.50"
            assert order["total_price"] == "5.00"
            assert order["quantity"] == 2  # a count, not text

    def test_credit_has_balance_and_transactions_without_the_admin_identity(self, db, populated):
        credit = _json(_build(db, populated["customer"]), "credit.json")

        assert credit["balance"]["current_balance"] == "12.50"
        (transaction,) = credit["transactions"]
        assert transaction["reason"] == "Refund"
        assert transaction["amount"] == "12.50"
        assert "created_by" not in transaction
        assert str(ADMIN_ID) not in json.dumps(credit)

    def test_purchase_history_shows_when_it_is_deleted(self, db, populated):
        (event,) = _json(_build(db, populated["customer"]), "purchase_history.json")

        assert event["event_type"] == "ORDER_CREATED"
        assert event["amount"] == "5.00"
        assert "ttl" not in event
        assert datetime.fromisoformat(event["delete_after"]) > datetime.now(UTC)

    def test_nothing_of_other_customers_is_included(self, db, populated):
        files = _build(db, populated["customer"])
        everything = b"".join(files.values()).decode("utf-8")

        assert populated["other"].customer_id not in everything
        assert populated["other_order"].order_id not in everything
        assert "Other" not in everything
        assert "99.00" not in everything

    def test_a_customer_without_any_data_still_gets_a_valid_zip(self, db, customer):
        files = _build(db, customer)

        assert _json(files, "orders.json") == []
        assert _json(files, "credit.json") == {"balance": None, "transactions": []}
        assert _json(files, "purchase_history.json") == []

    def test_non_ascii_text_is_kept_readable(self, db):
        customer = _customer(db, first_name="Jöran")

        raw = _build(db, customer)["profile.json"].decode("utf-8")

        assert "Jöran" in raw
        assert "\\u00f6" not in raw

    def test_previous_export_time_is_shown_as_a_date(self, db):
        customer = _customer(db, last_data_export_at=1_800_000_000)

        profile = _json(_build(db, customer), "profile.json")

        assert profile["last_data_export_at"] == datetime.fromtimestamp(1_800_000_000, UTC).isoformat()

    def test_readme_gets_the_export_date_and_customer_id(self, db, customer):
        readme = _build(db, customer)["README.txt"].decode()

        assert customer.customer_id in readme
        assert "2026-11-15T12:00:00+00:00" in readme


class TestStrictReads:
    """A failed read must raise for the data export, never look like "no data"."""

    @staticmethod
    def _boom(*args, **kwargs):
        raise RuntimeError("Cannot read from backfilling global secondary index: customer-index")

    def test_history_by_customer_raises_when_the_index_cannot_be_read(self, db, customer):
        db.order_history_repo.table = Mock(query=self._boom)

        with pytest.raises(RuntimeError, match="backfilling"):
            db.get_order_history_by_customer(customer.customer_id)

    def test_all_credit_transactions_raise_when_they_cannot_be_read(self, db, customer):
        db.credit_repo.transactions_table = Mock(query=self._boom)

        with pytest.raises(RuntimeError):
            db.get_all_credit_transactions_by_customer(customer.customer_id)

    def test_strict_orders_raise_but_the_default_stays_forgiving(self, db, customer):
        db.order_repo.table = Mock(query=self._boom)

        with pytest.raises(RuntimeError):
            db.get_orders_by_customer(customer.customer_id, strict=True)
        assert db.get_orders_by_customer(customer.customer_id) == []  # existing callers are unaffected

    def test_strict_credit_raises_but_the_default_stays_forgiving(self, db, customer):
        db.credit_repo.table = Mock(get_item=self._boom)

        with pytest.raises(RuntimeError):
            db.get_customer_credit(customer.customer_id, strict=True)
        assert db.get_customer_credit(customer.customer_id) is None

    def test_the_export_service_does_not_swallow_a_failed_read(self, db, customer):
        db.order_history_repo.table = Mock(query=self._boom)
        service = DataExportService(db, lambda key, **p: key)

        with pytest.raises(RuntimeError, match="backfilling"):
            service.build_zip(customer)


class TestMyDataCommand:
    @pytest.fixture
    def handler(self, db):
        handler = DataExportCommands(db, ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        return handler

    @pytest.fixture
    def lambda_client(self):
        with patch("boto3.client") as client:
            yield client.return_value

    def _sent(self, handler):
        return [(c.args[0], c.args[1]) for c in handler._send_message.call_args_list]

    def test_first_request_starts_the_exporter_asynchronously(self, handler, db, customer, lambda_client):
        result = handler.handle_my_data(USER_ID)

        assert result == {"status": "success"}
        call = lambda_client.invoke.call_args.kwargs
        assert call["InvocationType"] == "Event"
        payload = json.loads(call["Payload"])
        assert payload["customer_id"] == customer.customer_id
        assert payload["chat_id"] == USER_ID
        assert payload["previous"] is None
        assert payload["environment"] == "test"
        assert db.get_customer(customer.customer_id).last_data_export_at == payload["claimed_at"]

    def test_everything_is_sent_to_the_private_chat(self, handler, customer, lambda_client):
        handler.handle_my_data(USER_ID)

        assert {chat for chat, _ in self._sent(handler)} == {USER_ID}

    def test_second_request_within_a_month_is_refused_with_the_next_date(self, handler, customer, lambda_client):
        handler.handle_my_data(USER_ID)
        lambda_client.invoke.reset_mock()
        handler._send_message.reset_mock()

        result = handler.handle_my_data(USER_ID)

        assert result == {"status": "rate_limited"}
        lambda_client.invoke.assert_not_called()
        (chat, text) = self._sent(handler)[0]
        assert chat == USER_ID
        assert "30" in text  # the real (Dutch) text names the 30 days

    def test_refusal_names_the_date_the_export_is_possible_again(self, handler, db, customer, lambda_client):
        db.claim_data_export(customer.customer_id, 1_800_000_000, MONTH)
        handler._t = Mock(side_effect=lambda key, user_id=None, **p: f"{key}|{p.get('date', '')}")

        handler.handle_my_data(USER_ID)

        expected = datetime.fromtimestamp(1_800_000_000 + MONTH, UTC)
        text = handler._send_message.call_args.args[1]
        assert text.startswith("data_export_too_soon|")
        assert f"{expected:%Y-%m}" in text

    def test_request_is_allowed_again_after_a_month(self, handler, db, customer, lambda_client):
        db.claim_data_export(customer.customer_id, 1, MONTH)  # a very old export

        assert handler.handle_my_data(USER_ID) == {"status": "success"}
        assert json.loads(lambda_client.invoke.call_args.kwargs["Payload"])["previous"] == 1

    def test_failing_to_start_the_exporter_releases_the_claim(self, handler, db, customer, lambda_client):
        lambda_client.invoke.side_effect = RuntimeError("boom")

        result = handler.handle_my_data(USER_ID)

        assert result == {"status": "error"}
        assert db.get_customer(customer.customer_id).last_data_export_at is None
        lambda_client.invoke.side_effect = None
        assert handler.handle_my_data(USER_ID) == {"status": "success"}

    def test_database_failure_is_reported_without_starting_the_exporter(self, handler, db, customer, lambda_client):
        db.claim_data_export = Mock(return_value=None)

        assert handler.handle_my_data(USER_ID) == {"status": "error"}
        lambda_client.invoke.assert_not_called()

    def test_unknown_user_gets_nothing(self, handler, lambda_client):
        assert handler.handle_my_data(31337) == {"status": "not_found"}
        lambda_client.invoke.assert_not_called()
        handler._send_message.assert_not_called()


class TestDataExporterLambda:
    @pytest.fixture
    def telegram(self):
        """Capture what is sent to Telegram: (url, data, files)"""
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            response = MagicMock(status_code=200, text="ok")
            response.json.return_value = {"result": {"message_id": 321}}
            return response

        with patch("services.telegram_client.requests.post", side_effect=post):
            yield calls

    @pytest.fixture
    def event(self, db, customer):
        import boto3

        boto3.client("ssm", region_name="eu-west-1").put_parameter(
            Name="/ubbc-bot/test/telegram-bot-token", Value="token", Type="SecureString"
        )
        claim = db.claim_data_export(customer.customer_id, 1_800_000_000, MONTH)
        return {
            "customer_id": customer.customer_id,
            "chat_id": USER_ID,
            "claimed_at": 1_800_000_000,
            "previous": claim.previous,
            "environment": "test",
        }

    def _documents(self, telegram):
        return [kwargs for url, kwargs in telegram if url.endswith("/sendDocument")]

    def test_sends_a_valid_zip_to_the_customer_and_keeps_the_claim(self, db, populated, event, telegram):
        result = data_exporter.lambda_handler(event, None)

        assert result["statusCode"] == 200
        (document,) = self._documents(telegram)
        assert document["data"]["chat_id"] == USER_ID
        filename, content, mime = document["files"]["document"]
        assert filename.startswith("ubbc_my_data_test_") and filename.endswith(".zip")
        assert mime == "application/zip"
        assert set(_unzip(content.getvalue())) == FILES
        assert db.get_customer(event["customer_id"]).last_data_export_at == event["claimed_at"]

    def test_zip_filename_contains_no_personal_data(self, db, populated, event, telegram):
        data_exporter.lambda_handler(event, None)

        filename = self._documents(telegram)[0]["files"]["document"][0]
        assert "Jantje" not in filename and populated["customer"].customer_id not in filename

    def test_the_sent_file_is_tracked_and_deleted_after_an_hour(self, db, populated, event, telegram):
        data_exporter.lambda_handler(event, None)

        (row,) = db.get_notification_messages_by_offer(EXPORT_OFFER_ID)
        assert (row.kind, row.chat_id, row.message_id) == (EXPORT_KIND, USER_ID, 321)
        assert abs(row.expires_at - (time.time() + EXPORT_LIFETIME_SECONDS)) < 60

    def test_caption_mentions_the_expiry(self, db, populated, event, telegram):
        data_exporter.lambda_handler(event, None)

        assert "60" in self._documents(telegram)[0]["data"]["caption"]

    def _readme(self, telegram) -> str:
        files = _unzip(self._documents(telegram)[0]["files"]["document"][1].getvalue())
        return files["README.txt"].decode("utf-8")

    def test_readme_is_in_dutch_by_default(self, db, populated, event, telegram):
        data_exporter.lambda_handler(event, None)

        readme = self._readme(telegram)
        assert readme.startswith("Jouw gegevens van de UBBC Bot")
        assert populated["customer"].customer_id in readme
        assert "{" not in readme  # every placeholder was filled

    def test_readme_follows_the_customers_language(self, db, populated, event, telegram):
        db.update_customer(event["customer_id"], {"language": "en"})

        data_exporter.lambda_handler(event, None)

        readme = self._readme(telegram)
        assert readme.startswith("Your data from the UBBC Bot")
        assert "{" not in readme

    def test_failed_send_releases_the_claim_and_tells_the_customer(self, db, populated, event):
        def post(url, **kwargs):
            return MagicMock(status_code=500 if url.endswith("/sendDocument") else 200, text="err")

        with patch("services.telegram_client.requests.post", side_effect=post) as telegram_post:
            result = data_exporter.lambda_handler(event, None)

        assert result["statusCode"] == 500
        assert db.get_customer(event["customer_id"]).last_data_export_at is None
        assert any(c.args[0].endswith("/sendMessage") for c in telegram_post.call_args_list)

    def test_exception_while_building_releases_the_claim(self, db, populated, event, telegram):
        with patch.object(DataExportService, "build_zip", side_effect=RuntimeError("boom")):
            result = data_exporter.lambda_handler(event, None)

        assert result["statusCode"] == 500
        assert db.get_customer(event["customer_id"]).last_data_export_at is None
        assert self._documents(telegram) == []

    def test_a_release_restores_an_earlier_export_time(self, db, populated, event, telegram):
        db.release_data_export_claim(event["customer_id"], event["claimed_at"], None)
        db.claim_data_export(event["customer_id"], 1_000, MONTH)
        later = {**event, "claimed_at": 1_000 + MONTH, "previous": 1_000}
        db.claim_data_export(event["customer_id"], 1_000 + MONTH, MONTH)

        with patch.object(DataExportService, "build_zip", side_effect=RuntimeError("boom")):
            data_exporter.lambda_handler(later, None)

        assert int(db.get_customer(event["customer_id"]).last_data_export_at) == 1_000

    @pytest.mark.parametrize(
        "repository, method, message",
        [
            (
                OrderHistoryRepository,
                "get_events_by_customer",
                "Cannot read from backfilling global secondary index: customer-index",
            ),
            (CreditRepository, "get_all_credit_transactions_by_customer", "throttled"),
            (CreditRepository, "get_customer_credit", "throttled"),
            (OrderRepository, "get_orders_by_customer", "throttled"),
        ],
        ids=["history-index-backfilling", "credit-transactions", "credit-balance", "orders"],
    )
    def test_an_unreadable_source_fails_the_export_instead_of_sending_it_incomplete(
        self, db, populated, event, telegram, repository, method, message
    ):
        with patch.object(repository, method, side_effect=RuntimeError(message)):
            result = data_exporter.lambda_handler(event, None)

        assert result["statusCode"] == 500
        assert self._documents(telegram) == []  # no zip, so no "complete looking" export with a hole in it
        assert db.get_customer(event["customer_id"]).last_data_export_at is None  # the month is not used up
        assert db.get_notification_messages_by_offer(EXPORT_OFFER_ID) == []
        sent = [kw for url, kw in telegram if url.endswith("/sendMessage")]
        assert sent and sent[0]["json"]["chat_id"] == USER_ID  # the customer is told it failed

    def test_customer_deleted_in_the_meantime_sends_nothing(self, db, populated, event, telegram):
        db.delete_customer(event["customer_id"])

        result = data_exporter.lambda_handler(event, None)

        assert result["statusCode"] == 500
        assert self._documents(telegram) == []


class TestAdminExport:
    """/export_user_data: the admin builds the same zip for a customer who asked by email"""

    @pytest.fixture
    def handler(self, db):
        handler = DataExportCommands(db, ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        return handler

    @pytest.fixture
    def lambda_client(self):
        with patch("boto3.client") as client:
            yield client.return_value

    @staticmethod
    def _payload(lambda_client):
        return json.loads(lambda_client.invoke.call_args.kwargs["Payload"])

    def test_without_arguments_shows_usage(self, handler, lambda_client):
        assert handler.handle_export_user_data(ADMIN_ID, []) == {"status": "invalid_args"}
        lambda_client.invoke.assert_not_called()

    def test_unknown_customer_is_reported(self, handler, customer, lambda_client):
        assert handler.handle_export_user_data(ADMIN_ID, ["nobody-like-this"])["status"] == "user_not_found"
        lambda_client.invoke.assert_not_called()

    def test_the_zip_goes_to_the_admin_not_to_the_customer(self, handler, customer, lambda_client):
        result = handler.handle_export_user_data(ADMIN_ID, ["jantje"])

        assert result == {"status": "success"}
        payload = self._payload(lambda_client)
        assert payload["customer_id"] == customer.customer_id
        assert payload["chat_id"] == ADMIN_ID
        assert lambda_client.invoke.call_args.kwargs["InvocationType"] == "Event"

    def test_it_makes_no_claim_so_the_customers_own_monthly_slot_is_untouched(
        self, handler, db, customer, lambda_client
    ):
        db.claim_data_export(customer.customer_id, 1_800_000_000, MONTH)

        handler.handle_export_user_data(ADMIN_ID, ["jantje"])
        handler.handle_export_user_data(ADMIN_ID, ["jantje"])  # not limited to once a month either

        assert lambda_client.invoke.call_count == 2
        assert self._payload(lambda_client).get("claimed_at") is None
        assert int(db.get_customer(customer.customer_id).last_data_export_at) == 1_800_000_000

    def test_resolves_a_partial_customer_id(self, handler, customer, lambda_client):
        handler.handle_export_user_data(ADMIN_ID, [customer.customer_id[:8]])

        assert self._payload(lambda_client)["customer_id"] == customer.customer_id

    def test_ambiguous_names_show_a_choice_that_leads_to_the_export(self, handler, db, customer, lambda_client):
        other = _customer(db, telegram_id=7, first_name="Jantje")

        result = handler.handle_export_user_data(ADMIN_ID, ["jantje"])

        assert result["status"] == "disambiguation_shown"
        lambda_client.invoke.assert_not_called()
        markup = handler._send_message.call_args.kwargs["reply_markup"]
        callbacks = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        assert f"export_user_data_select_{other.customer_id}" in callbacks

        handler.handle_export_user_data_select(ADMIN_ID, other.customer_id)

        assert self._payload(lambda_client)["customer_id"] == other.customer_id

    def test_failure_to_start_is_reported(self, handler, customer, lambda_client):
        lambda_client.invoke.side_effect = RuntimeError("boom")

        assert handler.handle_export_user_data(ADMIN_ID, ["jantje"]) == {"status": "error"}

    def test_the_exporter_lambda_sends_to_the_admin_without_touching_any_claim(self, db, populated, telegram_post):
        import boto3

        boto3.client("ssm", region_name="eu-west-1").put_parameter(
            Name="/ubbc-bot/test/telegram-bot-token", Value="token", Type="SecureString"
        )
        customer = populated["customer"]
        event = {"customer_id": customer.customer_id, "chat_id": ADMIN_ID, "environment": "test"}

        result = data_exporter.lambda_handler(event, None)

        assert result["statusCode"] == 200
        (document,) = [kw for url, kw in telegram_post if url.endswith("/sendDocument")]
        assert document["data"]["chat_id"] == ADMIN_ID
        assert set(_unzip(document["files"]["document"][1].getvalue())) == FILES
        assert db.get_customer(customer.customer_id).last_data_export_at is None

    def test_a_failed_admin_export_does_not_try_to_release_a_claim(self, db, populated):
        import boto3

        boto3.client("ssm", region_name="eu-west-1").put_parameter(
            Name="/ubbc-bot/test/telegram-bot-token", Value="token", Type="SecureString"
        )
        db.claim_data_export(populated["customer"].customer_id, 1_800_000_000, MONTH)
        event = {"customer_id": populated["customer"].customer_id, "chat_id": ADMIN_ID, "environment": "test"}

        with (
            patch.object(DataExportService, "build_zip", side_effect=RuntimeError("boom")),
            patch("services.telegram_client.requests.post"),
        ):
            data_exporter.lambda_handler(event, None)

        # The customer's own claim must survive an admin export that failed
        assert int(db.get_customer(populated["customer"].customer_id).last_data_export_at) == 1_800_000_000

    @pytest.fixture
    def telegram_post(self):
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            response = MagicMock(status_code=200, text="ok")
            response.json.return_value = {"result": {"message_id": 321}}
            return response

        with patch("services.telegram_client.requests.post", side_effect=post):
            yield calls


class TestClearDataExport:
    """/clear_data_export: the admin lets a customer use /my_data again before the 30 days are over"""

    @pytest.fixture
    def handler(self, db):
        handler = DataExportCommands(db, ADMIN_ID, "test", "token")
        handler._send_message = Mock(return_value={"success": True})
        return handler

    @pytest.fixture
    def lambda_client(self):
        with patch("boto3.client") as client:
            yield client.return_value

    def test_without_arguments_shows_usage(self, handler):
        assert handler.handle_clear_data_export(ADMIN_ID, []) == {"status": "invalid_args"}

    def test_unknown_customer_is_reported(self, handler):
        assert handler.handle_clear_data_export(ADMIN_ID, ["nobody-like-this"])["status"] == "user_not_found"

    def test_clears_the_time_and_the_customer_can_export_again(self, handler, db, customer, lambda_client):
        handler.handle_my_data(USER_ID)
        assert handler.handle_my_data(USER_ID) == {"status": "rate_limited"}

        result = handler.handle_clear_data_export(ADMIN_ID, ["jantje"])

        assert result == {"status": "success"}
        assert db.get_customer(customer.customer_id).last_data_export_at is None
        assert handler.handle_my_data(USER_ID) == {"status": "success"}

    def test_nothing_else_of_the_customer_changes(self, handler, db, customer):
        db.claim_data_export(customer.customer_id, 1_800_000_000, MONTH)

        handler.handle_clear_data_export(ADMIN_ID, ["jantje"])

        after = db.get_customer(customer.customer_id)
        assert (after.first_name, after.username, after.language) == ("Jantje", f"user{USER_ID}", "nl")
        assert after.authorization_status == AuthorizationStatus.APPROVED.value

    def test_a_customer_who_never_exported_has_nothing_to_clear(self, handler, customer):
        result = handler.handle_clear_data_export(ADMIN_ID, ["jantje"])

        assert result == {"status": "nothing_to_clear"}

    def test_clearing_twice_reports_nothing_to_clear_the_second_time(self, handler, db, customer):
        db.claim_data_export(customer.customer_id, 1_800_000_000, MONTH)

        assert handler.handle_clear_data_export(ADMIN_ID, ["jantje"]) == {"status": "success"}
        assert handler.handle_clear_data_export(ADMIN_ID, ["jantje"]) == {"status": "nothing_to_clear"}

    def test_a_stale_cached_customer_does_not_hide_a_recent_export(self, handler, db, customer):
        # The name lookup uses cached customer lists. Warm the cache first, then export.
        assert db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        db.claim_data_export(customer.customer_id, 1_800_000_000, MONTH)

        result = handler.handle_clear_data_export(ADMIN_ID, ["jantje"])

        assert result == {"status": "success"}
        assert db.get_customer(customer.customer_id).last_data_export_at is None

    def test_resolves_a_partial_customer_id(self, handler, db, customer):
        db.claim_data_export(customer.customer_id, 1_800_000_000, MONTH)

        assert handler.handle_clear_data_export(ADMIN_ID, [customer.customer_id[:8]]) == {"status": "success"}

    def test_ambiguous_names_show_a_choice_that_leads_to_the_clear(self, handler, db, customer):
        other = _customer(db, telegram_id=7, first_name="Jantje")
        db.claim_data_export(other.customer_id, 1_800_000_000, MONTH)

        result = handler.handle_clear_data_export(ADMIN_ID, ["jantje"])

        assert result["status"] == "disambiguation_shown"
        markup = handler._send_message.call_args.kwargs["reply_markup"]
        callbacks = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        assert f"clear_data_export_select_{other.customer_id}" in callbacks

        assert handler.handle_clear_data_export_select(ADMIN_ID, other.customer_id) == {"status": "success"}
        assert db.get_customer(other.customer_id).last_data_export_at is None

    def test_a_failing_update_is_reported_and_leaves_the_time(self, handler, db, customer):
        db.claim_data_export(customer.customer_id, 1_800_000_000, MONTH)
        db.clear_data_export = Mock(return_value=False)

        assert handler.handle_clear_data_export(ADMIN_ID, ["jantje"]) == {"status": "error"}
        assert int(db.get_customer(customer.customer_id).last_data_export_at) == 1_800_000_000

    def test_the_repository_ignores_a_missing_customer(self, db):
        assert db.clear_data_export("does-not-exist") is False
        assert db.get_customer("does-not-exist") is None

    def test_log_names_the_customer_id_only(self, handler, db, customer, caplog):
        import logging

        db.claim_data_export(customer.customer_id, 1_800_000_000, MONTH)
        caplog.set_level(logging.INFO)

        handler.handle_clear_data_export(ADMIN_ID, ["jantje"])

        logs = "\n".join(r.getMessage() for r in caplog.records)
        assert customer.customer_id in logs
        assert "Jantje" not in logs


class TestAuthorization:
    def _router(self, status):
        db = Mock()
        db.get_customer_by_telegram_id.return_value = Mock(authorization_status=status, language="nl")
        handlers = {"data_export": Mock(), "auth": Mock(), "info": Mock()}
        router = CommandRouter(db, ADMIN_ID, "test", handlers)
        router.base_handler._send_message = Mock()
        return router, handlers

    def test_approved_customer_can_use_it(self):
        router, handlers = self._router("approved")

        router.route_command(USER_ID, USER_ID, "/my_data")

        handlers["data_export"].handle_my_data.assert_called_once_with(USER_ID)

    @pytest.mark.parametrize("status", ["unauthorized", "rejected"])
    def test_unapproved_customers_cannot(self, status):
        router, handlers = self._router(status)

        router.route_command(USER_ID, USER_ID, "/my_data")

        handlers["data_export"].handle_my_data.assert_not_called()

    def test_in_a_group_the_command_is_redirected_in_production(self):
        db = Mock()
        db.get_customer_by_telegram_id.return_value = Mock(authorization_status="approved", language="nl")
        handlers = {"data_export": Mock()}
        router = CommandRouter(db, ADMIN_ID, "prod", handlers)
        router.base_handler._send_message = Mock()

        router.route_command(GROUP_ID, USER_ID, "/my_data")

        handlers["data_export"].handle_my_data.assert_not_called()

    def test_even_asked_in_a_test_group_the_reply_goes_to_the_user(self):
        router, handlers = self._router("approved")

        router.route_command(GROUP_ID, USER_ID, "/my_data")

        handlers["data_export"].handle_my_data.assert_called_once_with(USER_ID)

    def test_admin_command_is_routed_for_the_admin(self):
        router, handlers = self._router("approved")

        router.route_command(ADMIN_ID, ADMIN_ID, "/export_user_data jantje beton")

        handlers["data_export"].handle_export_user_data.assert_called_once_with(ADMIN_ID, ["jantje", "beton"])

    def test_customers_cannot_export_other_peoples_data(self):
        router, handlers = self._router("approved")

        router.route_command(USER_ID, USER_ID, "/export_user_data jantje")

        handlers["data_export"].handle_export_user_data.assert_not_called()

    def test_clear_command_is_routed_for_the_admin(self):
        router, handlers = self._router("approved")

        router.route_command(ADMIN_ID, ADMIN_ID, "/clear_data_export jantje beton")

        handlers["data_export"].handle_clear_data_export.assert_called_once_with(ADMIN_ID, ["jantje", "beton"])

    def test_customers_cannot_clear_their_own_limit(self):
        router, handlers = self._router("approved")

        router.route_command(USER_ID, USER_ID, "/clear_data_export jantje")

        handlers["data_export"].handle_clear_data_export.assert_not_called()

    def test_the_clear_selection_button_is_admin_only(self):
        from services.callback_handler import CallbackHandler

        callbacks = CallbackHandler(Mock(), ADMIN_ID, "test", "token", {}, Mock())
        assert not callbacks.customer_callback("clear_data_export_select_abc-123")

    def test_the_clear_selection_button_routes_to_the_handler_for_the_admin(self):
        from services.callback_handler import CallbackHandler

        handlers = {name: Mock() for name in ("data_export", "user", "admin_commands", "admin_order", "credit")}
        callback_handler = CallbackHandler(Mock(), ADMIN_ID, "test", "token", handlers, Mock())
        query = {
            "id": "q",
            "from": {"id": ADMIN_ID},
            "message": {"chat": {"id": ADMIN_ID}, "message_id": 1},
            "data": "clear_data_export_select_abc-123",
        }

        callback_handler.handle_callback_query(query)

        handlers["data_export"].handle_clear_data_export_select.assert_called_once_with(ADMIN_ID, "abc-123")

    @pytest.mark.parametrize("data", ["export_user_data_select_abc-123"])
    def test_the_selection_button_is_admin_only(self, data):
        from services.callback_handler import CallbackHandler

        callbacks = CallbackHandler(Mock(), ADMIN_ID, "test", "token", {}, Mock())
        assert not callbacks.customer_callback(data)
