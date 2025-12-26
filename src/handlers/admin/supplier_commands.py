from typing import Dict, Any
from handlers.base_handler import BaseHandler
from models.entities import Supplier

class SupplierCommands(BaseHandler):
    def handle_add_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_supplier command"""
        error = self._validate_args(args, 1, 'usage_add_supplier', chat_id)
        if error:
            return error

        supplier_name = ' '.join(args).strip()
        
        # Validate supplier name
        if len(supplier_name) > 50:
            self._send_message(chat_id, self._t('supplier_name_too_long', chat_id))
            return {'status': 'invalid_name'}
        
        if '<' in supplier_name or '>' in supplier_name:
            self._send_message(chat_id, self._t('supplier_name_invalid_chars', chat_id))
            return {'status': 'invalid_name'}
        
        # Check for duplicate
        if self.db.get_supplier_by_name(supplier_name):
            self._send_message(chat_id, self._t('supplier_exists', chat_id, name=supplier_name))
            return {'status': 'duplicate_supplier'}
        
        supplier = Supplier(name=supplier_name)
        
        if self.db.create_supplier(supplier):
            self._send_message(chat_id, self._t('supplier_added', chat_id, name=supplier_name))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_add_supplier', chat_id))
            return {'status': 'error'}

    def handle_retire_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /retire_supplier command"""
        error = self._validate_args(args, 1, 'usage_retire_supplier', chat_id)
        if error:
            return error

        supplier_name = ' '.join(args).strip()
        
        # Find supplier by name
        supplier = self.db.get_supplier_by_name(supplier_name)
        if not supplier:
            self._send_message(chat_id, self._t('supplier_not_found', chat_id, name=supplier_name))
            return {'status': 'supplier_not_found'}
        
        if supplier.status == "retired":
            self._send_message(chat_id, self._t('supplier_already_retired', chat_id, name=supplier_name))
            return {'status': 'already_retired'}
        
        # Update supplier status to retired
        if self.db.update_supplier(supplier.supplier_id, {'status': 'retired'}):
            self._send_message(chat_id, self._t('supplier_retired', chat_id, name=supplier_name))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_retire_supplier', chat_id))
            return {'status': 'error'}

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
        page_suppliers, total_pages = self._paginate_list(filtered_suppliers, page, 10)
        
        status_text = status_filter.title()
        message = self._t('suppliers_list_title', status=status_text, page=page, total_pages=total_pages)
        
        # Calculate max name length for alignment
        max_name_length = max(len(supplier.name) for supplier in page_suppliers) if page_suppliers else 0
        
        for supplier in page_suppliers:
            status_emoji = "✅" if supplier.status == "active" else "❌"
            contact = supplier.contact_email or self._t('not_set')
            padded_name = supplier.name.ljust(max_name_length)
            message += f"{status_emoji} {padded_name} | {contact}\n"
        
        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_pagination_keyboard(page, total_pages, f"suppliers_{status_filter}")
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_edit_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /edit_supplier command"""
        error = self._validate_args(args, 1, 'usage_edit_supplier', chat_id)
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
            status=supplier.status,
            contact=supplier.contact_email or self._t('not_set')
        )
        
        keyboard = {
            "inline_keyboard": [
                [{"text": self._t('edit_name'), "callback_data": f"edit_supplier_name_{supplier.supplier_id}"}],
                [{"text": self._t('edit_contact'), "callback_data": f"edit_supplier_contact_{supplier.supplier_id}"}],
                [{"text": self._t('toggle_status'), "callback_data": f"edit_supplier_status_{supplier.supplier_id}"}],
                [{"text": self._t('cancel'), "callback_data": "cancel_action"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_update_supplier_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_supplier_name command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_update_supplier_name', chat_id))
            return {'status': 'invalid_args'}
        
        supplier_id = args[0]
        new_name = ' '.join(args[1:]).strip()
        
        if len(new_name) > 50:
            self._send_message(chat_id, self._t('supplier_name_too_long', chat_id))
            return {'status': 'invalid_name'}
        
        if '<' in new_name or '>' in new_name:
            self._send_message(chat_id, self._t('supplier_name_invalid_chars', chat_id))
            return {'status': 'invalid_name'}
        
        supplier = self.db.get_supplier(supplier_id)
        if not supplier:
            self._send_message(chat_id, self._t('supplier_not_found'))
            return {'status': 'supplier_not_found'}
        
        # Check for duplicate name
        existing = self.db.get_supplier_by_name(new_name)
        if existing and existing.supplier_id != supplier_id:
            self._send_message(chat_id, self._t('supplier_name_exists', name=new_name))
            return {'status': 'duplicate_name'}
        
        if self.db.update_supplier(supplier_id, {'name': new_name}):
            self._send_message(chat_id, self._t('supplier_name_updated', chat_id, old_name=supplier.name, new_name=new_name))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_update_supplier_name', chat_id))
            return {'status': 'error'}
    
    def handle_update_supplier_contact(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_supplier_contact command"""
        if len(args) < 2:
            self._send_message(chat_id, self._t('usage_update_supplier_contact', chat_id))
            return {'status': 'invalid_args'}
        
        supplier_id = args[0]
        contact_email = args[1]
        
        # Basic email validation
        if '@' not in contact_email or '.' not in contact_email:
            self._send_message(chat_id, self._t('invalid_email', chat_id))
            return {'status': 'invalid_email'}
        
        supplier = self.db.get_supplier(supplier_id)
        if not supplier:
            self._send_message(chat_id, self._t('supplier_not_found'))
            return {'status': 'supplier_not_found'}
        
        if self.db.update_supplier(supplier_id, {'contact_email': contact_email}):
            old_contact = supplier.contact_email or self._t('not_set')
            self._send_message(chat_id, self._t('supplier_contact_updated', old_contact=old_contact, new_contact=contact_email))
            return {'status': 'success'}
        else:
            self._send_message(chat_id, self._t('failed_update_supplier_contact', chat_id))
            return {'status': 'error'}