from decimal import Decimal

import pytest

from models.entities import Order
from repositories.order_repository import OrderRepository


@pytest.fixture
def order_repo(dynamodb):
    return OrderRepository()


class TestOrderRepository:
    def test_create_order(self, order_repo):
        order = Order(
            order_id="order-1",
            customer_id="cust-1",
            offer_id=1,
            box_id="box-1",
            quantity=5,
            unit_price=Decimal("10.0"),
            total_price=Decimal("50.0"),
            status="active",
        )
        result = order_repo.create_order(order)

        assert result is not None
        assert result.order_id == "order-1"

        # Verify it exists
        saved = order_repo.get_order("order-1")
        assert saved is not None
        assert saved.customer_id == "cust-1"
        assert saved.quantity == 5

    def test_get_order(self, order_repo):
        order = Order(
            order_id="order-2",
            customer_id="cust-2",
            offer_id=2,
            box_id="box-2",
            quantity=3,
            unit_price=Decimal("15.0"),
            total_price=Decimal("45.0"),
            status="active",
        )
        order_repo.create_order(order)

        retrieved = order_repo.get_order("order-2")
        assert retrieved is not None
        assert retrieved.order_id == "order-2"
        assert retrieved.quantity == 3

    def test_get_order_not_found(self, order_repo):
        result = order_repo.get_order("nonexistent")
        assert result is None

    def test_get_orders_by_customer(self, order_repo):
        order1 = Order(
            order_id="order-3",
            customer_id="cust-3",
            offer_id=1,
            box_id="box-1",
            quantity=2,
            unit_price=Decimal("10"),
            total_price=Decimal("20"),
            status="active",
        )
        order2 = Order(
            order_id="order-4",
            customer_id="cust-3",
            offer_id=2,
            box_id="box-2",
            quantity=3,
            unit_price=Decimal("10"),
            total_price=Decimal("30"),
            status="active",
        )
        order3 = Order(
            order_id="order-5",
            customer_id="cust-4",
            offer_id=1,
            box_id="box-1",
            quantity=1,
            unit_price=Decimal("10"),
            total_price=Decimal("10"),
            status="active",
        )

        order_repo.create_order(order1)
        order_repo.create_order(order2)
        order_repo.create_order(order3)

        orders = order_repo.get_orders_by_customer("cust-3")
        assert len(orders) == 2
        order_ids = [o.order_id for o in orders]
        assert "order-3" in order_ids
        assert "order-4" in order_ids

    def test_get_orders_by_offer(self, order_repo):
        order1 = Order(
            order_id="order-6",
            customer_id="cust-5",
            offer_id=5,
            box_id="box-5",
            quantity=2,
            unit_price=Decimal("10"),
            total_price=Decimal("20"),
            status="active",
        )
        order2 = Order(
            order_id="order-7",
            customer_id="cust-6",
            offer_id=5,
            box_id="box-5",
            quantity=3,
            unit_price=Decimal("10"),
            total_price=Decimal("30"),
            status="active",
        )
        order3 = Order(
            order_id="order-8",
            customer_id="cust-7",
            offer_id=6,
            box_id="box-6",
            quantity=1,
            unit_price=Decimal("10"),
            total_price=Decimal("10"),
            status="active",
        )

        order_repo.create_order(order1)
        order_repo.create_order(order2)
        order_repo.create_order(order3)

        orders = order_repo.get_orders_by_offer(5)
        assert len(orders) == 2
        order_ids = [o.order_id for o in orders]
        assert "order-6" in order_ids
        assert "order-7" in order_ids

    def test_get_orders_by_box(self, order_repo):
        order1 = Order(
            order_id="order-9",
            customer_id="cust-8",
            offer_id=7,
            box_id="box-7",
            quantity=2,
            unit_price=Decimal("10"),
            total_price=Decimal("20"),
            status="active",
        )
        order2 = Order(
            order_id="order-10",
            customer_id="cust-9",
            offer_id=7,
            box_id="box-7",
            quantity=3,
            unit_price=Decimal("10"),
            total_price=Decimal("30"),
            status="active",
        )

        order_repo.create_order(order1)
        order_repo.create_order(order2)

        orders = order_repo.get_orders_by_box("box-7")
        assert len(orders) == 2

    def test_update_order(self, order_repo):
        order = Order(
            order_id="order-11",
            customer_id="cust-10",
            offer_id=8,
            box_id="box-8",
            quantity=5,
            unit_price=Decimal("10"),
            total_price=Decimal("50"),
            status="active",
        )
        order_repo.create_order(order)

        updates = {"status": "completed", "total_price": Decimal("45.0")}
        assert order_repo.update_order("order-11", updates) is True

        updated = order_repo.get_order("order-11")
        assert updated.status == "completed"
        assert updated.total_price == Decimal("45.0")

    def test_delete_order(self, order_repo):
        order = Order(
            order_id="order-12",
            customer_id="cust-11",
            offer_id=9,
            box_id="box-9",
            quantity=2,
            unit_price=Decimal("10"),
            total_price=Decimal("20"),
            status="active",
        )
        order_repo.create_order(order)

        assert order_repo.get_order("order-12") is not None
        assert order_repo.delete_order("order-12") is True
        assert order_repo.get_order("order-12") is None

    def test_get_all_orders(self, order_repo):
        order1 = Order(
            order_id="order-13",
            customer_id="cust-12",
            offer_id=10,
            box_id="box-10",
            quantity=1,
            unit_price=Decimal("10"),
            total_price=Decimal("10"),
            status="active",
        )
        order2 = Order(
            order_id="order-14",
            customer_id="cust-13",
            offer_id=11,
            box_id="box-11",
            quantity=2,
            unit_price=Decimal("10"),
            total_price=Decimal("20"),
            status="cancelled",
        )

        order_repo.create_order(order1)
        order_repo.create_order(order2)

        all_orders = order_repo.get_all_orders()
        assert len(all_orders) >= 2

    def test_get_all_orders_with_status_filter(self, order_repo):
        order1 = Order(
            order_id="order-15",
            customer_id="cust-14",
            offer_id=12,
            box_id="box-12",
            quantity=1,
            unit_price=Decimal("10"),
            total_price=Decimal("10"),
            status="active",
        )
        order2 = Order(
            order_id="order-16",
            customer_id="cust-15",
            offer_id=13,
            box_id="box-13",
            quantity=2,
            unit_price=Decimal("10"),
            total_price=Decimal("20"),
            status="cancelled",
        )

        order_repo.create_order(order1)
        order_repo.create_order(order2)

        active_orders = order_repo.get_all_orders(statuses=["active"])
        active_ids = [o.order_id for o in active_orders]
        assert "order-15" in active_ids
