"""Orders are read through indexes instead of scanning the whole table.

A scan reads every order and filters afterwards, so a job that needs "the orders in status X" got slower with every
order ever placed. The `status-index` answers that question directly.

While an index is still being built by a deploy (or does not exist yet), the same question is answered with a scan,
so the answer is the same and only slower.
"""

import logging
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from models.entities import Box, Offer, Order, Supplier
from repositories.order_repository import BOX_INDEX, STATUS_INDEX, OrderRepository
from services.database import DynamoDBService
from services.user_cache import UserCache


def _order(order_id, status, offer_id=1, box_id="box-a", customer_id="cust-1", quantity=1):
    return Order(
        order_id=order_id,
        customer_id=customer_id,
        offer_id=offer_id,
        box_id=box_id,
        quantity=quantity,
        unit_price=Decimal("2.50"),
        total_price=Decimal("2.50") * quantity,
        status=status,
    )


@contextmanager
def watching_scans(table):
    """Yields a mock that counts the scans of the table, while still performing them"""
    with patch.object(table, "scan", wraps=table.scan) as scan:
        yield scan


@pytest.fixture
def db(dynamodb):
    UserCache.invalidate_cache()
    yield DynamoDBService()
    UserCache.invalidate_cache()


@pytest.fixture
def repo(db) -> OrderRepository:
    return db.order_repo


@pytest.fixture
def orders(repo):
    created = [
        _order("o1", "ready_for_labeling", offer_id=1, box_id="box-a"),
        _order("o2", "ready_for_labeling", offer_id=2, box_id="box-b", customer_id="cust-2"),
        _order("o3", "ordered", offer_id=1, box_id="box-a"),
        _order("o4", "awaiting_payment", offer_id=3, box_id="box-c"),
        _order("o5", "cancelled", offer_id=3, box_id="box-c"),
    ]
    for order in created:
        assert repo.create_order(order)
    return created


def _ids(orders) -> list[str]:
    return sorted(order.order_id for order in orders)


class TestOrdersByStatus:
    def test_only_the_orders_with_that_status_are_returned_whatever_their_offer_or_customer(self, repo, orders):
        assert _ids(repo.get_orders_by_status("ready_for_labeling")) == ["o1", "o2"]
        assert _ids(repo.get_orders_by_status("awaiting_payment")) == ["o4"]

    def test_the_orders_are_complete(self, repo, orders):
        found = repo.get_orders_by_status("awaiting_payment")[0]

        assert (found.offer_id, found.box_id, found.customer_id) == (3, "box-c", "cust-1")
        assert found.status == "awaiting_payment"
        assert found.total_price == Decimal("2.50")

    def test_a_status_without_orders_gives_an_empty_list(self, repo, orders):
        assert repo.get_orders_by_status("completed") == []

    def test_the_table_is_not_scanned(self, repo, orders):
        with watching_scans(repo.table) as scan:
            repo.get_orders_by_status("ready_for_labeling")

        assert scan.call_count == 0

    def test_an_order_that_changes_status_moves_to_the_other_list(self, repo, orders):
        assert repo.update_order("o1", {"status": "labeling_completed"})

        assert _ids(repo.get_orders_by_status("ready_for_labeling")) == ["o2"]
        assert _ids(repo.get_orders_by_status("labeling_completed")) == ["o1"]


class TestAllOrders:
    def test_the_orders_of_several_statuses_are_returned_together(self, repo, orders):
        found = repo.get_all_orders(statuses=["pending", "ordered", "awaiting_payment"])

        assert _ids(found) == ["o3", "o4"]

    def test_the_fields_the_lists_need_are_there(self, repo, orders):
        found = {order.order_id: order for order in repo.get_all_orders(statuses=["ordered"])}

        assert (found["o3"].offer_id, found["o3"].quantity, found["o3"].status, found["o3"].box_id) == (
            1,
            1,
            "ordered",
            "box-a",
        )

    def test_a_status_given_twice_does_not_duplicate_orders(self, repo, orders):
        assert _ids(repo.get_all_orders(statuses=["ordered", "ordered"])) == ["o3"]

    def test_with_statuses_the_table_is_not_scanned(self, repo, orders):
        with watching_scans(repo.table) as scan:
            repo.get_all_orders(statuses=["pending", "ordered"])

        assert scan.call_count == 0

    def test_without_statuses_every_order_is_returned(self, repo, orders):
        assert _ids(repo.get_all_orders()) == ["o1", "o2", "o3", "o4", "o5"]


