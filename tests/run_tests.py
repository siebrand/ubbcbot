#!/usr/bin/env python3

"""
Test runner for UBBC Bot
Executes all test modules and reports results
"""

import sys
import os
import subprocess

def run_test_file(test_file):
    """Run a single test file and return success status"""
    try:
        result = subprocess.run([sys.executable, test_file], 
                              capture_output=True, text=True, cwd=os.path.dirname(test_file))
        
        if result.returncode == 0:
            print(f"✅ {os.path.basename(test_file)}")
            return True
        else:
            print(f"❌ {os.path.basename(test_file)}")
            print(f"   Error: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ {os.path.basename(test_file)} - Exception: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Running UBBC Bot Tests\n")
    
    test_dir = os.path.dirname(__file__)
    test_files = [
        os.path.join(test_dir, "test_add_box.py"),
        os.path.join(test_dir, "test_commands.py"),
        os.path.join(test_dir, "test_customer_orders.py"),
        os.path.join(test_dir, "test_admin_operations.py"),
        os.path.join(test_dir, "test_user_management.py"),
        os.path.join(test_dir, "test_supplier_management.py"),
        os.path.join(test_dir, "test_help_system.py"),
        os.path.join(test_dir, "test_webhook_callbacks.py"),
        os.path.join(test_dir, "test_offer_management.py"),
        os.path.join(test_dir, "test_pagination.py")
    ]
    
    passed = 0
    total = len(test_files)
    
    for test_file in test_files:
        if os.path.exists(test_file):
            if run_test_file(test_file):
                passed += 1
        else:
            print(f"⚠️  {os.path.basename(test_file)} - File not found")
    
    print(f"\n📊 Results: {passed}/{total} test files passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("💥 Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())