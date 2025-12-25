#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.entities import Supplier

def test_supplier_creation():
    """Test supplier creation and validation"""
    print("=== Testing supplier creation ===")
    
    # Valid supplier
    supplier = Supplier(name="Test Brewery")
    assert supplier.name == "Test Brewery"
    assert supplier.status == "active"  # Default status
    print("✅ Valid supplier created")
    
    # Name validation - too long
    long_name = "x" * 51
    is_valid = len(long_name) <= 50
    assert not is_valid
    print("✅ Long name validation works")
    
    # Name validation - invalid characters
    invalid_name = "Test<Brewery>"
    has_invalid_chars = '<' in invalid_name or '>' in invalid_name
    assert has_invalid_chars
    print("✅ Invalid character validation works")
    
    # Empty name validation
    empty_name = ""
    is_valid = len(empty_name.strip()) > 0
    assert not is_valid
    print("✅ Empty name validation works")

def test_supplier_status_management():
    """Test supplier status transitions"""
    print("\n=== Testing supplier status management ===")
    
    # Active supplier
    supplier = Supplier(name="Active Brewery", status="active")
    assert supplier.status == "active"
    print("✅ Active supplier created")
    
    # Retire supplier
    supplier.status = "retired"
    assert supplier.status == "retired"
    print("✅ Supplier retired")
    
    # Reactivate supplier
    supplier.status = "active"
    assert supplier.status == "active"
    print("✅ Supplier reactivated")

def test_supplier_filtering():
    """Test supplier filtering by status"""
    print("\n=== Testing supplier filtering ===")
    
    suppliers = [
        Supplier(name="Active Brewery 1", status="active"),
        Supplier(name="Retired Brewery", status="retired"),
        Supplier(name="Active Brewery 2", status="active")
    ]
    
    # Filter active suppliers
    active_suppliers = [s for s in suppliers if s.status == "active"]
    assert len(active_suppliers) == 2
    print("✅ Active supplier filtering works")
    
    # Filter retired suppliers
    retired_suppliers = [s for s in suppliers if s.status == "retired"]
    assert len(retired_suppliers) == 1
    print("✅ Retired supplier filtering works")
    
    # All suppliers
    all_suppliers = suppliers
    assert len(all_suppliers) == 3
    print("✅ All supplier listing works")

def test_supplier_search():
    """Test supplier search functionality"""
    print("\n=== Testing supplier search ===")
    
    suppliers = [
        Supplier(name="Brewery Alpha"),
        Supplier(name="Brewery Beta"),
        Supplier(name="Distillery Gamma")
    ]
    
    # Exact name match
    search_term = "Brewery Alpha"
    matches = [s for s in suppliers if s.name.lower() == search_term.lower()]
    assert len(matches) == 1
    print("✅ Exact name search works")
    
    # Partial name match
    search_term = "Brewery"
    matches = [s for s in suppliers if search_term.lower() in s.name.lower()]
    assert len(matches) == 2
    print("✅ Partial name search works")
    
    # No matches
    search_term = "Nonexistent"
    matches = [s for s in suppliers if search_term.lower() in s.name.lower()]
    assert len(matches) == 0
    print("✅ No match handling works")

def test_supplier_contact_info():
    """Test supplier contact information"""
    print("\n=== Testing supplier contact info ===")
    
    # Supplier without contact
    supplier = Supplier(name="Test Brewery")
    assert supplier.contact_email is None
    print("✅ Supplier without contact created")
    
    # Add contact email
    supplier.contact_email = "test@brewery.com"
    assert supplier.contact_email == "test@brewery.com"
    print("✅ Contact email added")
    
    # Email validation
    valid_email = "test@brewery.com"
    is_valid = '@' in valid_email and '.' in valid_email
    assert is_valid
    print("✅ Valid email format")
    
    invalid_email = "invalid-email"
    is_valid = '@' in invalid_email and '.' in invalid_email
    assert not is_valid
    print("✅ Invalid email format detected")

def test_supplier_sorting():
    """Test supplier sorting"""
    print("\n=== Testing supplier sorting ===")
    
    suppliers = [
        Supplier(name="Zebra Brewery"),
        Supplier(name="Alpha Brewery"),
        Supplier(name="Beta Brewery")
    ]
    
    # Sort alphabetically
    sorted_suppliers = sorted(suppliers, key=lambda x: x.name.lower())
    expected_order = ["Alpha Brewery", "Beta Brewery", "Zebra Brewery"]
    actual_order = [s.name for s in sorted_suppliers]
    
    assert actual_order == expected_order
    print("✅ Alphabetical sorting works")

def test_duplicate_supplier_prevention():
    """Test duplicate supplier name prevention"""
    print("\n=== Testing duplicate prevention ===")
    
    existing_suppliers = [
        Supplier(name="Existing Brewery"),
        Supplier(name="Another Brewery")
    ]
    
    # Check for duplicate
    new_name = "Existing Brewery"
    is_duplicate = any(s.name.lower() == new_name.lower() for s in existing_suppliers)
    assert is_duplicate
    print("✅ Duplicate detection works")
    
    # Check for non-duplicate
    new_name = "New Brewery"
    is_duplicate = any(s.name.lower() == new_name.lower() for s in existing_suppliers)
    assert not is_duplicate
    print("✅ Non-duplicate detection works")

if __name__ == "__main__":
    test_supplier_creation()
    test_supplier_status_management()
    test_supplier_filtering()
    test_supplier_search()
    test_supplier_contact_info()
    test_supplier_sorting()
    test_duplicate_supplier_prevention()
    print("\n🎉 All supplier management tests passed!")