class TestLookupsBySupplier:
    @pytest.fixture
    def catalogue(self, db, orders):
        for name in ("HD", "DK"):
            assert db.create_supplier(Supplier(name=name))
        price = Decimal("2.50")
        for offer_id, supplier in ((1, "HD"), (2, "DK"), (3, "DK")):
            offer = Offer(offer_id=offer_id, name=f"Beer {offer_id}", supplier_name=supplier, price_per_unit=price)
            assert db.create_offer(offer)

    def test_suppliers_with_orders_in_a_status(self, db, catalogue):
        assert sorted(s.name for s in db.get_suppliers_with_orders_by_status("ready_for_labeling")) == ["DK", "HD"]
        assert [s.name for s in db.get_suppliers_with_orders_by_status("awaiting_payment")] == ["DK"]
        assert db.get_suppliers_with_orders_by_status("completed") == []

    def test_offers_of_a_supplier_with_orders_in_a_status(self, db, catalogue):
        assert [o.offer_id for o in db.get_offers_by_supplier_and_order_status("DK", "ready_for_labeling")] == [2]
        assert [o.offer_id for o in db.get_offers_by_supplier_and_order_status("HD", "ready_for_labeling")] == [1]
        assert db.get_offers_by_supplier_and_order_status("HD", "awaiting_payment") == []

    def test_labeling_lists_do_not_scan_the_orders(self, db, catalogue):
        with watching_scans(db.orders_table) as table_scan, watching_scans(db.order_repo.table) as repo_scan:
            db.get_suppliers_with_ready_for_labeling_offers()
            db.get_ready_for_labeling_offers_by_supplier("DK")

        assert table_scan.call_count == 0
        assert repo_scan.call_count == 0


class TestOrdersByBox:
    def test_only_the_orders_of_that_box_are_returned_whatever_their_status(self, repo, orders):
        assert _ids(repo.get_orders_by_box("box-a")) == ["o1", "o3"]
        assert _ids(repo.get_orders_by_box("box-c")) == ["o4", "o5"]

    def test_the_orders_are_complete(self, repo, orders):
        found = {order.order_id: order for order in repo.get_orders_by_box("box-b")}

        assert (found["o2"].customer_id, found["o2"].offer_id) == ("cust-2", 2)
        assert found["o2"].status == "ready_for_labeling"
        assert found["o2"].total_price == Decimal("2.50")

    def test_a_box_without_orders_gives_an_empty_list(self, repo, orders):
        assert repo.get_orders_by_box("box-zzz") == []

    def test_the_table_is_not_scanned(self, repo, orders):
        with watching_scans(repo.table) as scan:
            repo.get_orders_by_box("box-a")

        assert scan.call_count == 0

    def test_an_order_that_moves_to_another_box_is_found_there(self, repo, orders):
        assert repo.update_order("o1", {"box_id": "box-b"})

        assert _ids(repo.get_orders_by_box("box-a")) == ["o3"]
        assert _ids(repo.get_orders_by_box("box-b")) == ["o1", "o2"]

    def test_a_missing_index_gives_the_same_orders_with_a_scan(self, repo, orders, caplog):
        repo.table.update(GlobalSecondaryIndexUpdates=[{"Delete": {"IndexName": BOX_INDEX}}])

        with caplog.at_level(logging.WARNING), watching_scans(repo.table) as scan:
            found = repo.get_orders_by_box("box-a")

        assert _ids(found) == ["o1", "o3"]
        assert scan.call_count == 1
        assert BOX_INDEX in caplog.text


