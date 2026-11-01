import pytest

from models.entities import Supplier
from repositories.supplier_repository import SupplierRepository


@pytest.fixture
def supplier_repo(dynamodb):
    return SupplierRepository()


class TestSupplierRepository:
    def test_create_supplier(self, supplier_repo):
        supplier = Supplier(name="Test Brewery", contact_email="test@brewery.com")
        assert supplier_repo.create_supplier(supplier) is True

        # Verify it exists
        saved = supplier_repo.get_supplier(supplier.supplier_id)
        assert saved is not None
        assert saved.name == "Test Brewery"
        assert saved.contact_email == "test@brewery.com"

    def test_create_duplicate_supplier_fails(self, supplier_repo):
        supplier1 = Supplier(name="Unique Brewery")
        supplier_repo.create_supplier(supplier1)

        # Try to create another with same name
        supplier2 = Supplier(name="Unique Brewery")
        assert supplier_repo.create_supplier(supplier2) is False

    def test_update_supplier(self, supplier_repo):
        supplier = Supplier(name="Old Name")
        supplier_repo.create_supplier(supplier)

        updates = {"name": "New Name", "status": "inactive"}
        assert supplier_repo.update_supplier(supplier.supplier_id, updates) is True

        updated = supplier_repo.get_supplier(supplier.supplier_id)
        assert updated.name == "New Name"
        assert updated.status == "inactive"

    def test_list_suppliers(self, supplier_repo):
        supplier1 = Supplier(name="Brewery A")
        supplier2 = Supplier(name="Brewery B")
        supplier_repo.create_supplier(supplier1)
        supplier_repo.create_supplier(supplier2)

        suppliers = supplier_repo.list_suppliers()
        assert len(suppliers) == 2
        names = [s.name for s in suppliers]
        assert "Brewery A" in names
        assert "Brewery B" in names

    def test_get_supplier_by_name(self, supplier_repo):
        supplier = Supplier(name="Target Brewery")
        supplier_repo.create_supplier(supplier)

        found = supplier_repo.get_supplier_by_name("Target Brewery")
        assert found is not None
        assert found.supplier_id == supplier.supplier_id

        not_found = supplier_repo.get_supplier_by_name("Nonexistent")
        assert not_found is None
