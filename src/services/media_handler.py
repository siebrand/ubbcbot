import logging
import uuid
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger()

class MediaHandler:
    def __init__(self, db, admin_user_id: int, environment: str, telegram_token: str):
        self.db = db
        self.admin_user_id = admin_user_id
        self.environment = environment
        self.telegram_token = telegram_token

    def handle_media_group_image(self, chat_id: int, offer_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle image from media group (multiple images)"""
        # For now, process each image immediately
        return self.handle_offer_image_upload(chat_id, offer_id, message['photo'])
    
    def handle_offer_image_upload(self, chat_id: int, offer_id: str, photos: list) -> Dict[str, Any]:
        """Handle image upload for offer"""
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        try:
            offer_id_int = int(offer_id)
            offer = self.db.get_offer(offer_id_int)
            
            if not offer:
                base_handler._send_message(chat_id, base_handler._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            # Get the largest photo size
            largest_photo = max(photos, key=lambda p: p['file_size'])
            file_id = largest_photo['file_id']
            
            # Download image from Telegram
            image_data = self._download_telegram_file(file_id)
            if not image_data:
                base_handler._send_message(chat_id, base_handler._t('download_failed'))
                return {'status': 'download_failed'}
            
            # Upload to S3
            file_name = f"{uuid.uuid4()}.jpg"
            image_url = self.db.upload_image_to_s3(image_data, file_name, offer_id_int)
            
            if not image_url:
                base_handler._send_message(chat_id, base_handler._t('upload_failed'))
                return {'status': 'upload_failed'}
            
            # Update offer with new image
            current_images = offer.images or []
            current_images.append(image_url)
            
            if self.db.update_offer(offer_id_int, {'images': current_images}):
                # Send confirmation with button to continue editing
                message = base_handler._t('image_uploaded', count=len(current_images))
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": base_handler._t('continue_editing'), "callback_data": f"offer_details_{offer_id_int}_edit"}],
                        [{"text": base_handler._t('view_details'), "callback_data": f"offer_details_{offer_id_int}"}],
                        [{"text": base_handler._t('done_editing'), "callback_data": "done_editing"}]
                    ]
                }
                
                base_handler._send_message(chat_id, message, reply_markup=keyboard)
                return {'status': 'success'}
            else:
                base_handler._send_message(chat_id, base_handler._t('update_failed'))
                return {'status': 'update_failed'}
                
        except ValueError:
            base_handler._send_message(chat_id, base_handler._t('invalid_offer_id'))
            return {'status': 'invalid_offer_id'}
        except Exception as e:
            logger.error(f"Error uploading image: {e}")
            base_handler._send_message(chat_id, base_handler._t('image_upload_failed'))
            return {'status': 'error'}
    
    def handle_clear_offer_images(self, chat_id: int, offer_id: str) -> Dict[str, Any]:
        """Handle clearing all images for an offer"""
        from handlers.base_handler import BaseHandler
        base_handler = BaseHandler(self.db, self.admin_user_id, self.environment, self.telegram_token)
        
        try:
            offer_id_int = int(offer_id)
            offer = self.db.get_offer(offer_id_int)
            
            if not offer:
                base_handler._send_message(chat_id, base_handler._t('offer_not_found'))
                return {'status': 'offer_not_found'}
            
            if not offer.images:
                base_handler._send_message(chat_id, base_handler._t('no_images_to_clear'))
                return {'status': 'no_images'}
            
            # Delete images from S3
            self.db.delete_offer_images(offer_id_int)
            
            # Update offer to remove images
            if self.db.update_offer(offer_id_int, {'images': []}):
                base_handler._send_message(chat_id, base_handler._t('images_cleared', count=len(offer.images), offer_id=offer_id))
                return {'status': 'success'}
            else:
                base_handler._send_message(chat_id, base_handler._t('update_failed'))
                return {'status': 'update_failed'}
                
        except ValueError:
            base_handler._send_message(chat_id, base_handler._t('invalid_offer_id'))
            return {'status': 'invalid_offer_id'}
        except Exception as e:
            logger.error(f"Error clearing images: {e}")
            base_handler._send_message(chat_id, base_handler._t('failed_clear_images'))
            return {'status': 'error'}
    
    def convert_entities_to_html(self, text: str, entities: list) -> str:
        """Convert Telegram message entities to HTML format"""
        if not entities:
            return text
        
        # Sort entities by offset in reverse order to avoid offset shifts
        sorted_entities = sorted(entities, key=lambda x: x['offset'], reverse=True)
        
        result = text
        for entity in sorted_entities:
            start = entity['offset']
            length = entity['length']
            end = start + length
            entity_text = text[start:end]
            
            if entity['type'] == 'bold':
                result = result[:start] + f"<b>{entity_text}</b>" + result[end:]
            elif entity['type'] == 'italic':
                result = result[:start] + f"<i>{entity_text}</i>" + result[end:]
            elif entity['type'] == 'spoiler':
                result = result[:start] + f"<tg-spoiler>{entity_text}</tg-spoiler>" + result[end:]
        
        return result
    
    def _download_telegram_file(self, file_id: str) -> Optional[bytes]:
        """Download file from Telegram"""
        try:
            # Get file path
            url = f"https://api.telegram.org/bot{self.telegram_token}/getFile"
            response = requests.get(url, params={'file_id': file_id}, timeout=20)
            
            if response.status_code != 200:
                return None
            
            file_path = response.json()['result']['file_path']
            
            # Download file
            download_url = f"https://api.telegram.org/file/bot{self.telegram_token}/{file_path}"
            file_response = requests.get(download_url, timeout=20)
            
            if file_response.status_code == 200:
                return file_response.content
            
            return None
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None