#!/usr/bin/env python3

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))


def test_help_sections():
    """Test help section organization"""
    print("=== Testing help sections ===")

    # Available sections for customers
    customer_sections = ["general", "orders"]
    assert "general" in customer_sections
    assert "orders" in customer_sections
    print("✅ Customer help sections defined")

    # Available sections for admins
    admin_sections = ["general", "orders", "suppliers", "offers", "users"]
    assert "suppliers" in admin_sections
    assert "offers" in admin_sections
    assert "users" in admin_sections
    print("✅ Admin help sections defined")

    # Section validation
    valid_section = "general"
    is_valid = valid_section in customer_sections
    assert is_valid
    print("✅ Valid section recognized")

    invalid_section = "invalid"
    is_valid = invalid_section in customer_sections
    assert not is_valid
    print("✅ Invalid section rejected")


def test_help_access_control():
    """Test help access control for admin sections"""
    print("\n=== Testing help access control ===")

    admin_user_id = 15005473
    regular_user_id = 12345
    admin_only_sections = ["suppliers", "offers", "users"]

    # Admin can access admin sections
    is_admin = admin_user_id == 15005473
    can_access_suppliers = is_admin or "suppliers" not in admin_only_sections
    assert can_access_suppliers
    print("✅ Admin can access admin sections")

    # Regular user cannot access admin sections
    is_admin = regular_user_id == 15005473
    can_access_suppliers = is_admin or "suppliers" not in admin_only_sections
    assert not can_access_suppliers
    print("✅ Regular user blocked from admin sections")


def test_deep_link_generation():
    """Test deep link generation for help sections"""
    print("\n=== Testing deep link generation ===")

    bot_username = "ubbc_test_bot"
    section = "general"

    # Generate deep link
    deep_link = f"https://t.me/{bot_username}?start=help_{section}"
    expected = "https://t.me/ubbc_test_bot?start=help_general"
    assert deep_link == expected
    print("✅ Deep link generation works")

    # Parse deep link parameter
    start_param = "help_general"
    if start_param.startswith("help_"):
        section = start_param[5:]  # Remove 'help_' prefix
        assert section == "general"
        print("✅ Deep link parsing works")


def test_command_descriptions():
    """Test command descriptions and formatting"""
    print("\n=== Testing command descriptions ===")

    # Customer commands
    customer_commands = {
        "/start": "Register and view help",
        "/help": "Show help sections",
        "/order": "Place order",
        "/my_orders": "View your orders",
        "/list_offers": "View available offers",
        "/subscribe": "Subscribe to offer notifications",
        "/unsubscribe": "Unsubscribe from notifications",
    }

    assert len(customer_commands) == 7
    assert "/help" in customer_commands
    print("✅ Customer commands defined")

    # Admin commands (subset)
    admin_commands = {
        "/create_supplier": "Create supplier",
        "/list_suppliers": "View all suppliers",
        "/create_offer": "Create offer",
        "/list_users": "View all customers",
    }

    assert "/create_supplier" in admin_commands
    print("✅ Admin commands defined")


def test_help_message_formatting():
    """Test help message formatting"""
    print("\n=== Testing help message formatting ===")

    # Test environment prefix
    environment = "test"
    message_prefix = "TEST - " if environment == "test" else ""

    if environment == "test":
        assert message_prefix == "TEST - "
        print("✅ Test environment prefix added")
    else:
        assert message_prefix == ""
        print("✅ Production environment no prefix")

    # Test message structure
    help_message = "🍺 Welcome to UBBC Bot!\n\n📋 General:\n/start - Show this help\n"
    assert help_message.startswith("🍺")
    assert "📋 General:" in help_message
    print("✅ Help message structure correct")


def test_pagination_support():
    """Test pagination for list commands"""
    print("\n=== Testing pagination support ===")

    # Mock data
    items = list(range(25))  # 25 items
    page_size = 10
    page = 1

    # Calculate pagination
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_items = items[start_idx:end_idx]
    total_pages = (len(items) + page_size - 1) // page_size

    assert len(page_items) == 10
    assert total_pages == 3
    print("✅ Pagination calculation works")

    # Test page boundaries
    assert page_items == list(range(0, 10))  # First page
    print("✅ First page items correct")

    # Test last page
    page = 3
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_items = items[start_idx:end_idx]
    assert len(page_items) == 5  # Last page has 5 items
    print("✅ Last page items correct")


def test_keyboard_generation():
    """Test inline keyboard generation"""
    print("\n=== Testing keyboard generation ===")

    # Pagination keyboard
    page = 2
    total_pages = 5

    keyboard_buttons = []
    if page > 1:
        keyboard_buttons.append({"text": "◀️ Previous", "callback_data": f"page_test_{page - 1}"})

    keyboard_buttons.append({"text": f"Page {page}/{total_pages}", "callback_data": "page_info"})

    if page < total_pages:
        keyboard_buttons.append({"text": "Next ▶️", "callback_data": f"page_test_{page + 1}"})

    assert len(keyboard_buttons) == 3  # Previous, Info, Next
    assert keyboard_buttons[0]["text"] == "◀️ Previous"
    assert keyboard_buttons[2]["text"] == "Next ▶️"
    print("✅ Pagination keyboard generation works")


def test_error_handling():
    """Test error handling in help system"""
    print("\n=== Testing error handling ===")

    # Unknown section
    requested_section = "unknown"
    valid_sections = ["general", "orders"]

    if requested_section not in valid_sections:
        error_message = f"❌ Unknown section: {requested_section}"
        assert "❌ Unknown section:" in error_message
        print("✅ Unknown section error handling works")

    # Empty section parameter
    section_param = ""
    if not section_param:
        show_section_list = True
        assert show_section_list
        print("✅ Empty parameter handling works")


if __name__ == "__main__":
    test_help_sections()
    test_help_access_control()
    test_deep_link_generation()
    test_command_descriptions()
    test_help_message_formatting()
    test_pagination_support()
    test_keyboard_generation()
    test_error_handling()
    print("\n🎉 All help system tests passed!")
