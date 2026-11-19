"""The refill plan: which pending orders move from later boxes into the room of earlier ones (audit 3, T3)."""

from models.entities import Box, BoxStatus, Order, OrderStatus
from services.box_refill import Move, boxes_emptied, plan_refill


def box(box_id, quantity, capacity=6, status=BoxStatus.OPEN.value):
    return Box(box_id=box_id, offer_id=7, current_quantity=quantity, max_capacity=capacity, status=status)


def order(order_id, box_id, quantity, status=OrderStatus.PENDING.value):
    return Order(
        order_id=order_id, customer_id=f"cust-{order_id}", box_id=box_id, offer_id=7, quantity=quantity, status=status
    )


def moved(moves):
    return [(m.order_id, m.from_box_id, m.to_box_id) for m in moves]


def test_a_later_box_is_emptied_into_the_room_of_an_earlier_one():
    boxes = [box("a", 4), box("b", 2)]
    moves = plan_refill(boxes, [order("o1", "a", 4), order("o2", "b", 2)])

    assert moves == [Move("o2", "cust-o2", 2, "b", "a")]
    assert boxes_emptied(boxes, moves) == ["b"]


def test_the_latest_box_is_taken_from_first():
    boxes = [box("a", 3), box("b", 6), box("c", 3)]
    orders = [order("o1", "a", 3), order("o2", "b", 6), order("o3", "c", 3)]

    assert moved(plan_refill(boxes, orders)) == [("o3", "c", "a")]


def test_the_largest_order_that_fits_fills_the_gap():
    boxes = [box("a", 3), box("b", 6)]
    orders = [order("o1", "a", 3), order("o2", "b", 1), order("o3", "b", 4), order("o4", "b", 3), order("o5", "b", 2)]

    moves = plan_refill(boxes, orders)

    assert moved(moves) == [("o4", "b", "a")]  # 4 does not fit, 3 does
    assert boxes_emptied(boxes, moves) == []


def test_an_order_is_never_split():
    boxes = [box("a", 4), box("b", 3)]

    assert plan_refill(boxes, [order("o1", "a", 4), order("o2", "b", 3)]) == []


def test_boxes_already_ordered_or_delivered_take_no_part():
    boxes = [
        box("a", 2, status=BoxStatus.ORDERED.value),
        box("b", 2, status=BoxStatus.DELIVERED.value),
        box("c", 2),
        box("d", 2, status=BoxStatus.ORDERED.value),
    ]
    orders = [order("o1", "a", 2), order("o2", "b", 2), order("o3", "c", 2), order("o4", "d", 2)]

    assert plan_refill(boxes, orders) == []


def test_only_pending_orders_move():
    boxes = [box("a", 2), box("b", 2)]
    orders = [order("o1", "a", 2), order("o2", "b", 2, status=OrderStatus.CANCELLED.value)]

    assert plan_refill(boxes, orders) == []


def test_several_gaps_are_filled_from_the_back():
    boxes = [box("a", 4), box("b", 4), box("c", 2), box("d", 2)]
    orders = [order("o1", "a", 4), order("o2", "b", 4), order("o3", "c", 2), order("o4", "d", 2)]

    moves = plan_refill(boxes, orders)

    assert moved(moves) == [("o4", "d", "a"), ("o3", "c", "b")]
    assert boxes_emptied(boxes, moves) == ["c", "d"]


def test_full_boxes_without_room_give_nothing_to_do():
    boxes = [box("a", 6, status=BoxStatus.FULL.value), box("b", 2)]

    assert plan_refill(boxes, [order("o1", "a", 6), order("o2", "b", 2)]) == []
