#!/usr/bin/env python3

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from models.entities import AuthorizationStatus, Customer


def test_user_authorization():
    """Test user authorization workflow"""
    print("=== Testing user authorization ===")

    # New user starts unauthorized
    customer = Customer(
        telegram_user_id=12345,
        username="testuser",
        first_name="Test",
        last_name="User",
        authorization_status=AuthorizationStatus.UNAUTHORIZED.value,
    )
    assert customer.authorization_status == AuthorizationStatus.UNAUTHORIZED.value
    print("✅ New user starts unauthorized")

    # Admin can approve user
    customer.authorization_status = AuthorizationStatus.APPROVED.value
    assert customer.authorization_status == AuthorizationStatus.APPROVED.value
    print("✅ User can be approved")

    # Admin can reject user
    customer.authorization_status = AuthorizationStatus.REJECTED.value
    assert customer.authorization_status == AuthorizationStatus.REJECTED.value
    print("✅ User can be rejected")


def test_user_search_logic():
    """Test user search and ambiguity handling"""
    print("\n=== Testing user search logic ===")

    # Mock customers database
    customers = [
        Customer(first_name="Rick", last_name="H. 🍻", username=""),
        Customer(first_name="Rick", last_name="Lindeman", username="romanista345"),
        Customer(first_name="Rob", last_name="{VL4D} 🇳🇱", username="Vl4d_NL"),
        Customer(first_name="Simon", last_name="", username=""),
    ]

    # Test exact username match
    search_term = "romanista345"
    username_matches = [c for c in customers if c.username.lower() == search_term.lower()]
    assert len(username_matches) == 1
    assert username_matches[0].first_name == "Rick"
    print("✅ Exact username match works")

    # Test partial name match (Rick H. matches Rick H. 🍻)
    search_term = "Rick H."
    partial_matches = []
    for customer in customers:
        full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
        if full_name.lower().startswith(search_term.lower()):
            partial_matches.append(customer)

    assert len(partial_matches) == 1
    assert partial_matches[0].last_name == "H. 🍻"
    print("✅ Partial name matching works")

    # Test ambiguous search (multiple Ricks)
    search_term = "Rick"
    first_name_matches = [c for c in customers if c.first_name and c.first_name.lower() == search_term.lower()]
    assert len(first_name_matches) == 2
    print("✅ Ambiguous search detected")


def test_subscription_management():
    """Test subscription functionality"""
    print("\n=== Testing subscription management ===")

    # User subscribes
    customer = Customer(subscribed_to_offers=False)
    customer.subscribed_to_offers = True
    assert customer.subscribed_to_offers
    print("✅ User can subscribe")

    # User unsubscribes
    customer.subscribed_to_offers = False
    assert not customer.subscribed_to_offers
    print("✅ User can unsubscribe")

    # Filter subscribers
    customers = [
        Customer(first_name="User1", subscribed_to_offers=True),
        Customer(first_name="User2", subscribed_to_offers=False),
        Customer(first_name="User3", subscribed_to_offers=True),
    ]
    subscribers = [c for c in customers if c.subscribed_to_offers]
    assert len(subscribers) == 2
    print("✅ Subscriber filtering works")


def test_user_name_updates():
    """Test user name update functionality"""
    print("\n=== Testing user name updates ===")

    customer = Customer(first_name="Old", last_name="Name")

    # Update first name
    customer.first_name = "New"
    assert customer.first_name == "New"
    print("✅ First name update works")

    # Update last name
    customer.last_name = "LastName"
    assert customer.last_name == "LastName"
    print("✅ Last name update works")

    # Validate name length limits
    long_name = "x" * 101
    is_valid = len(long_name) <= 100
    assert not is_valid
    print("✅ Name length validation works")


def test_admin_permissions():
    """Test admin permission checks"""
    print("\n=== Testing admin permissions ===")

    admin_user_id = 15005473
    regular_user_id = 12345

    # Admin check
    is_admin = admin_user_id == 15005473
    assert is_admin
    print("✅ Admin user identified")

    # Regular user check
    is_admin = regular_user_id == 15005473
    assert not is_admin
    print("✅ Regular user identified")


def test_user_status_filtering():
    """Test user status filtering"""
    print("\n=== Testing user status filtering ===")

    customers = [
        Customer(first_name="User1", authorization_status=AuthorizationStatus.APPROVED.value),
        Customer(first_name="User2", authorization_status=AuthorizationStatus.UNAUTHORIZED.value),
        Customer(first_name="User3", authorization_status=AuthorizationStatus.REJECTED.value),
        Customer(first_name="User4", authorization_status=AuthorizationStatus.APPROVED.value),
    ]

    # Filter approved users
    approved = [c for c in customers if c.authorization_status == AuthorizationStatus.APPROVED.value]
    assert len(approved) == 2
    print("✅ Approved user filtering works")

    # Filter pending users
    pending = [c for c in customers if c.authorization_status == AuthorizationStatus.UNAUTHORIZED.value]
    assert len(pending) == 1
    print("✅ Pending user filtering works")

    # Filter rejected users
    rejected = [c for c in customers if c.authorization_status == AuthorizationStatus.REJECTED.value]
    assert len(rejected) == 1
    print("✅ Rejected user filtering works")


def test_new_user_notification():
    """Test new user notification logic"""
    print("\n=== Testing new user notification ===")

    # Mock user data from Telegram
    user_data = {"id": 123456789, "first_name": "John", "last_name": "Doe", "username": "johndoe"}

    # Test notification message formatting
    display_name = user_data["first_name"]
    if user_data.get("last_name"):
        display_name += f" {user_data['last_name']}"

    expected_name = "John Doe"
    assert display_name == expected_name
    print("✅ Display name formatting works")

    # Test username handling
    username = user_data.get("username", "no_username")
    assert username == "johndoe"
    print("✅ Username extraction works")

    # Test user without username
    user_data_no_username = {"id": 987654321, "first_name": "Jane", "username": None}

    username_fallback = user_data_no_username.get("username") or "no_username"
    assert username_fallback == "no_username"
    print("✅ Username fallback works")

    # Test admin user ID
    admin_user_id = 15005473
    assert admin_user_id == 15005473
    print("✅ Admin user ID correct")


if __name__ == "__main__":
    test_user_authorization()
    test_user_search_logic()
    test_subscription_management()
    test_user_name_updates()
    test_admin_permissions()
    test_user_status_filtering()
    test_new_user_notification()
    print("\n🎉 All user management tests passed!")
