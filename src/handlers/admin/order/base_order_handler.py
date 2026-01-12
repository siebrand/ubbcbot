from typing import Dict, Any
from decimal import Decimal
from handlers.base_handler import BaseHandler
from utils.pagination import PaginationUtils

class BaseOrderHandler(BaseHandler):
    """Base class for order-related handlers with shared utilities"""
    
    def _show_customer_orders(self, chat_id: int, customer, page: int = 1, 
                             show_order_ids: bool = False, user_id: int = None) -> Dict[str, Any]:
        """Shared method to display customer orders with pagination"""
        orders = self.db.get_orders_by_customer(customer.customer_id)
        
        if not orders:
            display_name = f"{customer.first_name} {customer.last_name}" or self._t('unknown', user_id=None)
            if user_id and self._is_admin(user_id):
                keyboard = {"inline_keyboard": [[{"text": self._t('back_to_admin'), "callback_data": "admin:main"}]]}
                self._send_message(chat_id, self._t('no_orders_for_user', name=display_name), reply_markup=keyboard)
            else:
                self._send_message(chat_id, self._t('no_orders', user_id))
            return {'status': 'no_orders'}

        # Sort orders by offer_id ascending
        orders.sort(key=lambda x: x.offer_id)
        
        # Aggregate orders by offer, price and status
        aggregated = {}
        bot_username = self._get_bot_username()
        
        for order in orders:
            offer = self.db.get_offer(order.offer_id)
            offer_name = offer.name if offer else self._t('unknown', user_id=None)
            
            key = (order.offer_id, order.unit_price, order.status)
            if key not in aggregated:
                aggregated[key] = {
                    'offer_name': offer_name,
                    'offer_id': order.offer_id,
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
            
            # Add date in localized format (d MMM yy)
            from utils.timezone import to_cet_localized
            date_str = to_cet_localized(order.created_at, 'nl')
            aggregated[key]['dates'].add(date_str)

        # Group by status
        status_groups = {}
        for (offer_id, unit_price, status), data in aggregated.items():
            if status not in status_groups:
                status_groups[status] = {'total_price': Decimal('0.0'), 'items': []}
            status_groups[status]['total_price'] += data['total_price']
            status_groups[status]['items'].append(((offer_id, unit_price, status), data))
        
        # Flatten items for pagination
        all_items = []
        for status in ['pending', 'ordered', 'ready_for_labeling', 'labeling_completed', 'awaiting_payment', 'delivered', 'completed', 'cancelled']:
            if status in status_groups:
                all_items.extend([(status, item) for item in status_groups[status]['items']])
        
        # Paginate
        page_items, total_pages = PaginationUtils.paginate_list(all_items, page, 10)
        
        # Build message
        is_admin = user_id and self._is_admin(user_id)
        display_name = self._escape_html(f"{customer.first_name} {customer.last_name}" or self._t('unknown', user_id=None))
        
        if is_admin:
            message = self._t('user_orders_title', user_id=None, name=display_name)
        else:
            message = self._t('my_orders_title', user_id)
        
        if total_pages > 1:
            message += f" - Page {page}/{total_pages}"
        message += "\n\n"
        
        # Calculate grand total once (excluding cancelled and completed)
        non_cancelled_statuses = [s for s in status_groups.keys() if s not in ['cancelled', 'completed']]
        grand_total = sum(status_groups[s]['total_price'] for s in non_cancelled_statuses) if len(non_cancelled_statuses) > 1 else None
        
        # Display paginated items
        current_status = None
        item_index = 0
        statuses_in_page = []
        
        for status, ((offer_id, unit_price, order_status), data) in page_items:
            if status != current_status:
                # Show subtotal for previous section (except cancelled)
                if current_status is not None and current_status != 'cancelled':
                    status_label = self._t(f"status_{current_status}", user_id=None)
                    subtotal_line = f"\n{status_label}: €{status_groups[current_status]['total_price']:.2f}"
                    if grand_total is not None:
                        subtotal_line += f" ({self._t('grand_total', user_id=None)}: €{grand_total:.2f})"
                    message += subtotal_line + "\n"
                
                if current_status is not None:
                    message += "\n"
                status_emoji = {
                    'pending': '⏳',
                    'ordered': '📦',
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
                statuses_in_page.append(status)
            
            # Alternate diamond icons for better readability
            line_icon = "🔸" if item_index % 2 == 0 else "🔹"
            item_index += 1
            
            date_display = f"[{list(data['dates'])[0]}]" if len(data['dates']) == 1 else f"[{self._t('multiple_days_label')}]"
            
            # Create clickable offer link on offer_id for non-cancelled orders
            if status != 'cancelled':
                offer_id_link = f"<a href='https://t.me/{bot_username}?start=view_offer_{data['offer_id']}'>{data['offer_id']}</a>"
            else:
                offer_id_link = str(data['offer_id'])
            
            if show_order_ids or is_admin:
                short_order_id = data['order_ids'][0][:8] if data['order_ids'] else "unknown"
                message += f"{line_icon} {date_display} [{offer_id_link}] {self._escape_html(data['offer_name'])} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f} - {short_order_id}\n"
            else:
                message += f"{line_icon} {date_display} [{offer_id_link}] {self._escape_html(data['offer_name'])} €{data['unit_price']:.2f} {data['quantity']}x €{data['total_price']:.2f}\n"
        
        # Show subtotal for last section (except cancelled)
        if current_status is not None and current_status != 'cancelled':
            status_label = self._t(f"status_{current_status}", user_id=None)
            subtotal_line = f"\n{status_label}: €{status_groups[current_status]['total_price']:.2f}"
            if grand_total is not None:
                subtotal_line += f" ({self._t('grand_total', user_id=None)}: €{grand_total:.2f})"
            message += subtotal_line + "\n"
        
        # Add pagination keyboard
        keyboard_buttons = []
        if total_pages > 1:
            if is_admin:
                callback_prefix = f"user_orders_{customer.customer_id}"
            else:
                callback_prefix = f"my_orders_{user_id}"
            keyboard = PaginationUtils.build_pagination_keyboard(page, total_pages, callback_prefix, enhanced=True)
            keyboard_buttons = keyboard['inline_keyboard']
        
        # Add back button for admin
        if is_admin:
            keyboard_buttons.append([{"text": self._t('back_to_admin'), "callback_data": "admin:main"}])
        
        reply_markup = {"inline_keyboard": keyboard_buttons} if keyboard_buttons else None
        parse_mode = "HTML"
        
        self._send_message(chat_id, message, reply_markup=reply_markup, parse_mode=parse_mode)
        return {'status': 'success'}