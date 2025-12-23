import os
import json
import requests
import logging
from typing import Dict, Any, Optional
from services.database import DynamoDBService
from models.entities import Supplier, Offer, Customer, Box, Order, BoxStatus, OfferStatus

logger = logging.getLogger()

class BotService:
    def __init__(self):
        self.db = DynamoDBService()
        self.admin_user_id = int(os.environ.get('ADMIN_USER_ID', '15005473'))
        self.environment = os.environ.get('ENVIRONMENT', 'test')
        self.telegram_token = self._get_telegram_token()

    def _get_telegram_token(self) -> str:
        """Get Telegram token from Parameter Store"""
        import boto3
        ssm = boto3.client('ssm')
        try:
            response = ssm.get_parameter(
                Name=f'/ubbc-bot/{self.environment}/telegram-bot-token',
                WithDecryption=True
            )
            return response['Parameter']['Value']
        except Exception as e:
            logger.error(f"Error getting Telegram token: {e}")
            return ""

    def _send_message(self, chat_id: int, text: str) -> bool:
        """Send message to Telegram chat"""
        if self.environment == 'test':
            text = f"TEST - {text}"
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, json=data)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id

    def process_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming Telegram update"""
        try:
            if 'message' not in update:
                return {'status': 'ignored'}

            message = update['message']
            chat_id = message['chat']['id']
            user_id = message['from']['id']
            text = message.get('text', '')

            # Register customer if not exists
            self._register_customer_if_needed(message['from'])

            # Handle commands
            if text.startswith('/'):
                return self._handle_command(chat_id, user_id, text)
            
            return {'status': 'processed'}

        except Exception as e:
            logger.error(f"Error processing update: {e}")
            return {'status': 'error', 'error': str(e)}

    def _register_customer_if_needed(self, user_data: Dict[str, Any]):
        """Register customer if they don't exist"""
        telegram_user_id = user_data['id']
        existing_customer = self.db.get_customer_by_telegram_id(telegram_user_id)
        
        if not existing_customer:
            customer = Customer(
                telegram_user_id=telegram_user_id,
                username=user_data.get('username'),
                first_name=user_data.get('first_name'),
                last_name=user_data.get('last_name')
            )
            self.db.create_customer(customer)

    def _handle_command(self, chat_id: int, user_id: int, text: str) -> Dict[str, Any]:
        """Handle bot commands"""
        parts = text.split()
        command = parts[0].lower()

        # Admin commands
        if self._is_admin(user_id):
            if command == '/add_supplier':
                return self._handle_add_supplier(chat_id, parts[1:])
            elif command == '/create_offer':
                return self._handle_create_offer(chat_id, parts[1:])
            elif command == '/list_offers':
                return self._handle_list_offers(chat_id)
            elif command == '/box_status':
                return self._handle_box_status(chat_id)

        # Customer commands
        if command == '/start':
            return self._handle_start(chat_id, user_id)
        elif command == '/order':
            return self._handle_order(chat_id, user_id, parts[1:])
        elif command == '/my_orders':
            return self._handle_my_orders(chat_id, user_id)

        return {'status': 'unknown_command'}

    def _handle_add_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_supplier command"""
        if not args:
            self._send_message(chat_id, "Usage: /add_supplier <name>")
            return {'status': 'invalid_args'}

        supplier_name = ' '.join(args)
        supplier = Supplier(name=supplier_name)
        
        if self.db.create_supplier(supplier):
            self._send_message(chat_id, f"✅ Supplier '{supplier_name}' added with ID: {supplier.supplier_id}")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to add supplier")
            return {'status': 'error'}

    def _handle_create_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /create_offer command"""
        if len(args) < 4:
            self._send_message(chat_id, "Usage: /create_offer <supplier_id> <name> <price> <box_size>")
            return {'status': 'invalid_args'}

        try:
            supplier_id = args[0]
            name = args[1]
            price = float(args[2])
            box_size = int(args[3])

            # Validate box size
            valid_sizes = [1, 2, 6, 8, 10, 12, 15, 16, 18, 20, 24]
            if box_size not in valid_sizes:
                self._send_message(chat_id, f"❌ Invalid box size. Valid sizes: {valid_sizes}")
                return {'status': 'invalid_box_size'}

            # Check supplier exists
            supplier = self.db.get_supplier(supplier_id)
            if not supplier:
                self._send_message(chat_id, "❌ Supplier not found")
                return {'status': 'supplier_not_found'}

            # Create offer
            offer = Offer(
                supplier_id=supplier_id,
                name=name,
                price_per_unit=price,
                wholesale_box_size=box_size,
                min_quantity_breakeven=max(1, int(box_size * 0.8))  # 80% of box size
            )

            if self.db.create_offer(offer):
                # Create initial box
                box = Box(
                    offer_id=offer.offer_id,
                    max_capacity=box_size,
                    min_breakeven=offer.min_quantity_breakeven
                )
                self.db.create_box(box)

                self._send_message(chat_id, f"✅ Offer '{name}' created with ID: {offer.offer_id}")
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to create offer")
                return {'status': 'error'}

        except ValueError:
            self._send_message(chat_id, "❌ Invalid price or box size format")
            return {'status': 'invalid_format'}

    def _handle_list_offers(self, chat_id: int) -> Dict[str, Any]:
        """Handle /list_offers command"""
        offers = self.db.list_offers()
        
        if not offers:
            self._send_message(chat_id, "No offers found")
            return {'status': 'no_offers'}

        message = "📋 <b>Active Offers:</b>\n\n"
        for offer in offers:
            if offer.status == OfferStatus.ACTIVE.value:
                supplier = self.db.get_supplier(offer.supplier_id)
                supplier_name = supplier.name if supplier else "Unknown"
                
                message += f"🍺 <b>{offer.name}</b>\n"
                message += f"   ID: {offer.offer_id}\n"
                message += f"   Supplier: {supplier_name}\n"
                message += f"   Price: €{offer.price_per_unit:.2f}\n"
                message += f"   Box Size: {offer.wholesale_box_size}\n\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}

    def _handle_box_status(self, chat_id: int) -> Dict[str, Any]:
        """Handle /box_status command"""
        offers = self.db.list_offers()
        
        message = "📦 <b>Box Status:</b>\n\n"
        for offer in offers:
            if offer.status == OfferStatus.ACTIVE.value:
                boxes = self.db.get_boxes_by_offer(offer.offer_id)
                
                message += f"🍺 <b>{offer.name}</b>\n"
                for box in boxes:
                    status_emoji = {
                        BoxStatus.OPEN.value: "🟢",
                        BoxStatus.MINIMUM_REACHED.value: "🟡",
                        BoxStatus.FULL.value: "🔴",
                        BoxStatus.ORDERED.value: "📦",
                        BoxStatus.DELIVERED.value: "✅"
                    }.get(box.status, "❓")
                    
                    message += f"   {status_emoji} Box {box.box_id[:8]}: {box.current_quantity}/{box.max_capacity} ({box.status})\n"
                message += "\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}

    def _handle_start(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /start command"""
        message = "🍺 Welcome to UBBC Bot!\n\n"
        message += "Available commands:\n"
        message += "/start - Show this help\n"
        message += "/order <offer_id> <quantity> - Place an order\n"
        message += "/my_orders - View your orders\n"
        
        if self._is_admin(user_id):
            message += "\n👑 Admin commands:\n"
            message += "/add_supplier <name> - Add supplier\n"
            message += "/create_offer <supplier_id> <name> <price> <box_size> - Create offer\n"
            message += "/list_offers - List all offers\n"
            message += "/box_status - View box status\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}

    def _handle_order(self, chat_id: int, user_id: int, args: list) -> Dict[str, Any]:
        """Handle /order command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /order <offer_id> <quantity>")
            return {'status': 'invalid_args'}

        try:
            offer_id = args[0]
            quantity = int(args[1])

            if quantity <= 0:
                self._send_message(chat_id, "❌ Quantity must be positive")
                return {'status': 'invalid_quantity'}

            # Get offer
            offer = self.db.get_offer(offer_id)
            if not offer or offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, "❌ Offer not found or inactive")
                return {'status': 'offer_not_found'}

            # Get customer
            customer = self.db.get_customer_by_telegram_id(user_id)
            if not customer:
                self._send_message(chat_id, "❌ Customer not found")
                return {'status': 'customer_not_found'}

            # Find available box
            boxes = self.db.get_boxes_by_offer(offer_id)
            available_box = None
            
            for box in boxes:
                if box.status in [BoxStatus.OPEN.value, BoxStatus.MINIMUM_REACHED.value]:
                    if box.current_quantity + quantity <= box.max_capacity:
                        available_box = box
                        break

            # Create new box if needed
            if not available_box:
                available_box = Box(
                    offer_id=offer_id,
                    max_capacity=offer.wholesale_box_size,
                    min_breakeven=offer.min_quantity_breakeven
                )
                self.db.create_box(available_box)

            # Create order
            order = Order(
                customer_id=customer.customer_id,
                box_id=available_box.box_id,
                offer_id=offer_id,
                quantity=quantity,
                unit_price=offer.price_per_unit,
                total_price=offer.price_per_unit * quantity
            )

            if self.db.create_order(order):
                # Update box quantity and status
                new_quantity = available_box.current_quantity + quantity
                updates = {'current_quantity': new_quantity}
                
                if new_quantity >= available_box.min_breakeven:
                    updates['status'] = BoxStatus.MINIMUM_REACHED.value
                if new_quantity >= available_box.max_capacity:
                    updates['status'] = BoxStatus.FULL.value

                self.db.update_box(available_box.box_id, updates)

                self._send_message(chat_id, 
                    f"✅ Order placed!\n"
                    f"Order ID: {order.order_id}\n"
                    f"Product: {offer.name}\n"
                    f"Quantity: {quantity}\n"
                    f"Total: €{order.total_price:.2f}")
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to place order")
                return {'status': 'error'}

        except ValueError:
            self._send_message(chat_id, "❌ Invalid quantity format")
            return {'status': 'invalid_format'}

    def _handle_my_orders(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /my_orders command"""
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, "❌ Customer not found")
            return {'status': 'customer_not_found'}

        orders = self.db.get_orders_by_customer(customer.customer_id)
        
        if not orders:
            self._send_message(chat_id, "You have no orders")
            return {'status': 'no_orders'}

        message = "📋 <b>Your Orders:</b>\n\n"
        for order in orders:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else "Unknown"
            
            status_emoji = {
                'pending': '⏳',
                'confirmed': '✅',
                'cancelled': '❌',
                'delivered': '📦'
            }.get(order.status, '❓')
            
            message += f"{status_emoji} <b>{offer_name}</b>\n"
            message += f"   Quantity: {order.quantity}\n"
            message += f"   Total: €{order.total_price:.2f}\n"
            message += f"   Status: {order.status}\n\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}