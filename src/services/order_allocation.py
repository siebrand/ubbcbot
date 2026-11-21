"""Where the units of an order request go.

An order stays in one box, so a request that spans boxes becomes one order per box. The boxes of the offer that have
room are filled first, in this order, each group oldest first: delivered boxes (stock at hand), ordered boxes (on
their way from the wholesaler), then the boxes still being filled. What is left goes into new boxes of the offer's
box size, as many as it needs, but only while the offer may get new boxes (see may_create_boxes); otherwise it is
the shortfall, which is not ordered.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from models.entities import Box, BoxStatus, OfferStatus

# The order in which boxes with room are filled (a full box has no room)
_FILL_RANK = {BoxStatus.DELIVERED.value: 0, BoxStatus.ORDERED.value: 1}
_OTHER_RANK = 2


@dataclass(frozen=True)
class Allocation:
    """The units of a request per existing box, the units of each new box, and what was requested"""

    existing: tuple[tuple[Box, int], ...]
    new_boxes: tuple[int, ...]
    requested: int

    @property
    def placed(self) -> int:
        return sum(units for _, units in self.existing) + sum(self.new_boxes)

    @property
    def shortfall(self) -> int:
        return self.requested - self.placed


def may_create_boxes(offer, boxes: Iterable[Box]) -> bool:
    """An order may make a new box for an active or import offer none of whose boxes is ordered or delivered. Room
    next to an ordered or delivered box is the admin's decision (/create_box)."""
    if offer.status not in (OfferStatus.ACTIVE.value, OfferStatus.IMPORT.value):
        return False
    return not any(box.status in (BoxStatus.ORDERED.value, BoxStatus.DELIVERED.value) for box in boxes)


def _created(box: Box) -> str:
    created = box.created_at
    return created.isoformat() if isinstance(created, datetime) else str(created or "")


def allocate(boxes: Iterable[Box], quantity: int, box_size: int, may_create: bool) -> Allocation:
    """Spread ``quantity`` units over the boxes with room and, when ``may_create``, new boxes of ``box_size``"""
    rest = quantity
    existing = []
    for box in sorted(boxes, key=lambda b: (_FILL_RANK.get(b.status, _OTHER_RANK), _created(b))):
        units = min(box.max_capacity - box.current_quantity, rest)
        if units > 0:
            existing.append((box, units))
            rest -= units
    new_boxes = []
    while may_create and rest > 0 and box_size > 0:
        units = min(box_size, rest)
        new_boxes.append(units)
        rest -= units
    return Allocation(tuple(existing), tuple(new_boxes), quantity)
