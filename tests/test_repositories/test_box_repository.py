import pytest
from repositories.box_repository import BoxRepository
from models.entities import Box

@pytest.fixture
def box_repo(dynamodb):
    return BoxRepository()

class TestBoxRepository:
    def test_create_box(self, box_repo):
        box = Box(box_id="box-1", offer_id=1, current_quantity=0, max_capacity=12, status="open")
        result = box_repo.create_box(box)
        
        assert result is not None
        assert result.box_id == "box-1"
        
        # Verify it exists
        saved = box_repo.get_box("box-1")
        assert saved is not None
        assert saved.offer_id == 1
        assert saved.current_quantity == 0
        assert saved.max_capacity == 12
        assert saved.status == "open"

    def test_get_box(self, box_repo):
        box = Box(box_id="box-2", offer_id=2, current_quantity=5, max_capacity=10, status="open")
        box_repo.create_box(box)
        
        retrieved = box_repo.get_box("box-2")
        assert retrieved is not None
        assert retrieved.box_id == "box-2"
        assert retrieved.current_quantity == 5
        assert retrieved.max_capacity == 10

    def test_get_box_not_found(self, box_repo):
        result = box_repo.get_box("nonexistent")
        assert result is None

    def test_get_boxes_by_offer(self, box_repo):
        box1 = Box(box_id="box-3", offer_id=3, current_quantity=0, max_capacity=12, status="open")
        box2 = Box(box_id="box-4", offer_id=3, current_quantity=12, max_capacity=12, status="full")
        box3 = Box(box_id="box-5", offer_id=4, current_quantity=0, max_capacity=12, status="open")
        
        box_repo.create_box(box1)
        box_repo.create_box(box2)
        box_repo.create_box(box3)
        
        boxes = box_repo.get_boxes_by_offer(3)
        assert len(boxes) == 2
        box_ids = [b.box_id for b in boxes]
        assert "box-3" in box_ids
        assert "box-4" in box_ids
        assert "box-5" not in box_ids

    def test_get_all_boxes(self, box_repo):
        box1 = Box(box_id="box-6", offer_id=5, current_quantity=0, max_capacity=12, status="open")
        box2 = Box(box_id="box-7", offer_id=6, current_quantity=6, max_capacity=12, status="open")
        
        box_repo.create_box(box1)
        box_repo.create_box(box2)
        
        all_boxes = box_repo.get_all_boxes()
        assert len(all_boxes) >= 2
        box_ids = [b.box_id for b in all_boxes]
        assert "box-6" in box_ids
        assert "box-7" in box_ids

    def test_update_box(self, box_repo):
        box = Box(box_id="box-8", offer_id=7, current_quantity=0, max_capacity=12, status="open")
        box_repo.create_box(box)
        
        updates = {"current_quantity": 8, "status": "open"}
        assert box_repo.update_box("box-8", updates) is True
        
        updated = box_repo.get_box("box-8")
        assert updated.current_quantity == 8
        assert updated.status == "open"

    def test_update_box_to_full(self, box_repo):
        box = Box(box_id="box-9", offer_id=8, current_quantity=10, max_capacity=12, status="open")
        box_repo.create_box(box)
        
        updates = {"current_quantity": 12, "status": "full"}
        assert box_repo.update_box("box-9", updates) is True
        
        updated = box_repo.get_box("box-9")
        assert updated.current_quantity == 12
        assert updated.status == "full"

    def test_delete_box(self, box_repo):
        box = Box(box_id="box-10", offer_id=9, current_quantity=0, max_capacity=12, status="open")
        box_repo.create_box(box)
        
        # Verify it exists
        assert box_repo.get_box("box-10") is not None
        
        # Delete it
        assert box_repo.delete_box("box-10") is True
        
        # Verify it's gone
        assert box_repo.get_box("box-10") is None

    def test_decimal_conversion(self, box_repo):
        """Test that Decimal values from DynamoDB are properly converted to int"""
        box = Box(box_id="box-11", offer_id=10, current_quantity=7, max_capacity=24, status="open")
        box_repo.create_box(box)
        
        retrieved = box_repo.get_box("box-11")
        assert isinstance(retrieved.current_quantity, int)
        assert isinstance(retrieved.max_capacity, int)
        assert retrieved.current_quantity == 7
        assert retrieved.max_capacity == 24
