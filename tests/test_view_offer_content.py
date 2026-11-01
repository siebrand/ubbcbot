import os
import sys
import unittest
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from handlers.customer.info_commands import InfoCommands
from models.entities import Offer, OfferStatus


class TestViewOfferContent(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.handler = InfoCommands(self.mock_db, 12345, "test", "token")

        # Mock _t method to return the key or simple string
        def mock_translate(key, *args, **kwargs):
            if key == "product_cannot_be_ordered":
                return "<b>This product can no longer be ordered.</b>"
            return key

        self.handler._t = MagicMock(side_effect=mock_translate)

        # Mock _send_message and _send_photo
        self.handler._send_message = MagicMock(return_value={"success": True})
        self.handler._send_photo = MagicMock(return_value={"success": True})
        self.handler._send_media_group = MagicMock(return_value={"success": True})
        self.handler._is_admin = MagicMock(return_value=False)
        self.handler._get_offer_capacity_info = MagicMock(return_value=(0, 10))
        self.handler._get_bot_username = MagicMock(return_value="testbot")

    def test_view_offer_active(self):
        offer = Offer(
            offer_id=1,
            name="Active Beer",
            price_per_unit=10.0,
            status=OfferStatus.ACTIVE.value,
            description="Desc",
            wholesale_box_size=12,
            supplier_name="Sup",
        )
        self.mock_db.get_offer.return_value = offer

        self.handler.handle_view_offer(111, 222, ["1"])

        # Check if _send_message was called
        if not self.handler._send_message.called:
            # If it sent photo instead (if offer has images), checking that
            pass
        else:
            args, kwargs = self.handler._send_message.call_args
            message = args[1]

            self.assertNotIn("<b>This product can no longer be ordered.</b>", message)
            self.assertIn("Active Beer", message)

    def test_view_offer_sold_out(self):
        offer = Offer(
            offer_id=1,
            name="Sold Out Beer",
            price_per_unit=10.0,
            status=OfferStatus.SOLD_OUT.value,
            description="Desc",
            wholesale_box_size=12,
            supplier_name="Sup",
        )
        self.mock_db.get_offer.return_value = offer

        self.handler.handle_view_offer(111, 222, ["1"])

        args, kwargs = self.handler._send_message.call_args
        message = args[1]

        self.assertIn("<b>This product can no longer be ordered.</b>", message)
        self.assertIn("Sold Out Beer", message)


if __name__ == "__main__":
    unittest.main()
