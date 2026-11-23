import logging

from models.entities import Box, BoxStatus, OfferStatus

logger = logging.getLogger()


class BoxStatusManager:
    """Centralized service for all box status updates"""

    def __init__(self, db):
        self.db = db

    def get_delivered_boxes(self, boxes: list[Box]) -> list[Box]:
        """Filter boxes to only delivered status"""
        return [box for box in boxes if box.status == BoxStatus.DELIVERED.value]

    def get_available_capacity_in_delivered(self, boxes: list[Box]) -> int:
        """Calculate total available capacity in delivered boxes"""
        delivered_boxes = self.get_delivered_boxes(boxes)
        return sum(
            box.max_capacity - box.current_quantity
            for box in delivered_boxes
            if box.current_quantity < box.max_capacity
        )

    def get_available_capacity_for_orders(self, boxes: list[Box]) -> int:
        """Calculate total available capacity in all boxes (any box under capacity can accept orders)"""
        return sum(box.max_capacity - box.current_quantity for box in boxes if box.current_quantity < box.max_capacity)

    def update_box_after_order_placement(self, box_id: str, quantity_added: int) -> bool:
        """Atomically add quantity to a box, rejecting if it would exceed capacity.

        The quantity change is a single conditional UpdateItem, so two concurrent
        orders can never overfill the box. The FULL status follows the quantity that
        increment returned, and is written only while the box is still open and at
        capacity: a concurrent cancel in between cannot leave an open box marked full,
        and an ORDERED or DELIVERED box keeps its status.
        """
        box = self.db.get_box(box_id)
        if not box:
            logger.error(f"Box {box_id} not found")
            return False

        # Atomic, capacity-guarded increment: concurrent callers cannot overfill.
        new_quantity = self.db.add_to_box_quantity(box_id, quantity_added, box.max_capacity)
        if new_quantity is None:
            return False

        if new_quantity >= box.max_capacity:
            self.db.mark_box_full_if_at_capacity(box_id)

        return True

    def update_box_after_order_cancellation(self, box_id: str, quantity_removed: int) -> bool:
        """Atomically subtract quantity from a box after an order is cancelled.

        Uses the same atomic increment (with a negative delta) so a concurrent
        placement and cancellation cannot clobber each other's quantity. A FULL box
        reopens when the quantity the decrement returned is below capacity, written only
        while it is still full and below capacity (whatever the status read before the
        decrement said); ORDERED and DELIVERED boxes stay.
        """
        box = self.db.get_box(box_id)
        if not box:
            logger.error(f"Box {box_id} not found")
            return False

        # Atomic decrement (negative delta; max guard is a no-op for subtraction).
        new_quantity = self.db.add_to_box_quantity(box_id, -quantity_removed, box.max_capacity)
        if new_quantity is None:
            return False

        if new_quantity < box.max_capacity:
            self.db.reopen_box_if_below_capacity(box_id)

        return True

    def update_box_status_after_change(self, box_id: str) -> None:
        """The status follow-up of a change whose units already moved in the same write as the order (a cancel or a
        move, see DynamoDBService.cancel_order_with_box and move_order_to_box): a FULL box below capacity reopens, an
        OPEN box at capacity is FULL, each on condition of the live status and quantity. An ORDERED or DELIVERED box
        keeps its status: it is never reopened."""
        box = self.db.get_box(box_id)
        if not box:
            return
        if box.current_quantity < box.max_capacity:
            self.db.reopen_box_if_below_capacity(box_id)
        else:
            self.db.mark_box_full_if_at_capacity(box_id)

    def mark_boxes_as_ordered(self, box_ids: list) -> list:
        """Mark multiple boxes as ORDERED, returns list of updated box objects"""
        updated_boxes = []
        for box_id in box_ids:
            if self.db.update_box(box_id, {"status": BoxStatus.ORDERED.value}):
                box = self.db.get_box(box_id)
                if box:
                    updated_boxes.append(box)
        return updated_boxes

    def mark_box_as_delivered(self, box_id: str) -> Box | None:
        """Mark box as DELIVERED, returns updated box object or None"""
        if self.db.update_box(box_id, {"status": BoxStatus.DELIVERED.value}):
            return self.db.get_box(box_id)
        return None

    def update_offer_status_after_change(self, offer_id: int, finalizing_import: bool = False) -> str | None:
        """
        Check and update offer status based on box states
        Returns: new status if changed, None otherwise

        An import offer keeps its status until /finalize_import (``finalizing_import``): an order placed for it in
        the meantime (/order_for, the CSV import) does not make it active or sold out.
        """
        offer = self.db.get_offer(offer_id)
        statuses = [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value]
        if finalizing_import:
            statuses.append(OfferStatus.IMPORT.value)
        if not offer or offer.status not in statuses:
            return None

        boxes = self.db.get_boxes_by_offer(offer_id)
        if not boxes:
            return None

        # Check if there are delivered boxes
        delivered_boxes = self.get_delivered_boxes(boxes)

        new_status = None
        if delivered_boxes:
            # Use delivered box logic: check capacity in delivered boxes
            capacity = self.get_available_capacity_in_delivered(boxes)

            if capacity == 0:
                # All delivered boxes full -> SOLD_OUT
                if offer.status != OfferStatus.SOLD_OUT.value:
                    self.db.update_offer(offer_id, {"status": OfferStatus.SOLD_OUT.value})
                    new_status = OfferStatus.SOLD_OUT.value
            else:
                # Delivered boxes have space -> ACTIVE
                if offer.status != OfferStatus.ACTIVE.value:
                    self.db.update_offer(offer_id, {"status": OfferStatus.ACTIVE.value})
                    new_status = OfferStatus.ACTIVE.value
        else:
            # No delivered boxes: fall back to existing logic
            has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes)
            has_available_space = any(box.current_quantity < box.max_capacity for box in boxes)

            if has_ordered_boxes and not has_available_space:
                if offer.status != OfferStatus.SOLD_OUT.value:
                    self.db.update_offer(offer_id, {"status": OfferStatus.SOLD_OUT.value})
                    new_status = OfferStatus.SOLD_OUT.value
            else:
                if offer.status != OfferStatus.ACTIVE.value:
                    self.db.update_offer(offer_id, {"status": OfferStatus.ACTIVE.value})
                    new_status = OfferStatus.ACTIVE.value

        return new_status
