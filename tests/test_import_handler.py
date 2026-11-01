import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from handlers.admin.import_handler import ImportHandler
from models.entities import AuthorizationStatus, Box, BoxStatus, Customer, Offer, OfferStatus


class TestImportHandler(unittest.TestCase):
    """Test import handler functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.db = Mock()
        self.admin_user_id = 15005473
        self.environment = "test"
        self.telegram_token = "test_token"

        self.handler = ImportHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)

    def test_import_orders_sets_pending_state(self):
        """Test that import_orders sets pending state in DynamoDB"""
        chat_id = 123
        user_id = self.admin_user_id

        self.db.get_edit_context_by_chat_id.return_value = None
        self.db.cleanup_old_edit_contexts.return_value = 0

        with patch.object(self.handler, "_send_message") as mock_send:
            result = self.handler.handle_import_orders(chat_id, user_id)

            self.db.create_edit_context.assert_called_once()
            self.assertEqual(result["status"], "awaiting_file")
            mock_send.assert_called_once()

    def test_import_orders_blocks_concurrent(self):
        """Test that concurrent imports are blocked"""
        chat_id = 123
        user_id = self.admin_user_id

        # Mock existing context
        existing_context = Mock(edit_type="import_csv")
        self.db.get_edit_context_by_chat_id.return_value = existing_context

        with patch.object(self.handler, "_send_error") as mock_send:
            mock_send.return_value = {"status": "already_pending"}
            self.handler.handle_import_orders(chat_id, user_id)

            mock_send.assert_called_once_with(chat_id, "import_already_pending", "already_pending")

    def test_find_customer_exact_username(self):
        """Test finding customer by exact username"""
        customer = Customer(
            customer_id="cust1",
            telegram_user_id=123,
            username="alice",
            first_name="Alice",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )

        with patch.object(self.handler, "_find_customer_with_disambiguation") as mock_find:
            mock_find.return_value = (customer, None)
            result, error = self.handler._find_customer_for_import("alice", 123)

            self.assertIsNotNone(result)
            self.assertIsNone(error)
            self.assertEqual(result.customer_id, "cust1")

    def test_find_customer_by_name(self):
        """Test finding customer by name when username not found"""
        customer = Customer(
            customer_id="cust1",
            telegram_user_id=123,
            username="alice_user",
            first_name="Alice",
            authorization_status=AuthorizationStatus.APPROVED.value,
        )

        with patch.object(self.handler, "_find_customer_with_disambiguation") as mock_find:
            mock_find.return_value = (customer, None)
            result, error = self.handler._find_customer_for_import("Alice", 123)

            self.assertIsNotNone(result)
            self.assertIsNone(error)
            self.assertEqual(result.customer_id, "cust1")

    def test_find_customer_multiple_matches(self):
        """Test finding customer returns error for multiple matches"""
        with (
            patch.object(self.handler, "_find_customer_with_disambiguation") as mock_find,
            patch.object(self.handler, "_t") as mock_t,
        ):
            mock_find.return_value = (None, {"status": "disambiguation_shown"})
            mock_t.return_value = "multiple_matches"

            result, error = self.handler._find_customer_for_import("Alice", 123)

            self.assertIsNone(result)
            self.assertIsNotNone(error)
            self.assertEqual(error, "multiple_matches")

    def test_find_customer_not_found(self):
        """Test finding customer returns error when not found"""
        with (
            patch.object(self.handler, "_find_customer_with_disambiguation") as mock_find,
            patch.object(self.handler, "_t") as mock_t,
        ):
            mock_find.return_value = (None, {"status": "user_not_found"})
            mock_t.return_value = "not_found"

            result, error = self.handler._find_customer_for_import("unknown", 123)

            self.assertIsNone(result)
            self.assertIsNotNone(error)
            self.assertEqual(error, "not_found")

    def test_create_import_order_with_existing_box(self):
        """Test creating import order with existing open box"""
        offer = Offer(
            offer_id=1,
            name="Test Offer",
            price_per_unit=Decimal("5.00"),
            wholesale_box_size=12,
            status=OfferStatus.IMPORT.value,
        )

        customer = Customer(customer_id="cust1", telegram_user_id=123, first_name="Alice")

        box = Box(box_id="box1", offer_id=1, current_quantity=5, max_capacity=12, status=BoxStatus.OPEN.value)

        self.db.get_boxes_by_offer.return_value = [box]
        self.db.create_order.return_value = Mock(order_id="order1")

        with patch.object(self.handler.box_status_manager, "update_box_after_order_placement") as mock_update:
            result = self.handler._create_import_order(offer, customer)

            self.assertTrue(result["success"])
            self.db.create_order.assert_called_once()
            mock_update.assert_called_once_with("box1", 1)

    def test_create_import_order_creates_new_box(self):
        """Test creating import order creates new box when none available"""
        offer = Offer(
            offer_id=1,
            name="Test Offer",
            price_per_unit=Decimal("5.00"),
            wholesale_box_size=12,
            status=OfferStatus.IMPORT.value,
        )

        customer = Customer(customer_id="cust1", telegram_user_id=123, first_name="Alice")

        new_box = Box(box_id="box1", offer_id=1, current_quantity=0, max_capacity=12, status=BoxStatus.OPEN.value)

        self.db.get_boxes_by_offer.return_value = []
        self.db.create_box.return_value = new_box
        self.db.create_order.return_value = Mock(order_id="order1")

        with patch.object(self.handler.box_status_manager, "update_box_after_order_placement"):
            result = self.handler._create_import_order(offer, customer)

            self.assertTrue(result["success"])
            self.db.create_box.assert_called_once()
            self.db.create_order.assert_called_once()

    def test_finalize_import_sold_out(self):
        """Test finalizing import when offer is sold out"""
        offer = Offer(offer_id=1, name="Test Offer", status=OfferStatus.IMPORT.value)

        boxes = [Box(box_id="box1", status=BoxStatus.FULL.value), Box(box_id="box2", status=BoxStatus.FULL.value)]

        self.db.get_offer.return_value = offer
        self.db.get_boxes_by_offer.return_value = boxes
        self.db.get_orders_by_box.return_value = []
        self.db.list_offers.return_value = []

        with (
            patch.object(self.handler, "_validate_and_get_offer") as mock_validate,
            patch.object(self.handler, "_validate_args") as mock_args,
            patch.object(self.handler, "_send_success") as mock_send,
            patch.object(self.handler, "_send_message"),
            patch.object(self.handler.box_status_manager, "mark_boxes_as_ordered"),
            patch.object(self.handler.box_status_manager, "update_offer_status_after_change") as mock_update_status,
        ):
            mock_validate.return_value = (offer, None)
            mock_args.return_value = None
            mock_send.return_value = {"status": "success"}
            mock_update_status.return_value = OfferStatus.SOLD_OUT.value

            self.handler.handle_finalize_import(123, ["1"])

            mock_update_status.assert_called_once_with(1)
            mock_send.assert_called_once()

    def test_finalize_import_active(self):
        """Test finalizing import when offer has capacity"""
        offer = Offer(offer_id=1, name="Test Offer", status=OfferStatus.IMPORT.value)

        boxes = [Box(box_id="box1", status=BoxStatus.OPEN.value, current_quantity=5, max_capacity=12)]

        self.db.get_offer.return_value = offer
        self.db.get_boxes_by_offer.return_value = boxes
        self.db.get_orders_by_box.return_value = []
        self.db.list_offers.return_value = []

        with (
            patch.object(self.handler, "_validate_and_get_offer") as mock_validate,
            patch.object(self.handler, "_validate_args") as mock_args,
            patch.object(self.handler, "_send_success") as mock_send,
            patch.object(self.handler, "_announce_offer") as mock_announce,
            patch.object(self.handler, "_send_message"),
            patch.object(self.handler.box_status_manager, "mark_boxes_as_ordered"),
            patch.object(self.handler.box_status_manager, "update_offer_status_after_change") as mock_update_status,
        ):
            mock_validate.return_value = (offer, None)
            mock_args.return_value = None
            mock_send.return_value = {"status": "success"}
            mock_update_status.return_value = OfferStatus.ACTIVE.value

            self.handler.handle_finalize_import(123, ["1"])

            mock_update_status.assert_called_once_with(1)
            mock_announce.assert_called_once()
            mock_send.assert_called_once()

    def test_finalize_import_wrong_status(self):
        """Test finalizing import fails for non-IMPORT status"""
        offer = Offer(offer_id=1, name="Test Offer", status=OfferStatus.DRAFT.value)

        with (
            patch.object(self.handler, "_validate_and_get_offer") as mock_validate,
            patch.object(self.handler, "_validate_args") as mock_args,
            patch.object(self.handler, "_send_error") as mock_send,
        ):
            mock_validate.return_value = (offer, None)
            mock_args.return_value = None
            mock_send.return_value = {"status": "wrong_status"}

            self.handler.handle_finalize_import(123, ["1"])

            mock_send.assert_called_once()
            self.db.update_offer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
