from typing import Dict, Any, Callable, Optional

class UpdateUtils:
    def __init__(self, db, t_func, send_message_func):
        self.db = db
        self._t = t_func
        self._send_message = send_message_func
    
    def update_entity_field(self, entity_type: str, entity_id: str, field: str, new_value: str, 
                           validation_func: Optional[Callable] = None, 
                           success_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Generic entity field update with validation and callbacks"""
        
        # Get entity
        if entity_type == 'supplier':
            entity = self.db.get_supplier(entity_id)
            update_func = self.db.update_supplier
        elif entity_type == 'customer':
            entity = self.db.get_customer(entity_id)
            update_func = self.db.update_customer
        elif entity_type == 'offer':
            entity = self.db.get_offer(entity_id)
            update_func = self.db.update_offer
        else:
            return {'status': 'invalid_entity_type'}
        
        if not entity:
            return {'status': 'entity_not_found'}
        
        # Validate new value if validator provided
        if validation_func:
            validation_result = validation_func(new_value, entity)
            if not validation_result['valid']:
                return {'status': 'validation_failed', 'message': validation_result['message']}
        
        # Get old value for response
        old_value = getattr(entity, field, None) or self._t('not_set')
        
        # Update entity
        if update_func(entity_id, {field: new_value}):
            # Success callback if provided
            if success_callback:
                success_callback(entity, old_value, new_value)
            
            return {'status': 'success', 'old_value': old_value, 'new_value': new_value}
        else:
            return {'status': 'update_failed'}
    
    def create_field_validators(self):
        """Create common field validators"""
        def validate_name(value: str, entity) -> Dict[str, Any]:
            if len(value) > 100:
                return {'valid': False, 'message': self._t('name_too_long')}
            if '<' in value or '>' in value:
                return {'valid': False, 'message': self._t('invalid_chars')}
            return {'valid': True}
        
        def validate_email(value: str, entity) -> Dict[str, Any]:
            if '@' not in value or '.' not in value:
                return {'valid': False, 'message': self._t('invalid_email')}
            return {'valid': True}
        
        def validate_price(value: str, entity) -> Dict[str, Any]:
            try:
                price = float(value)
                if price <= 0:
                    return {'valid': False, 'message': self._t('price_must_positive')}
                return {'valid': True}
            except ValueError:
                return {'valid': False, 'message': self._t('invalid_price_format')}
        
        return {
            'name': validate_name,
            'email': validate_email,
            'price': validate_price
        }
    
    def handle_supplier_update(self, chat_id: int, args: list, field: str) -> Dict[str, Any]:
        """Handle supplier field updates with unified pattern"""
        if len(args) < 2:
            usage_key = f'usage_update_supplier_{field}'
            self._send_message(chat_id, self._t(usage_key))
            return {'status': 'invalid_args'}
        
        supplier_id = args[0]
        new_value = ' '.join(args[1:]).strip()
        
        validators = self.create_field_validators()
        validator = validators.get(field if field != 'contact_email' else 'email')
        
        def success_callback(entity, old_value, new_value):
            success_key = f'supplier_{field}_updated'
            self._send_message(chat_id, self._t(success_key, old_value=old_value, new_value=new_value))
            # Show edit interface
            updated_supplier = self.db.get_supplier(supplier_id)
            if updated_supplier:
                self._show_supplier_edit_interface(chat_id, updated_supplier)
        
        result = self.update_entity_field('supplier', supplier_id, field, new_value, validator, success_callback)
        
        if result['status'] != 'success':
            error_key = f'failed_update_supplier_{field}'
            self._send_message(chat_id, self._t(error_key))
        
        return result
    
    def handle_customer_update(self, chat_id: int, args: list, field: str) -> Dict[str, Any]:
        """Handle customer field updates with unified pattern"""
        if len(args) < 2:
            usage_key = f'usage_update_user_{field}'
            self._send_message(chat_id, self._t(usage_key))
            return {'status': 'invalid_args'}
        
        customer_id = args[0]
        new_value = ' '.join(args[1:]).strip()
        
        validators = self.create_field_validators()
        validator = validators.get('name')  # Both first_name and last_name use name validator
        
        def success_callback(entity, old_value, new_value):
            success_key = f'{field}_updated'
            self._send_message(chat_id, self._t(success_key, old_name=old_value, new_name=new_value))
            # Return to edit interface
            updated_customer = self.db.get_customer(customer_id)
            if updated_customer:
                self._show_customer_edit_interface(chat_id, updated_customer)
        
        result = self.update_entity_field('customer', customer_id, field, new_value, validator, success_callback)
        
        if result['status'] != 'success':
            error_key = f'failed_update_{field}'
            self._send_message(chat_id, self._t(error_key))
        
        return result
    
    def _show_supplier_edit_interface(self, chat_id: int, supplier):
        """Show supplier edit interface - to be implemented by handler"""
        pass
    
    def _show_customer_edit_interface(self, chat_id: int, customer):
        """Show customer edit interface - to be implemented by handler"""
        pass