from typing import Dict, Any
import logging
from services.database import DynamoDBService

logger = logging.getLogger()

class BaseHandler:
    def __init__(self, db: DynamoDBService, admin_user_id: int, environment: str, telegram_token: str):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.telegram_token = telegram_token
        self._bot_username = None

    def _get_bot_username(self) -> str:
        """Get bot username from Telegram API"""
        if self._bot_username:
            return self._bot_username
            
        import requests
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/getMe"
            response = requests.get(url)
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
        import requests
        
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
            response = requests.post(url, json=data)
            if self.environment == 'test':
                logger.info(f"Telegram API response: {response.status_code} - {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                return {'success': True, 'message_id': result['result']['message_id']}
            return {'success': False}
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {'success': False}

    def _delete_message(self, chat_id: int, message_id: int) -> bool:
        """Delete message from Telegram chat"""
        import requests
        
        if not self.telegram_token:
            logger.error("Telegram token is empty")
            return False
            
        url = f"https://api.telegram.org/bot{self.telegram_token}/deleteMessage"
        data = {
            'chat_id': chat_id,
            'message_id': message_id
        }
        
        try:
            response = requests.post(url, json=data)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            return False

    def _send_message_simple(self, chat_id: int, text: str, parse_mode: str = None, reply_markup: dict = None, force_group: bool = False) -> bool:
        """Send message and return simple boolean for backward compatibility"""
        result = self._send_message(chat_id, text, parse_mode, reply_markup, force_group)
        return result.get('success', False)

    def _send_document(self, chat_id: int, content: str, filename: str, caption: str = None) -> bool:
        """Send document to Telegram chat"""
        import requests
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
            response = requests.post(url, data=data, files=files)
            if self.environment == 'test':
                logger.info(f"Telegram API response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending document: {e}")
            return False
    
    def _build_pagination_keyboard(self, current_page: int, total_pages: int, entity_type: str, filters: str = "") -> Dict[str, Any]:
        """Build pagination keyboard for list commands"""
        keyboard = []
        
        if total_pages > 1:
            nav_buttons = []
            
            # Previous page button
            if current_page > 1:
                nav_buttons.append({
                    "text": "◀️ Previous", 
                    "callback_data": f"page_{entity_type}_{current_page - 1}_{filters}"
                })
            
            # Page indicator
            nav_buttons.append({
                "text": f"Page {current_page}/{total_pages}",
                "callback_data": "page_info"
            })
            
            # Next page button
            if current_page < total_pages:
                nav_buttons.append({
                    "text": "Next ▶️", 
                    "callback_data": f"page_{entity_type}_{current_page + 1}_{filters}"
                })
            
            keyboard.append(nav_buttons)
        
        return {"inline_keyboard": keyboard}
    
    def _paginate_list(self, items: list, page: int, page_size: int = 10) -> tuple:
        """Paginate a list of items"""
        total_pages = (len(items) + page_size - 1) // page_size if items else 1
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = items[start_idx:end_idx]
        
        return page_items, total_pages
    
    def _send_photo(self, chat_id: int, photo_url: str, caption: str = None, force_group: bool = False) -> dict:
        """Send photo to Telegram chat"""
        import requests
        
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
                logger.info(f"Sending photo to chat {chat_id}: {photo_url}")
            response = requests.post(url, json=data)
            if self.environment == 'test':
                logger.info(f"Telegram API response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                return {'success': True, 'message_id': result['result']['message_id']}
            return {'success': False}
        except Exception as e:
            logger.error(f"Error sending photo: {e}")
            return {'success': False}