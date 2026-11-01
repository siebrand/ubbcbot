#!/usr/bin/env python3

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest


class TestPagination(unittest.TestCase):
    def test_pagination_callback_format(self):
        """Test pagination callback data format matches parsing expectations"""
        # Test callback data format without filters
        callback_data = "page_customers_2"
        parts = callback_data.split("_")

        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "page")
        self.assertEqual(parts[1], "customers")
        self.assertEqual(int(parts[2]), 2)

    def test_pagination_callback_format_with_filters(self):
        """Test pagination callback data format with filters"""
        # Test callback data format with filters
        callback_data = "page_customers_approved_3"
        parts = callback_data.split("_")

        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[0], "page")
        entity_type = parts[1]  # customers

        # Check if entity_type starts with customers_
        if entity_type == "customers" and len(parts) >= 4:
            # This is customers_filter format
            entity_with_filter = f"{parts[1]}_{parts[2]}"  # customers_approved
            page = int(parts[3])  # 3

            self.assertTrue(entity_with_filter.startswith("customers_"))
            status_filter = entity_with_filter.split("_", 1)[1]  # approved
            self.assertEqual(status_filter, "approved")
            self.assertEqual(page, 3)

    def test_pagination_logic(self):
        """Test pagination calculation logic"""
        # Test pagination math
        items = list(range(25))  # 25 items
        page_size = 10

        # Calculate total pages
        total_pages = (len(items) + page_size - 1) // page_size
        self.assertEqual(total_pages, 3)

        # Test page 1
        page = 1
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = items[start_idx:end_idx]

        self.assertEqual(len(page_items), 10)
        self.assertEqual(page_items, list(range(10)))

        # Test page 3 (partial)
        page = 3
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = items[start_idx:end_idx]

        self.assertEqual(len(page_items), 5)
        self.assertEqual(page_items, list(range(20, 25)))

    def test_empty_list_pagination(self):
        """Test pagination with empty list"""
        items = []
        page_size = 10

        total_pages = (len(items) + page_size - 1) // page_size if items else 1
        self.assertEqual(total_pages, 1)

        page = 1
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = items[start_idx:end_idx]

        self.assertEqual(page_items, [])


if __name__ == "__main__":
    print("🧪 Testing Pagination")
    unittest.main(verbosity=2)
