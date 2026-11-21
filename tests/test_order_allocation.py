"""Where the units of an order request go (services/order_allocation.py): the boxes with room, delivered first, then
ordered, then open, each group oldest first; the rest in new boxes, only while the offer may get them."""

import pytest

from models.entities import Box, BoxStatus, Offer, OfferStatus
from services.order_allocation import allocate, may_create_boxes


def box(box_id, quantity, status=BoxStatus.OPEN.value, day=1, capacity=6):
    return Box(
        box_id=box_id,
        offer_id=7,
        current_quantity=quantity,
        max_capacity=capacity,
        status=status,
        created_at=f"2026-11-{day:02d}T09:00:00+00:00",
    )


def placed(allocation):
    return [(b.box_id, units) for b, units in allocation.existing]


def test_two_delivered_boxes_with_room_share_the_request():
    allocation = allocate([box("d1", 4, "delivered"), box("d2", 4, "delivered", day=2)], 4, 6, may_create=False)

    assert placed(allocation) == [("d1", 2), ("d2", 2)]
    assert allocation.new_boxes == ()
    assert (allocation.placed, allocation.shortfall) == (4, 0)


def test_what_does_not_fit_and_may_not_get_a_box_is_the_shortfall():
    allocation = allocate([box("d1", 4, "delivered")], 4, 6, may_create=False)

    assert placed(allocation) == [("d1", 2)]
    assert (allocation.placed, allocation.shortfall) == (2, 2)


def test_no_room_at_all():
    allocation = allocate([box("d1", 6, "delivered")], 3, 6, may_create=False)

    assert (placed(allocation), allocation.placed, allocation.shortfall) == ([], 0, 3)


def test_the_rest_goes_into_new_boxes_of_the_box_size():
    allocation = allocate([box("o1", 3)], 5, 6, may_create=True)

    assert placed(allocation) == [("o1", 3)]
    assert allocation.new_boxes == (2,)
    assert allocation.placed == 5


def test_as_many_new_boxes_as_needed():
    allocation = allocate([], 5, 1, may_create=True)

    assert allocation.new_boxes == (1, 1, 1, 1, 1)


def test_the_last_new_box_may_be_partly_filled():
    assert allocate([], 5, 2, may_create=True).new_boxes == (2, 2, 1)


def test_delivered_then_ordered_then_open_each_oldest_first():
    boxes = [
        box("open-old", 5, "open", day=1),
        box("dlvr-new", 5, "delivered", day=4),
        box("ordr", 5, "ordered", day=3),
        box("dlvr-old", 5, "delivered", day=2),
    ]

    allocation = allocate(boxes, 5, 6, may_create=False)

    assert placed(allocation) == [("dlvr-old", 1), ("dlvr-new", 1), ("ordr", 1), ("open-old", 1)]
    assert allocation.shortfall == 1


def test_a_full_box_takes_nothing():
    allocation = allocate([box("f", 6, "full"), box("o", 2, day=2)], 2, 6, may_create=False)

    assert placed(allocation) == [("o", 2)]


@pytest.mark.parametrize(
    "status, boxes, expected",
    [
        (OfferStatus.ACTIVE.value, [], True),
        (OfferStatus.IMPORT.value, [box("o", 6, "full")], True),
        (OfferStatus.ACTIVE.value, [box("o", 6, "ordered")], False),
        (OfferStatus.ACTIVE.value, [box("d", 6, "delivered")], False),
        (OfferStatus.SOLD_OUT.value, [], False),
    ],
)
def test_when_an_offer_may_get_new_boxes(status, boxes, expected):
    assert may_create_boxes(Offer(offer_id=7, status=status), boxes) is expected
