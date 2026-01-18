import pytest
from repositories.customer_repository import CustomerRepository
from repositories.system_repository import SystemRepository
from models.entities import Customer, AuthorizationStatus

@pytest.fixture
def system_repo(dynamodb):
    return SystemRepository()

@pytest.fixture
def customer_repo(dynamodb, system_repo):
    return CustomerRepository(system_repo)

class TestCustomerRepository:
    def test_create_customer(self, customer_repo):
        customer = Customer(telegram_user_id=123, username="testuser")
        created = customer_repo.create_customer(customer)
        
        assert created is not None
        assert created.username == "testuser"
        
        saved = customer_repo.get_customer(created.customer_id)
        assert saved is not None
        assert saved.telegram_user_id == 123

    def test_create_duplicate_customer_returns_existing(self, customer_repo):
        customer1 = Customer(telegram_user_id=456, username="user1")
        created1 = customer_repo.create_customer(customer1)
        
        customer2 = Customer(telegram_user_id=456, username="user2")
        created2 = customer_repo.create_customer(customer2)
        
        assert created1.customer_id == created2.customer_id
        # Should retain original username
        assert created2.username == "user1"

    def test_create_guest_customer_generates_id(self, customer_repo):
        guest = Customer(is_guest=True, first_name="Guest")
        created = customer_repo.create_customer(guest)
        
        assert created is not None
        assert created.telegram_user_id < 0  # Should be negative
        assert created.is_guest is True

    def test_get_customer_by_telegram_id(self, customer_repo):
        customer = Customer(telegram_user_id=789, username="finder")
        customer_repo.create_customer(customer)
        
        found = customer_repo.get_customer_by_telegram_id(789)
        assert found is not None
        assert found.username == "finder"

    def test_get_customers_by_status(self, customer_repo):
        c1 = Customer(telegram_user_id=1, authorization_status=AuthorizationStatus.APPROVED.value)
        c2 = Customer(telegram_user_id=2, authorization_status=AuthorizationStatus.APPROVED.value)
        c3 = Customer(telegram_user_id=3, authorization_status=AuthorizationStatus.UNAUTHORIZED.value)
        
        customer_repo.create_customer(c1)
        customer_repo.create_customer(c2)
        customer_repo.create_customer(c3)
        
        approved = customer_repo.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        assert len(approved) == 2
        
        unauthorized = customer_repo.get_customers_by_status(AuthorizationStatus.UNAUTHORIZED.value)
        assert len(unauthorized) == 1

    def test_update_customer(self, customer_repo):
        customer = Customer(telegram_user_id=999, first_name="Old")
        customer_repo.create_customer(customer)
        
        updates = {"first_name": "New", "authorization_status": AuthorizationStatus.APPROVED.value}
        assert customer_repo.update_customer(customer.customer_id, updates) is True
        
        updated = customer_repo.get_customer(customer.customer_id)
        assert updated.first_name == "New"
        assert updated.authorization_status == AuthorizationStatus.APPROVED.value

    def test_get_subscribers(self, customer_repo):
        c1 = Customer(telegram_user_id=1, subscribed_to_offers=True)
        c2 = Customer(telegram_user_id=2, subscribed_to_offers=False)
        
        customer_repo.create_customer(c1)
        customer_repo.create_customer(c2)
        
        subs = customer_repo.get_subscribers()
        assert len(subs) == 1
        assert subs[0].telegram_user_id == 1
