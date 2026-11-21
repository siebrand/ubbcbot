"""The box status after a quantity change follows the quantity the increment left, not the box read before it
(audit 6, B1): a concurrent placement or cancel between the read and the increment must not leave a full box open or
an open box full, and a status is never written over an ordered or delivered box."""

import pytest

from models.entities import Box, BoxStatus
from services.box_status_manager import BoxStatusManager
from services.database import DynamoDBService


@pytest.fixture
def db(dynamodb):
    return DynamoDBService()


def make_box(db, quantity, status=BoxStatus.OPEN.value, box_id="box-1"):
    assert db.create_box(Box(box_id=box_id, offer_id=7, current_quantity=quantity, max_capacity=6, status=status))


def concurrent_after_read(db, change):
    """Let ``change`` happen right after the manager has read the box, before its own increment"""
    read = db.get_box

    def get_box(box_id):
        box = read(box_id)
        change()
        return box

    db.get_box = get_box


def test_a_cancel_between_read_and_placement_leaves_the_box_open(db):
    make_box(db, 4)
    concurrent_after_read(db, lambda: db.box_repo.increment_box_quantity("box-1", -2, 6))

    assert BoxStatusManager(db).update_box_after_order_placement("box-1", 2)

    box = db.box_repo.get_box("box-1")
    assert box.current_quantity == 4
    assert box.status == BoxStatus.OPEN.value


def test_a_placement_that_filled_the_box_between_read_and_cancel_reopens_it(db):
    make_box(db, 5)

    def fill():
        db.box_repo.increment_box_quantity("box-1", 1, 6)
        db.box_repo.update_box("box-1", {"status": BoxStatus.FULL.value})

    concurrent_after_read(db, fill)

    assert BoxStatusManager(db).update_box_after_order_cancellation("box-1", 1)

    box = db.box_repo.get_box("box-1")
    assert box.current_quantity == 5
    assert box.status == BoxStatus.OPEN.value


def test_the_last_unit_of_an_open_box_makes_it_full(db):
    make_box(db, 5)

    assert BoxStatusManager(db).update_box_after_order_placement("box-1", 1)

    assert db.box_repo.get_box("box-1").status == BoxStatus.FULL.value


@pytest.mark.parametrize("status", [BoxStatus.ORDERED.value, BoxStatus.DELIVERED.value])
def test_filling_an_ordered_or_delivered_box_keeps_its_status(db, status):
    make_box(db, 5, status)

    assert BoxStatusManager(db).update_box_after_order_placement("box-1", 1)

    box = db.box_repo.get_box("box-1")
    assert box.current_quantity == 6
    assert box.status == status


@pytest.mark.parametrize("status", [BoxStatus.ORDERED.value, BoxStatus.DELIVERED.value])
def test_a_cancel_from_an_ordered_or_delivered_box_keeps_its_status(db, status):
    make_box(db, 6, status)

    assert BoxStatusManager(db).update_box_after_order_cancellation("box-1", 2)

    box = db.box_repo.get_box("box-1")
    assert box.current_quantity == 4
    assert box.status == status


def test_a_placement_that_would_overfill_changes_nothing(db):
    make_box(db, 5)

    assert not BoxStatusManager(db).update_box_after_order_placement("box-1", 2)

    box = db.box_repo.get_box("box-1")
    assert box.current_quantity == 5
    assert box.status == BoxStatus.OPEN.value


def test_the_status_after_a_change_is_written_on_condition_of_the_live_quantity(db):
    make_box(db, 6, BoxStatus.FULL.value)
    db.box_repo.increment_box_quantity("box-1", -1, 6)

    BoxStatusManager(db).update_box_status_after_change("box-1")

    assert db.box_repo.get_box("box-1").status == BoxStatus.OPEN.value


def test_add_to_box_quantity_returns_the_new_quantity(db):
    make_box(db, 2)

    assert db.add_to_box_quantity("box-1", 3, 6) == 5
    assert db.add_to_box_quantity("box-1", 2, 6) is None
    assert db.add_to_box_quantity("box-1", -4, 6) == 1
