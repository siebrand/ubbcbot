import unittest
from unittest.mock import Mock, MagicMock
from handlers.customer.order_commands import CustomerOrderCommands
from models.entities import Order, Offer, Box, Customer


class TestOrderNotificationMilestones(unittest.TestCase):
    """Test milestone-based group notification logic"""
    
    def setUp(self):
        self.db = Mock()
        self.admin_user_id = 123456
        self.environment = "test"
        self.telegram_token = "test_token"
        self.handler = CustomerOrderCommands(self.db, self.admin_user_id, self.environment, self.telegram_token)
    
    def test_first_order_triggers_notification(self):
        """First order should trigger group notification"""
        offer_id = 1
        quantity = 1
        
        # Mock single order
        self.db.get_orders_by_offer.return_value = [
            Mock(status='pending', quantity=1)
        ]
        
        # Mock offer and boxes
        self.db.get_offer.return_value = Mock(offer_id=offer_id)
        self.db.get_boxes_by_offer.return_value = [
            Mock(max_capacity=24, current_quantity=1)
        ]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertTrue(result, "First order should trigger notification")
    
    def test_second_order_does_not_trigger_notification(self):
        """2nd order should NOT trigger group notification"""
        offer_id = 1
        quantity = 1
        
        # Mock 2 orders
        self.db.get_orders_by_offer.return_value = [
            Mock(status='pending', quantity=1),
            Mock(status='pending', quantity=1)
        ]
        
        self.db.get_offer.return_value = Mock(offer_id=offer_id)
        self.db.get_boxes_by_offer.return_value = [
            Mock(max_capacity=24, current_quantity=2)
        ]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertFalse(result, "2nd order should NOT trigger notification")
    
    def test_capacity_threshold_75_percent_triggers_notification(self):
        """Crossing 75% capacity threshold should trigger notification"""
        offer_id = 1
        quantity = 2
        
        # Mock orders
        self.db.get_orders_by_offer.return_value = [
            Mock(status='pending', quantity=1),
            Mock(status='pending', quantity=1),
            Mock(status='pending', quantity=1),
            Mock(status='pending', quantity=1),
            Mock(status='pending', quantity=2)  # This order crosses 75% threshold
        ]
        
        self.db.get_offer.return_value = Mock(offer_id=offer_id)
        # Total capacity: 24, current: 6, remaining: 18 (75%)
        # After this order: remaining 16 (66.7%) - crosses 75% threshold
        self.db.get_boxes_by_offer.return_value = [
            Mock(max_capacity=24, current_quantity=6)
        ]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertTrue(result, "Crossing 75% threshold should trigger notification")
    
    def test_last_5_units_triggers_notification(self):
        """Crossing into last 5 units should trigger notification"""
        offer_id = 1
        quantity = 2
        
        self.db.get_orders_by_offer.return_value = [Mock(status='pending', quantity=1)] * 10
        self.db.get_offer.return_value = Mock(offer_id=offer_id)
        # Total: 24, current: 19, remaining: 5 (just crossed into last 5)
        self.db.get_boxes_by_offer.return_value = [
            Mock(max_capacity=24, current_quantity=19)
        ]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertTrue(result, "Crossing into last 5 units should trigger notification")
    
    def test_sold_out_triggers_notification(self):
        """Sold out (remaining = 0) should trigger notification"""
        offer_id = 1
        quantity = 1
        
        self.db.get_orders_by_offer.return_value = [Mock(status='pending', quantity=1)] * 24
        self.db.get_offer.return_value = Mock(offer_id=offer_id)
        # Total: 24, current: 24, remaining: 0 (sold out)
        self.db.get_boxes_by_offer.return_value = [
            Mock(max_capacity=24, current_quantity=24)
        ]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertTrue(result, "Sold out should trigger notification")
    
    def test_cancelled_orders_excluded_from_count(self):
        """Cancelled orders should not count toward order count"""
        offer_id = 1
        quantity = 1
        
        # 2 active orders + 1 cancelled = should NOT trigger (not 3rd order)
        self.db.get_orders_by_offer.return_value = [
            Mock(status='pending', quantity=1),
            Mock(status='pending', quantity=1),
            Mock(status='cancelled', quantity=1)
        ]
        
        self.db.get_offer.return_value = Mock(offer_id=offer_id)
        self.db.get_boxes_by_offer.return_value = [
            Mock(max_capacity=24, current_quantity=2)
        ]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertFalse(result, "Cancelled orders should not count toward milestones")
    
    def test_small_box_odd_orders_trigger_notification(self):
        """Small boxes (1-4 units) should trigger on odd orders only"""
        offer_id = 1
        quantity = 1
        
        # Test 1-unit box: order 1 (odd) should trigger
        self.db.get_orders_by_offer.return_value = [Mock(status='pending', quantity=1)]
        self.db.get_offer.return_value = Mock(offer_id=offer_id)
        self.db.get_boxes_by_offer.return_value = [Mock(max_capacity=1, current_quantity=1)]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertTrue(result, "1-unit box: order 1 should trigger")
        
        # Test 2-unit box: order 1 (odd) should trigger
        self.db.get_orders_by_offer.return_value = [Mock(status='pending', quantity=1)]
        self.db.get_boxes_by_offer.return_value = [Mock(max_capacity=2, current_quantity=1)]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertTrue(result, "2-unit box: order 1 should trigger")
        
        # Test 4-unit box: order 3 (odd) should trigger
        self.db.get_orders_by_offer.return_value = [Mock(status='pending', quantity=1)] * 3
        self.db.get_boxes_by_offer.return_value = [Mock(max_capacity=4, current_quantity=3)]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertTrue(result, "4-unit box: order 3 should trigger")
    
    def test_small_box_even_orders_do_not_trigger_notification(self):
        """Small boxes (1-4 units) should NOT trigger on even orders"""
        offer_id = 1
        quantity = 1
        
        # Test 2-unit box: order 2 (even) should NOT trigger
        self.db.get_orders_by_offer.return_value = [Mock(status='pending', quantity=1)] * 2
        self.db.get_offer.return_value = Mock(offer_id=offer_id)
        self.db.get_boxes_by_offer.return_value = [Mock(max_capacity=2, current_quantity=2)]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertFalse(result, "2-unit box: order 2 should NOT trigger")
        
        # Test 4-unit box: order 2 (even) should NOT trigger
        self.db.get_orders_by_offer.return_value = [Mock(status='pending', quantity=1)] * 2
        self.db.get_boxes_by_offer.return_value = [Mock(max_capacity=4, current_quantity=2)]
        
        result = self.handler._should_send_group_notification(offer_id, quantity)
        self.assertFalse(result, "4-unit box: order 2 should NOT trigger")


if __name__ == '__main__':
    unittest.main()
