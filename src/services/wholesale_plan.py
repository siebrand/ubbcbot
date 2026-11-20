"""Which pending orders a wholesale order can serve: oldest first, the one that only partly fits is reduced.

Only the decision lives here; handlers/admin/offer/management.py writes it to the database and tells everyone.
"""

from dataclasses import dataclass, field


@dataclass
class WholesalePlan:
    units_available: int
    fulfilled: list = field(default_factory=list)  # orders that fit as they are
    reduced: list = field(default_factory=list)  # (order, old quantity, new quantity)
    cancelled: list = field(default_factory=list)  # orders that do not fit at all
    # orders that changed between the plan and its write (cancelled, moved): left as they are, out of the lists above
    changed: list = field(default_factory=list)

    @property
    def units_allocated(self) -> int:
        return sum(order.quantity for order in self.fulfilled) + sum(new for _, _, new in self.reduced)

    @property
    def units_left(self) -> int:
        return self.units_available - self.units_allocated


def boxes_needed(units: int, box_size: int) -> int:
    """Whole boxes for this many units"""
    return (units + box_size - 1) // box_size


def plan_wholesale(pending_orders: list, boxes_ordered: int, box_size: int) -> WholesalePlan:
    """Serve the pending orders first in, first out from ``boxes_ordered`` boxes of ``box_size`` units"""
    plan = WholesalePlan(units_available=boxes_ordered * box_size)
    for order in sorted(pending_orders, key=lambda o: o.created_at):
        room = plan.units_left
        if room <= 0:
            plan.cancelled.append(order)
        elif order.quantity <= room:
            plan.fulfilled.append(order)
        else:
            plan.reduced.append((order, order.quantity, room))
    return plan
