"""The lookups behind the delivery and labeling workflows: which suppliers, offers and boxes have work waiting.

Wholesale delivery starts from boxes with status "ordered"; labeling from orders with status "ready_for_labeling".
"""

from unittest.mock import patch

import pytest

from models.entities import Box, Offer, Order, Supplier
from services.database import DynamoDBService


@pytest.fixture
def db(dynamodb):
    service = DynamoDBService()
    for name in ("Molen", "Kees", "Oersoep"):
        service.create_supplier(Supplier(supplier_id=f"sup-{name}", name=name))
    for offer_id, supplier in [(1, "Molen"), (2, "Molen"), (3, "Kees"), (4, "Oersoep")]:
        service.create_offer(Offer(offer_id=offer_id, name=f"Bier {offer_id}", supplier_name=supplier))
    for box_id, offer_id, status in [
        ("b1", 1, "ordered"),
        ("b2", 2, "open"),
        ("b3", 3, "ordered"),
        ("b4", 4, "delivered"),
        ("b5", 1, "ordered"),
    ]:
        service.create_box(Box(box_id=box_id, offer_id=offer_id, status=status))
    for order_id, box_id, offer_id, status in [
        ("o1", "b1", 1, "ready_for_labeling"),
        ("o2", "b1", 1, "ordered"),
        ("o3", "b4", 4, "ready_for_labeling"),
        ("o4", "b3", 3, "ordered"),
    ]:
        service.order_repo.create_order(Order(order_id=order_id, box_id=box_id, offer_id=offer_id, status=status))
    return service


def names(suppliers) -> list[str]:
    return sorted(s.name for s in suppliers)


def ids(offers) -> list[int]:
    return sorted(int(o.offer_id) for o in offers)


class TestBoxStatus:
    def test_suppliers_with_ordered_boxes(self, db):
        assert names(db.get_suppliers_with_ordered_offers()) == ["Kees", "Molen"]

    def test_offers_of_a_supplier_with_ordered_boxes(self, db):
        assert ids(db.get_ordered_offers_by_supplier("Molen")) == [1]
        assert ids(db.get_ordered_offers_by_supplier("Oersoep")) == []

    def test_any_box_status(self, db):
        assert names(db.get_suppliers_with_boxes_by_status("delivered")) == ["Oersoep"]
        assert ids(db.get_offers_by_supplier_and_box_status("Molen", "open")) == [2]

    def test_boxes_with_orders(self, db):
        assert sorted(b.box_id for b in db.get_boxes_by_offer_with_orders(1)) == ["b1"]


class TestReads:
    @pytest.mark.parametrize(
        "lookup",
        [
            lambda db: db.get_suppliers_with_ordered_offers(),
            lambda db: db.get_ordered_offers_by_supplier("Molen"),
            lambda db: db.get_suppliers_with_ready_for_labeling_offers(),
            lambda db: db.get_ready_for_labeling_offers_by_supplier("Molen"),
        ],
    )
    def test_offers_and_suppliers_are_read_once_not_per_item(self, db, lookup):
        with (
            patch.object(db, "get_offer", side_effect=AssertionError("one read per offer")),
            patch.object(db, "get_supplier_by_name", side_effect=AssertionError("one read per supplier")),
            patch.object(db.supplier_repo.table, "scan", wraps=db.supplier_repo.table.scan) as supplier_scans,
        ):
            assert lookup(db)

        assert supplier_scans.call_count <= 1


class TestOrderStatus:
    def test_suppliers_with_orders_ready_for_labeling(self, db):
        assert names(db.get_suppliers_with_ready_for_labeling_offers()) == ["Molen", "Oersoep"]

    def test_offers_of_a_supplier_ready_for_labeling(self, db):
        assert ids(db.get_ready_for_labeling_offers_by_supplier("Molen")) == [1]
        assert ids(db.get_ready_for_labeling_offers_by_supplier("Kees")) == []

    def test_boxes_with_orders_ready_for_labeling(self, db):
        assert [b.box_id for b in db.get_boxes_by_offer_with_ready_orders(1)] == ["b1"]
        assert db.get_boxes_by_offer_with_ready_orders(3) == []
