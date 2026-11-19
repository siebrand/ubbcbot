"""Which pending orders a wholesale order serves: first in, first out."""

from types import SimpleNamespace

from services.wholesale_plan import boxes_needed, plan_wholesale


def order(name, quantity, day):
    return SimpleNamespace(name=name, quantity=quantity, created_at=f"2026-11-{day:02d}")


def names(orders) -> list[str]:
    return [o.name for o in orders]


def test_orders_that_fit_are_fulfilled_oldest_first():
    plan = plan_wholesale([order("b", 2, 2), order("a", 3, 1)], boxes_ordered=1, box_size=6)

    assert names(plan.fulfilled) == ["a", "b"]
    assert plan.reduced == plan.cancelled == []
    assert (plan.units_allocated, plan.units_left) == (5, 1)


def test_the_first_order_that_does_not_fit_is_reduced_and_the_rest_cancelled():
    plan = plan_wholesale([order("a", 4, 1), order("b", 4, 2), order("c", 1, 3)], boxes_ordered=1, box_size=6)

    assert names(plan.fulfilled) == ["a"]
    assert [(o.name, old, new) for o, old, new in plan.reduced] == [("b", 4, 2)]
    assert names(plan.cancelled) == ["c"]
    assert plan.units_left == 0


def test_more_boxes_than_needed_leaves_room():
    plan = plan_wholesale([order("a", 4, 1)], boxes_ordered=2, box_size=6)

    assert plan.units_left == 8


def test_no_pending_orders():
    plan = plan_wholesale([], boxes_ordered=1, box_size=6)

    assert (plan.fulfilled, plan.reduced, plan.cancelled, plan.units_left) == ([], [], [], 6)


def test_boxes_needed_rounds_up():
    assert [boxes_needed(units, 6) for units in (0, 1, 6, 7, 12)] == [0, 1, 1, 2, 2]
