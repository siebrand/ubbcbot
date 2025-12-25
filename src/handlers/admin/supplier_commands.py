from typing import Dict, Any
from handlers.base_handler import BaseHandler
from models.entities import Supplier

class SupplierCommands(BaseHandler):
    def handle_add_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_supplier command"""
        if not args:
            self._send_message(chat_id, "Usage: /add_supplier [name]")
            return {'status': 'invalid_args'}

        supplier_name = ' '.join(args).strip()
        
        # Validate supplier name
        if len(supplier_name) > 50:
            self._send_message(chat_id, "❌ Supplier name too long (max 50 characters)")
            return {'status': 'invalid_name'}
        
        if '<' in supplier_name or '>' in supplier_name:
            self._send_message(chat_id, "❌ Supplier name cannot contain < or > characters")
            return {'status': 'invalid_name'}
        
        # Check for duplicate
        if self.db.get_supplier_by_name(supplier_name):
            self._send_message(chat_id, f"❌ Supplier '{supplier_name}' already exists")
            return {'status': 'duplicate_supplier'}
        
        supplier = Supplier(name=supplier_name)
        
        if self.db.create_supplier(supplier):
            self._send_message(chat_id, f"✅ Supplier '{supplier_name}' added with ID: {supplier.supplier_id}")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to add supplier")
            return {'status': 'error'}

    def handle_retire_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /retire_supplier command"""
        if not args:
            self._send_message(chat_id, "Usage: /retire_supplier [name]")
            return {'status': 'invalid_args'}

        supplier_name = ' '.join(args).strip()
        
        # Find supplier by name
        supplier = self.db.get_supplier_by_name(supplier_name)
        if not supplier:
            self._send_message(chat_id, f"❌ Supplier '{supplier_name}' not found")
            return {'status': 'supplier_not_found'}
        
        if supplier.status == "retired":
            self._send_message(chat_id, f"❌ Supplier '{supplier_name}' is already retired")
            return {'status': 'already_retired'}
        
        # Update supplier status to retired
        if self.db.update_supplier(supplier.supplier_id, {'status': 'retired'}):
            self._send_message(chat_id, f"✅ Supplier '{supplier_name}' has been retired")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to retire supplier")
            return {'status': 'error'}

    def handle_list_suppliers(self, chat_id: int, page: int = 1) -> Dict[str, Any]:
        """Handle /list_suppliers command with pagination"""
        suppliers = self.db.list_suppliers()
        
        if not suppliers:
            self._send_message(chat_id, "No suppliers found")
            return {'status': 'no_suppliers'}

        # Filter active suppliers and sort alphabetically
        active_suppliers = [s for s in suppliers if s.status == "active"]
        active_suppliers.sort(key=lambda x: x.name.lower())

        # Paginate results
        page_suppliers, total_pages = self._paginate_list(active_suppliers, page, 10)
        
        message = f"📋 Registered Suppliers (Page {page}/{total_pages}):\n\n"
        for supplier in page_suppliers:
            status_emoji = "✅" if supplier.status == "active" else "❌"
            contact = supplier.contact_email or "Not set"
            message += f"{status_emoji} {supplier.name}\n"
            message += f"   Contact: {contact}\n\n"
        
        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_pagination_keyboard(page, total_pages, "suppliers")
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_edit_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /edit_supplier command"""
        if not args:
            self._send_message(chat_id, "Usage: /edit_supplier [name]")
            return {'status': 'invalid_args'}

        supplier_name = ' '.join(args).strip()
        supplier = self.db.get_supplier_by_name(supplier_name)
        
        if not supplier:
            self._send_message(chat_id, f"❌ Supplier '{supplier_name}' not found")
            return {'status': 'supplier_not_found'}
        
        # Show current supplier details with edit options
        message = f"📝 Edit Supplier: {supplier.name}\n\n"
        message += f"Current Status: {supplier.status}\n"
        message += f"Contact: {supplier.contact_email or 'Not set'}\n\n"
        message += "Select what to edit:"
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "📝 Edit Name", "callback_data": f"edit_supplier_name_{supplier.supplier_id}"}],
                [{"text": "📧 Edit Contact", "callback_data": f"edit_supplier_contact_{supplier.supplier_id}"}],
                [{"text": "🔄 Toggle Status", "callback_data": f"edit_supplier_status_{supplier.supplier_id}"}],
                [{"text": "❌ Cancel", "callback_data": "cancel_action"}]
            ]
        }
        
        self._send_message(chat_id, message, reply_markup=keyboard)
        return {'status': 'success'}
    
    def handle_update_supplier_name(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_supplier_name command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /update_supplier_name [supplier_id] [new_name]")
            return {'status': 'invalid_args'}
        
        supplier_id = args[0]
        new_name = ' '.join(args[1:]).strip()
        
        if len(new_name) > 50:
            self._send_message(chat_id, "❌ Supplier name too long (max 50 characters)")
            return {'status': 'invalid_name'}
        
        if '<' in new_name or '>' in new_name:
            self._send_message(chat_id, "❌ Supplier name cannot contain < or > characters")
            return {'status': 'invalid_name'}
        
        supplier = self.db.get_supplier(supplier_id)
        if not supplier:
            self._send_message(chat_id, "❌ Supplier not found")
            return {'status': 'supplier_not_found'}
        
        # Check for duplicate name
        existing = self.db.get_supplier_by_name(new_name)
        if existing and existing.supplier_id != supplier_id:
            self._send_message(chat_id, f"❌ Supplier name '{new_name}' already exists")
            return {'status': 'duplicate_name'}
        
        if self.db.update_supplier(supplier_id, {'name': new_name}):
            self._send_message(chat_id, f"✅ Supplier name updated: '{supplier.name}' → '{new_name}'")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to update supplier name")
            return {'status': 'error'}
    
    def handle_update_supplier_contact(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /update_supplier_contact command"""
        if len(args) < 2:
            self._send_message(chat_id, "Usage: /update_supplier_contact [supplier_id] [email]")
            return {'status': 'invalid_args'}
        
        supplier_id = args[0]
        contact_email = args[1]
        
        # Basic email validation
        if '@' not in contact_email or '.' not in contact_email:
            self._send_message(chat_id, "❌ Invalid email format")
            return {'status': 'invalid_email'}
        
        supplier = self.db.get_supplier(supplier_id)
        if not supplier:
            self._send_message(chat_id, "❌ Supplier not found")
            return {'status': 'supplier_not_found'}
        
        if self.db.update_supplier(supplier_id, {'contact_email': contact_email}):
            old_contact = supplier.contact_email or "Not set"
            self._send_message(chat_id, f"✅ Supplier contact updated: '{old_contact}' → '{contact_email}'")
            return {'status': 'success'}
        else:
            self._send_message(chat_id, "❌ Failed to update supplier contact")
            return {'status': 'error'}