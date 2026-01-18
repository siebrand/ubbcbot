import pytest
from repositories.offer_repository import OfferRepository
from repositories.system_repository import SystemRepository
from models.entities import Offer
from decimal import Decimal

@pytest.fixture
def system_repo(dynamodb):
    # Ensure table exists (now handled by conftest.py)
    return SystemRepository()

@pytest.fixture
def offer_repo(dynamodb, system_repo):
    # Ensure table exists (now handled by conftest.py)
    return OfferRepository(system_repo)

class TestOfferRepository:
    def test_create_offer_generates_id(self, offer_repo):
        offer = Offer(name="Test IPA", price_per_unit=Decimal('2.50'))
        assert offer.offer_id == 0  # Default
        
        assert offer_repo.create_offer(offer) is True
        
        # ID should have been generated (retrieved from object passed by reference? 
        # Python passes object references, so modification in create_offer is visible)
        assert offer.offer_id == 1
        
        # Verify persistence
        saved = offer_repo.get_offer(1)
        assert saved is not None
        assert saved.name == "Test IPA"
        assert saved.offer_id == 1

    def test_get_offer(self, offer_repo):
        offer = Offer(offer_id=10, name="Stout")
        offer_repo.create_offer(offer)
        
        saved = offer_repo.get_offer(10)
        assert saved is not None
        assert saved.name == "Stout"

    def test_list_offers(self, offer_repo):
        offer1 = Offer(name="Offer 1")
        offer2 = Offer(name="Offer 2")
        offer_repo.create_offer(offer1)
        offer_repo.create_offer(offer2)
        
        offers = offer_repo.list_offers()
        assert len(offers) == 2
        ids = [o.offer_id for o in offers]
        assert 1 in ids
        assert 2 in ids

    def test_update_offer(self, offer_repo):
        offer = Offer(name="Old Name")
        offer_repo.create_offer(offer)
        
        updates = {"name": "New Name", "status": "active"}
        assert offer_repo.update_offer(offer.offer_id, updates) is True
        
        updated = offer_repo.get_offer(offer.offer_id)
        assert updated.name == "New Name"
        assert updated.status == "active"

    def test_append_offer_image(self, offer_repo):
        offer = Offer(name="Image Offer")
        offer_repo.create_offer(offer)
        
        assert offer_repo.append_offer_image(offer.offer_id, "http://example.com/img.jpg") is True
        
        updated = offer_repo.get_offer(offer.offer_id)
        assert len(updated.images) == 1
        assert updated.images[0] == "http://example.com/img.jpg"
