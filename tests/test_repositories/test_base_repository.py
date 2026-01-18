import pytest
from datetime import datetime
from repositories.base_repository import BaseRepository

class TestBaseRepository:
    def test_init_sets_table_name(self, dynamodb):
        repo = BaseRepository("items")
        assert repo.table_name.endswith("-items")
        assert repo.table is not None

    def test_prepare_item_serializes_datetime(self):
        repo = BaseRepository("items")
        now = datetime.now()
        item = {
            "id": "123",
            "created_at": now,
            "name": "Test"
        }
        
        prepared = repo._prepare_item(item)
        
        assert prepared["id"] == "123"
        assert prepared["created_at"] == now.isoformat()
        assert prepared["name"] == "Test"

    def test_prepare_item_removes_none(self):
        repo = BaseRepository("items")
        item = {
            "id": "123",
            "description": None,
            "name": "Test"
        }
        
        prepared = repo._prepare_item(item)
        
        assert "id" in prepared
        assert "name" in prepared
        assert "description" not in prepared

    def test_serialize_datetime(self):
        repo = BaseRepository("items")
        now = datetime.now()
        
        assert repo._serialize_datetime(now) == now.isoformat()
        assert repo._serialize_datetime("string") == "string"
        assert repo._serialize_datetime(123) == 123
