import logging
import requests
from typing import Dict, Any
from handlers.base_handler import BaseHandler
from models.entities import OfferStatus, Order, BoxStatus
from services.box_status_manager import BoxStatusManager
from utils.csv_parser import CSVParser

logger = logging.getLogger()

class ImportHandler(BaseHandler):
    """Handler for order import operations"""
    
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        super().__init__(db, admin_user_id, environment, telegram_token)
        self.box_status_manager = BoxStatusManager(db)
    
    def handle_import_orders(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /import_orders command - prompt for CSV file"""
        # Check if already waiting for file
        existing = self.db.get_edit_context_by_chat_id(chat_id)
        if existing and existing.edit_type == 'import_csv':
            return self._send_error(chat_id, 'import_already_pending', 'already_pending')
        
        # Store context in DynamoDB
        from utils.edit_context import EditContextManager
        edit_context_manager = EditContextManager(self.db, self._t, self._send_message)
        edit_context_manager.store_edit_context(chat_id, 'import_csv', 'pending')
        
        # Send prompt with force reply
        self._send_message(
            chat_id,
            self._t('import_orders_prompt'),
            reply_markup={"force_reply": True, "input_field_placeholder": self._t('placeholder_csv_file')}
        )
        return {'status': 'awaiting_file'}
    
    def handle_document_upload(self, chat_id: int, user_id: int, file_id: str, file_name: str) -> Dict[str, Any]:
        """Handle document upload for import"""
        # Check if user is waiting for import file
        context = self.db.get_edit_context_by_chat_id(chat_id)
        if not context or context.edit_type != 'import_csv':
            return {'status': 'not_waiting'}
        
        # Clear context
        self.db.delete_edit_context(context.context_id)
        
        # Download file
        file_content = self._download_file(file_id)
        if not file_content:
            return self._send_error(chat_id, 'import_download_failed', 'download_failed')
        
        # Parse CSV
        parse_result = CSVParser.parse_import_csv(file_content)
        
        if not parse_result['success']:
            error_key = f"import_error_{parse_result['error']}"
            if parse_result['error'] == 'too_many_lines':
                return self._send_error(chat_id, error_key, parse_result['error'], 
                                      line_count=parse_result['line_count'], 
                                      max_lines=CSVParser.MAX_LINES)
            elif parse_result['error'] == 'empty_cell':
                return self._send_error(chat_id, error_key, parse_result['error'],
                                      line=parse_result['line'],
                                      field=parse_result['field'])
            elif parse_result['error'] == 'invalid_headers':
                return self._send_error(chat_id, error_key, parse_result['error'],
                                      expected=', '.join(parse_result['expected']),
                                      found=', '.join(parse_result.get('found', [])))
            else:
                return self._send_error(chat_id, error_key, parse_result['error'])
        
        # Process rows
        rows = parse_result['rows']
        self._send_message(chat_id, self._t('import_processing', row_count=len(rows)))
        
        success_count = 0
        errors = []
        max_errors = 5
        
        for idx, row in enumerate(rows, start=2):  # Line numbers start at 2 (header is 1)
            # Stop processing if we hit max errors
            if len(errors) >= max_errors:
                break
            offer_id_str = row['offer_id'].strip()
            username = row['username'].strip()
            
            # Validate offer_id
            try:
                offer_id = int(offer_id_str)
            except ValueError:
                errors.append(self._t('import_line_error_invalid_offer_id', 
                                    line=idx, offer_id=offer_id_str))
                continue
            
            # Get offer
            offer = self.db.get_offer(offer_id)
            if not offer:
                errors.append(self._t('import_line_error_offer_not_found',
                                    line=idx, offer_id=offer_id))
                continue
            
            # Check offer status
            if offer.status != OfferStatus.IMPORT.value:
                errors.append(self._t('import_line_error_wrong_status',
                                    line=idx, offer_id=offer_id, status=offer.status))
                continue
            
            # Find customer (no interactive disambiguation)
            customer, error = self._find_customer_for_import(username, chat_id)
            if error:
                errors.append(self._t('import_line_error_customer',
                                    line=idx, username=username, reason=error))
                continue
            
            # Create order
            order_result = self._create_import_order(offer, customer)
            if order_result['success']:
                success_count += 1
            else:
                errors.append(self._t('import_line_error_order_failed',
                                    line=idx, username=username, offer_id=offer_id))
        
        # Send summary
        summary = self._t('import_completed', success_count=success_count)
        
        if errors:
            summary += "\n\n" + self._t('import_errors_header', error_count=len(errors))
            for error in errors[:5]:  # Show max 5 errors
                summary += f"\n{error}"
            
            if len(errors) > 5:
                summary += "\n" + self._t('import_more_errors', remaining=len(errors) - 5)
        
        self._send_message(chat_id, summary)
        return {'status': 'success', 'imported': success_count, 'errors': len(errors)}
    
    def _find_customer_for_import(self, username: str, chat_id: int) -> tuple:
        """Find customer for import - returns customer or error string"""
        # Use base handler's disambiguation method without interactive UI
        customer, error = self._find_customer_with_disambiguation(username, chat_id, 'import', None)
        
        if error:
            # Return error message string instead of dict
            if error['status'] == 'user_not_found':
                return None, self._t('not_found')
            elif error['status'] == 'disambiguation_shown':
                return None, self._t('multiple_matches')
        
        return customer, None
    
    def _create_import_order(self, offer, customer) -> Dict[str, Any]:
        """Create order for import (quantity=1, no announcement)"""
        try:
            # Get or create box
            boxes = self.db.get_boxes_by_offer(offer.offer_id)
            open_boxes = [b for b in boxes if b.status == BoxStatus.OPEN.value and b.current_quantity < b.max_capacity]
            
            if open_boxes:
                box = open_boxes[0]
            else:
                # Create new box
                from models.entities import Box
                box = Box(
                    offer_id=offer.offer_id,
                    max_capacity=offer.wholesale_box_size,
                    status=BoxStatus.OPEN.value
                )
                box = self.db.create_box(box)
                if not box:
                    return {'success': False}
            
            # Create order
            order = Order(
                customer_id=customer.customer_id,
                box_id=box.box_id,
                offer_id=offer.offer_id,
                quantity=1,
                unit_price=offer.price_per_unit,
                total_price=offer.price_per_unit,
                placed_by_admin=True
            )
            
            created_order = self.db.create_order(order)
            if not created_order:
                return {'success': False}
            
            # Update box
            self.box_status_manager.update_box_after_order_placement(box.box_id, 1)
            
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error creating import order: {e}")
            return {'success': False}
    
    def _download_file(self, file_id: str) -> bytes:
        """Download file from Telegram"""
        try:
            # Get file path
            url = f"https://api.telegram.org/bot{self.telegram_token}/getFile"
            response = requests.get(url, params={'file_id': file_id}, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Failed to get file info: {response.status_code}")
                return None
            
            file_path = response.json()['result']['file_path']
            
            # Download file
            download_url = f"https://api.telegram.org/file/bot{self.telegram_token}/{file_path}"
            download_response = requests.get(download_url, timeout=30)
            
            if download_response.status_code != 200:
                logger.error(f"Failed to download file: {download_response.status_code}")
                return None
            
            return download_response.content
            
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None
    
    def handle_finalize_import(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /finalize_import command"""
        # If no args, show list of IMPORT offers
        if not args:
            return self._show_import_offers_selection(chat_id)
        
        error = self._validate_args(args, 1, 'usage_finalize_import', chat_id)
        if error:
            return error
        
        offer, error = self._validate_and_get_offer(args, chat_id)
        if error:
            return error
        
        # Check offer status
        if offer.status != OfferStatus.IMPORT.value:
            return self._send_error(chat_id, 'finalize_import_wrong_status', 'wrong_status',
                                  status=offer.status)
        
        # Check if sold out
        boxes = self.db.get_boxes_by_offer(offer.offer_id)
        all_full = all(b.status == BoxStatus.FULL.value for b in boxes) if boxes else False
        
        if all_full and boxes:
            # Mark as SOLD_OUT, no announcements
            self.db.update_offer(offer.offer_id, {'status': OfferStatus.SOLD_OUT.value})
            return self._send_success(chat_id, 'finalize_import_sold_out', 'success',
                                    offer_id=offer.offer_id, name=offer.name)
        else:
            # Mark as ACTIVE and announce
            self.db.update_offer(offer.offer_id, {'status': OfferStatus.ACTIVE.value})
            offer.status = OfferStatus.ACTIVE.value
            
            # Announce using existing logic
            self._announce_offer(offer)
            
            return self._send_success(chat_id, 'finalize_import_active', 'success',
                                    offer_id=offer.offer_id, name=offer.name)
    
    def _announce_offer(self, offer):
        """Announce offer to default group and subscribers"""
        import os
        default_group_id = os.environ.get('DEFAULT_GROUP_ID')
        
        # Send to default group
        if default_group_id:
            self._send_rich_offer_message(int(default_group_id), offer, force_group=True, include_buttons=False)
        
        # Send to subscribers
        self._notify_subscribers_rich(offer)
    
    def _show_import_offers_selection(self, chat_id: int) -> Dict[str, Any]:
        """Show offers with IMPORT status for finalization"""
        offers = self.db.list_offers()
        import_offers = [o for o in offers if o.status == OfferStatus.IMPORT.value]
        
        if not import_offers:
            self._send_message(chat_id, self._t('no_import_offers'))
            return {'status': 'no_offers'}
        
        message = self._t('select_offer_finalize_import') + "\n\n"
        keyboard_buttons = []
        
        for offer in import_offers:
            # Get order count
            orders = self.db.get_orders_by_offer(offer.offer_id)
            order_count = len([o for o in orders if o.status == 'pending'])
            
            message += f"🍺 {offer.offer_id}. {offer.name} ({order_count} orders)\n"
            keyboard_buttons.append([{
                "text": f"{offer.offer_id}. {offer.name}",
                "callback_data": f"finalize_import_{offer.offer_id}"
            }])
        
        keyboard_buttons.append([{"text": self._t('cancel'), "callback_data": "cancel_action"}])
        keyboard = {"inline_keyboard": keyboard_buttons}
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
