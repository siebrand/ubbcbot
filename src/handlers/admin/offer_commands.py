import os
from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import Offer, Box, Order, BoxStatus, OfferStatus

class OfferCommands(BaseHandler):
    def handle_create_offer(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /create_offer command"""
        if len(args) < 4:
            self._send_message(chat_id, "Usage: /create_offer <supplier_name> <name> <price> <box_size>")
            return {'status': 'invalid_args'}

        try:
            supplier_name = args[0]
            price = float(args[-2])
            box_size = int(args[-1])
            
            # Validate and sanitize name
            name = ' '.join(args[1:-2]).strip()
            if len(name) > 100:
                self._send_message(chat_id, "❌ Product name too long (max 100 characters)")
                return {'status': 'invalid_name'}
            
            if '<' in name or '>' in name:
                self._send_message(chat_id, "❌ Product name cannot contain < or > characters")
                return {'status': 'invalid_name'}

            # Validate box size
            valid_sizes = [1, 2, 6, 8, 10, 12, 15, 16, 18, 20, 24]
            if box_size not in valid_sizes:
                self._send_message(chat_id, f"❌ Invalid box size. Valid sizes: {valid_sizes}")
                return {'status': 'invalid_box_size'}

            # Check supplier exists
            supplier = self.db.get_supplier_by_name(supplier_name)
            if not supplier:
                self._send_message(chat_id, "❌ Supplier not found")
                return {'status': 'supplier_not_found'}

            # Create offer
            offer = Offer(
                supplier_name=supplier_name,
                name=name,
                price_per_unit=Decimal(str(price)),
                wholesale_box_size=box_size,
                min_quantity_breakeven=max(1, int(box_size * 0.8))
            )

            if self.db.create_offer(offer):
                # Create initial box
                box = Box(
                    offer_id=offer.offer_id,
                    max_capacity=box_size,
                    min_breakeven=offer.min_quantity_breakeven
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
                        unit_price=Decimal(str(price)),
                        total_price=Decimal(str(price))
                    )
                    self.db.create_order(admin_order)
                    
                    # Update box quantity
                    updates = {'current_quantity': 1}
                    if 1 >= box.max_capacity:
                        updates['status'] = BoxStatus.FULL.value
                    elif 1 >= box.min_breakeven:
                        updates['status'] = BoxStatus.MINIMUM_REACHED.value
                    
                    if not self.db.update_box(box.box_id, updates):
                        self._send_message(chat_id, "⚠️ Auto-order placed but box update failed")
                    else:
                        self._send_message(chat_id, f"✅ Auto-ordered 1 unit for you. Order ID: {admin_order.order_id}")

                # Announce new offer to default group
                self._announce_offer(offer)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, "❌ Failed to create offer")
                return {'status': 'error'}

        except (ValueError, IndexError) as e:
            self._send_message(chat_id, f"❌ Invalid format. Error: {str(e)}")
            return {'status': 'invalid_format'}

    def handle_box_status(self, chat_id: int) -> Dict[str, Any]:
        """Handle /box_status command"""
        offers = self.db.list_offers()
        
        message = "📦 Box Status:\n\n"
        for offer in offers:
            if offer.status == OfferStatus.ACTIVE.value:
                boxes = self.db.get_boxes_by_offer(offer.offer_id)
                boxes.sort(key=lambda x: x.box_id)
                
                for box in boxes:
                    status_emoji = {
                        BoxStatus.OPEN.value: "🟢",
                        BoxStatus.MINIMUM_REACHED.value: "🟡",
                        BoxStatus.FULL.value: "🔴",
                        BoxStatus.ORDERED.value: "📦",
                        BoxStatus.DELIVERED.value: "✅"
                    }.get(box.status, "❓")
                    
                    message += f"🍺 {offer.name} €{offer.price_per_unit:.2f}\n   {status_emoji} Box {box.box_id[:8]}: {box.current_quantity}/{box.max_capacity} ({box.status})\n\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}

    def _announce_offer(self, offer):
        """Announce new offer to default group"""
        default_group_id = os.environ.get('DEFAULT_GROUP_ID')
        if default_group_id:
            announcement = f"🍺 New offer available!\n\n"
            announcement += f"[{offer.offer_id}] {offer.name}\n"
            announcement += f"Price: €{offer.price_per_unit:.2f} per unit\n"
            announcement += f"Box size: {offer.wholesale_box_size} units\n\n"
            announcement += f"Order with: /order {offer.offer_id} [quantity]"
            
            # Create inline keyboard with order buttons
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🍺 Order 1", "callback_data": f"order_{offer.offer_id}_1"},
                        {"text": "🍺🍺 Order 2", "callback_data": f"order_{offer.offer_id}_2"}
                    ]
                ]
            }
            
            self._send_message(int(default_group_id), announcement, reply_markup=reply_markup)