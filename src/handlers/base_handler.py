from typing import Dict, Any
import logging
import json
import os
from services.database import DynamoDBService
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from io import BytesIO
from utils.validation import ValidationUtils
from utils.pagination import PaginationUtils

logger = logging.getLogger()

class BaseHandler:
    def __init__(self, db: DynamoDBService, admin_user_id: int, environment: str, telegram_token: str):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.telegram_token = telegram_token
        self._bot_username = None
        self._translations = {}
        self.bot = Bot(token=telegram_token) if telegram_token else None
        self.validator = ValidationUtils(db, self._t)

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
        
        if not self.bot:
            return "ubbc_test_bot" if self.environment == 'test' else "ubbc_bot"
        
        try:
            bot_info = self.bot.get_me()
            self._bot_username = bot_info.username
            return self._bot_username
        except TelegramError as e:
            logger.error(f"Error getting bot username: {e}")
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
        if not self.bot:
            logger.error("Bot not initialized")
            return {'success': False}
        
        if self.environment == 'test':
            text = f"TEST - {text}"
        
        # In production, redirect to PM unless explicitly for group
        if self.environment == 'prod' and chat_id < 0 and not force_group:
            logger.info(f"Production group message blocked")
            return {'success': False}
        
        try:
            # Debug logging for box size 1 related messages
            if "box size 1" in text.lower() or ("ordered" in text.lower() and "🍺" in text):
                logger.info(f"DEBUG: Box size 1 message - chat_id: {chat_id}, force_group: {force_group}")
            
            message = self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            return {'success': True, 'message_id': message.message_id}
            
        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            if "box size 1" in text.lower():
                logger.error(f"DEBUG: Box size 1 message failed: {e}")
            return {'success': False}

    def _delete_message(self, chat_id: int, message_id: int) -> bool:
        """Delete message from Telegram chat"""
        if not self.bot:
            return False
        try:
            self.bot.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except TelegramError as e:
            logger.error(f"Error deleting message: {e}")
            return False

    def _send_message_simple(self, chat_id: int, text: str, parse_mode: str = None, reply_markup: dict = None, force_group: bool = False) -> bool:
        """Send message and return simple boolean for backward compatibility"""
        result = self._send_message(chat_id, text, parse_mode, reply_markup, force_group)
        return result.get('success', False)

    def _send_document(self, chat_id: int, content: str, filename: str, caption: str = None) -> bool:
        """Send document to Telegram chat"""
        if not self.bot:
            return False
        
        if self.environment == 'test' and caption:
            caption = f"TEST - {caption}"
        
        try:
            file_data = BytesIO(content.encode('utf-8'))
            self.bot.send_document(
                chat_id=chat_id,
                document=file_data,
                filename=filename,
                caption=caption
            )
            return True
        except TelegramError as e:
            logger.error(f"Error sending document: {e}")
            return False
    
    def _build_pagination_keyboard(self, current_page: int, total_pages: int, entity_type: str, filters: str = "") -> Dict[str, Any]:
        """Build pagination keyboard for list commands"""
        return PaginationUtils.build_pagination_keyboard(current_page, total_pages, entity_type, filters)
    
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
        self._send_message(chat_id, self._t(error_key, **kwargs))
        return {'status': status}
    
    def _send_success(self, chat_id: int, success_key: str, status: str = 'success', **kwargs):
        """Send success message and return status"""
        self._send_message(chat_id, self._t(success_key, **kwargs))
        return {'status': status}
    
    def _send_photo(self, chat_id: int, photo_url: str, caption: str = None, force_group: bool = False) -> dict:
        """Send photo to Telegram chat"""
        if not self.bot:
            return {'success': False}
        
        if self.environment == 'test' and caption:
            caption = f"TEST - {caption}"
        
        if self.environment == 'prod' and chat_id < 0 and not force_group:
            return {'success': False}
        
        try:
            message = self.bot.send_photo(
                chat_id=chat_id,
                photo=photo_url,
                caption=caption
            )
            return {'success': True, 'message_id': message.message_id}
        except TelegramError as e:
            logger.error(f"Error sending photo: {e}")
            return {'success': False}
    
    def _send_media_group(self, chat_id: int, media_group: list, force_group: bool = False) -> dict:
        """Send media group to Telegram chat"""
        if not self.bot:
            return {'success': False}
        
        if self.environment == 'prod' and chat_id < 0 and not force_group:
            return {'success': False}
        
        try:
            messages = self.bot.send_media_group(chat_id=chat_id, media=media_group)
            return {'success': True, 'message_ids': [msg.message_id for msg in messages]}
        except TelegramError as e:
            logger.error(f"Error sending media group: {e}")
            return {'success': False}
    
    def _find_customer_with_disambiguation(self, identifier: str, chat_id: int, callback_prefix: str):
        """Find customer with disambiguation UI if multiple matches"""
        customer, error = self.validator.find_customer_with_disambiguation(identifier, chat_id, callback_prefix)
        
        if error:
            if error['status'] == 'user_not_found':
                self._send_message(chat_id, error['message'])
                return None, error
            elif error['status'] == 'disambiguation_shown':
                self._send_message(chat_id, error['message'], reply_markup=error['keyboard'])
                return None, error
        
        return customer, None
