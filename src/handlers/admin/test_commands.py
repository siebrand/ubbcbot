import logging
from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Supplier, Offer, Box, Order, BoxStatus

logger = logging.getLogger()

class TestCommands(BaseHandler):
    def handle_setup_test_data(self, chat_id: int) -> Dict[str, Any]:
        """Handle /setup_test_data command - creates test suppliers and offers (test environment only)"""
        # Only allow in test environment
        if self.environment != 'test':
            self._send_message(chat_id, self._t('test_env_only'))
            return {'status': 'environment_restricted'}
            
        try:
            # Test suppliers
            suppliers = [
                {"name": "HD"},
                {"name": "DK"}, 
                {"name": "BW"},
                {"name": "DM"}
            ]
            
            # Create suppliers
            created_suppliers = 0
            for supplier_data in suppliers:
                if not self.db.get_supplier_by_name(supplier_data["name"]):
                    supplier = Supplier(name=supplier_data["name"])
                    if self.db.create_supplier(supplier):
                        created_suppliers += 1
            
            # Test offers
            offers = [
                {"supplier": "HD", "name": "Hopduvel Tripel", "price": 4.50, "box_size": 12},
                {"supplier": "DK", "name": "De Koninck Bolleke", "price": 2.80, "box_size": 24},
                {"supplier": "BW", "name": "West Coast IPA", "price": 5.20, "box_size": 6},
                {"supplier": "DM", "name": "Duvel Golden Ale", "price": 3.90, "box_size": 12},
                {"supplier": "HD", "name": "Hopduvel Saison", "price": 4.20, "box_size": 12},
                {"supplier": "BW", "name": "Hazy IPA", "price": 5.50, "box_size": 6},
                {"supplier": "HD", "name": "Limited Edition Barrel Aged", "price": 25.00, "box_size": 1},
                {"supplier": "DK", "name": "Vintage Reserve", "price": 18.50, "box_size": 2}
            ]
            
            # Create offers
            created_offers = 0
            for offer_data in offers:
                offer = Offer(
                    supplier_name=offer_data["supplier"],
                    name=offer_data["name"],
                    price_per_unit=Decimal(str(offer_data["price"])),
                    wholesale_box_size=offer_data["box_size"],
                    min_quantity_breakeven=max(1, int(offer_data["box_size"] * 0.8)),
                    status='active'
                )
                
                if self.db.create_offer(offer):
                    created_offers += 1
                    
                    # Create initial box
                    box = Box(
                        offer_id=offer.offer_id,
                        max_capacity=offer_data["box_size"],
                        min_breakeven=int(offer.min_quantity_breakeven)
                    )
                    self.db.create_box(box)
                    
                    # Auto-order 1 unit for admin
                    admin_customer = self.db.get_customer_by_telegram_id(self.admin_user_id)
                    if admin_customer:
                        admin_order = Order(
                            customer_id=admin_customer.customer_id,
                            box_id=box.box_id,
                            offer_id=offer.offer_id,
                            quantity=1,
                            unit_price=Decimal(str(offer_data["price"])),
                            total_price=Decimal(str(offer_data["price"]))
                        )
                        self.db.create_order(admin_order)
                        
                        # Update box quantity
                        updates = {'current_quantity': 1}
                        if 1 >= box.max_capacity:
                            updates['status'] = BoxStatus.FULL.value
                        elif 1 >= box.min_breakeven:
                            updates['status'] = BoxStatus.MINIMUM_REACHED.value
                        self.db.update_box(box.box_id, updates)
            
            self._send_message(chat_id, self._t('test_data_success', suppliers=created_suppliers, offers=created_offers))
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error setting up test data: {e}")
            self._send_message(chat_id, self._t('test_data_failed'))
            return {'status': 'error'}