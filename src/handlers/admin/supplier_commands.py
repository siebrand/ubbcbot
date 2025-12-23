from typing import Dict, Any
from handlers.base_handler import BaseHandler
from models.entities import Supplier

class SupplierCommands(BaseHandler):
    def handle_add_supplier(self, chat_id: int, args: list) -> Dict[str, Any]:
        """Handle /add_supplier command"""
        if not args:
            self._send_message(chat_id, "Usage: /add_supplier <name>")
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
            self._send_message(chat_id, "Usage: /retire_supplier <name>")
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

    def handle_list_suppliers(self, chat_id: int) -> Dict[str, Any]:
        """Handle /list_suppliers command"""
        suppliers = self.db.list_suppliers()
        
        if not suppliers:
            self._send_message(chat_id, "No suppliers found")
            return {'status': 'no_suppliers'}

        # Filter active suppliers and sort alphabetically
        active_suppliers = [s for s in suppliers if s.status == "active"]
        active_suppliers.sort(key=lambda x: x.name.lower())

        message = "📋 Registered Suppliers:\n\n"
        for supplier in active_suppliers:
            message += f"{supplier.name}\n"

        self._send_message(chat_id, message)
        return {'status': 'success'}