class TestBoxListsOfTheJobs:
    """The labeling job asks for the orders of every box of an offer: one lookup per box, so it must be cheap"""

    @pytest.fixture
    def boxes(self, db, orders):
        # box-a (offer 1) has an order ready for labeling and one only ordered; box-d (offer 1) only an ordered one
        for box_id, offer_id in (("box-a", 1), ("box-b", 2), ("box-c", 3), ("box-d", 1)):
            assert db.create_box(Box(box_id=box_id, offer_id=offer_id, max_capacity=12))
        assert db.order_repo.create_order(_order("o6", "ordered", offer_id=1, box_id="box-d"))

    def test_the_boxes_of_an_offer_with_orders_ready_for_labeling(self, db, boxes):
        assert [box.box_id for box in db.get_boxes_by_offer_with_ready_orders(1)] == ["box-a"]
        assert [box.box_id for box in db.get_boxes_by_offer_with_ready_orders(2)] == ["box-b"]
        assert db.get_boxes_by_offer_with_ready_orders(3) == []

    def test_no_box_costs_a_scan_of_the_orders(self, db, boxes):
        with watching_scans(db.orders_table) as table_scan, watching_scans(db.order_repo.table) as repo_scan:
            db.get_boxes_by_offer_with_ready_orders(1)
            for box_id in ("box-a", "box-b", "box-c", "box-d"):
                db.get_orders_by_box(box_id)

        assert table_scan.call_count == 0
        assert repo_scan.call_count == 0


class TestWhileTheIndexIsNotAvailable:
    BACKFILLING = ClientError(
        {
            "Error": {
                "Code": "ValidationException",
                "Message": f"Cannot read from backfilling global secondary index: {STATUS_INDEX}",
            }
        },
        "Query",
    )

    def test_a_missing_index_gives_the_same_orders_with_a_scan(self, repo, orders, caplog):
        repo.table.update(GlobalSecondaryIndexUpdates=[{"Delete": {"IndexName": STATUS_INDEX}}])

        with caplog.at_level(logging.WARNING), watching_scans(repo.table) as scan:
            found = repo.get_orders_by_status("ready_for_labeling")

        assert _ids(found) == ["o1", "o2"]
        assert scan.call_count == 1
        assert STATUS_INDEX in caplog.text

    def test_an_index_that_is_still_being_built_gives_the_same_orders_with_a_scan(self, repo, orders):
        with patch.object(repo.table, "query", side_effect=self.BACKFILLING), watching_scans(repo.table) as scan:
            found = repo.get_all_orders(statuses=["ready_for_labeling", "ordered"])

        assert _ids(found) == ["o1", "o2", "o3"]
        assert scan.call_count >= 1

    def test_the_answer_of_dynamodb_for_an_index_that_does_not_exist_gives_the_same_orders_with_a_scan(
        self, repo, orders
    ):
        missing = ClientError(
            {
                "Error": {
                    "Code": "ValidationException",
                    "Message": f"The table does not have the specified index: {STATUS_INDEX}",
                }
            },
            "Query",
        )

        with patch.object(repo.table, "query", side_effect=missing), watching_scans(repo.table) as scan:
            found = repo.get_orders_by_status("ready_for_labeling")

        assert _ids(found) == ["o1", "o2"]
        assert scan.call_count == 1

    def test_a_missing_table_is_not_answered_with_a_scan(self, repo, orders):
        no_table = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Requested resource not found"}}, "Query"
        )

        with patch.object(repo.table, "query", side_effect=no_table), watching_scans(repo.table) as scan:
            found = repo.get_orders_by_status("ready_for_labeling")

        assert found == []
        assert scan.call_count == 0

    def test_other_database_errors_are_not_answered_with_a_scan(self, repo, orders):
        denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Query")

        with patch.object(repo.table, "query", side_effect=denied), watching_scans(repo.table) as scan:
            found = repo.get_orders_by_status("ready_for_labeling")

        assert found == []
        assert scan.call_count == 0
