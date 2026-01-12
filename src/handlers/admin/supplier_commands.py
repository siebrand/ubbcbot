from typing import Dict, Any
from handlers.base_handler import BaseHandler
from models.entities import Supplier
from utils.update_utils import UpdateUtils

class SupplierCommands(BaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_utils = UpdateUtils(self.db, self._t, self._send_message)
        self.update_utils._show_supplier_edit_interface = self._show_edit_interface
    def handle_add_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_supplier command"""
        if not args:
            # Show button interface to add supplier
            message = self._t('add_supplier_prompt')
            keyboard = {
                "inline_keyboard": [
                    [{"text": self._t('add_supplier_button'), "callback_data": "add_supplier_start"}],
                    [{"text": self._t('cancel'), "callback_data": "cancel_action"}]
                ]
            }
            self._send_message(chat_id, message, reply_markup=keyboard)
            return {'status': 'awaiting_input'}

        supplier_name = ' '.join(args).strip()
        return self._create_supplier(chat_id, supplier_name)
    
    def _create_supplier(self, chat_id: int, supplier_name: str) -> Dict[str, Any]:
        """Create supplier and show edit interface on success"""
        # Validate supplier name
        if len(supplier_name) > 50:
            return self._send_error(chat_id, 'supplier_name_too_long', 'invalid_name')
        
        if '<' in supplier_name or '>' in supplier_name:
            return self._send_error(chat_id, 'supplier_name_invalid_chars', 'invalid_name')
        
        # Check for duplicate
        if self.db.get_supplier_by_name(supplier_name):
            return self._send_error(chat_id, 'supplier_exists', 'duplicate_supplier', name=supplier_name)
        
        supplier = Supplier(name=supplier_name)
        
        if self.db.create_supplier(supplier):
            self._send_message(chat_id, self._t('supplier_added', name=supplier_name))
            # Show edit interface using the supplier object directly
            return self._show_edit_interface(chat_id, supplier)
        else:
            return self._send_error(chat_id, 'failed_add_supplier', 'error')
    
    def _show_edit_interface(self, chat_id: int, supplier) -> Dict[str, Any]:
        """Show edit interface for supplier"""
        message = self._t('edit_supplier_title', 
            name=supplier.name,
            full_name=supplier.full_name or self._t('not_set'),
            status=supplier.status,
            contact=supplier.contact_email or self._t('not_set')
        )
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('edit_name'), "callback_data": f"edit_supplier_name_{supplier.supplier_id}"}],
                [{"text": self._t('edit_full_name'), "callback_data": f"edit_supplier_full_name_{supplier.supplier_id}"}],
                [{"text": self._t('edit_contact'), "callback_data": f"edit_supplier_contact_{supplier.supplier_id}"}],
                [{"text": self._t('toggle_status'), "callback_data": f"edit_supplier_status_{supplier.supplier_id}"}],
                [{"text": self._t('back_to_admin'), "callback_data": "back_to_supplier_list"}],
                [{"text": self._t('done_general'), "callback_data": "cancel_action"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}

    def handle_retire_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /retire_supplier command"""
        error = self._validate_args(args, 1, 'usage_archive_supplier', chat_id)
        if error:
            return error

        supplier_name = ' '.join(args).strip()
        
        # Find supplier by name
        supplier = self.db.get_supplier_by_name(supplier_name)
        if not supplier:
            return self._send_error(chat_id, 'supplier_not_found', 'supplier_not_found', user_id=chat_id, name=supplier_name)
        
        if supplier.status == "retired":
            return self._send_error(chat_id, 'supplier_already_retired', 'already_retired', user_id=chat_id, name=supplier_name)
        
        # Update supplier status to retired
        if self.db.update_supplier(supplier.supplier_id, {'status': 'retired'}):
            return self._send_success(chat_id, 'supplier_retired', user_id=chat_id, name=supplier_name)
        else:
            return self._send_error(chat_id, 'failed_retire_supplier', 'error', user_id=chat_id)

    def handle_list_suppliers(self, chat_id: int, page: int = 1, status_filter: str = "active") -> Dict[str, Any]:
        """Handle /list_suppliers command with pagination and status filter"""
        suppliers = self.db.list_suppliers()
        
        if not suppliers:
            self._send_message(chat_id, self._t('no_suppliers', chat_id))
            return {'status': 'no_suppliers'}

        # Filter suppliers by status and sort alphabetically
        if status_filter == "all":
            filtered_suppliers = suppliers
        else:
            filtered_suppliers = [s for s in suppliers if s.status == status_filter]
        
        filtered_suppliers.sort(key=lambda x: x.name.lower())

        # Paginate results
        page_suppliers, total_pages = self._paginate_list(filtered_suppliers, page, 5)
        
        status_text = status_filter.title()
        message = self._t('suppliers_list_title', status=status_text, page=page, total_pages=total_pages) + "\n"
        
        # Create detailed list with edit buttons
        keyboard_buttons = []
        
        for supplier in page_suppliers:
            status_emoji = "✅" if supplier.status == "active" else "❌"
            contact = supplier.contact_email or self._t('not_set')
            full_name = supplier.full_name or self._t('not_set')
            
            # Single line format: emoji name | full_name | contact
            message += f"{status_emoji} {supplier.name} | {full_name} | {contact}\n"
            
            # Add edit button for each supplier
            keyboard_buttons.append([{"text": f"✏️ {supplier.name} bewerken", "callback_data": f"edit_supplier_select_{supplier.supplier_id}"}])
        
        # Add pagination keyboard if needed
        if total_pages > 1:
            pagination_buttons = self._build_pagination_keyboard(page, total_pages, f"suppliers_{status_filter}")
            if pagination_buttons and 'inline_keyboard' in pagination_buttons:
                keyboard_buttons.extend(pagination_buttons['inline_keyboard'])
        
        # Add done button
        keyboard_buttons.append([{"text": self._t('done_general'), "callback_data": "cancel_action"}])
        
        keyboard = {"inline_keyboard": keyboard_buttons} if keyboard_buttons else None
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def show_edit_interface_by_id(self, chat_id: int, supplier_id: str) -> Dict[str, Any]:
        """Show edit interface for supplier by ID"""
        supplier = self.db.get_supplier(supplier_id)
        if not supplier:
            self._send_message(chat_id, self._t('supplier_not_found', name=supplier_id))
            return {'status': 'supplier_not_found'}
        
        return self._show_edit_interface(chat_id, supplier)
    
    def handle_edit_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /edit_supplier command"""
        error = self._validate_args(args, 1, 'usage_update_supplier', chat_id)
        if error:
            return error

        supplier_name = ' '.join(args).strip()
        supplier = self.db.get_supplier_by_name(supplier_name)
        
        if not supplier:
            self._send_message(chat_id, self._t('supplier_not_found', chat_id, name=supplier_name))
            return {'status': 'supplier_not_found'}
        
        # Show current supplier details with edit options
        message = self._t('edit_supplier_title', 
            name=supplier.name,
            full_name=supplier.full_name or self._t('not_set'),
            status=supplier.status,
            contact=supplier.contact_email or self._t('not_set')
        )
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('edit_name'), "callback_data": f"edit_supplier_name_{supplier.supplier_id}"}],
                [{"text": self._t('edit_full_name'), "callback_data": f"edit_supplier_full_name_{supplier.supplier_id}"}],
                [{"text": self._t('edit_contact'), "callback_data": f"edit_supplier_contact_{supplier.supplier_id}"}],
                [{"text": self._t('toggle_status'), "callback_data": f"edit_supplier_status_{supplier.supplier_id}"}],
                [{"text": self._t('done_general'), "callback_data": "cancel_action"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_update_supplier_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_supplier_name command"""
        return self.update_utils.handle_supplier_update(chat_id, args, 'name')
    
    def handle_update_supplier_contact(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_supplier_contact command"""
        return self.update_utils.handle_supplier_update(chat_id, args, 'contact_email')
    
    def handle_update_supplier_full_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_supplier_full_name command"""
        return self.update_utils.handle_supplier_update(chat_id, args, 'full_name')