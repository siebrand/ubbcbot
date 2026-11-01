"""Tests for update_id idempotency (ProcessedUpdateRepository)."""

import pytest

from repositories.processed_update_repository import ProcessedUpdateRepository


@pytest.fixture
def repo(dynamodb):
    return ProcessedUpdateRepository()


class TestProcessedUpdateRepository:
    def test_first_time_returns_true(self, repo):
        assert repo.mark_processed(1001) is True

    def test_duplicate_returns_false(self, repo):
        assert repo.mark_processed(2002) is True
        # Same update_id re-delivered -> rejected by the conditional write
        assert repo.mark_processed(2002) is False

    def test_distinct_update_ids_independent(self, repo):
        assert repo.mark_processed(3003) is True
        assert repo.mark_processed(3004) is True

    def test_sets_ttl_attribute(self, repo):
        repo.mark_processed(4004)
        item = repo.table.get_item(Key={"update_id": "4004"})["Item"]
        assert "ttl" in item
        assert int(item["ttl"]) > 0
