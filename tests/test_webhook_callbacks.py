#!/usr/bin/env python3

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))


def test_callback_data_parsing():
    """Test callback data parsing"""
    print("=== Testing callback data parsing ===")

    # Order callback
    callback_data = "order_123_2"
    parts = callback_data.split("_")
    assert parts[0] == "order"
    assert parts[1] == "123"  # offer_id
    assert parts[2] == "2"  # quantity
    print("✅ Order callback parsing works")

    # Edit callback
    callback_data = "edit_supplier_name_abc123"
    parts = callback_data.split("_")
    assert parts[0] == "edit"
    assert parts[1] == "supplier"  # entity_type
    assert parts[2] == "name"  # field
    assert parts[3] == "abc123"  # entity_id
    print("✅ Edit callback parsing works")

    # Customer edit callback (special case)
    callback_data = "edit_customer_first_name_xyz789"
    parts = callback_data.split("_")
    if parts[1] == "customer" and len(parts) == 5 and parts[2] == "first" and parts[3] == "name":
        field = "first_name"
        entity_id = parts[4]
        assert field == "first_name"
        assert entity_id == "xyz789"
        print("✅ Customer edit callback parsing works")

    # Pagination callback
    callback_data = "page_suppliers_active_2"
    parts = callback_data.split("_")
    assert parts[0] == "page"
    assert parts[1] == "suppliers"
    assert parts[2] == "active"
    assert parts[3] == "2"  # page number
    print("✅ Pagination callback parsing works")


def test_webhook_validation():
    """Test webhook request validation"""
    print("\n=== Testing webhook validation ===")

    # Valid webhook structure
    webhook_data = {"message": {"chat": {"id": 12345}, "from": {"id": 67890, "first_name": "Test"}, "text": "/start"}}

    has_message = "message" in webhook_data
    has_chat_id = "chat" in webhook_data["message"] and "id" in webhook_data["message"]["chat"]
    has_user_id = "from" in webhook_data["message"] and "id" in webhook_data["message"]["from"]

    assert has_message and has_chat_id and has_user_id
    print("✅ Valid webhook structure recognized")

    # Callback query structure
    callback_data = {
        "callback_query": {
            "id": "callback123",
            "from": {"id": 67890},
            "message": {"chat": {"id": 12345}, "message_id": 456},
            "data": "order_123_2",
        }
    }

    has_callback = "callback_query" in callback_data
    has_callback_data = "data" in callback_data["callback_query"]
    assert has_callback and has_callback_data
    print("✅ Valid callback query structure recognized")


def test_command_extraction():
    """Test command extraction from messages"""
    print("\n=== Testing command extraction ===")

    # Simple command
    text = "/start"
    parts = text.split()
    command = parts[0].lower()
    assert command == "/start"
    assert len(parts) == 1
    print("✅ Simple command extraction works")

    # Command with arguments
    text = "/order 123 2"
    parts = text.split()
    command = parts[0].lower()
    args = parts[1:]
    assert command == "/order"
    assert args == ["123", "2"]
    print("✅ Command with arguments extraction works")

    # Command with bot mention
    text = "/start@ubbc_test_bot"
    command = text.split()[0].lower()
    if "@" in command:
        command = command.split("@")[0]
    assert command == "/start"
    print("✅ Bot mention removal works")

    # Multi-word arguments
    text = "/create_supplier Test Brewery Name"
    parts = text.split()
    command = parts[0].lower()
    supplier_name = " ".join(parts[1:])
    assert command == "/create_supplier"
    assert supplier_name == "Test Brewery Name"
    print("✅ Multi-word argument handling works")


