import logging
from typing import Dict, Any, Optional
from models.entities import EditContext

logger = logging.getLogger()

class EditContextManager:
    def __init__(self, db, t_func, send_message_func):
        self.db = db
        self._t = t_func
        self._send_message = send_message_func
    
    def store_edit_context(self, chat_id: int, edit_type: str, entity_id: str):
        """Store edit context in DynamoDB for processing replies"""
        logger.info(f"Storing edit context: chat_id={chat_id}, type={edit_type}, entity_id={entity_id}")
        
        # Delete any existing context for this chat
        existing = self.db.get_edit_context_by_chat_id(chat_id)
        if existing:
            self.db.delete_edit_context(existing.context_id)
        
        # Cleanup old contexts periodically
        import random
        if random.randint(1, 20) == 1:
            cleaned = self.db.cleanup_old_edit_contexts()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} old edit contexts")
        
        # Create new context
        context = EditContext(
            chat_id=chat_id,
            edit_type=edit_type,
            entity_id=entity_id
        )
        self.db.create_edit_context(context)
    
    def prompt_for_text_input(self, chat_id: int, prompt_key: str, placeholder: str, **kwargs):
        """Send text input prompt with force reply"""
        self._send_message(
            chat_id, 
            self._t(prompt_key, **kwargs),
            reply_markup={"force_reply": True, "input_field_placeholder": placeholder}
        )
    
    def handle_supplier_edit(self, chat_id: int, field: str, supplier_id: str) -> Dict[str, Any]:
        """Handle supplier edit callbacks with unified pattern"""
        supplier = self.db.get_supplier(supplier_id)
        if not supplier:
            self._send_message(chat_id, self._t('supplier_not_found', name=supplier_id))
            return {'status': 'supplier_not_found'}
        
        if field == 'status':
            # Toggle status immediately
            new_status = 'retired' if supplier.status == 'active' else 'active'
            if self.db.update_supplier(supplier_id, {'status': new_status}):
                self._send_message(chat_id, self._t('supplier_status_updated', 
                                                 name=supplier.name, status=new_status))
                return {'status': 'success'}
            else:
                self._send_message(chat_id, self._t('failed_update_supplier_status'))
                return {'status': 'error'}
        
        # Handle text input fields
        field_config = {
            'name': {
                'context_type': 'supplier_name',
                'prompt_key': 'enter_new_supplier_name',
                'placeholder': self._t('placeholder_supplier_name'),
                'prompt_args': {'name': supplier.name}
            },
            'contact': {
                'context_type': 'supplier_contact',
                'prompt_key': 'enter_supplier_contact',
                'placeholder': self._t('placeholder_supplier_contact'),
                'prompt_args': {'name': supplier.name}
            },
            'full_name': {
                'context_type': 'supplier_full_name',
                'prompt_key': 'enter_supplier_full_name',
                'placeholder': self._t('placeholder_supplier_full_name'),
                'prompt_args': {'name': supplier.name}
            }
        }
        
        if field in field_config:
            config = field_config[field]
            self.store_edit_context(chat_id, config['context_type'], supplier_id)
            self.prompt_for_text_input(chat_id, config['prompt_key'], config['placeholder'], **config['prompt_args'])
            return {'status': 'text_input_required'}
        
        self._send_message(chat_id, self._t('unknown_edit_field'))
        return {'status': 'unknown_field'}
    
    def handle_offer_edit(self, chat_id: int, field: str, offer_id: str) -> Dict[str, Any]:
        """Handle offer edit callbacks with unified pattern"""
        field_config = {
            'name': {
                'context_type': 'offer_name',
                'prompt_key': 'enter_new_offer_name',
                'placeholder': self._t('placeholder_offer_name'),
                'prompt_args': {'offer_id': offer_id}
            },
            'price': {
                'context_type': 'offer_price',
                'prompt_key': 'enter_new_offer_price',
                'placeholder': self._t('placeholder_offer_price'),
                'prompt_args': {'offer_id': offer_id}
            },
            'description': {
                'context_type': 'offer_description',
                'prompt_key': 'enter_new_offer_description',
                'placeholder': self._t('placeholder_offer_description'),
                'prompt_args': {'offer_id': offer_id}
            }
        }
        
        if field in field_config:
            config = field_config[field]
            self.store_edit_context(chat_id, config['context_type'], offer_id)
            self.prompt_for_text_input(chat_id, config['prompt_key'], config['placeholder'], **config['prompt_args'])
            return {'status': 'text_input_required'}
        
        self._send_message(chat_id, self._t('unknown_edit_field'))
        return {'status': 'unknown_field'}
    
    def handle_customer_edit(self, chat_id: int, field: str, customer_id: str) -> Dict[str, Any]:
        """Handle customer edit callbacks with unified pattern"""
        field_config = {
            'first_name': {
                'context_type': 'customer_first_name',
                'prompt_key': 'enter_new_first_name',
                'placeholder': self._t('placeholder_first_name')
            },
            'last_name': {
                'context_type': 'customer_last_name',
                'prompt_key': 'enter_new_last_name',
                'placeholder': self._t('placeholder_last_name')
            },
            'contact': {
                'context_type': 'customer_contact',
                'prompt_key': 'enter_new_contact',
                'placeholder': self._t('placeholder_contact')
            },
            'location': {
                'context_type': 'customer_location',
                'prompt_key': 'enter_new_location',
                'placeholder': self._t('placeholder_location')
            }
        }
        
        if field in field_config:
            config = field_config[field]
            self.store_edit_context(chat_id, config['context_type'], customer_id)
            self.prompt_for_text_input(chat_id, config['prompt_key'], config['placeholder'])
            return {'status': 'text_input_required'}
        
        self._send_message(chat_id, self._t('unknown_edit_field'))
        return {'status': 'unknown_field'}
    
    def handle_input_prompts(self, chat_id: int, prompt_type: str, entity_id: str = 'new') -> Dict[str, Any]:
        """Handle various input prompts with unified pattern"""
        prompt_config = {
            'create_supplier_name': {
                'context_type': 'create_supplier_name',
                'prompt_key': 'enter_supplier_name',
                'placeholder': self._t('placeholder_supplier_name')
            },
            'user_orders_input': {
                'context_type': 'user_orders_input',
                'prompt_key': 'enter_username_for_orders',
                'placeholder': self._t('placeholder_username')
            },
            'cancel_order_input': {
                'context_type': 'cancel_order_input',
                'prompt_key': 'enter_username_for_cancel',
                'placeholder': self._t('placeholder_username')
            },
            'order_for_input': {
                'context_type': 'order_for_input',
                'prompt_key': 'enter_username_for_order_for',
                'placeholder': self._t('placeholder_username')
            },
            'edit_supplier_input': {
                'context_type': 'edit_supplier_input',
                'prompt_key': 'enter_supplier_name_to_edit',
                'placeholder': self._t('placeholder_supplier_name')
            },
            'approve_user_input': {
                'context_type': 'approve_user_input',
                'prompt_key': 'enter_username_to_approve',
                'placeholder': self._t('placeholder_username')
            },
            'user_status_input': {
                'context_type': 'user_status_input',
                'prompt_key': 'enter_username_for_status',
                'placeholder': self._t('placeholder_username')
            }
        }
        
        if prompt_type in prompt_config:
            config = prompt_config[prompt_type]
            self.store_edit_context(chat_id, config['context_type'], entity_id)
            self.prompt_for_text_input(chat_id, config['prompt_key'], config['placeholder'])
            return {'status': 'text_input_required'}
        
        return {'status': 'unknown_prompt_type'}