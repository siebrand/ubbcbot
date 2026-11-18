"""DynamoDB returns at most 1 MB per scan or query call. Every read must follow LastEvaluatedKey.

The repository tests force a page per item by capping every call at one item (Limit=1).
"""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from models.entities import CreditTransaction, CustomerCredit, EditContext, NotificationMessage, Supplier
from repositories.credit_repository import CreditRepository
from repositories.edit_context_repository import EditContextRepository
from repositories.notification_repository import NotificationRepository
from repositories.offer_repository import OfferRepository
from repositories.supplier_repository import SupplierRepository
from repositories.system_repository import SystemRepository
from utils.dynamodb import read_all_pages

N = 5


@contextmanager
def one_item_per_call(table):
    scan, query = table.scan, table.query
    with (
        patch.object(table, "scan", side_effect=lambda **kw: scan(Limit=1, **kw)),
        patch.object(table, "query", side_effect=lambda **kw: query(Limit=1, **kw)),
    ):
        yield


class TestReadAllPages:
    def test_follows_last_evaluated_key(self):
        read = Mock(
            side_effect=[
                {"Items": [1, 2], "LastEvaluatedKey": {"k": 2}},
                {"Items": [], "LastEvaluatedKey": {"k": 3}},  # a filtered page can be empty
                {"Items": [4]},
            ]
        )

        assert read_all_pages(read, {"FilterExpression": "x"}) == [1, 2, 4]
        assert [c.kwargs for c in read.call_args_list] == [
            {"FilterExpression": "x"},
            {"FilterExpression": "x", "ExclusiveStartKey": {"k": 2}},
            {"FilterExpression": "x", "ExclusiveStartKey": {"k": 3}},
        ]

    def test_the_callers_parameters_are_not_changed(self):
        params = {"FilterExpression": "x"}
        read_all_pages(Mock(side_effect=[{"Items": [], "LastEvaluatedKey": {"k": 1}}, {"Items": []}]), params)

        assert params == {"FilterExpression": "x"}


class TestOffers:
    @pytest.fixture
    def repo(self, dynamodb):
        repo = OfferRepository(SystemRepository())
        now = datetime.now(UTC).isoformat()
        for i in range(1, N + 1):
            repo.table.put_item(Item={"offer_id": i, "name": f"Bier {i}", "status": "sold_out", "created_at": now})
        return repo

    def test_list_offers(self, repo):
        with one_item_per_call(repo.table):
            assert len(repo._list_offers_uncached()) == N

    def test_recent_sold_out(self, repo):
        with one_item_per_call(repo.table):
            assert len(repo.list_sold_out_offers_recent()) == N


class TestSuppliers:
    @pytest.fixture
    def repo(self, dynamodb):
        repo = SupplierRepository()
        for i in range(1, N + 1):
            repo.create_supplier(Supplier(supplier_id=f"s{i}", name=f"Brouwerij {i}"))
        return repo

    def test_list(self, repo):
        with one_item_per_call(repo.table):
            assert len(repo.list_suppliers()) == N

    def test_by_name(self, repo):
        with one_item_per_call(repo.table):
            assert repo.get_supplier_by_name("Brouwerij 5").supplier_id == "s5"


class TestCredits:
    @pytest.fixture
    def repo(self, dynamodb):
        repo = CreditRepository()
        for i in range(1, N + 1):
            repo.create_customer_credit(CustomerCredit(customer_id=f"c{i}", current_balance=Decimal("10")))
            repo.create_credit_transaction(
                CreditTransaction(transaction_id=f"t{i}", customer_id="c1", amount=Decimal("1"), transaction_type="x")
            )
        return repo

    @pytest.mark.parametrize("minimum", [None, Decimal("5")])
    def test_customers_with_a_balance(self, repo, minimum):
        with one_item_per_call(repo.table):
            assert len(repo.get_customers_with_credit_balance(minimum)) == N

    def test_all_transactions_of_a_customer(self, repo):
        with one_item_per_call(repo.transactions_table):
            assert len(repo.get_all_credit_transactions_by_customer("c1")) == N


class TestNotifications:
    def test_messages_of_an_offer(self, dynamodb):
        repo = NotificationRepository()
        for i in range(1, N + 1):
            repo.create_notification_message(NotificationMessage(notification_id=f"n{i}", offer_id=7, message_id=i))

        with one_item_per_call(repo.table):
            assert len(repo.get_notification_messages_by_offer(7)) == N


class TestEditContexts:
    @pytest.fixture
    def repo(self, dynamodb):
        repo = EditContextRepository()
        old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        for i in range(1, N + 1):
            repo.table.put_item(Item={"context_id": f"x{i}", "chat_id": i, "edit_type": "t", "created_at": old})
        return repo

    def test_the_context_of_a_chat_on_a_later_page(self, repo):
        with one_item_per_call(repo.table):
            assert repo.get_edit_context_by_chat_id(N).context_id == f"x{N}"

    def test_cleanup_removes_every_old_context(self, repo):
        with one_item_per_call(repo.table):
            assert repo.cleanup_old_edit_contexts() == N

    def test_a_new_context_replaces_the_old_one_on_a_later_page(self, repo):
        with one_item_per_call(repo.table):
            repo.create_edit_context(EditContext(context_id="new", chat_id=N, edit_type="t"))

        assert repo.table.get_item(Key={"context_id": f"x{N}"}).get("Item") is None
