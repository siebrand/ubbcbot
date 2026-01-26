import logging
import os
import json
import boto3
from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Supplier, Offer, Box, Order, BoxStatus
from services.box_status_manager import BoxStatusManager

logger = logging.getLogger()

class TestCommands(BaseHandler):
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)
        self.lambda_client = boto3.client('lambda')
        self.user_message_lambda = os.environ.get('USER_MESSAGE_LAMBDA_NAME')
    
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
                    status='active'
                )
                
                if self.db.create_offer(offer):
                    created_offers += 1
                    
                    # Create initial box
                    box = Box(
                        offer_id=offer.offer_id,
                        max_capacity=offer_data["box_size"]
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
                        
                        # Update box quantity via service
                        self.box_status_manager.update_box_after_order_placement(box.box_id, 1)
            
            self._send_message(chat_id, self._t('test_data_success', suppliers=created_suppliers, offers=created_offers))
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error setting up test data: {e}")
            self._send_message(chat_id, self._t('test_data_failed'))
            return {'status': 'error'}
    
    def handle_test_user_message(self, chat_id: int, user_id: int, message: str) -> Dict[str, Any]:
        """Handle /test_user_message command - sends test message from admin account"""
        try:
            # Invoke user message sender Lambda
            payload = {
                'user_id': user_id,
                'message': message
            }
            
            response = self.lambda_client.invoke(
                FunctionName=self.user_message_lambda,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            result = json.loads(response['Payload'].read())
            
            if result.get('statusCode') == 200:
                self._send_message(chat_id, f"✓ Test message sent to user {user_id}")
                return {'status': 'success'}
            else:
                body = json.loads(result.get('body', '{}'))
                error = body.get('error', 'Unknown error')
                self._send_message(chat_id, f"✗ Failed to send message: {error}")
                return {'status': 'error'}
                
        except Exception as e:
            logger.error(f"Error sending test user message: {e}")
            self._send_message(chat_id, f"✗ Error: {str(e)}")
            return {'status': 'error'}