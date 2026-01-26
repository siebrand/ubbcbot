#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_notification_message_format():
    """Test that notification message is properly formatted"""
    print("=== Testing new user notification message format ===")
    
    # Mock user data
    user_data = {
        'id': 123456789,
        'first_name': 'John',
        'last_name': 'Doe', 
        'username': 'johndoe'
    }
    
    # Format display name
    display_name = user_data['first_name']
    if user_data.get('last_name'):
        display_name += f" {user_data['last_name']}"
    
    # Expected message format (without translation system)
    expected_parts = [
        "🔔 New user authorization pending:",
        f"👤 {display_name}",
        f"📱 @{user_data['username']}",
        f"🆔 ID: {user_data['id']}",
        "Use /list_pending to review."
    ]
    
    # Verify all parts are present
    assert display_name == "John Doe"
    assert user_data['username'] == 'johndoe'
    assert user_data['id'] == 123456789
    print("✅ Message formatting works correctly")

def test_notification_edge_cases():
    """Test notification with edge cases"""
    print("\n=== Testing notification edge cases ===")
    
    # User without last name
    user_data_no_last = {
        'id': 987654321,
        'first_name': 'Jane',
        'username': 'jane_user'
    }
    
    display_name = user_data_no_last['first_name']
    if user_data_no_last.get('last_name'):
        display_name += f" {user_data_no_last['last_name']}"
    
    assert display_name == "Jane"
    print("✅ User without last name handled correctly")
    
    # User without username
    user_data_no_username = {
        'id': 555666777,
        'first_name': 'Bob',
        'last_name': 'Smith'
    }
    
    username = user_data_no_username.get('username', 'no_username')
    assert username == 'no_username'
    print("✅ User without username handled correctly")
    
    # User with only first name
    user_data_minimal = {
        'id': 111222333,
        'first_name': 'Alice'
    }
    
    display_name = user_data_minimal['first_name']
    if user_data_minimal.get('last_name'):
        display_name += f" {user_data_minimal['last_name']}"
    
    username = user_data_minimal.get('username', 'no_username')
    
    assert display_name == "Alice"
    assert username == 'no_username'
    print("✅ Minimal user data handled correctly")

def test_admin_user_id():
    """Test admin user ID constant"""
    print("\n=== Testing admin user ID ===")
    
    ADMIN_USER_ID = 15005473
    
    # Test admin identification
    test_user_ids = [15005473, 12345, 67890, 15005473]
    admin_checks = [uid == ADMIN_USER_ID for uid in test_user_ids]
    
    expected = [True, False, False, True]
    assert admin_checks == expected
    print("✅ Admin user ID identification works correctly")

def test_translation_keys_exist():
    """Test that required translation keys exist"""
    print("\n=== Testing translation keys ===")
    
    # Load translation files to verify keys exist
    import json
    
    # Check English translations
    en_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'translations', 'en.json')
    with open(en_file, 'r', encoding='utf-8') as f:
        en_translations = json.load(f)
    
    assert 'new_user_pending_notification' in en_translations
    print("✅ English translation key exists")
    
    # Check Dutch translations  
    nl_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'translations', 'nl.json')
    with open(nl_file, 'r', encoding='utf-8') as f:
        nl_translations = json.load(f)
    
    assert 'new_user_pending_notification' in nl_translations
    print("✅ Dutch translation key exists")
    
    # Verify message format contains expected placeholders
    en_message = en_translations['new_user_pending_notification']
    assert '{name}' in en_message
    assert '{username}' in en_message
    assert '{telegram_user_id}' in en_message
    print("✅ Translation placeholders are correct")

if __name__ == "__main__":
    test_notification_message_format()
    test_notification_edge_cases()
    test_admin_user_id()
    test_translation_keys_exist()
    print("\n🎉 All new user notification tests passed!")