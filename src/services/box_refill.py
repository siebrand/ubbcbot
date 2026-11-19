"""Refill the boxes of an offer after cancellations: move orders from later boxes into the room of earlier ones.

Only boxes that are not yet ordered at the wholesaler (open or full) take part, and only their pending orders move:
an ordered or delivered box holds beer that is already bought. An order is moved whole, never split, so a customer's
order stays one order in one box. The plan is a pure function; the handler carries it out, one transaction per move.
"""

from dataclasses import dataclass

from models.entities import Box, BoxStatus, OfferStatus, Order, OrderStatus

REFILLABLE_BOX_STATUSES = (BoxStatus.OPEN.value, BoxStatus.FULL.value)
# The owner's rule: the boxes of a completed or inactive offer are left as they are
CLOSED_OFFER_STATUSES = (OfferStatus.COMPLETED.value, OfferStatus.INACTIVE.value)


@dataclass(frozen=True)
class Move:
    order_id: str
    customer_id: str
    quantity: int
    from_box_id: str
    to_box_id: str


def plan_refill(boxes: list[Box], orders: list[Order]) -> list[Move]:
    """The moves that fill the earliest boxes first, taking orders from the latest boxes first.

    ``boxes`` are in creation order (as ``get_boxes_by_offer`` returns them). Per gap the largest order that fits is
    taken, so a gap is filled with as few moves as possible.
    """
    candidates = [box for box in boxes if box.status in REFILLABLE_BOX_STATUSES]
    room = {box.box_id: box.max_capacity - box.current_quantity for box in candidates}
    contents: dict[str, list[Order]] = {box.box_id: [] for box in candidates}
    for order in orders:
        if order.status == OrderStatus.PENDING.value and order.box_id in contents:
            contents[order.box_id].append(order)

    moves = []
    for i, target in enumerate(candidates):
        for source in reversed(candidates[i + 1 :]):
            for order in sorted(contents[source.box_id], key=lambda o: (-o.quantity, o.order_id)):
                if room[target.box_id] <= 0:
                    break
                if order.quantity > room[target.box_id]:
                    continue
                moves.append(Move(order.order_id, order.customer_id, order.quantity, source.box_id, target.box_id))
                room[target.box_id] -= order.quantity
                room[source.box_id] += order.quantity
                contents[source.box_id].remove(order)
    return moves


def boxes_emptied(boxes: list[Box], moves: list[Move]) -> list[str]:
    """The boxes that hold nothing once the moves are done"""
    left = {box.box_id: box.current_quantity for box in boxes}
    for move in moves:
        left[move.from_box_id] -= move.quantity
        left[move.to_box_id] += move.quantity
    sources = {move.from_box_id for move in moves}
    return [box.box_id for box in boxes if box.box_id in sources and left[box.box_id] <= 0]
