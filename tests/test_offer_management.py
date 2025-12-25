#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import unittest
from models.entities import Offer, OfferStatus

class TestOfferManagement(unittest.TestCase):
    def test_offer_status_enum_includes_draft(self):
        """Test that OfferStatus enum includes DRAFT"""
        self.assertEqual(OfferStatus.DRAFT.value, 'draft')
        self.assertIn(OfferStatus.DRAFT, list(OfferStatus))
        
        # Test all expected statuses exist
        expected_statuses = ['draft', 'active', 'inactive', 'ordered', 'sold_out', 'completed', 'delivered']
        actual_statuses = [status.value for status in OfferStatus]
        
        for status in expected_statuses:
            self.assertIn(status, actual_statuses, f"Status '{status}' should be in OfferStatus enum")
    
    def test_offer_model_has_new_fields(self):
        """Test that Offer model has new fields and correct defaults"""
        # Test default values
        offer = Offer()
        self.assertTrue(hasattr(offer, 'images'), "Offer should have images field")
        self.assertTrue(hasattr(offer, 'description'), "Offer should have description field")
        self.assertEqual(offer.status, OfferStatus.DRAFT.value, "Default status should be DRAFT")
        self.assertEqual(offer.images, [], "Default images should be empty list")
        self.assertEqual(offer.description, "", "Default description should be empty string")
        
        # Test with values
        offer_with_data = Offer(
            name="Test Beer",
            description="A great beer",
            images=["https://example.com/image1.jpg"],
            status=OfferStatus.ACTIVE.value
        )
        
        self.assertEqual(offer_with_data.description, "A great beer")
        self.assertEqual(len(offer_with_data.images), 1)
        self.assertEqual(offer_with_data.images[0], "https://example.com/image1.jpg")
        self.assertEqual(offer_with_data.status, OfferStatus.ACTIVE.value)
    
    def test_offer_status_transitions(self):
        """Test valid offer status transitions"""
        # Draft to Active
        offer = Offer(status=OfferStatus.DRAFT.value)
        offer.status = OfferStatus.ACTIVE.value
        self.assertEqual(offer.status, OfferStatus.ACTIVE.value)
        
        # Active to Sold Out
        offer.status = OfferStatus.SOLD_OUT.value
        self.assertEqual(offer.status, OfferStatus.SOLD_OUT.value)
        
        # Test all status values are strings
        for status in OfferStatus:
            self.assertIsInstance(status.value, str)

if __name__ == '__main__':
    print("🧪 Testing Enhanced Offer Management")
    unittest.main(verbosity=2)