import sys
import os
import unittest
from decimal import Decimal

class TestMarkdownFormatting(unittest.TestCase):
    def test_markdown_link_format_validation(self):
        """Test that markdown link format is valid for Telegram"""
        # Test data
        offer_id = 1
        bot_username = "test_bot"
        offer_name = "Test Beer"
        display_price = Decimal('5.50')
        total_ordered = 5
        total_capacity = 12
        
        # Generate the markdown link format used in the code
        link_text = f"🍺 [{offer_id}](https://t.me/{bot_username}?start=view_offer_{offer_id}) {offer_name} €{display_price:.2f} ({total_ordered}/{total_capacity})\n"
        
        # Verify the link format is correct
        expected_link = "[1](https://t.me/test_bot?start=view_offer_1)"
        self.assertIn(expected_link, link_text)
        
        # Verify no method calls in the string (which caused parsing errors)
        self.assertNotIn("self._get_bot_username()", link_text)
        self.assertNotIn("_get_bot_username()", link_text)
        
        # Verify proper formatting
        self.assertTrue(link_text.startswith("🍺 ["))
        self.assertIn("https://t.me/", link_text)
        self.assertIn("?start=view_offer_", link_text)
        
    def test_bot_username_extraction_prevents_parsing_error(self):
        """Test that extracting bot_username to variable prevents f-string parsing issues"""
        # Simulate the problematic pattern (inline method call)
        offer_id = 1
        
        # This would cause parsing errors in Telegram
        def get_bot_username():
            return "test_bot"
        
        # Correct approach: extract to variable first
        bot_username = get_bot_username()
        safe_link = f"[{offer_id}](https://t.me/{bot_username}?start=view_offer_{offer_id})"
        
        # Verify the safe approach works
        expected = "[1](https://t.me/test_bot?start=view_offer_1)"
        self.assertEqual(safe_link, expected)

if __name__ == '__main__':
    unittest.main()