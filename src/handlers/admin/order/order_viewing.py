from typing import Dict, Any
from decimal import Decimal
from models.entities import AuthorizationStatus, OrderStatus, OfferStatus
from .base_order_handler import BaseOrderHandler

class OrderViewing(BaseOrderHandler):
    """Handles order viewing and export functionality"""
    
    def handle_user_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /user_orders command"""
        if not args:
            # Show button-based UI to ask for username
            message = self._t('enter_username_for_orders', chat_id)
            keyboard = {
                "inline_keyboard": [[
                    {"text": "📝 Enter Username", "callback_data": "enter_username_orders"}
                ]]
            }
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'awaiting_input'}

        identifier = ' '.join(args)
        customer, error = self._find_customer_with_disambiguation(identifier, chat_id, "user_orders_select")
        
        if error:
            return error
        
        return self._show_user_orders(chat_id, customer)
    
    def _show_user_orders(self, chat_id: int, customer, page: int = 1) -> Dict[str, Any]:
        """Show orders for a specific customer with pagination"""
        orders = self.db.get_orders_by_customer(customer.customer_id)
        
        if not orders:
            display_name = f"{customer.first_name} {customer.last_name}" or self._t('unknown', user_id=None)
            self._send_message(chat_id, self._t('no_orders_for_user', name=display_name))
            return {'status': 'no_orders'}

        # Sort orders by offer_id ascending
        orders.sort(key=lambda x: x.offer_id)
        
        # Aggregate orders by offer, price and status
        aggregated = {}
        for order in orders:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else self._t('unknown', user_id=None)
            
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

        # Group by status
        status_groups = {}
        for (offer_id, unit_price, status), data in aggregated.items():
            if status not in status_groups:
                status_groups[status] = {'total_price': Decimal('0.0'), 'items': []}
            status_groups[status]['total_price'] += data['total_price']
            status_groups[status]['items'].append(((offer_id, unit_price, status), data))
        
        # Flatten items for pagination
        all_items = []
        for status in ['pending', 'ordered', 'confirmed', 'ready_for_labeling', 'labeling_completed', 'awaiting_payment', 'delivered', 'completed', 'cancelled']:
            if status in status_groups:
                all_items.extend([(status, item) for item in status_groups[status]['items']])
        
        # Paginate
        page_items, total_pages = self._paginate_list(all_items, page, 10)
        
        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or self._t('unknown', user_id=None))
        message = self._t('user_orders_title', user_id=None, name=display_name)
        if total_pages > 1:
            message += f" - Page {page}/{total_pages}"
        message += "\n\n"
        
        # Display paginated items
        current_status = None
        for status, ((offer_id, unit_price, order_status), data) in page_items:
            if status != current_status:
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
                status_label = self._t(f"status_{status}", user_id=None).upper()
                message += f"{status_emoji} {status_label}:\n"
                current_status = status
            
            date_display = f"[{list(data['dates'])[0]}]" if len(data['dates']) == 1 else f"[{self._t('multiple_days_label')}]"
            short_order_id = data['order_ids'][0][:8] if data['order_ids'] else "unknown"
            message += f"🔸 {date_display} [{offer_id}] {data['offer_name']} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f} - {short_order_id}\n"
        
        # Add pagination keyboard
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_pagination_keyboard(page, total_pages, f"user_orders_{customer.customer_id}", enhanced=True)
        
        self._send_message(chat_id, message, reply_markup=keyboard, parse_mode="HTML")
        return {'status': 'success'}

    def handle_all_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /all_orders command"""
        if not args:
            # Show status selection buttons
            keyboard = {
                "inline_keyboard": [
                    [{"text": "Ready for Labeling", "callback_data": "export_orders_ready_for_labeling"}],
                    [{"text": "Labeling Completed", "callback_data": "export_orders_labeling_completed"}],
                    [{"text": "Awaiting Payment", "callback_data": "export_orders_awaiting_payment"}],
                    [{"text": "Completed", "callback_data": "export_orders_completed"}],
                    [{"text": "Active", "callback_data": "export_orders_active"}],
                    [{"text": "Cancelled", "callback_data": "export_orders_cancelled"}],
                    [{"text": "All", "callback_data": "export_orders_all"}],
                    [{"text": "Full Export (All Fields)", "callback_data": "export_orders_full"}]
                ]
            }
            self._send_message(chat_id, "📊 Select order status to export:", reply_markup=keyboard)
            return {'status': 'selection_shown'}
        
        # Get filter from args
        status_filter = args[0].lower()
        return self._export_orders_by_status(chat_id, status_filter)
    
    def _export_orders_by_status(self, chat_id: int, status_filter: str) -> Dict[str, Any]:
        """Export orders by status filter"""
        # Get all customers and their orders
        customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)
        
        all_orders = []
        for customer in customers:
            orders = self.db.get_orders_by_customer(customer.customer_id)
            for order in orders:
                if status_filter == 'active' and order.status not in ['pending', 'ordered']:
                    continue
                elif status_filter == 'cancelled' and order.status != 'cancelled':
                    continue
                elif status_filter == 'ordered' and order.status != 'ordered':
                    continue
                elif status_filter == 'ready_for_labeling' and order.status != OrderStatus.READY_FOR_LABELING.value:
                    continue
                elif status_filter == 'labeling_completed' and order.status != OrderStatus.LABELING_COMPLETED.value:
                    continue
                elif status_filter == 'awaiting_payment' and order.status != OrderStatus.AWAITING_PAYMENT.value:
                    continue
                elif status_filter == 'completed' and order.status != OrderStatus.COMPLETED.value:
                    continue
                elif status_filter not in ['all', 'full'] and status_filter not in ['active', 'cancelled', 'ordered', 'ready_for_labeling', 'labeling_completed', 'awaiting_payment', 'completed']:
                    continue
                all_orders.append((customer, order))
        
        if not all_orders:
            self._send_message(chat_id, self._t('no_orders_status', status=status_filter))
            return {'status': 'no_orders'}
        
        # Sort by customer name for grouping
        all_orders.sort(key=lambda x: (x[0].first_name or '', x[0].last_name or ''))
        
        # Generate CSV based on export type
        if status_filter == 'full':
            csv_content = self._generate_full_export_csv(all_orders)
        else:
            csv_content = self._generate_pick_list_csv(all_orders)
        
        # Add CET timestamp to filename
        from utils.timezone import to_cet_string
        from datetime import datetime, UTC
        timestamp = to_cet_string(datetime.now(UTC), '%Y%m%d_%H%M%S')
        csv_filename = f"orders_{self.environment}_{status_filter}_{timestamp}.csv"
        
        # Send CSV file
        caption = self._t('pick_list_csv_caption', user_id=None, 
                         status=status_filter.replace('_', ' ').title(), 
                         count=len(all_orders))
        self._send_document(chat_id, csv_content, csv_filename, caption)
        
        return {'status': 'success'}
    
    def _generate_pick_list_csv(self, orders_data: list) -> str:
        """Generate pick list CSV content with normalized quantities (1 unit per row)"""
        # CSV headers
        headers = ['Naam', 'Product', 'Prijs']
        
        csv_content = ','.join(headers) + '\n'
        
        # Group by customer and sort
        customer_orders = {}
        for customer, order in orders_data:
            customer_key = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or self._t('unknown', user_id=None)
            if customer_key not in customer_orders:
                customer_orders[customer_key] = []
            customer_orders[customer_key].append((customer, order))
        
        # Generate CSV data with normalized quantities
        for customer_name in sorted(customer_orders.keys()):
            for customer, order in customer_orders[customer_name]:
                offer = self.db.get_offer(order.offer_id)
                offer_name = offer.name if offer else self._t('unknown', user_id=None)
                
                # Expand order quantity to individual rows
                for _ in range(int(order.quantity)):
                    csv_content += f'"{customer_name}","{offer_name}",€{order.unit_price:.2f}\n'
        
        return csv_content
    
    def _generate_full_export_csv(self, orders_data: list) -> str:
        """Generate full export CSV with all order fields"""
        if not orders_data:
            return ''
        
        # Get headers dynamically from Order dataclass
        from models.entities import Order
        headers = list(Order.__dataclass_fields__.keys())
        
        csv_content = ','.join(headers) + '\n'
        
        # Generate CSV data with all fields
        for customer, order in orders_data:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or 'unknown'
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else 'unknown'
            
            from utils.timezone import to_cet_string
            
            # Build row dynamically
            row_values = []
            for field in headers:
                value = getattr(order, field)
                
                # Format datetime fields
                if field in ['created_at', 'update_date'] and value:
                    value = to_cet_string(value, '%Y-%m-%d %H:%M:%S')
                elif value is None:
                    value = ''
                
                # Quote string fields
                if isinstance(value, str):
                    row_values.append(f'"{value}"')
                else:
                    row_values.append(str(value))
            
            csv_content += ','.join(row_values) + '\n'
        
        return csv_content

    def handle_offer_orders(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /offer_orders command"""
        if not args:
            # Show button-based UI to select offer
            return self._show_offer_selection_for_orders(chat_id)
        
        try:
            offer_id = int(args[0])
            return self._show_orders_for_offer(chat_id, offer_id)
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id', chat_id))
            return {'status': 'invalid_format'}
    
    def _show_offer_selection_for_orders(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Show paginated list of offers for order viewing"""
        offers = [o for o in self.db.list_offers() if o.status in [OfferStatus.ACTIVE.value, OfferStatus.SOLD_OUT.value, OfferStatus.INACTIVE.value]]
        
        if not offers:
            self._send_message(chat_id, self._t('no_offers_available', chat_id))
            return {'status': 'no_offers'}
        
        # Sort by offer_id descending (newest first)
        offers.sort(key=lambda x: x.offer_id, reverse=True)
        
        # Paginate results
        page_offers, total_pages = self._paginate_list(offers, page, 10)
        
        message = self._t('select_offer_for_orders', chat_id, page=page, total_pages=total_pages) + "\n\n"
        keyboard_buttons = []
        
        for offer in page_offers:
            supplier = self.db.get_supplier_by_name(offer.supplier_name)
            supplier_name = supplier.name if supplier else self._t('unknown', user_id=None)
            
            # Get order count for this offer
            orders = self.db.get_orders_by_offer(offer.offer_id)
            order_count = len(orders)
            
            button_text = f"🍺 {offer.name} - €{offer.price_per_unit:.2f} ({supplier_name}) [{order_count} orders]"
            keyboard_buttons.append([{"text": button_text, "callback_data": f"offer_orders_{offer.offer_id}"}])
        
        # Add pagination if needed
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": self._t('previous', chat_id), "callback_data": f"offer_orders_page_{page - 1}"})
            nav_buttons.append({"text": self._t('page_indicator', chat_id, page=page, total_pages=total_pages), "callback_data": "page_info"})
            if page < total_pages:
                nav_buttons.append({"text": self._t('next', chat_id), "callback_data": f"offer_orders_page_{page + 1}"})
            keyboard_buttons.append(nav_buttons)
        
        # Add cancel button
        keyboard_buttons.append([{"text": self._t('cancel', chat_id), "callback_data": "cancel_action"}])
        
        keyboard = {"inline_keyboard": keyboard_buttons}
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def _show_orders_for_offer(self, chat_id: int, offer_id: int, page: int = 1) -> Dict[str, Any]:
        """Show paginated orders for a specific offer"""
        offer = self.db.get_offer(offer_id)
        if not offer:
            self._send_message(chat_id, self._t('offer_not_found', chat_id))
            return {'status': 'offer_not_found'}
        
        orders = self.db.get_orders_by_offer(offer_id)
        if not orders:
            self._send_message(chat_id, self._t('no_orders_for_offer', chat_id, offer_name=offer.name))
            return {'status': 'no_orders'}
        
        # Sort by creation date (oldest first)
        orders.sort(key=lambda x: x.created_at)
        
        # Paginate results
        page_orders, total_pages = self._paginate_list(orders, page, 10)
        
        # Calculate totals
        active_orders = [o for o in orders if o.status in ['pending', 'ordered']]
        total_quantity = sum(o.quantity for o in orders)
        active_quantity = sum(o.quantity for o in active_orders)
        total_value = sum(o.total_price for o in orders)
        active_value = sum(o.total_price for o in active_orders)
        
        message = self._t('offer_orders_header', chat_id,
            offer_name=offer.name,
            offer_id=offer_id,
            page=page,
            total_pages=total_pages,
            total_orders=len(orders),
            active_orders=len(active_orders),
            total_quantity=total_quantity,
            active_quantity=active_quantity,
            total_value=total_value,
            active_value=active_value
        ) + "\n\n"
        
        for i, order in enumerate(page_orders):
            customer = self.db.get_customer(order.customer_id)
            customer_name = f"{customer.first_name} {customer.last_name}" if customer else self._t('unknown', user_id=None)
            
            from utils.timezone import to_cet_string
            order_date = to_cet_string(order.created_at, '%Y-%m-%d')
            
            status_emoji = {
                'pending': '⏳',
                'ordered': '📦',
                'cancelled': '❌',
                'ready_for_labeling': '🏷️',
                'labeling_completed': '✅',
                'awaiting_payment': '💳',
                'completed': '✅'
            }.get(order.status, '❓')
            
            # Alternate diamond icons for better readability
            line_icon = "🔸" if i % 2 == 0 else "🔹"
            
            message += f"{line_icon} [{order_date}] {customer_name} {order.quantity}x €{order.total_price:.2f} - {order.order_id[:8]}\n"
        
        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append({"text": self._t('previous', chat_id), "callback_data": f"offer_orders_detail_{offer_id}_{page - 1}"})
            nav_buttons.append({"text": self._t('page_indicator', chat_id, page=page, total_pages=total_pages), "callback_data": "page_info"})
            if page < total_pages:
                nav_buttons.append({"text": self._t('next', chat_id), "callback_data": f"offer_orders_detail_{offer_id}_{page + 1}"})
            keyboard = {"inline_keyboard": [nav_buttons]}
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}

    def handle_user_orders_select(self, chat_id: int, customer_id: str) -> Dict[str, Any]:
        """Handle user selection from disambiguation buttons for user_orders"""
        customer = self.db.get_customer(customer_id)
        
        if not customer:
            self._send_message(chat_id, self._t('user_not_found', chat_id, identifier=customer_id))
            return {'status': 'user_not_found'}
        
        return self._show_user_orders(chat_id, customer)

    def handle_offer_orders_page(self, chat_id: int, page: int) -> Dict[str, Any]:
        """Handle pagination for offer selection"""
        return self._show_offer_selection_for_orders(chat_id, page)
    
    def handle_offer_orders_detail_page(self, chat_id: int, offer_id: str, page: int) -> Dict[str, Any]:
        """Handle pagination for offer orders detail"""
        try:
            return self._show_orders_for_offer(chat_id, int(offer_id), page)
        except ValueError:
            self._send_message(chat_id, self._t('invalid_offer_id', chat_id))
            return {'status': 'invalid_format'}
    
    def handle_export_orders_callback(self, chat_id: int, status_filter: str) -> Dict[str, Any]:
        """Handle export orders callback"""
        return self._export_orders_by_status(chat_id, status_filter)