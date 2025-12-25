from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from models.entities import OfferStatus

class InfoCommands(BaseHandler):
    def handle_start(self, chat_id: int, user_id: int, args: list = None) -> Dict[str, Any]:
        """Handle /start command with optional help section parameter"""
        import logging
        logger = logging.getLogger()
        
        if self.environment == 'test':
            logger.info(f"Processing /start command for user {user_id}, chat {chat_id}")
        
        # Check if specific help section requested
        section = args[0].lower() if args and len(args) > 0 else None
        
        if section:
            return self._show_help_section(chat_id, user_id, section)
        
        # Show general help
        message = "🍺 Welcome to UBBC Bot!\n\n"
        message += "📋 General:\n"
        message += "/start - Show this help\n"
        message += "/help [section] - Show help for specific section\n\n"
        message += "🛒 Orders:\n"
        message += "/list_offers - View available offers\n"
        message += "/order <offer_id> [quantity] - Place an order\n"
        message += "/confirm_order <offer_id> <quantity> - Confirm duplicate order\n"
        message += "/my_orders [id] - View your orders\n\n"
        message += "🔔 Notifications:\n"
        message += "/subscribe - Subscribe to offer notifications\n"
        message += "/unsubscribe - Unsubscribe from notifications\n"
        
        if self._is_admin(user_id):
            message += "\n👑 Admin sections available: suppliers, offers, orders, users\n"
            message += "Use /help [section] for detailed commands\n"
        
        result = self._send_message(chat_id, message)
        success = result.get('success', False)
        if self.environment == 'test':
            logger.info(f"Message send result: {success}")
        
        return {'status': 'success'}
    
    def handle_help(self, chat_id: int, user_id: int, args: list = None) -> Dict[str, Any]:
        """Handle /help command with optional section parameter"""
        section = args[0].lower() if args and len(args) > 0 else None
        
        if section:
            return self._show_help_section(chat_id, user_id, section)
        
        # Show available sections
        message = "📚 Help Sections:\n\n"
        message += "📋 [/help general](https://t.me/{bot_username}?start=help_general) - Basic commands\n"
        message += "🛒 [/help orders](https://t.me/{bot_username}?start=help_orders) - Order management\n"
        
        if self._is_admin(user_id):
            message += "\n👑 Admin Sections:\n"
            message += "🏭 [/help suppliers](https://t.me/{bot_username}?start=help_suppliers) - Supplier management\n"
            message += "🍺 [/help offers](https://t.me/{bot_username}?start=help_offers) - Offer management\n"
            message += "👥 [/help users](https://t.me/{bot_username}?start=help_users) - User management\n"
        
        # Replace bot_username placeholder
        bot_username = self._get_bot_username()
        message = message.format(bot_username=bot_username)
        
        self._send_message(chat_id, message, parse_mode="Markdown")
        return {'status': 'success'}
    
    def _show_help_section(self, chat_id: int, user_id: int, section: str) -> Dict[str, Any]:
        """Show help for specific section"""
        if section == "general":
            message = "📋 General Commands:\n\n"
            message += "/start - Show main help\n"
            message += "/help [section] - Show help for specific section\n"
            message += "/list_offers - View available offers\n"
            message += "/subscribe - Subscribe to offer notifications\n"
            message += "/unsubscribe - Unsubscribe from notifications\n"
        
        elif section == "orders":
            message = "🛒 Order Commands:\n\n"
            message += "/order <offer_id> [quantity] - Place an order\n"
            message += "/confirm_order <offer_id> <quantity> - Confirm duplicate order\n"
            message += "/my_orders [id] - View your orders\n"
        
        elif section == "suppliers" and self._is_admin(user_id):
            message = "🏭 Supplier Management:\n\n"
            message += "/add_supplier <name> - Add supplier\n"
            message += "/retire_supplier <name> - Retire supplier\n"
            message += "/list_suppliers [active|retired|all] - List suppliers\n"
            message += "/edit_supplier <name> - Edit supplier details\n"
        
        elif section == "offers" and self._is_admin(user_id):
            message = "🍺 Offer Management:\n\n"
            message += "/create_offer <supplier> <name> <price> <box_size> - Create draft offer\n"
            message += "/edit_offer_details <offer_id> - Edit description and images\n"
            message += "/preview_offer <offer_id> - Preview offer appearance\n"
            message += "/publish_offer <offer_id> - Publish draft offer\n"
            message += "/cancel_offer <offer_id> - Cancel offer and all orders\n"
            message += "/edit_offer <offer_id> - Edit basic offer details\n"
            message += "/add_box <offer_id> - Add box to offer\n"
            message += "/box_status - View box status\n"
            message += "/fulfill_offer <offer_id> - Start fulfillment process\n"
        
        elif section == "users" and self._is_admin(user_id):
            message = "👥 User Management:\n\n"
            message += "/pending_users - View users awaiting approval\n"
            message += "/list_users - View all customers\n"
            message += "/approve_user <username> - Approve user\n"
            message += "/reject_user <username> - Reject user\n"
            message += "/user_status <username> - Check user status\n"
            message += "/update_user <username> <first_name> [last_name] - Update name\n"
            message += "/order_for <username> <offer_id> [quantity] - Place order for user\n"
            message += "/cancel_order <order_id> - Cancel customer order\n"
            message += "/user_orders <username> - View orders for user\n"
            message += "/all_orders [status] - Download CSV of orders\n"
        
        else:
            if not self._is_admin(user_id) and section in ["suppliers", "offers", "users"]:
                message = "❌ Admin-only section"
            else:
                message = f"❌ Unknown section: {section}\n\n"
                message += "Available sections: general, orders"
                if self._is_admin(user_id):
                    message += ", suppliers, offers, users"
        
        self._send_message(chat_id, message)
        return {'status': 'success'}

    def handle_subscribe(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /subscribe command"""
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, "❌ You must register first. Send /start")
            return {'status': 'not_registered'}
        
        # Update subscription status
        if self.db.update_customer(customer.customer_id, {'subscribed_to_offers': True}):
            self._send_message(chat_id, "✅ Subscribed to new offer notifications! You'll receive private messages when new offers are available.")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to subscribe")
            return {'status': 'error'}
    
    def handle_unsubscribe(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /unsubscribe command"""
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, "❌ You are not registered")
            return {'status': 'not_registered'}
        
        # Update subscription status
        if self.db.update_customer(customer.customer_id, {'subscribed_to_offers': False}):
            self._send_message(chat_id, "✅ Unsubscribed from offer notifications")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to unsubscribe")
            return {'status': 'error'}
    
    def handle_list_offers(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /list_offers command"""
        offers = self.db.list_offers()
        
        if not offers:
            self._send_message(chat_id, "No offers found")
            return {'status': 'no_offers'}

        # Sort offers by offer_id ascending
        offers.sort(key=lambda x: x.offer_id)

        message = ""
        
        # Check for active discount
        active_discount = self.db.get_active_discount()
        if active_discount:
            message += f"🎉 DISCOUNT ACTIVE: {active_discount.discount_percentage}% OFF!\n"
            if active_discount.end_time:
                from utils.timezone import to_cet_string
                message += f"Valid until: {to_cet_string(active_discount.end_time)}\n"
            message += "\n"
        
        is_admin = self._is_admin(user_id)
        
        if is_admin:
            # Show all offers with status indicators for admin
            message += "📋 All Offers (Admin View):\n\n"
            
            # Group by status
            draft_offers = [o for o in offers if o.status == OfferStatus.DRAFT.value]
            active_offers = [o for o in offers if o.status == OfferStatus.ACTIVE.value]
            other_offers = [o for o in offers if o.status not in [OfferStatus.DRAFT.value, OfferStatus.ACTIVE.value]]
            
            # Show draft offers first
            if draft_offers:
                message += "📝 DRAFT OFFERS:\n"
                for offer in draft_offers:
                    escaped_name = offer.name.replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
                    message += f"📝 [{offer.offer_id}] {escaped_name} €{offer.price_per_unit:.2f} (draft)\n"
                message += "\n"
            
            # Show active offers
            if active_offers:
                message += "🍺 ACTIVE OFFERS:\n"
                for offer in active_offers:
                    # Get total customer orders vs total capacity
                    boxes = self.db.get_boxes_by_offer(offer.offer_id)
                    total_capacity = sum(box.max_capacity for box in boxes)
                    
                    # Count actual customer orders (not box quantities)
                    all_orders = self.db.get_orders_by_offer(offer.offer_id)
                    active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
                    total_ordered = sum(order.quantity for order in active_orders)
                    
                    original_price = offer.price_per_unit
                    display_price = original_price
                    
                    if active_discount:
                        display_price = original_price * (1 - active_discount.discount_percentage / 100)
                    
                    bot_username = self._get_bot_username()
                    message += f"🍺 <a href='https://t.me/{bot_username}?start=offer_details_{offer.offer_id}'>[{offer.offer_id}]</a> {offer.name} €{display_price:.2f} ({total_ordered}/{total_capacity})\n"
                message += "\n"
            
            # Show other status offers
            if other_offers:
                # Group by specific status
                status_groups = {}
                for offer in other_offers:
                    if offer.status not in status_groups:
                        status_groups[offer.status] = []
                    status_groups[offer.status].append(offer)
                
                for status, status_offers in status_groups.items():
                    status_emoji = {
                        OfferStatus.SOLD_OUT.value: "🚫",
                        OfferStatus.ORDERED.value: "📦",
                        OfferStatus.COMPLETED.value: "✅",
                        OfferStatus.DELIVERED.value: "🚚",
                        OfferStatus.INACTIVE.value: "❌"
                    }.get(status, "❓")
                    
                    message += f"{status_emoji} {status.upper()}:\n"
                    
                    for offer in status_offers:
                        # Get order counts for non-active offers too
                        boxes = self.db.get_boxes_by_offer(offer.offer_id)
                        total_capacity = sum(box.max_capacity for box in boxes)
                        
                        all_orders = self.db.get_orders_by_offer(offer.offer_id)
                        active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
                        total_ordered = sum(order.quantity for order in active_orders)
                        
                        escaped_name = offer.name.replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
                        message += f"{status_emoji} [{offer.offer_id}] {escaped_name} €{offer.price_per_unit:.2f} ({total_ordered}/{total_capacity})\n"
                    
                    message += "\n"
        else:
            # Show only active offers for customers
            message += "📋 Active Offers:\n\n"
            active_found = False
            for offer in offers:
                if offer.status == OfferStatus.ACTIVE.value:
                    active_found = True
                    # Get total customer orders vs total capacity
                    boxes = self.db.get_boxes_by_offer(offer.offer_id)
                    total_capacity = sum(box.max_capacity for box in boxes)
                    
                    # Count actual customer orders (not box quantities)
                    all_orders = self.db.get_orders_by_offer(offer.offer_id)
                    active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
                    total_ordered = sum(order.quantity for order in active_orders)
                    
                    original_price = offer.price_per_unit
                    display_price = original_price
                    
                    if active_discount:
                        display_price = original_price * (1 - active_discount.discount_percentage / 100)
                    
                    bot_username = self._get_bot_username()
                    message += f"🍺 <a href='https://t.me/{bot_username}?start=offer_details_{offer.offer_id}'>[{offer.offer_id}]</a> {offer.name} €{display_price:.2f} ({total_ordered}/{total_capacity})\n"
            
            if not active_found:
                self._send_message(chat_id, "🍺 No active offers available")
                return {'status': 'no_offers'}

        self._send_message(chat_id, message, parse_mode="HTML")
        return {'status': 'success'}

    def handle_my_orders(self, chat_id: int, user_id: int, args: list = None) -> Dict[str, Any]:
        """Handle /my_orders command"""
        show_ids = args and len(args) > 0 and args[0].lower() == 'id'
        
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, "❌ Customer not found")
            return {'status': 'customer_not_found'}

        orders = self.db.get_orders_by_customer(customer.customer_id)
        
        if not orders:
            self._send_message(chat_id, "You have no orders")
            return {'status': 'no_orders'}

        # Sort orders by offer_id ascending
        orders.sort(key=lambda x: x.offer_id)
        
        # Aggregate orders by offer, price and status
        aggregated = {}
        for order in orders:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else "Unknown"
            
            key = (order.offer_id, order.unit_price, order.status)
            if key not in aggregated:
                aggregated[key] = {
                    'offer_name': offer_name,
                    'unit_price': order.unit_price,
                    'status': order.status,
                    'quantity': 0,
                    'total_price': Decimal('0.0'),
                    'dates': set(),
                    'order_ids': []
                }
            
            aggregated[key]['quantity'] += order.quantity
            aggregated[key]['total_price'] += order.total_price
            aggregated[key]['order_ids'].append(order.order_id)
            
            # Add date
            from utils.timezone import to_cet_string
            aggregated[key]['dates'].add(to_cet_string(order.created_at, '%Y-%m-%d'))

        message = "📋 Your Orders:\n\n"
        
        # Group by status for totals
        status_groups = {}
        for (offer_id, unit_price, status), data in aggregated.items():
            if status not in status_groups:
                status_groups[status] = {'total_price': Decimal('0.0'), 'items': []}
            status_groups[status]['total_price'] += data['total_price']
            status_groups[status]['items'].append(((offer_id, unit_price, status), data))
        
        # Display orders grouped by status
        open_statuses = ['pending', 'ordered', 'confirmed']
        open_total = Decimal('0.0')
        
        # First show open orders
        for status in ['pending', 'ordered', 'confirmed', 'delivered']:
            if status not in status_groups:
                continue
                
            status_emoji = {
                'pending': '⏳',
                'ordered': '📦',
                'confirmed': '✅',
                'cancelled': '❌',
                'delivered': '🚚'
            }.get(status, '❓')
            
            # Add status header if multiple statuses present
            if len(status_groups) > 1:
                message += f"{status_emoji} {status.upper()}:\n"
            
            for (offer_id, unit_price, order_status), data in status_groups[status]['items']:
                # Determine date display
                if len(data['dates']) == 1:
                    date_display = f"[{list(data['dates'])[0]}]"
                else:
                    date_display = "[multiple days]"
                
                order_line = f"{status_emoji} {date_display} {data['offer_name']} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f}"
                
                if show_ids:
                    ids_display = ', '.join(data['order_ids'])
                    order_line += f" - {ids_display}"
                
                message += order_line + "\n"
            
            # Add status total if multiple statuses present
            if len(status_groups) > 1:
                message += f"Subtotal: €{status_groups[status]['total_price']:.2f}\n\n"
            
            # Add to open total if applicable
            if status in open_statuses:
                open_total += status_groups[status]['total_price']
        
        # Add open orders total before cancelled orders
        if open_total > 0 and 'cancelled' in status_groups:
            message += f"📊 Open Orders Total: €{open_total:.2f}\n\n"
        
        # Show cancelled orders last (no total needed)
        if 'cancelled' in status_groups:
            status_emoji = '❌'
            if len(status_groups) > 1:
                message += f"{status_emoji} CANCELLED:\n"
            
            for (offer_id, unit_price, order_status), data in status_groups['cancelled']['items']:
                # Determine date display
                if len(data['dates']) == 1:
                    date_display = f"[{list(data['dates'])[0]}]"
                else:
                    date_display = "[multiple days]"
                
                order_line = f"{status_emoji} {date_display} {data['offer_name']} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f}"
                
                if show_ids:
                    ids_display = ', '.join(data['order_ids'])
                    order_line += f" - {ids_display}"
                
                message += order_line + "\n"
        
        # Add open orders total if no cancelled orders
        elif open_total > 0:
            message += f"📊 Open Orders Total: €{open_total:.2f}"

        self._send_message(chat_id, message)
        return {'status': 'success'}
    
    def handle_offer_details(self, chat_id: int, user_id: int, args: list = None) -> Dict[str, Any]:
        """Handle offer details display from deep link"""
        if not args:
            self._send_message(chat_id, "❌ No offer ID provided")
            return {'status': 'invalid_args'}
        
        try:
            offer_id = int(args[0])
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, "❌ Offer not found")
                return {'status': 'offer_not_found'}
            
            # Only show active offers to non-admin users
            if not self._is_admin(user_id) and offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, "❌ Offer not available")
                return {'status': 'offer_not_available'}
            
            # Send rich offer details
            self._send_rich_offer_details(chat_id, offer, user_id)
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, "❌ Invalid offer ID")
            return {'status': 'invalid_format'}
    
    def _send_rich_offer_details(self, chat_id: int, offer, user_id: int):
        """Send rich offer details with images and description"""
        # Send images first if available
        if offer.images:
            for image_url in offer.images:
                try:
                    self._send_photo(chat_id, image_url)
                except Exception as e:
                    print(f"Failed to send image {image_url}: {e}")
        
        # Build detailed message
        message = f"🍺 {offer.name}\n\n"
        message += f"🏷️ Offer ID: {offer.offer_id}\n"
        message += f"💰 Price: €{offer.price_per_unit:.2f} per unit\n"
        
        # Show box size and supplier only to admins
        if self._is_admin(user_id):
            message += f"📦 Box size: {offer.wholesale_box_size} units\n"
            message += f"🏭 Supplier: {offer.supplier_name}\n"
        
        if offer.status == OfferStatus.ACTIVE.value:
            # Show availability for active offers
            boxes = self.db.get_boxes_by_offer(offer.offer_id)
            total_capacity = sum(box.max_capacity for box in boxes)
            all_orders = self.db.get_orders_by_offer(offer.offer_id)
            active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
            total_ordered = sum(order.quantity for order in active_orders)
            available = total_capacity - total_ordered
            
            message += f"📋 Available: {available}/{total_capacity} units\n"
        else:
            message += f"📋 Status: {offer.status}\n"
        
        if offer.description:
            message += f"\n📝 Description:\n{offer.description}\n"
        
        # Add order buttons for active offers
        reply_markup = None
        if offer.status == OfferStatus.ACTIVE.value:
            message += f"\n📝 Order with: /order {offer.offer_id} [quantity]"
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🍺   Order 1", "callback_data": f"order_{offer.offer_id}_1"},
                        {"text": "🍺🍺 Order 2", "callback_data": f"order_{offer.offer_id}_2"}
                    ]
                ]
            }
        
        self._send_message(chat_id, message, reply_markup=reply_markup, parse_mode="HTML")