import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from models.entities import Offer, OfferStatus
from services.offer_message_builder import OfferMessageBuilder


def _t(key, *_a, **_k):
    # echo the key so tests can detect which suffix label was used
    return key


class TestOfferMessageBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = OfferMessageBuilder(bot_username="ubbc_test_bot", translate=_t)
        self.offer = Offer(
            offer_id=12,
            name="Beer",
            description="Tasty",
            price_per_unit=Decimal("4.50"),
            status=OfferStatus.ACTIVE.value,
        )

    def test_active_has_no_icon_and_has_buttons(self):
        text, markup = self.builder.build(self.offer)
        self.assertIn("12", text)
        self.assertIn("Beer", text)
        self.assertIn("4.50", text)
        self.assertNotIn("🔴", text)
        self.assertNotIn("⛔", text)
        # order buttons present
        callbacks = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
        self.assertIn("order_12_1", callbacks)
        self.assertIn("order_12_2", callbacks)

    def test_sold_out_has_icon_and_no_buttons(self):
        self.offer.status = OfferStatus.SOLD_OUT.value
        text, markup = self.builder.build(self.offer)
        self.assertTrue(text.startswith("🔴"))
        self.assertIn("status_sold_out", text)  # localized suffix label
        self.assertIsNone(markup)

    def test_cancelled_has_icon_and_no_buttons(self):
        self.offer.status = OfferStatus.INACTIVE.value  # cancelled offers become INACTIVE
        text, markup = self.builder.build(self.offer, cancelled=True)
        self.assertTrue(text.startswith("⛔"))
        self.assertIn("status_cancelled", text)
        self.assertIsNone(markup)

    def test_active_with_buttons_false_has_no_buttons(self):
        # Group/channel announcements are rendered button-less even when active.
        text, markup = self.builder.build(self.offer, with_buttons=False)
        self.assertIn("Beer", text)
        self.assertNotIn("🔴", text)
        self.assertIsNone(markup)

    def test_description_included(self):
        text, _ = self.builder.build(self.offer)
        self.assertIn("Tasty", text)

    def test_name_is_html_escaped(self):
        self.offer.name = "A <b>bold</b> & risky name"
        text, _ = self.builder.build(self.offer)
        self.assertNotIn("<b>bold</b>", text)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", text)
        self.assertIn("&amp;", text)


if __name__ == "__main__":
    unittest.main()
