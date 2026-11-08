"""Tests for Telegram HTML validation in offer content.

Telegram's parse_mode=HTML supports only a small tag set. Unsupported tags
(e.g. <ul>/<li>) make Telegram reject the whole message, so they must be caught
before the content is stored.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from handlers.admin.offer.editing import OfferEditingHandler


class TestHtmlValidation(unittest.TestCase):
    def setUp(self):
        self.handler = OfferEditingHandler(MagicMock(), 15005473, "test", "token")

    def test_plain_text_is_valid(self):
        ok, key = self.handler._validate_html_content("Gewoon tekst zonder tags")
        self.assertTrue(ok)
        self.assertEqual(key, "")

    def test_supported_tags_are_valid(self):
        content = "<b>Vet</b> <i>schuin</i> <a href='https://x'>link</a> <code>x</code>"
        ok, key = self.handler._validate_html_content(content)
        self.assertTrue(ok)
        self.assertEqual(key, "")

    def test_ul_li_rejected(self):
        content = "Details:\n<ul><li>Datum: morgen</li><li>Prijs: €60</li></ul>"
        ok, key = self.handler._validate_html_content(content)
        self.assertFalse(ok)
        self.assertEqual(key, "html_unsupported_tag")

    def test_other_unsupported_tags_rejected(self):
        for tag in ("<p>para</p>", "text<br>more", "<div>x</div>", "<h1>title</h1>"):
            ok, key = self.handler._validate_html_content(tag)
            self.assertFalse(ok, f"{tag} should be rejected")
            self.assertEqual(key, "html_unsupported_tag")

    def test_unbalanced_supported_tag_still_rejected(self):
        ok, key = self.handler._validate_html_content("<b>never closed")
        self.assertFalse(ok)
        self.assertEqual(key, "product_name_invalid_chars")

    def test_tag_case_insensitive(self):
        ok, key = self.handler._validate_html_content("<B>Vet</B>")
        self.assertTrue(ok)

    def test_description_update_rejects_unsupported_tag(self):
        # End-to-end: the update handler must not store content with <ul>/<li>.
        self.handler._send_message = MagicMock()
        self.handler.db.update_offer = MagicMock(return_value=True)
        self.handler.db.get_offer.return_value = MagicMock(offer_id=929, description="old")

        result = self.handler.handle_update_offer_description(123, ["929", "<ul><li>x</li></ul>"])

        self.assertEqual(result["status"], "invalid_description")
        self.handler.db.update_offer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
