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
        message = self._t('welcome_ubbc')
        
        if self._is_admin(user_id):
            message += self._t('admin_sections_available')
        
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
        
        # Get bot username first
        bot_username = self._get_bot_username()
        
        # Show available sections
        message = self._t('help_sections', bot_username=bot_username)
        
        if self._is_admin(user_id):
            message += self._t('admin_help_sections', bot_username=bot_username)
        
        # Replace bot_username placeholder
        message = message.format(bot_username=bot_username)
        
        self._send_message(chat_id, message, parse_mode="Markdown")
        return {'status': 'success'}
    
    def _show_help_section(self, chat_id: int, user_id: int, section: str) -> Dict[str, Any]:
        """Show help for specific section"""
        if section == "all":
            # Show all available sections
            sections = ["general", "orders"]
            if self._is_admin(user_id):
                sections.extend(["suppliers", "offers", "users", "delivery"])
            
            message = ""
            for i, sect in enumerate(sections):
                if i > 0:
                    message += "\n\n"
                message += self._get_section_help(sect)
            
            self._send_message(chat_id, message)
            return {'status': 'success'}
        
        elif section in ["general", "orders", "suppliers", "offers", "users", "delivery"]:
            if section in ["suppliers", "offers", "users", "delivery"] and not self._is_admin(user_id):
                message = self._t('admin_only_section')
            else:
                message = self._get_section_help(section)
        
        else:
            available_sections = ["general", "orders", "all"]
            if self._is_admin(user_id):
                available_sections.extend(["suppliers", "offers", "users", "delivery"])
            
            sections_text = ", ".join(available_sections)
            message = self._t('unknown_section', user_id, section=section, sections=sections_text)
        
        self._send_message(chat_id, message)
        return {'status': 'success'}
    
    def _get_section_help(self, section: str) -> str:
        """Get help text for a specific section"""
        if section == "general":
            return self._t('help_general')
        elif section == "orders":
            return self._t('help_orders')
        elif section == "suppliers":
            return self._t('help_suppliers')
        elif section == "offers":
            return self._t('help_offers')
        elif section == "users":
            return self._t('help_users')
        elif section == "delivery":
            return self._t('help_delivery')
        return ""

    def _format_offer_line(self, offer, status_emoji, total_ordered=None, total_capacity=None, is_draft=False):
        """Format a single offer line with consistent markup"""
        bot_username = self._get_bot_username()
        
        if is_draft:
            return f"{status_emoji} <a href='https://t.me/{bot_username}?start=offer_details_{offer.offer_id}'><b>{offer.offer_id}</b></a> <b>{offer.name}</b> €{offer.price_per_unit:.2f} (draft)\n"
        elif total_ordered is not None and total_capacity is not None:
            return f"{status_emoji} <a href='https://t.me/{bot_username}?start=offer_details_{offer.offer_id}'><b>{offer.offer_id}</b></a> <b>{offer.name}</b> €{offer.price_per_unit:.2f} ({total_ordered}/{total_capacity})\n"
        else:
            return f"{status_emoji} <a href='https://t.me/{bot_username}?start=offer_details_{offer.offer_id}'><b>{offer.offer_id}</b></a> <b>{offer.name}</b> €{offer.price_per_unit:.2f}\n"
    
    def _get_offer_capacity_info(self, offer_id: int):
        """Get order and capacity information for an offer"""
        boxes = self.db.get_boxes_by_offer(offer_id)
        total_capacity = sum(box.max_capacity for box in boxes)
        all_orders = self.db.get_orders_by_offer(offer_id)
        active_orders = [o for o in all_orders if o.status in ['pending', 'ordered']]
        total_ordered = sum(order.quantity for order in active_orders)
        return total_ordered, total_capacity
    
    def _apply_discount_to_offer(self, offer, active_discount):
        """Apply discount to offer and return modified copy"""
        if not active_discount:
            return offer
        
        display_price = offer.price_per_unit * (1 - active_discount.discount_percentage / 100)
        offer_copy = type(offer)(**{k: v for k, v in offer.__dict__.items()})
        offer_copy.price_per_unit = display_price
        return offer_copy
    
    def _validate_customer(self, chat_id: int, user_id: int):
        """Validate customer exists and return customer object or error status"""
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, self._t('must_register', user_id))
            return None, {'status': 'not_registered'}
        return customer, None
    
    def handle_subscribe(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /subscribe command"""
        customer, error = self._validate_customer(chat_id, user_id)
        if error:
            return error
        
        # Update subscription status
        if self.db.update_customer(customer.customer_id, {'subscribed_to_offers': True}):
            self._send_message(chat_id, self._t('subscribed', user_id))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_subscribe', user_id))
            return {'status': 'error'}
    
    def handle_unsubscribe(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /unsubscribe command"""
        customer, error = self._validate_customer(chat_id, user_id)
        if error:
            return error
        
        # Update subscription status
        if self.db.update_customer(customer.customer_id, {'subscribed_to_offers': False}):
            self._send_message(chat_id, self._t('unsubscribed', user_id))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_unsubscribe', user_id))
            return {'status': 'error'}
    
    def handle_list_offers(self, chat_id: int, user_id: int, args: list = None) -> Dict[str, Any]:
        """Handle /list_offers command"""
        offers = self.db.list_offers()
        
        if not offers:
            self._send_message(chat_id, self._t('no_offers', user_id))
            return {'status': 'no_offers'}

        # Sort offers by offer_id ascending
        offers.sort(key=lambda x: x.offer_id)

        message = ""
        
        # Check for active discount
        active_discount = self.db.get_active_discount()
        if active_discount:
            message += self._t('discount_active', percentage=active_discount.discount_percentage)
            if active_discount.end_time:
                from utils.timezone import to_cet_string
                message += "\n" + self._t('valid_until', end_time=to_cet_string(active_discount.end_time))
            message += "\n\n"
        
        is_admin = self._is_admin(user_id)
        # Check if admin wants to see user view or sold out offers
        show_user_view = args and len(args) > 0 and args[0].lower() == 'user' and is_admin
        show_sold_out = args and len(args) > 0 and args[0].lower() == 'sold_out'
        
        if show_sold_out:
            # Show sold out offers from last 7 days for any user
            sold_out_offers = self.db.list_sold_out_offers_recent(7)
            
            if not sold_out_offers:
                self._send_message(chat_id, self._t('no_offers', user_id))
                return {'status': 'no_offers'}
            
            message += self._t('sold_out_offers_title', user_id) + "\n\n"
            for offer in sold_out_offers:
                total_ordered, total_capacity = self._get_offer_capacity_info(offer.offer_id)
                message += self._format_offer_line(offer, "🚫", total_ordered, total_capacity)
            
            self._send_message(chat_id, message, parse_mode="HTML")
            return {'status': 'success'}
        
        if is_admin and not show_user_view:
            # Show all offers with status indicators for admin
            message += self._t('all_offers_admin') + "\n\n"
            
            # Group by status
            draft_offers = [o for o in offers if o.status == OfferStatus.DRAFT.value]
            active_offers = [o for o in offers if o.status == OfferStatus.ACTIVE.value]
            other_offers = [o for o in offers if o.status not in [OfferStatus.DRAFT.value, OfferStatus.ACTIVE.value]]
            
            # Show draft offers first
            if draft_offers:
                message += self._t('draft_offers') + "\n"
                for offer in draft_offers:
                    message += self._format_offer_line(offer, "📝", is_draft=True)
                message += "\n"
            
            # Show active offers
            if active_offers:
                message += self._t('active_offers') + "\n"
                for offer in active_offers:
                    total_ordered, total_capacity = self._get_offer_capacity_info(offer.offer_id)
                    offer_to_display = self._apply_discount_to_offer(offer, active_discount)
                    message += self._format_offer_line(offer_to_display, "🍺", total_ordered, total_capacity)
                message += "\n"
            
            # Show other status offers in correct order
            if other_offers:
                # Define the correct order
                status_order = [OfferStatus.SOLD_OUT.value, OfferStatus.COMPLETED.value, OfferStatus.INACTIVE.value]
                
                for status in status_order:
                    status_offers = [o for o in other_offers if o.status == status]
                    if not status_offers:
                        continue
                        
                    status_emoji = {
                        OfferStatus.SOLD_OUT.value: "🚫",
                        OfferStatus.ORDERED.value: "📦",
                        OfferStatus.COMPLETED.value: "✅",
                        OfferStatus.DELIVERED.value: "🚚",
                        OfferStatus.INACTIVE.value: "❌"
                    }.get(status, "❓")
                    
                    status_label = {
                        OfferStatus.SOLD_OUT.value: self._t('status_sold_out', user_id=None),
                        OfferStatus.ORDERED.value: self._t('status_ordered', user_id=None),
                        OfferStatus.DELIVERED.value: self._t('status_delivered', user_id=None),
                        OfferStatus.COMPLETED.value: self._t('status_completed', user_id=None),
                        OfferStatus.INACTIVE.value: self._t('status_inactive', user_id=None)
                    }.get(status, status.upper())
                    
                    message += f"{status_emoji} {status_label}:\n"
                    
                    for offer in status_offers:
                        total_ordered, total_capacity = self._get_offer_capacity_info(offer.offer_id)
                        message += self._format_offer_line(offer, status_emoji, total_ordered, total_capacity)
                    
                    message += "\n"
        else:
            # Show only active offers for customers
            message += self._t('active_offers_customer') + "\n\n"
            active_found = False
            for offer in offers:
                if offer.status == OfferStatus.ACTIVE.value:
                    active_found = True
                    total_ordered, total_capacity = self._get_offer_capacity_info(offer.offer_id)
                    offer_to_display = self._apply_discount_to_offer(offer, active_discount)
                    message += self._format_offer_line(offer_to_display, "🍺", total_ordered, total_capacity)
            
            if not active_found:
                self._send_message(chat_id, self._t('no_offers', user_id))
                return {'status': 'no_offers'}

        self._send_message(chat_id, message, parse_mode="HTML")
        return {'status': 'success'}

    def handle_my_orders(self, chat_id: int, user_id: int, args: list = None) -> Dict[str, Any]:
        """Handle /my_orders command"""
        show_ids = args and len(args) > 0 and args[0].lower() == 'id'
        
        customer = self.db.get_customer_by_telegram_id(user_id)
        if not customer:
            self._send_message(chat_id, self._t('customer_not_found', user_id))
            return {'status': 'customer_not_found'}

        orders = self.db.get_orders_by_customer(customer.customer_id)
        
        if not orders:
            self._send_message(chat_id, self._t('no_orders', user_id))
            return {'status': 'no_orders'}

        # Sort orders by offer_id ascending
        orders.sort(key=lambda x: x.offer_id)
        
        # Aggregate orders by offer, price and status
        aggregated = {}
        for order in orders:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else self._t('unknown', user_id)
            
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

        message = self._t('my_orders_title', user_id) + "\n\n"
        
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
        for status in ['pending', 'ordered', 'confirmed', 'ready_for_labeling', 'labeling_completed', 'awaiting_payment', 'delivered', 'completed']:
            if status not in status_groups:
                continue
                
            status_emoji = {
                'pending': '⏳',
                'ordered': '📦',
                'confirmed': '✅',
                'ready_for_labeling': '🏷️',
                'labeling_completed': '✅',
                'awaiting_payment': '💳',
                'cancelled': '❌',
                'delivered': '🚚',
                'completed': '✅'
            }.get(status, '❓')
            
            # Add status header if multiple statuses present or if this is completed status
            if len(status_groups) > 1 or status == 'completed':
                status_key = f"status_{status}"
                status_label = self._t(status_key, user_id).upper()
                message += f"{status_emoji} {status_label}:\n"
            
            line_count = 0
            for (offer_id, unit_price, order_status), data in status_groups[status]['items']:
                # Determine date display
                if len(data['dates']) == 1:
                    date_display = f"[{list(data['dates'])[0]}]"
                else:
                    date_display = f"[{self._t('multiple_days_label', user_id)}]"
                
                # Alternate diamond icons for better readability
                line_icon = "🔸" if line_count % 2 == 0 else "🔹"
                
                order_line = f"{line_icon} {date_display} [{offer_id}] {data['offer_name']} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f}"
                
                if show_ids:
                    ids_display = ', '.join([order_id[:8] for order_id in data['order_ids']])
                    order_line += f" - {ids_display}"
                
                message += order_line + "\n"
                line_count += 1
            
            # Add status total if multiple statuses present
            if len(status_groups) > 1:
                message += "\n" + self._t('subtotal_label', user_id, total=status_groups[status]['total_price']) + "\n\n"
            
            # Add to open total if applicable
            if status in open_statuses:
                open_total += status_groups[status]['total_price']
        
        # Add open orders total before cancelled orders
        if open_total > 0 and 'cancelled' in status_groups:
            message += "\n" + self._t('open_orders_total_label', user_id, total=open_total) + "\n\n"
        
        # Show cancelled orders last (no total needed)
        if 'cancelled' in status_groups:
            status_emoji = '❌'
            if len(status_groups) > 1:
                cancelled_label = self._t('status_cancelled', user_id).upper()
                message += f"{status_emoji} {cancelled_label}:\n"
            
            line_count = 0
            for (offer_id, unit_price, order_status), data in status_groups['cancelled']['items']:
                # Determine date display
                if len(data['dates']) == 1:
                    date_display = f"[{list(data['dates'])[0]}]"
                else:
                    date_display = f"[{self._t('multiple_days_label', user_id)}]"
                
                # Alternate diamond icons for better readability
                line_icon = "🔸" if line_count % 2 == 0 else "🔹"
                
                order_line = f"{line_icon} {date_display} [{offer_id}] {data['offer_name']} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f}"
                
                if show_ids:
                    ids_display = ', '.join([order_id[:8] for order_id in data['order_ids']])
                    order_line += f" - {ids_display}"
                
                message += order_line + "\n"
                line_count += 1
        
        # Add open orders total if no cancelled orders
        elif open_total > 0:
            message += "\n" + self._t('open_orders_total_label', user_id, total=open_total)

        self._send_message(chat_id, message)
        return {'status': 'success'}
    
    def handle_offer_details(self, chat_id: int, user_id: int, args: list = None) -> Dict[str, Any]:
        """Handle offer details display and editing from deep link or command"""
        if not args:
            # Show list of offers as buttons for admins, error for users
            if self._is_admin(user_id):
                offers = self.db.list_offers()
                draft_offers = [o for o in offers if o.status == OfferStatus.DRAFT.value]
                active_offers = [o for o in offers if o.status == OfferStatus.ACTIVE.value]
                all_offers = draft_offers + active_offers
                
                if not all_offers:
                    self._send_message(chat_id, self._t('no_offers_available'))
                    return {'status': 'no_offers'}
                
                message = self._t('select_offer_details')
                keyboard = {"inline_keyboard": []}
                
                for offer in all_offers:
                    status_prefix = "[DRAFT] " if offer.status == OfferStatus.DRAFT.value else ""
                    button_text = f"{status_prefix}[{offer.offer_id}] {offer.name} - €{offer.price_per_unit:.2f}"
                    keyboard["inline_keyboard"].append([{
                        "text": button_text,
                        "callback_data": f"offer_details_{offer.offer_id}"
                    }])
                
                keyboard["inline_keyboard"].append([{"text": self._t('cancel', user_id=None), "callback_data": "cancel_action"}])
                
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('no_offer_id_provided'))
                return {'status': 'invalid_args'}

        try:
            offer_id = int(args[0])
            # Check for "edit" parameter for admin edit mode
            edit_mode = len(args) > 1 and args[1].lower() == 'edit' and self._is_admin(user_id)
            # Check for "user" parameter for admin user view
            show_as_user = len(args) > 1 and args[1].lower() == 'user' and self._is_admin(user_id)
            
            offer = self.db.get_offer(offer_id)
            
            if not offer:
                self._send_message(chat_id, self._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            # Only show draft offers to admins
            if offer.status == OfferStatus.DRAFT.value and not self._is_admin(user_id):
                self._send_message(chat_id, self._t('offer_not_available'))
                return {'status': 'offer_not_available'}
            
            # Only show active offers to non-admin users
            if not self._is_admin(user_id) and offer.status != OfferStatus.ACTIVE.value:
                self._send_message(chat_id, self._t('offer_not_available'))
                return {'status': 'offer_not_available'}
            
            # Handle edit mode for admins
            if edit_mode:
                return self._show_edit_interface(chat_id, offer)
            
            # Send rich offer details
            if show_as_user:
                # Show as regular user would see it
                self._send_rich_offer_details(chat_id, offer, user_id=999999)  # Fake non-admin user ID
            else:
                self._send_rich_offer_details(chat_id, offer, user_id)
            
            # Add admin action buttons for draft offers
            if self._is_admin(user_id) and offer.status == OfferStatus.DRAFT.value:
                keyboard = {
                    "inline_keyboard": [
                        [{"text": self._t('edit_details'), "callback_data": f"offer_details_{offer_id}_edit"}],
                        [{"text": self._t('publish_offer_btn'), "callback_data": f"publish_offer_{offer_id}"}],
                        [{"text": self._t('cancel'), "callback_data": "cancel_action"}]
                    ]
                }
                self._send_message(chat_id, self._t('choose_action'), reply_markup=keyboard)
            
            return {'status': 'success'}
            
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id'))
            return {'status': 'invalid_format'}
    
    def _show_edit_interface(self, chat_id: int, offer) -> Dict[str, Any]:
        """Show editing interface for offer"""
        message = self._t('edit_offer_details',
            offer_id=offer.offer_id,
            name=offer.name,
            price=offer.price_per_unit,
            box_size=offer.wholesale_box_size,
            status=offer.status,
            supplier=offer.supplier_name,
            description=offer.description or self._t('not_set'),
            image_count=len(offer.images)
        )
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('edit_name'), "callback_data": f"edit_offer_name_{offer.offer_id}"}],
                [{"text": self._t('edit_price'), "callback_data": f"edit_offer_price_{offer.offer_id}"}],
                [{"text": self._t('edit_description'), "callback_data": f"edit_offer_description_{offer.offer_id}"}],
                [{"text": self._t('upload_image'), "callback_data": f"upload_offer_image_{offer.offer_id}"}],
                [{"text": self._t('clear_images'), "callback_data": f"clear_offer_images_{offer.offer_id}"}] if offer.images else [],
                [{"text": self._t('exit_edit_mode'), "callback_data": f"offer_details_{offer.offer_id}"}]
            ]
        }
        
        # Remove empty rows
        keyboard["inline_keyboard"] = [row for row in keyboard["inline_keyboard"] if row]
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def _send_rich_offer_details(self, chat_id: int, offer, user_id: int):
        """Send rich offer details with images and description"""
        # Send images as media group if available
        if offer.images:
            if len(offer.images) == 1:
                # Single image
                try:
                    image_url = offer.images[0]
                    if 's3.amazonaws.com' in image_url:
                        presigned_url = self.db.get_presigned_url(image_url)
                        if presigned_url:
                            image_url = presigned_url
                    self._send_photo(chat_id, image_url)
                except Exception as e:
                    print(f"Failed to send image {image_url}: {e}")
            else:
                # Multiple images as media group
                media_group = []
                for image_url in offer.images[:10]:  # Telegram limit is 10 images per group
                    try:
                        if 's3.amazonaws.com' in image_url:
                            presigned_url = self.db.get_presigned_url(image_url)
                            if presigned_url:
                                image_url = presigned_url
                        media_group.append({"type": "photo", "media": image_url})
                    except Exception as e:
                        print(f"Failed to prepare image {image_url}: {e}")
                
                if media_group:
                    self._send_media_group(chat_id, media_group)
        
        # Build detailed message
        is_draft = offer.status == OfferStatus.DRAFT.value
        is_admin = self._is_admin(user_id)
        
        message = ""
        if is_draft and is_admin:
            message = self._t('preview_offer_look') + "\n"

        if offer.status == OfferStatus.ACTIVE.value:
            # Get availability for active offers
            total_ordered, total_capacity = self._get_offer_capacity_info(offer.offer_id)
            available = total_capacity - total_ordered
            
            message += f"<b>{offer.offer_id}. {offer.name} €{offer.price_per_unit:.2f}  ({available}/{total_capacity})</b>\n\n"
        else:
            message += f"<b>{offer.offer_id}. {offer.name} €{offer.price_per_unit:.2f}</b>\n\n"
        
        # Show admin-only info
        if is_admin:
            message += self._t('box_size_units', size=offer.wholesale_box_size) + "\n"
            message += self._t('supplier_name', name=offer.supplier_name) + "\n"
            message += self._t('status_label', status=offer.status) + "\n"

        message += f"\n{offer.description}\n"
        
        # Add order buttons for active offers
        reply_markup = None
        if offer.status == OfferStatus.ACTIVE.value:
            message += "\n" + self._t('order_with_command', offer_id=offer.offer_id)
            if is_admin:
                reply_markup = {
                    "inline_keyboard": [
                        [
                            {"text": self._t('order_1'), "callback_data": f"order_{offer.offer_id}_1"},
                            {"text": self._t('order_2'), "callback_data": f"order_{offer.offer_id}_2"}
                        ],
                        [{"text": self._t('edit_offer_button'), "callback_data": f"offer_details_{offer.offer_id}_edit"}]
                    ]
                }
            else:
                reply_markup = {
                    "inline_keyboard": [
                        [
                            {"text": self._t('order_1'), "callback_data": f"order_{offer.offer_id}_1"},
                            {"text": self._t('order_2'), "callback_data": f"order_{offer.offer_id}_2"}
                        ]
                    ]
                }
        elif is_admin:
            # Add edit button for admins on non-active offers
            reply_markup = {
                "inline_keyboard": [
                    [{"text": self._t('edit_offer_button'), "callback_data": f"offer_details_{offer.offer_id}_edit"}]
                ]
            }
        
        self._send_message(chat_id, message, reply_markup=reply_markup, parse_mode="HTML")