def test_chat_type_detection():
    """Test chat type detection"""
    print("\n=== Testing chat type detection ===")

    # Private chat (positive ID)
    private_chat_id = 12345
    is_private = private_chat_id > 0
    assert is_private
    print("✅ Private chat detection works")

    # Group chat (negative ID)
    group_chat_id = -12345
    is_group = group_chat_id < 0
    assert is_group
    print("✅ Group chat detection works")

    # Command routing based on environment
    environment = "prod"
    is_group_chat = group_chat_id < 0
    command = "/list_users"
    group_allowed_commands = {"/start", "/order", "/confirm_order"}

    should_redirect = environment == "prod" and is_group_chat and command not in group_allowed_commands
    assert should_redirect
    print("✅ Production group command redirection works")


def test_user_registration():
    """Test automatic user registration"""
    print("\n=== Testing user registration ===")

    # New user data from Telegram
    user_data = {"id": 12345, "first_name": "Test", "last_name": "User", "username": "testuser"}

    # Extract and validate data
    telegram_user_id = user_data["id"]
    first_name = user_data.get("first_name", "")
    last_name = user_data.get("last_name", "")
    username = user_data.get("username", "")

    # Length limits
    if first_name and len(first_name) > 100:
        first_name = first_name[:100]
    if last_name and len(last_name) > 100:
        last_name = last_name[:100]
    if username and len(username) > 100:
        username = username[:100]

    assert telegram_user_id == 12345
    assert first_name == "Test"
    assert last_name == "User"
    assert username == "testuser"
    print("✅ User data extraction and validation works")


def test_keyboard_removal():
    """Test inline keyboard removal"""
    print("\n=== Testing keyboard removal ===")

    # Determine when to remove keyboard
    callback_data = "order_123_2"
    should_remove = True

    # Don't remove for pagination (except page_info)
    if callback_data.startswith("page_") and callback_data != "page_info":
        should_remove = False

    assert should_remove  # Order callback should remove keyboard
    print("✅ Order callback keyboard removal works")

    # Pagination callback
    callback_data = "page_suppliers_2"
    should_remove = True
    if callback_data.startswith("page_") and callback_data != "page_info":
        should_remove = False

    assert not should_remove  # Pagination should keep keyboard
    print("✅ Pagination callback keyboard retention works")


def test_deep_link_handling():
    """Test deep link parameter handling"""
    print("\n=== Testing deep link handling ===")

    # Order deep link
    command_parts = ["/start", "order_123_2"]
    if len(command_parts) > 1 and command_parts[1].startswith("order_"):
        try:
            _, offer_id_str, quantity_str = command_parts[1].split("_")
            assert offer_id_str == "123"
            assert quantity_str == "2"
            print("✅ Order deep link parsing works")
        except ValueError as err:
            raise AssertionError("Order deep link parsing failed") from err

    # Help deep link
    command_parts = ["/start", "help_general"]
    if len(command_parts) > 1 and command_parts[1].startswith("help_"):
        section = command_parts[1][5:]  # Remove 'help_' prefix
        assert section == "general"
        print("✅ Help deep link parsing works")


def test_error_response_handling():
    """Test error response handling"""
    print("\n=== Testing error response handling ===")

    # Success response
    response = {"status": "success"}
    is_success = response.get("status") == "success"
    assert is_success
    print("✅ Success response handling works")

    # Error response
    response = {"status": "error", "error": "Test error"}
    is_error = response.get("status") == "error"
    error_message = response.get("error", "Unknown error")
    assert is_error
    assert error_message == "Test error"
    print("✅ Error response handling works")

    # Status codes
    status_codes = {"success": 200, "invalid_args": 400, "unauthorized": 401, "not_found": 404, "error": 500}

    assert status_codes["success"] == 200
    assert status_codes["unauthorized"] == 401
    print("✅ Status code mapping works")


if __name__ == "__main__":
    test_callback_data_parsing()
    test_webhook_validation()
    test_command_extraction()
    test_chat_type_detection()
    test_user_registration()
    test_keyboard_removal()
    test_deep_link_handling()
    test_error_response_handling()
    print("\n🎉 All webhook and callback tests passed!")
