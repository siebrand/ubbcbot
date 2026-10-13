from typing import Dict, Any
import logging
import json
import os
import requests
from services.database import DynamoDBService
from utils.validation import ValidationUtils
from utils.pagination import PaginationUtils
from models.entities import OfferStatus
from services.box_status_manager import BoxStatusManager

logger = logging.getLogger()

class BaseHandler:
    def __init__(self, db: DynamoDBService, admin_user_id: int, environment: str, telegram_token: str):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.telegram_token = telegram_token
        self._bot_username = None
        self._translations = {}
        self.validator = ValidationUtils(db, self._t)
        self.box_status_manager = BoxStatusManager(db)

    def _load_translations(self, lang: str) -> Dict[str, str]:
        """Load translations for given language"""
        if lang in self._translations:
            return self._translations[lang]
        
        # Default to Dutch for most users, fallback to English
        lang_file = lang if lang in ['en', 'nl'] else 'nl'
        
        try:
            file_path = os.path.join(os.path.dirname(__file__), '..', 'translations', f'{lang_file}.json')
            with open(file_path, 'r', encoding='utf-8') as f:
                self._translations[lang] = json.load(f)
                return self._translations[lang]
        except Exception as e:
            logger.error(f"Error loading translations for {lang}: {e}")
            # Fallback to English if Dutch fails
            if lang_file != 'en':
                return self._load_translations('en')
            return {}

    def _t(self, key: str, user_id: int = None, force_group_lang: bool = False, **params) -> str:
        """Translate message key to user language"""
        # Force Dutch for group messages
        if force_group_lang:
            lang = 'nl'
        else:
            # Get user language preference, default to Dutch
            lang = 'nl'
            if user_id:
                customer = self.db.get_customer_by_telegram_id(user_id)
                if customer and hasattr(customer, 'language') and customer.language:
                    lang = customer.language
        
        translations = self._load_translations(lang)
        message = translations.get(key, key)
        return message.format(**params) if params else message

    def _get_bot_username(self) -> str:
        """Get bot username from Telegram API"""
        if self._bot_username:
            return self._bot_username
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/getMe"
            response = requests.get(url, timeout=20)
            if response.status_code == 200:
                data = response.json()
                self._bot_username = data['result']['username']
                return self._bot_username
        except Exception as e:
            logger.error(f"Error getting bot username: {e}")
        
        # Fallback based on environment
        return "ubbc_test_bot" if self.environment == 'test' else "ubbc_bot"

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_user_id

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters to prevent injection"""
        if not text:
            return ""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#x27;')

    def _send_message(self, chat_id: int, text: str, parse_mode: str = None, reply_markup: dict = None, force_group: bool = False) -> dict:
        """Send message to Telegram chat and return response with message_id"""

        # Skip sending to guest users (they don't have Telegram)
        if chat_id == -1:
            logger.info(f"Skipping message to guest user")
            return {'success': False, 'skipped_guest': True}
        
        if self.environment == 'test':
            text = f"TEST - {text}"
        
        if not self.telegram_token:
            logger.error("Telegram token is empty")
            return {'success': False}
        
        # In production, redirect to PM unless explicitly for group
        if self.environment == 'prod' and chat_id < 0 and not force_group:
            # This is a group chat in production - we need user_id to send PM
            # For now, just log and don't send (caller should handle PM sending)
            logger.info(f"Production group message blocked: {text[:50]}...")
            return {'success': False}
            
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'disable_web_page_preview': True
        }
        
        if parse_mode:
            data['parse_mode'] = parse_mode
        
        if reply_markup:
            data['reply_markup'] = reply_markup
        
        try:
            if self.environment == 'test':
                logger.info(f"Sending message to chat {chat_id}: {text[:50]}...")
            
            logger.info(f"DEBUG: message: chat_id: {chat_id}, force_group: {force_group}, text: {text[:100]}...")
            
            response = requests.post(url, json=data, timeout=20)
            if self.environment == 'test':
                logger.info(f"Telegram API response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                return {'success': True, 'message_id': result['result']['message_id']}
            else:
                logger.error(f"DEBUG: message failed - status: {response.status_code}, response: {response.text}")
                return {'success': False}
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {'success': False}

    def _delete_message(self, chat_id: int, message_id: int) -> bool:
        """Delete message from Telegram chat"""
        if not self.telegram_token:
            logger.error("Telegram token is empty")
            return False
            
        url = f"https://api.telegram.org/bot{self.telegram_token}/deleteMessage"
        data = {
            'chat_id': chat_id,
            'message_id': message_id
        }
        
        try:
            response = requests.post(url, json=data, timeout=20)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            return False

    def _set_message_reaction(self, chat_id: int, message_id: int, emoji: str = "👍") -> bool:
        """Set an emoji reaction on a Telegram message (e.g. 👍). Returns success."""
        if not self.telegram_token:
            logger.error("Telegram token is empty")
            return False

        url = f"https://api.telegram.org/bot{self.telegram_token}/setMessageReaction"
        data = {
            'chat_id': chat_id,
            'message_id': message_id,
            'reaction': [{'type': 'emoji', 'emoji': emoji}]
        }

        try:
            response = requests.post(url, json=data, timeout=20)
            if response.status_code != 200:
                logger.error(f"Failed to set reaction: status {response.status_code}, response {response.text}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error setting message reaction: {e}")
            return False

    def _send_message_simple(self, chat_id: int, text: str, parse_mode: str = None, reply_markup: dict = None, force_group: bool = False) -> bool:
        """Send message and return simple boolean for backward compatibility"""
        result = self._send_message(chat_id, text, parse_mode, reply_markup, force_group)
        return result.get('success', False)

    def _send_document(self, chat_id: int, content: str, filename: str, caption: str = None) -> bool:
        """Send document to Telegram chat"""
        from io import BytesIO
        
        if self.environment == 'test' and caption:
            caption = f"TEST - {caption}"
        
        if not self.telegram_token:
            logger.error("Telegram token is empty")
            return False
            
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendDocument"
        
        # Convert string content to bytes
        file_data = BytesIO(content.encode('utf-8'))
        
        files = {
            'document': (filename, file_data, 'text/csv')
        }
        
        data = {
            'chat_id': chat_id
        }
        
        if caption:
            data['caption'] = caption
        
        try:
            if self.environment == 'test':
                logger.info(f"Sending document to chat {chat_id}: {filename}")
            response = requests.post(url, data=data, files=files, timeout=20)
            if self.environment == 'test':
                logger.info(f"Telegram API response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending document: {e}")
            return False
    
    def _build_pagination_keyboard(self, current_page: int, total_pages: int, entity_type: str, filters: str = "", enhanced: bool = False) -> Dict[str, Any]:
        """Build pagination keyboard for list commands"""
        return PaginationUtils.build_pagination_keyboard(current_page, total_pages, entity_type, filters, enhanced)
    
    def _build_admin_menu_keyboard(self) -> Dict[str, Any]:
        """Build keyboard with button to return to admin menu"""
        return {
            "inline_keyboard": [[
                {"text": self._t('admin_menu', user_id=None), "callback_data": "admin:main"}
            ]]
        }
    
    def _paginate_list(self, items: list, page: int, page_size: int = 10) -> tuple:
        """Paginate a list of items"""
        return PaginationUtils.paginate_list(items, page, page_size)
    
    def _validate_and_get_offer(self, args: list, chat_id: int):
        """Validate offer ID and return offer or send error"""
        offer, error = self.validator.validate_and_get_offer(args)
        if error:
            if 'message' in error:
                self._send_message(chat_id, error['message'])
        return offer, error
    
    def _validate_and_get_customer(self, args: list, chat_id: int):
        """Validate customer ID and return customer or send error"""
        customer, error = self.validator.validate_and_get_customer(args)
        if error:
            if 'message' in error:
                self._send_message(chat_id, error['message'])
        return customer, error
    
    def _parse_int_arg(self, arg: str, error_key: str, chat_id: int):
        """Parse integer argument or send error"""
        try:
            return int(arg), None
        except ValueError:
            self._send_message(chat_id, self._t(error_key))
            return None, {'status': 'invalid_format'}
    
    def _validate_args(self, args: list, min_count: int, usage_key: str, chat_id: int):
        """Validate minimum argument count or send usage message"""
        if len(args) < min_count:
            self._send_message(chat_id, self._t(usage_key))
            return {'status': 'invalid_args'}
        return None
    
    def _send_error(self, chat_id: int, error_key: str, status: str, **kwargs):
        """Send error message and return status"""
        user_id = kwargs.pop('user_id', None)
        self._send_message(chat_id, self._t(error_key, user_id, **kwargs))
        return {'status': status}
    
    def _send_success(self, chat_id: int, success_key: str, status: str = 'success', **kwargs):
        """Send success message and return status"""
        user_id = kwargs.pop('user_id', None)
        self._send_message(chat_id, self._t(success_key, user_id, **kwargs))
        return {'status': status}
    
    def _send_photo(self, chat_id: int, photo_url: str, caption: str = None, force_group: bool = False) -> dict:
        """Send photo to Telegram chat"""
        # Skip sending to guest users (they don't have Telegram)
        if chat_id == -1:
            logger.info(f"Skipping photo to guest user")
            return {'success': False, 'skipped_guest': True}
        
        if self.environment == 'test' and caption:
            caption = f"TEST - {caption}"
        
        if not self.telegram_token:
            logger.error("Telegram token is empty")
            return {'success': False}
        
        # In production, redirect to PM unless explicitly for group
        if self.environment == 'prod' and chat_id < 0 and not force_group:
            logger.info(f"Production group photo blocked")
            return {'success': False}
            
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendPhoto"
        data = {
            'chat_id': chat_id,
            'photo': photo_url
        }
        
        if caption:
            data['caption'] = caption
        
        try:
            if self.environment == 'test':
                logger.info(f"Sending photo to chat {chat_id}: {photo_url[:150]}")
            response = requests.post(url, json=data, timeout=20)
            if self.environment == 'test':
                logger.info(f"Telegram API response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                return {'success': True, 'message_id': result['result']['message_id']}
            return {'success': False}
        except Exception as e:
            logger.error(f"Error sending photo: {e}")
            return {'success': False}
    
    def _send_media_group(self, chat_id: int, media_group: list, force_group: bool = False) -> dict:
        """Send media group to Telegram chat"""
        # Skip sending to guest users (they don't have Telegram)
        if chat_id == -1:
            logger.info(f"Skipping media group to guest user")
            return {'success': False, 'skipped_guest': True}
        
        if not self.telegram_token:
            logger.error("Telegram token is empty")
            return {'success': False}
        
        # In production, redirect to PM unless explicitly for group
        if self.environment == 'prod' and chat_id < 0 and not force_group:
            logger.info(f"Production group media group blocked")
            return {'success': False}
            
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMediaGroup"
        data = {
            'chat_id': chat_id,
            'media': media_group
        }
        
        try:
            if self.environment == 'test':
                logger.info(f"Sending media group to chat {chat_id}: {len(media_group)} items")
            response = requests.post(url, json=data, timeout=20)
            if self.environment == 'test':
                logger.info(f"Telegram API response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                return {'success': True, 'message_ids': [msg['message_id'] for msg in result['result']]}
            return {'success': False}
        except Exception as e:
            logger.error(f"Error sending media group: {e}")
            return {'success': False}
    
    def _find_customer_with_disambiguation(self, identifier: str, chat_id: int, callback_prefix: str, status_filter: str = None):
        """Find customer with disambiguation UI if multiple matches"""
        customer, error = self.validator.find_customer_with_disambiguation(identifier, chat_id, callback_prefix, status_filter)
        
        if error:
            if error['status'] == 'user_not_found':
                keyboard = error.get('keyboard')
                self._send_message(chat_id, error['message'], reply_markup=keyboard)
                return None, error
            elif error['status'] == 'disambiguation_shown':
                self._send_message(chat_id, error['message'], reply_markup=error['keyboard'])
                return None, error
        
        return customer, None
    
    def _check_offer_status_after_change(self, offer_id: int):
        """Check if offer should be SOLD_OUT or ACTIVE based on box states"""
        new_status = self.box_status_manager.update_offer_status_after_change(offer_id)
        if new_status == OfferStatus.SOLD_OUT.value:
            self._delete_offer_notifications(offer_id)
    
    def _delete_offer_notifications(self, offer_id: int):
        """Delete notification messages for sold out offer"""
        try:
            notifications = self.db.get_notification_messages_by_offer(offer_id)
            
            for notification in notifications:
                try:
                    if self._delete_message(notification.chat_id, notification.message_id):
                        self.db.delete_notification_message(notification.notification_id)
                        logger.info(f"Deleted notification message {notification.message_id} for offer {offer_id}")
                except Exception as e:
                    logger.error(f"Failed to delete message {notification.message_id}: {e}")
        except Exception as e:
            logger.error(f"Error deleting offer notifications: {e}")
